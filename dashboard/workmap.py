"""The Work map's data (#1081, FEAT-8 under M9 #1080): what each issue cost and what it returned.

`swarm map` prints it, and the Desk build (generate.py) writes it to `map.json` beside the
pages for the Work map page to read (FEAT-9). Per-issue cost may be published on both Desks
(GOV-0049); it is never summed across issues (GOV-0033): there is no total line, no total
field and no sum across rows, here or in state.json.

**Attribution.** A heartbeat event's `token_counts` are cumulative per session (heartbeat/
SCHEMA.md), so the tokens between two consecutive events of a session are what it spent in
between. They are charged to the issue of the session's latest `working_on` event before the
later of the two, so a `working_on` splits a session's tokens at the switch: tokens up to it go
to the issue it left. Tokens before any `working_on` go to one `unattributed` row, never dropped.
A count that falls (a restart) charges nothing for that kind, as spend.daily() does.

**Cost.** Each delta is priced with spend.py's PRICES for the event's model: the API list-price
equivalent, not what was billed (spend.METHOD). An unknown model gives tokens and no cost; the
row's `unpriced_tokens` says how many, and its `cost` is null if none of its tokens were priced.

**Buckets.** Spend and outcomes are kept per issue per UTC hour, so any window is a sum of
hours. A window of length L ends with the current hour and covers the L hours before it. The
`baseline` is the row's mean cost over the four windows before it, of the same length, or null
if the heartbeat data read doesn't reach back that far. `days` is 14 (date, cost, outcomes)
triples, one per UTC day, ending today.

**Outcomes**, each counted once, in the hour it happened:
  merged    a PR that closes the issue merged;
  approved  the reviewer App's first approval at the head of such a PR (the head it has now);
  closed    the issue closed (any issue but a session's tracking issue, Goals and
            gov:questions included, as the spec's "every issue closed in the window").
They count equally in v1 (the owner's choice, 2026-11-17).

**Per issue:** `goal` (the owner's open Goal or Area above it, from the plan), `effort` (the
classify/cache/effort.json label of its most recently merged PR, else of its most recent
classified PR, else `unclassified`), `role` (the role with the most cost on it in the window,
then the most tokens), `stage`, `needs_you`, and `lines` (additions plus deletions of its PRs'
commits committed in the window). `stage`, first that holds:
  blocked   an open blocked-by (read from the plan's go data, whatever its go kind), or a
            session on it is blocked on a gov question;
  merging   an open PR that closes it has the reviewer App's approval at head;
  review    an open PR that closes it is ready for review;
  building  a draft PR closes it, or a live session is on it;
  queued    it is go (the plan's go);
  null      none of these, or the issue is closed.

**Rows:** every open issue under the owner's open Goals and Areas (two levels down, as the plan
reads them), every issue closed in the window, every issue with spend or an outcome in the
window, and the unattributed row.

**API calls.** Reuses generate.fetch()'s issues, heartbeat comments and open PRs with their
reviews, plan.fetch()'s tree and go, and the needs-you list. It adds one search for the PRs
updated since the data's start, with their closing issues, approvals and commits:
`ceil(PRs / PR_PAGE)` GraphQL queries, 1 to 4 for two weeks. Stdlib only.
"""
from __future__ import annotations

import datetime as dt
import json
import math
import subprocess

import effort as effort_mod
import generate
import spend

SCHEMA = 1
WINDOWS = {"hour": 1, "day": 24, "week": 7 * 24, "month": 30 * 24}   # hours
DEFAULT_WINDOW = "day"
DESK_WINDOWS = ("hour", "day", "week")   # what map.json carries: the desk reads 14 days
BASELINE_WINDOWS = 4
DAYS = 14
KINDS = ("merged", "approved", "closed")
TOKEN_KINDS = ("input", "cache_creation", "cache_read", "output")   # spend.PRICES' order
UNCLASSIFIED = "unclassified"
UNATTRIBUTED = "unattributed"
STAGES = ("blocked", "merging", "review", "building", "queued")
FILE = "map.json"
PR_PAGE = 50
HOUR = dt.timedelta(hours=1)

PR_QUERY = """query($q: String!, $endCursor: String) {
  search(type: ISSUE, query: $q, first: %d, after: $endCursor) {
    pageInfo { hasNextPage endCursor }
    nodes { ... on PullRequest {
      number isDraft state mergedAt headRefOid
      closingIssuesReferences(first: 10) { nodes { number repository { nameWithOwner } } }
      reviews(first: 50, states: [APPROVED]) { nodes { author { login __typename } commit { oid } submittedAt } }
      commits(first: 100) { nodes { commit { additions deletions committedDate } } }
    } }
  }
}""" % PR_PAGE


# ---------------------------------------------------------------- reading

def days_needed(window: str) -> int:
    """Days of heartbeat data a window needs: itself and its baseline, and the 14 days."""
    return max(DAYS, math.ceil(WINDOWS[window] * (1 + BASELINE_WINDOWS) / 24) + 1)


def fetch_prs(repo: str, since: dt.datetime, run=subprocess.run) -> list[dict]:
    """The PRs updated since `since`, as GraphQL nodes. Raises RuntimeError."""
    q = f"repo:{repo} is:pr updated:>={since.strftime('%Y-%m-%dT%H:%M:%SZ')}"
    r = run(["gh", "api", "graphql", "--paginate", "-f", f"query={PR_QUERY}", "-f", f"q={q}",
             "--jq", ".data.search.nodes[]"], capture_output=True, text=True, timeout=180)
    if r.returncode != 0:
        raise RuntimeError(f"gh api graphql (the map's PRs) failed: {(r.stderr or '').strip()[:300]}")
    return [json.loads(line) for line in (r.stdout or "").splitlines() if line.strip()]


def gather(repo: str, now: dt.datetime, window: str, idle_minutes: int = generate.IDLE_MINUTES) -> dict:
    """Everything build() needs for `swarm map`: generate.fetch()'s data with the plan, the
    model generate.build() makes of it, the PRs and the effort cache. Raises RuntimeError."""
    import plan
    days = days_needed(window)
    try:
        data = generate.fetch(repo, now, days)
        data["plan"] = plan.fetch(repo)
        model = generate.build(data, now, dt.timedelta(minutes=idle_minutes), caps=generate.load_caps())
        since = now - dt.timedelta(days=days)
        return {"data": data, "model": model, "prs": fetch_prs(repo, since),
                "effort": effort_mod.load(), "since": since}
    except (OSError, subprocess.SubprocessError, ValueError) as e:
        raise RuntimeError(str(e) or type(e).__name__) from None


# ---------------------------------------------------------------- attribution

def hour_of(t: dt.datetime) -> dt.datetime:
    return t.astimezone(dt.timezone.utc).replace(minute=0, second=0, microsecond=0)


def _counts(t) -> dict | None:
    if not isinstance(t, dict):
        return None
    try:
        return {k: int(t[k]) for k in TOKEN_KINDS}
    except (KeyError, TypeError, ValueError):
        return None


def price(model: str | None, tokens: dict) -> float | None:
    r = spend.rates(model)
    if r is None:
        return None
    return sum(tokens[k] * p for k, p in zip(TOKEN_KINDS, r)) / 1_000_000


def charges(events: list[dict], role: str) -> list[dict]:
    """One session's spend between consecutive events (oldest first), each {ts, issue, role,
    model, tokens, cost}: `issue` is the latest working_on's before the event, else None."""
    out, prev, current = [], dict.fromkeys(TOKEN_KINDS, 0), None
    for ev in events:
        t = _counts(ev.get("token_counts"))
        ts = generate.parse_ts(ev.get("ts") or "")
        if t is not None and ts is not None:
            delta = {k: max(0, t[k] - prev[k]) for k in TOKEN_KINDS}
            prev = {k: max(prev[k], t[k]) for k in TOKEN_KINDS}
            n = sum(delta.values())
            if n:
                out.append({"ts": ts, "issue": current, "role": role, "model": ev.get("model"),
                            "tokens": n, "cost": price(ev.get("model"), delta)})
        if ev.get("event") == "working_on" and isinstance(ev.get("issue"), int):
            current = ev["issue"]
    return out


def all_charges(data: dict) -> list[dict]:
    """Every session's charges, from the tracking issues generate.fetch() read."""
    repo = data["repo"]
    out = []
    for s in generate.tracking_issues(data["issues"]):
        events = generate.session_events(s, data["comments"].get(s["issue"], []), repo)
        out += charges(events, s["role"])
    return out


def _ts(s) -> dt.datetime | None:
    return generate.parse_ts(s) if isinstance(s, str) else None


def _closes(pr: dict, repo: str) -> list[int]:
    return [c["number"] for c in ((pr.get("closingIssuesReferences") or {}).get("nodes") or [])
            if c and (c.get("repository") or {}).get("nameWithOwner") in (None, repo)]


def outcomes(prs: list[dict], issues: list[dict], repo: str) -> list[dict]:
    """Each outcome once, as {ts, issue, kind}: a closing PR's merge, the reviewer App's first
    approval at its head, and each issue's close."""
    out = []
    for p in prs:
        closes = _closes(p, repo)
        merged = _ts(p.get("mergedAt"))
        approvals = sorted(t for r in ((p.get("reviews") or {}).get("nodes") or []) if r
                           if generate.ghql.login(r.get("author")) == generate.REVIEWER
                           and (r.get("commit") or {}).get("oid") == p.get("headRefOid")
                           and (t := _ts(r.get("submittedAt"))) is not None)
        for n in closes:
            if merged:
                out.append({"ts": merged, "issue": n, "kind": "merged"})
            if approvals:
                out.append({"ts": approvals[0], "issue": n, "kind": "approved"})
    for i in issues:
        closed = _ts(i.get("closed_at"))
        if i.get("state") == "closed" and closed and not generate.is_tracking(i):
            out.append({"ts": closed, "issue": i["number"], "kind": "closed"})
    return out


# ---------------------------------------------------------------- per issue

def plan_index(plan_data: dict | None, plan_model: dict | None,
               repo: str) -> tuple[dict, dict, set, set]:
    """From the plan: each issue's Goal or Area {number, lead, title, kind} (open or closed
    sub-issues, two levels), each open sub-issue's go kind, the open sub-issues, and those of
    them with an open blocked-by. The last comes from the plan's go read (plan.GO_FIELD), not
    the go kind: plan.status() says `go` for an owner-`ready` issue before it looks at its
    blockers, and `waiting` only when blockers are its only reason."""
    goal_of, go, open_subs, blocked = {}, {}, set(), set()
    if not plan_model or not plan_model.get("read"):
        return goal_of, go, open_subs, blocked
    trees = (plan_data or {}).get("trees") or {}
    for s in plan_model["scopes"]:
        g = {"number": s["number"], "lead": s["lead"], "title": s["title"], "kind": s["kind"]}
        for a in ((trees.get(s["number"]) or {}).get("subIssues") or {}).get("nodes") or []:
            for x in [a, *(((a or {}).get("subIssues") or {}).get("nodes") or [])]:
                if not x or (x.get("repository") or {}).get("nameWithOwner") not in (None, repo):
                    continue
                goal_of.setdefault(x["number"], g)
                if (x.get("state") or "").lower() == "open":
                    open_subs.add(x["number"])
        for row in s["subs"]:
            for r in [row, *row.get("children", [])]:
                go[r["number"]] = r["status"]["kind"]
    for n, node in ((plan_data or {}).get("go") or {}).items():
        nodes = ((node or {}).get("blockedBy") or {}).get("nodes") or []
        if n in open_subs and any(b and (b.get("state") or "").upper() != "CLOSED" for b in nodes):
            blocked.add(n)
    return goal_of, go, open_subs, blocked


def stage(go_kind: str | None, open_prs: list[dict], session_on: bool, session_blocked: bool,
          open_blocker: bool = False) -> str | None:
    """One open issue's stage (see the module doc). `open_prs` are generate.build()'s PRs;
    `open_blocker` is whether it has an open blocked-by, whatever its go kind."""
    if open_blocker or go_kind == "waiting" or session_blocked:
        return "blocked"
    ready = [p for p in open_prs if not p.get("draft")]
    if any((p.get("reviewer") or {}).get("at_head") == "APPROVED" for p in ready):
        return "merging"
    if ready:
        return "review"
    if open_prs or session_on:
        return "building"
    if go_kind == "go":
        return "queued"
    return None


def needs_issues(model: dict) -> set[int]:
    """The issues in the needs-you list: a question or blocked item's issue, the issue a
    blocked session is on, and what a listed PR closes. Over-cap items are spend, so they're
    left out, as state.json leaves them (GOV-0014)."""
    prs = {p["number"]: p for p in model["prs"]}
    out = set()
    for item in generate.needs_you(model):
        if item["kind"] in ("blocked", "question"):
            out.add(int(item["ref"].lstrip("#")))
        elif item["kind"] == "pr":
            p = prs.get(int(item["ref"].split("#")[1]))
            out |= {c["number"] for c in (p or {}).get("closes") or []}
    out |= {s["issue"] for s in model["sessions"]
            if s["status"] == "blocked" and s.get("issue") and not s.get("never_acted")}
    return out


def effort_of(pr_numbers: set[int], cache: dict | None, repo: str) -> str:
    """The label of the most recently merged of these PRs in the effort cache, else of the
    most recent (highest numbered) classified one, else unclassified."""
    cands = []
    for key, p in ((cache or {}).get("prs") or {}).items():
        if not isinstance(p, dict) or not str(key).isdigit() or int(key) not in pr_numbers:
            continue
        if (p.get("repo") or repo) != repo or p.get("label") not in effort_mod.LABELS:
            continue
        cands.append((effort_mod._ts(p.get("merged_at")), int(key), p["label"]))
    merged = [c for c in cands if c[0] is not None]
    if merged:
        return max(merged, key=lambda c: (c[0], c[1]))[2]
    if cands:
        return max(cands, key=lambda c: c[1])[2]
    return UNCLASSIFIED


# ---------------------------------------------------------------- the map

def _span(end_hour: dt.datetime, hours: int, back: int = 0) -> tuple[dt.datetime, dt.datetime]:
    """[start, end) of the window `back` windows before the current one."""
    end = end_hour + HOUR - dt.timedelta(hours=hours * back)
    return end - dt.timedelta(hours=hours), end


def _sum_cost(items) -> float | None:
    """The priced part of these charges: 0 for none, None if every one is unpriced."""
    items = list(items)
    priced = [c["cost"] for c in items if c["cost"] is not None]
    return sum(priced) if priced or not items else None


def _money(x: float | None) -> float | None:
    return None if x is None else round(x, 4)


def build(g: dict, now: dt.datetime, window: str = DEFAULT_WINDOW) -> dict:
    """The map for one window: {"schema", "built_at", "repo", "window", "from", "to", "method",
    "rows"}. `g` is gather()'s dict (data, model, prs, effort, since). No total, anywhere."""
    if window not in WINDOWS:
        raise ValueError(f"unknown window {window!r}; choose from {', '.join(WINDOWS)}")
    data, model, repo = g["data"], g["model"], g["data"]["repo"]
    hours = WINDOWS[window]
    start, end = _span(hour_of(now), hours)
    since = g.get("since")
    issues = {i["number"]: i for i in data["issues"] if not generate.is_tracking(i)}
    plan_model = model.get("plan")
    if plan_model is None and data.get("plan") is not None:
        import committees
        import plan
        plan_model = plan.build(data["plan"], committees.owner_login(), repo)
    goal_of, go, open_subs, blocked = plan_index(data.get("plan"), plan_model, repo)

    spent = all_charges(data)
    happened = outcomes(g.get("prs") or [], data["issues"], repo)

    def within(x, a, b):
        return a <= x["ts"] < b

    in_window = [c for c in spent if within(c, start, end)]
    out_window = [o for o in happened if within(o, start, end)]
    closed = {n for n, i in issues.items() if i.get("state") == "closed"
              and (t := _ts(i.get("closed_at"))) and start <= t < end}
    keys = sorted(open_subs | closed | {c["issue"] for c in in_window if c["issue"] is not None}
                  | {o["issue"] for o in out_window})

    # PRs per issue: the search's, and the open ones generate.build() read with their reviews.
    prs_of: dict[int, set[int]] = {}
    for p in g.get("prs") or []:
        for n in _closes(p, repo):
            prs_of.setdefault(n, set()).add(p["number"])
    open_prs_of: dict[int, list[dict]] = {}
    for p in model["prs"]:
        for c in p.get("closes") or []:
            open_prs_of.setdefault(c["number"], []).append(p)
            prs_of.setdefault(c["number"], set()).add(p["number"])
    lines_of: dict[int, int] = {}
    for p in g.get("prs") or []:
        n_lines = sum((c.get("commit") or {}).get("additions", 0) + (c.get("commit") or {}).get("deletions", 0)
                      for c in ((p.get("commits") or {}).get("nodes") or []) if c
                      if (t := _ts((c.get("commit") or {}).get("committedDate"))) and start <= t < end)
        for n in _closes(p, repo):
            lines_of[n] = lines_of.get(n, 0) + n_lines

    live = [s for s in model["sessions"] if s["status"] != "stopped" and not s.get("never_acted")]
    needs = needs_issues(model)
    covered = since is None or _span(hour_of(now), hours, BASELINE_WINDOWS)[0] >= since
    today = now.astimezone(dt.timezone.utc).date()
    day_list = [today - dt.timedelta(days=i) for i in range(DAYS - 1, -1, -1)]

    def row(n: int | None) -> dict:
        mine = [c for c in in_window if c["issue"] == n]
        unpriced = sum(c["tokens"] for c in mine if c["cost"] is None)
        by_role: dict[str, list] = {}
        for c in mine:
            r = by_role.setdefault(c["role"], [0.0, 0])
            r[0] += c["cost"] or 0.0
            r[1] += c["tokens"]
        kinds = {k: sum(o["issue"] == n and o["kind"] == k for o in out_window) for k in KINDS}
        all_mine = [c for c in spent if c["issue"] == n]
        baseline = None
        if covered:
            past = [sum(c["cost"] or 0.0 for c in all_mine if within(c, *_span(hour_of(now), hours, k)))
                    for k in range(1, BASELINE_WINDOWS + 1)]
            baseline = sum(past) / BASELINE_WINDOWS
        days = []
        for d in day_list:
            a = dt.datetime.combine(d, dt.time(), dt.timezone.utc)
            b = a + dt.timedelta(days=1)
            days.append({"date": d.isoformat(),
                         "cost": _money(_sum_cost([c for c in all_mine if within(c, a, b)])),
                         "outcomes": sum(o["issue"] == n for o in happened if within(o, a, b))})
        base = {"issue": n, "cost": _money(_sum_cost(mine)), "unpriced_tokens": unpriced,
                "tokens": sum(c["tokens"] for c in mine), "outcomes": sum(kinds.values()),
                "outcome_kinds": kinds, "baseline": _money(baseline), "days": days,
                "role": max(by_role, key=lambda r: (by_role[r][0], by_role[r][1], r)) if by_role else None}
        if n is None:
            return {**base, "ref": UNATTRIBUTED, "title": "spend before any working_on",
                    "url": None, "state": None, "lines": 0, "goal": None, "effort": None,
                    "stage": None, "needs_you": False}
        it = issues.get(n) or {}
        state = it.get("state") or ("open" if n in open_subs else None)
        st = None
        if state == "open":
            on = [s for s in live if s.get("issue") == n]
            st = stage(go.get(n), open_prs_of.get(n, []), bool(on),
                       any(s["status"] == "blocked" for s in on), n in blocked)
        return {**base, "ref": f"#{n}", "title": it.get("title") or "",
                "url": it.get("html_url") or f"https://github.com/{repo}/issues/{n}",
                "state": state, "lines": lines_of.get(n, 0), "goal": goal_of.get(n),
                "effort": effort_of(prs_of.get(n, set()), g.get("effort"), repo),
                "stage": st, "needs_you": n in needs}

    rows = [row(n) for n in keys]
    rows.sort(key=lambda r: (-(r["cost"] or 0.0), -r["tokens"], r["issue"]))
    rows.append(row(None))
    return {"schema": SCHEMA, "built_at": generate.rfc3339(now), "repo": repo, "window": window,
            "from": generate.rfc3339(start), "to": generate.rfc3339(end),
            "baseline_covered": covered, "method": spend.METHOD, "rows": rows}


def desk_file(g: dict, now: dt.datetime) -> dict:
    """map.json: the map for each of DESK_WINDOWS (the desk's 14 days cover them)."""
    return {"schema": SCHEMA, "built_at": generate.rfc3339(now), "repo": g["data"]["repo"],
            "method": spend.METHOD, "windows": {w: build(g, now, w)["rows"] for w in DESK_WINDOWS}}


# ---------------------------------------------------------------- text

SPARK = " ▁▂▃▄▅▆▇█"


def spark(values: list[float | None]) -> str:
    top = max((v for v in values if v), default=0)
    if not top:
        return "·" * len(values)
    return "".join("·" if not v else SPARK[max(1, round(v / top * (len(SPARK) - 1)))] for v in values)


def text(m: dict) -> str:
    """The plain-text map: one line per issue, then the method. No total line (GOV-0033)."""
    head = ["ISSUE", "STAGE", "COST", "BASE", "TOKENS", "LINES", "OUT", "GOAL", "EFFORT", "ROLE",
            "YOU", "14 DAYS", "TITLE"]
    body = []
    for r in m["rows"]:
        cost = spend.usd(r["cost"]) + ("*" if r["unpriced_tokens"] else "")
        goal = r["goal"]
        body.append([r["ref"], r["stage"] or "-", cost, spend.usd(r["baseline"]),
                     f"{r['tokens']:,}", str(r["lines"]),
                     "/".join(str(r["outcome_kinds"][k]) for k in KINDS),
                     (goal["lead"] or f"#{goal['number']}") if goal else "-",
                     r["effort"] or "-", r["role"] or "-", "yes" if r["needs_you"] else "",
                     spark([d["cost"] for d in r["days"]]), r["title"][:50]])
    widths = [max(len(x[i]) for x in [head] + body) for i in range(len(head))]
    lines = [f"Work map, last {m['window']} ({m['from']} to {m['to']}), one row per issue:", ""]
    lines += ["  ".join(c.ljust(w) for c, w in zip(x, widths)).rstrip() for x in [head] + body]
    lines += ["",
              "OUT is merged/approved/closed. BASE is the mean cost of the four windows before"
              + ("." if m.get("baseline_covered") else "; '—': the data read doesn't reach back that far."),
              "* some tokens are from a model with no list price: they are counted but not priced.",
              spend.METHOD]
    return "\n".join(lines)
