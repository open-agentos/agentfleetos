#!/usr/bin/env python3
"""Render the swarm dashboard: static, read-only HTML pages (#401).

Reads, through `gh api` (in a swarm session that's ops/shims/gh acting as the role's App):
  - heartbeat events from the comments on `[heartbeat]` tracking issues (GOV-0003,
    heartbeat/SCHEMA.md). Only the GitHub copy is read, which never carries prompt
    text (GOV-0002); the local spool is not touched;
  - open PRs, the issues they close, and the reviewer App's reviews on each non-draft
    PR (GOV-0011's round count and Authority line);
  - open `gov:question` issues, `gov:lapsed` ones closed in the window, and
    governance/INDEX.md from the checkout (the governance section, #355).
  - for Governance's trends (#406) and how the questions went (#407), questions.py:
    `gov:question`s created in the window with their label and close events, PRs merged in
    the window, and record dates from the checkout.
  - for every page's header (#402, activity.py): the repo's public events, 1 to 3 pages, to
    say when the owner last acted.

Builds three pages in one look (layout.py), joined by one nav, Map · Crew · Governance
(#1113), each headed by a red LIVE mark, the build time and the owner's last act (#402), and
copies the self-hosted fonts and the pages' scripts (js/, #1106) beside them:
  - workmap.html, the Work map (workmap_page.py, #1082): a treemap of what each issue cost
    and what it returned, from map.json's data, with the counts strip above it and the lead's
    Briefing, the lists and the tape under it; the live Desk's home;
  - crew.html: one row per role (agents.py, #932), each opening its role view on the Work map
    (#1115), then on the floor (floor.py), the sessions table, the Actions reviewer, grants in
    use (grants.py, #713) and effort per open Goal (effort.py, #1013), all drawn client-side
    from state.json (crewpage.py and crew.js, #1139);
  - governance.html: the full decision log, open and lapsed gov questions, the committees
    (the committee desk and round grids, then past committees' cards and grids), the authority
    map (authority.py, #410), precedent in use, what the numbers say and how the questions went,
    all drawn client-side from state.json (govpage.py and governance.js, #1140).
Plus effort.html, the PRs behind each segment of Crew's Effort bars (#1013), and a redirect for
each retired page (REDIRECTS: index.html, the old desk, and the Bridge, Commissions, Agents,
Operations, Decisions and Authority pages). index.html is the --out page, so a host that serves
it at / (Pages) sends the browser on to the Work map.
Stdlib only. Crew loads its own script (crew.js, #1139), Governance its own
(governance.js, #1140), and the Work map its treemap (workmap.js, #1082). Each is a same-origin file in
js/, allowed by its hash in the page's CSP (option 3 of gov question #1102). Vendored libraries
(static/vendor/, #1107) are checked against their pinned hashes before anything is fetched or
written, and copied into js/ beside them; a mismatch fails the build.

    python3 dashboard/generate.py                 # writes dashboard/out/: workmap.html, crew.html, governance.html, ...
    python3 dashboard/generate.py --out /tmp/x/index.html --days 7 --idle-minutes 15
"""
from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import activity
import authority
import committees
import crewpage
import effort
import floor
import ghql
import governance
import govpage
import grants
import layout
import plan
import precedent
import questions
import report
import reviewer_runs
import spend
import trends
import wire
import workmap_page

HERE = Path(__file__).resolve().parent

IDLE_MINUTES = 15  # heartbeat/SCHEMA.md leaves the idle threshold to #4
DAYS = 14          # closed tracking issues older than this are skipped

MARKER_RE = re.compile(r"\A\s*<!-- productswarm-heartbeat schema_version=1 session_id=(\S+) -->")
BOT_RE = re.compile(r"\Aproductswarm-([a-z0-9-]+)\[bot\]\Z")
FENCE_RE = re.compile(r"```jsonl[^\n]*\n(.*?)```", re.S)
REPO_RE = re.compile(r"github\.com[:/]([\w.-]+/[\w.-]+?)(?:\.git)?/?$")

EVENTS = {"session_started", "prompt_submitted", "working_on", "pr_opened",
          "blocked", "heartbeat", "stopped"}
REQUIRED = ("schema_version", "ts", "session_id", "repo", "role", "model", "event")
# Fields allowed in the GitHub copy of an event (#/$defs/remote in event.schema.json).
REMOTE_FIELDS = set(REQUIRED) | {"issue", "pr", "gov_question", "cost_usd", "token_counts", "tools"}
QUIET_EVENTS = {"heartbeat", "prompt_submitted"}
STATUS_ORDER = {"blocked": 0, "active": 1, "idle": 2, "stopped": 3}

REVIEWER = "productswarm-reviewer[bot]"
# The roles whose own PRs GOV-0011's [respond] (and #739's [ruling]) restart: the PR's author
# role, not only the builder (#738, Option 1 of the owner's answer on #777). The reviewer
# opens no PRs. A PR by the owner or any other login has no role, so it stays the owner's.
RESPONDERS = ("builder", "planner", "docs", "designer", "analyst")
BUILDER = "productswarm-builder"   # the builder App; `gh` shows it as app/<slug>
CHANGES = "CHANGES_REQUESTED"
ROUNDS = 2         # author rounds per PR before the owner steps in (GOV-0011)
# The rubric line roles/reviewer.md asks for: "- **Authority:** pass|fail".
AUTHORITY_RE = re.compile(r"^[\s>*-]*Authority\s*:?[\s*]*:?\s*(pass|fail)\b", re.I | re.M)


# ---------------------------------------------------------------- reading GitHub

def gh_items(path: str, jq: str = ".[]") -> list[dict]:
    """Every item of a paginated list endpoint; `jq` picks the items out of each page
    (`.items[]` for search)."""
    r = subprocess.run(["gh", "api", "--paginate", path, "--jq", jq],
                       capture_output=True, text=True, timeout=120)
    if r.returncode != 0:
        raise RuntimeError(f"gh api {path} failed: {r.stderr.strip()[:300]}")
    return [json.loads(line) for line in r.stdout.splitlines() if line.strip()]


def gh_json(*args: str) -> object:
    r = subprocess.run(["gh", *args], capture_output=True, text=True, timeout=120)
    if r.returncode != 0:
        raise RuntimeError(f"gh {' '.join(args[:2])} failed: {r.stderr.strip()[:300]}")
    return json.loads(r.stdout or "null")


COMMENTS_BATCH = 25   # tracking issues per GraphQL query: about one rate-limit point each
COMMENTS_FIELD = ("i%d: issue(number: %d) { comments(first: 100) "
                  "{ totalCount nodes { body author { login __typename } } } }")


def tracking_comments(repo: str, numbers: list[int]) -> dict[int, list[dict]]:
    """Each tracking issue's comments in REST's shape ({"user": {"login"}, "body"}), oldest
    first: one GraphQL query per COMMENTS_BATCH issues, not one REST call per issue (#392).
    An issue with more than 100 comments, or one the query didn't return, falls back to REST."""
    out: dict[int, list[dict]] = {}
    for n, issue in ghql.batched(repo, numbers, COMMENTS_FIELD, COMMENTS_BATCH).items():
        nodes = ghql.complete((issue or {}).get("comments"))
        out[n] = (gh_items(f"repos/{repo}/issues/{n}/comments?per_page=100") if nodes is None else
                  [{"user": {"login": ghql.login(x.get("author"))}, "body": x.get("body") or ""}
                   for x in nodes])
    return out


def fetch(repo: str, now: dt.datetime, days: int,
          with_actions: bool = False, with_committees: bool = False,
          with_questions: bool = False, with_precedent: bool = False,
          with_activity: bool = False, with_grants: bool = False,
          with_plan: bool = False, with_trouble: bool = False, prev: Path | None = None) -> dict:
    """Everything the page needs, as plain API data. build() does the rest. `with_actions`
    reads the Actions
    reviewer section's (reviewer_runs.py), `with_committees` the committee Discussions
    (committees.py, GraphQL), `with_questions` the gov:question history the desk's trends
    read (questions.py, REST, search and GraphQL), and `with_precedent` the GOV citations
    (precedent.py), `with_activity` the repo's events for the header (activity.py), and
    `with_plan` the desk's plan and today's report (plan.py, report.py, #712), and `with_grants`
    the merger's comments for grants in use (grants.py, #713), and `with_trouble` the trouble
    report (fetch_trouble, #903). Only the page shows them, so swarm's snapshot() and the
    digest leave all eight off and make none of those calls; main() asks for them."""
    since = (now - dt.timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    issues: dict[int, dict] = {}
    items: dict[int, dict] = {}   # issues and PRs, for precedent.py's bodies
    for path in (f"repos/{repo}/issues?state=open&per_page=100",
                 f"repos/{repo}/issues?state=closed&since={since}&per_page=100"):
        for it in gh_items(path):
            items[it["number"]] = it
            if "pull_request" not in it:
                issues[it["number"]] = it
    comments = tracking_comments(repo, [s["issue"] for s in tracking_issues(issues.values())])
    prs = gh_json("pr", "list", "--repo", repo, "--state", "open", "--limit", "100", "--json",
                  "number,title,url,author,isDraft,createdAt,reviewDecision,closingIssuesReferences,"
                  "headRefOid,mergeable")      # mergeable: swarm watch's [conflict] (#893)
    reviews = {p["number"]: gh_items(f"repos/{repo}/pulls/{p['number']}/reviews?per_page=100")
               for p in prs or [] if not p.get("isDraft")}
    try:
        index = governance.INDEX.read_text(encoding="utf-8")
    except OSError:
        index = None   # the section says so; the rest of the page still builds
    try:
        jurisdictions = authority.JURISDICTIONS.read_text(encoding="utf-8")
    except OSError:
        jurisdictions = None   # the authority map says so (#410)
    return {"repo": repo, "issues": list(issues.values()), "comments": comments, "prs": prs or [],
            "reviews": reviews, "index": index, "jurisdictions": jurisdictions,
            "actions": reviewer_runs.fetch(repo, now, reviews) if with_actions else None,
            "committees": committees.fetch(repo, gh_items, gh_json) if with_committees else None,
            "questions": questions.fetch(repo, now, days, gh_items) if with_questions else None,
            "precedent": fetch_precedent(repo, now, days, list(items.values()), prev)
                         if with_precedent else None,
            "activity": activity.fetch(repo, gh_json, committees.owner_login(), wire.midnight(now))
                        if with_activity else None,
            "grants": grants.fetch(repo, now, gh_items, gh_json,
                                   {p["number"]: p.get("title") or "" for p in prs or []})
                      if with_grants else None,
            "plan": plan.fetch(repo) if with_plan else None,
            "report": fetch_report(repo, now) if with_plan else None,
            "trouble": fetch_trouble(repo, now) if with_trouble else None,
            # The tape's shipped and delivered items (#926, #1114), from the closed items read above.
            "merged": merged_prs(items.values())}


def merged_prs(items) -> list[dict]:
    """PRs among `items` (REST issues) that GitHub has merged, as {number, title, url, author,
    merged_at}. No API calls: the closed items fetch() reads already carry merged_at."""
    return [{"number": it["number"], "title": it.get("title") or "", "url": it.get("html_url"),
             "author": (it.get("user") or {}).get("login"), "merged_at": pr["merged_at"]}
            for it in items if (pr := it.get("pull_request") or {}).get("merged_at")]


def fetch_report(repo: str, now: dt.datetime) -> dict:
    """report.py's data: swarm.toml's report issue and daily_at, and the issue's recent comments."""
    issue, daily_at = report.config()
    return {"issue": issue, "daily_at": daily_at, "comments": report.fetch(repo, issue, now, gh_items)}


def fetch_trouble(repo: str, now: dt.datetime) -> dict:
    """`swarm trouble --json`'s report (launcher/trouble.py) for the desk's trouble panel (#903),
    without the owner-acts sync: the desk only reads, and on the engine host swarm.db holds no
    acts, so M4's acts criterion reads unmeasured and the panel says why. The rest it reads from
    GitHub, and from the launcher's state directory where it exists (the runs ledger, swarm
    watch's state, hand-started sessions); a part it can't read is named in the panel. If
    GitHub can't be read, {"error": why}: the panel says so and the rest of the desk builds."""
    try:
        sys.path.insert(0, str(HERE.parent / "launcher"))
        import manifest
        import swarm
        import trouble
        owner = swarm.owner_login()
        d = trouble.gather(swarm.Launcher(swarm.home()), repo, owner, manifest.DEFAULT_PATH,
                           now=now, sync_acts=False)
        return trouble.report(d)
    except (RuntimeError, OSError, subprocess.SubprocessError, ValueError) as e:
        return {"error": str(e) or type(e).__name__}


def fetch_precedent(repo: str, now: dt.datetime, days: int, items: list[dict],
                    prev: Path | None = None) -> dict:
    """precedent.py's data, leaving out tracking issues and the digest issue, and carrying
    counts forward from the last published state.json: the Pages copy, or with `prev` (the
    hosted desk, #664) that file on disk."""
    import digest   # here, not at the top: digest imports this module
    skip = ({t["issue"] for t in tracking_issues(items)}
            | {i["number"] for i in items if (i.get("body") or "").lstrip().startswith(digest.MARKER)})
    return precedent.fetch(repo, now, days, items, skip, gh_items, ghql, load_owner(),
                           precedent.published(repo) if prev is None else read_state(prev))


def read_state(path: Path) -> dict | None:
    """A state.json on disk, or None if it is missing or unreadable: the build then reads
    precedent's whole window again."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def load_owner() -> str | None:
    """humans.owner's login from jurisdictions.yml (launcher/swarm.py reads it the same way),
    or None if it can't be read: the owner's citations then count only in the total."""
    try:
        sys.path.insert(0, str(HERE.parent / "launcher"))
        import swarm
        return swarm.owner_login()
    except Exception:
        return None


# ---------------------------------------------------------------- deriving state

def reviewer_state(reviews: list[dict], head: str | None) -> dict:
    """The reviewer App's reviews on one PR (REST order, oldest first), as GOV-0011 reads
    them: how many times it requested changes, on any head, and its latest review at
    `head` with that review's Authority line and when it was posted (for #739's [ruling]).
    Keeps no review text (GOV-0002)."""
    mine = [r for r in reviews if (r.get("user") or {}).get("login") == REVIEWER]
    at_head = [r for r in mine if head and r.get("commit_id") == head]
    last = at_head[-1] if at_head else None
    m = AUTHORITY_RE.search((last or {}).get("body") or "")
    return {"changes_requested": sum(r.get("state") == CHANGES for r in mine),
            "at_head": last.get("state") if last else None,
            "authority": m.group(1).lower() if m else None,
            "at_head_at": (last or {}).get("submitted_at")}


def pr_role(author: str) -> str | None:
    """The productswarm role whose App opened a PR, from its author login: `gh` shows an App
    as app/productswarm-<role>, the REST API as productswarm-<role>[bot]. None for others."""
    m = re.fullmatch(r"(?:app/)?productswarm-([a-z0-9-]+?)(?:\[bot\])?", author or "")
    return m.group(1) if m else None


def past_bound(changes_requested: int) -> bool:
    """GOV-0011's round bound: the PR's author role gets ROUNDS rounds, so the reviewer App's
    (ROUNDS + 1)th "changes requested" on a PR sends it to the owner. evals/red_check.py
    (#330) counts with this too."""
    return changes_requested > ROUNDS


def needs_owner(r: dict, author: str) -> str | None:
    """Why GOV-0011 hands this PR to the owner instead of its author's role, else None.

    A role responds only on a PR its own App opened, and only the RESPONDERS do (#738,
    Option 1 of the owner's answer on #777), so requested changes on a PR the owner or
    another login opened go to the owner too (#178)."""
    if r["at_head"] is None:
        return None
    if r["authority"] == "fail":
        return "overstep: needs the owner"
    role = pr_role(author)
    if r["at_head"] == CHANGES and role not in RESPONDERS:
        return f"changes requested on a {role or 'non-swarm'} PR: needs the owner"
    if r["at_head"] == CHANGES and past_bound(r["changes_requested"]):
        return f"changes requested {r['changes_requested']} times: needs the owner"
    return None


def unreviewed(p: dict) -> str | None:
    """"no reviewer review at <sha7>" for a builder-App PR with no reviewer-App review at
    its current head, else None (#332). reviewDecision can't show this: an owner approval
    sets it too. Three builder PRs were merged with no reviewer review (#200, #269, #275)."""
    rv, head = p.get("reviewer") or {}, p.get("head")
    if head and pr_role(p.get("author", "")) == "builder" and rv.get("at_head") is None:
        return f"no reviewer review at {head[:7]}"
    return None


def parse_ts(s: str) -> dt.datetime | None:
    try:
        t = dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
    except (AttributeError, ValueError):
        return None
    return t if t.tzinfo else None


def tracking_issues(issues) -> list[dict]:
    """Tracking issues: the heartbeat marker, opened by a productswarm-<role>[bot] App."""
    out = []
    for it in issues:
        login = (it.get("user") or {}).get("login", "")
        bot = BOT_RE.match(login)
        marker = MARKER_RE.match(it.get("body") or "")
        if bot and marker:
            out.append({"issue": it["number"], "session_id": marker.group(1), "role": bot.group(1),
                        "author": login, "closed": it.get("state") == "closed",
                        "created_ts": parse_ts(it.get("created_at") or "")})
    return out


def is_tracking(issue: dict) -> bool:
    return bool(tracking_issues([issue]))


def parse_comment(body: str) -> list[dict]:
    """Events from the first ```jsonl fence of a tracking comment; bad lines are skipped."""
    m = FENCE_RE.search(body or "")
    if not m:
        return []
    out = []
    for line in m.group(1).splitlines():
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        if isinstance(ev, dict):
            out.append(ev)
    return out


def valid_event(ev: dict, session: dict, repo: str) -> bool:
    if any(k not in ev for k in REQUIRED) or set(ev) - REMOTE_FIELDS:
        return False
    if ev["schema_version"] != 1 or ev["event"] not in EVENTS or parse_ts(ev["ts"]) is None:
        return False
    # The comment must describe this tracking issue's session, role and repo.
    return (ev["session_id"] == session["session_id"] and ev["role"] == session["role"]
            and ev["repo"] == repo)


def session_events(session: dict, comments: list[dict], repo: str) -> list[dict]:
    """Valid events posted by the App that opened the tracking issue, oldest first."""
    events = []
    for c in comments:
        if (c.get("user") or {}).get("login") != session["author"]:
            continue  # anyone else's comment is not a heartbeat
        events += [e for e in parse_comment(c.get("body", "")) if valid_event(e, session, repo)]
    events.sort(key=lambda e: parse_ts(e["ts"]))
    return events


def derive(session: dict, events: list[dict], open_issues: set[int], now: dt.datetime,
           idle_after: dt.timedelta) -> dict:
    """Status per heartbeat/SCHEMA.md, 'How the dashboard reads status'."""
    last = events[-1] if events else None
    last_ts = parse_ts(last["ts"]) if last else None
    state_ev = next((e for e in reversed(events) if e["event"] not in QUIET_EVENTS), None)
    issue = next((e["issue"] for e in reversed(events) if e.get("issue")), None)
    # Show a PR only while the session is still on the issue it was opened for (#29).
    pr = next((e["pr"] for e in reversed(events) if e.get("pr") and e.get("issue") == issue), None)
    gov = None
    if (last and last["event"] == "stopped") or session["closed"]:
        status = "stopped"  # the hook closes the issue after posting `stopped`
    elif state_ev and state_ev["event"] == "blocked" and state_ev.get("gov_question") in open_issues:
        status, gov = "blocked", state_ev["gov_question"]
    elif last_ts is None or now - last_ts > idle_after:
        status = "idle"
    else:
        status = "active"
    # Never acted (#454): no events, and its tracking issue is older than the idle threshold,
    # such as the empty `[heartbeat] reviewer` issues Actions runs opened before #307. A newer
    # one stays visible: its first event may not have reached GitHub yet.
    created = session.get("created_ts")
    never_acted = (status == "idle" and not events and created is not None
                   and now - created > idle_after)
    return {
        "session_id": session["session_id"], "role": session["role"],
        "tracking_issue": session["issue"], "status": status, "issue": issue, "pr": pr,
        "gov_question": gov, "model": last["model"] if last else None,
        "last_event": last["event"] if last else None, "last_ts": last_ts,
        "started_ts": parse_ts(events[0]["ts"]) if events else None,
        "cost": spend.session_cost(events),
        "never_acted": never_acted,
    }


def load_caps(path: Path | None = None) -> dict[str, float]:
    """Per-session spend cap by role, from the committed swarm.toml (L4, #52).

    The manifest is public, so caps keep the page public-data-only. A session's cap is
    its role's `spend_cap_usd`; no cap if the role sets none (#45). A missing or invalid
    manifest gives no caps rather than breaking the page."""
    try:
        sys.path.insert(0, str(HERE.parent / "launcher"))
        import manifest
        sessions = manifest.load(path or manifest.DEFAULT_PATH)
    except Exception:   # ImportError (no tomllib), ManifestError: no caps, page still renders
        return {}
    return {s.role: s.spend_cap_usd for s in sessions if s.spend_cap_usd is not None}


def load_watch_interval(path: Path | None = None) -> float | None:
    """swarm watch's interval_minutes from the committed swarm.toml's [watch] table, which
    says when the watcher's published state is stale (#459). None if it can't be read."""
    try:
        sys.path.insert(0, str(HERE.parent / "launcher"))
        import manifest
        limits = manifest.load_watch(path or manifest.DEFAULT_PATH)
    except Exception:   # ImportError (no tomllib), ManifestError: no stale line
        return None
    return limits.interval_minutes if limits else None


def over_cap(cost: float | None, cap: float | None) -> bool:
    """Warn-only (GOV-0008): this flags a session; nothing stops it."""
    return cost is not None and cap is not None and cost > cap


def build(data: dict, now: dt.datetime, idle_after: dt.timedelta,
          caps: dict[str, float] | None = None, window: int = DAYS,
          watch_interval: float | None = None) -> dict:
    repo = data["repo"]
    issues = {i["number"]: i for i in data["issues"]}
    open_issues = {n for n, i in issues.items() if i.get("state") == "open"}
    sessions, events_of = [], {}
    for s in tracking_issues(issues.values()):
        events = session_events(s, data["comments"].get(s["issue"], []), repo)
        d = derive(s, events, open_issues, now, idle_after)
        d["cap"] = (caps or {}).get(d["role"])
        d["over_cap"] = d["status"] != "stopped" and over_cap(d["cost"], d["cap"])
        sessions.append(d)
        events_of[d["session_id"]] = events
    epoch = dt.datetime.min.replace(tzinfo=dt.timezone.utc)
    sessions.sort(key=lambda s: (STATUS_ORDER[s["status"]], -(s["last_ts"] or epoch).timestamp()))

    gov = []
    for n in sorted(open_issues):
        it = issues[n]
        labels = [lb["name"] for lb in it.get("labels", [])]
        if "gov:question" in labels and not is_tracking(it):
            gov.append({"number": n, "title": it["title"], "url": it["html_url"],
                        "labels": [lb for lb in labels if lb != "gov:question"],
                        "created_ts": parse_ts(it["created_at"]),
                        "ttl": time_to_live(it.get("body")),
                        "fields": governance.question_fields(it.get("body"), labels),
                        "waiting": [s for s in sessions if s["gov_question"] == n]})

    prs = []
    for p in sorted(data["prs"], key=lambda p: p["number"]):
        closes = [{"number": c["number"], "title": issues.get(c["number"], {}).get("title", "")}
                  for c in p.get("closingIssuesReferences") or []]
        prs.append({"number": p["number"], "title": p["title"], "url": p["url"],
                    "author": (p.get("author") or {}).get("login", ""), "draft": p.get("isDraft"),
                    "review": p.get("reviewDecision") or "", "created_ts": parse_ts(p["createdAt"]),
                    "closes": closes, "head": p.get("headRefOid"),
                    "mergeable": p.get("mergeable")})
        prs[-1]["reviewer"] = rv = reviewer_state((data.get("reviews") or {}).get(p["number"], []),
                                                  p.get("headRefOid"))
        prs[-1]["needs_owner"] = needs_owner(rv, prs[-1]["author"])

    comms = committees.build(data.get("committees"))
    owner = committees.owner_login()
    history = (questions.build(data["questions"], now, window, owner)
               if data.get("questions") is not None else None)

    m = {"repo": repo, "now": now, "idle_minutes": int(idle_after.total_seconds() // 60),
         "issue_titles": {n: i["title"] for n, i in issues.items()},
         "sessions": sessions, "prs": prs,
         "floor": floor.build([(s, events_of[s["session_id"]]) for s in sessions], now), "gov": gov, "days": window,
         "watcher": floor.watcher(data["issues"], owner, now, watch_interval),   # #459
         "governance": governance.build(data.get("index"), gov, data["issues"], now,
                                        now - dt.timedelta(days=window), parse_ts,
                                        time_to_live, ttl_date),
         "reviewer_runs": reviewer_runs.build(
             data.get("actions"), [p for p in prs if not p["draft"] and unreviewed(p)], now),
         "committees": comms,
         "trends": trends.build(history),
         "questions_went": questions.went(history, committees.records(),
                                          {c.get("question") for c in comms["committees"]}, owner),
         "precedent": precedent.build(data.get("precedent"), data.get("records") or {}, now, window),
         "activity": data.get("activity"),   # the repo's events; the wire (#405) reuses them
         "owner_last_acted": activity.owner_last_acted(data.get("activity"),
                                                       committees.owner_login(), repo, now),
         "wire": wire.build(data.get("activity"), data.get("questions"), data.get("reviews"), comms,
                            committees.records(), owner, repo, now)   # #405: today's governance events
                 if data.get("activity") is not None or data.get("questions") is not None else None,
         "grants": grants.build(data["grants"], now)   # #713: the merger's calls
                   if data.get("grants") is not None else None,
         "report": report.build(data["report"]["comments"], now, data["report"]["issue"],   # #712
                                data["report"]["daily_at"]) if data.get("report") else None,
         # with_plan reads both; the plan's own None means its read failed, which the panel says
         "plan": plan.build(data.get("plan"), owner, repo) if data.get("report") else None,
         "trouble": data.get("trouble"),   # #903: trouble.report()'s dict, or {"error": why}
         "merged": data.get("merged") or [],   # #1114: the Work map tape's merged PRs
         # #931: the owner's Goals and Areas closed in the window, for Commissions' "delivered"
         "closed_scopes": [{"number": i["number"], "title": i.get("title"), "url": i.get("html_url"),
                            "type": (i.get("type") or {}).get("name"), "closed_at": i.get("closed_at")}
                           for i in data["issues"]
                           if i.get("state") == "closed" and (i.get("type") or {}).get("name") in ("Goal", "Area")
                           and (i.get("user") or {}).get("login") == owner]}
    m["authority"] = authority.build(data.get("jurisdictions"), m["governance"]["all_records"])
    # #1013: effort per open Goal, from classify/cache/effort.json alone (main() reads it)
    m["effort"] = effort.build(data.get("effort"), repo, now, effort.goals_of(m))
    return m


TTL_RE = re.compile(r"^###\s*Time to live\s*\n+\s*(\S[^\n]*?)\s*$", re.M)


def time_to_live(body: str | None) -> str | None:
    """The 'Time to live' answer from a Governance question template body."""
    m = TTL_RE.search(body or "")
    return m.group(1) if m and m.group(1) != "_No response_" else None


TTL_DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})(?:\s|$)")


def ttl_date(ttl: str | None) -> dt.date | None:
    """The date a 'Time to live' answer starts with, or None if it doesn't start with one.
    A note after the date ("2026-11-30 (the rulings' review date)") is allowed."""
    m = TTL_DATE_RE.match(ttl or "")
    try:
        return dt.date.fromisoformat(m.group(1)) if m else None
    except ValueError:
        return None


# ---------------------------------------------------------------- needs you (L5)

# Idle sessions aren't here: they belong in `swarm ls` and the floor (#469).
NEEDS_KINDS = ("blocked", "question", "pr", "over_cap")   # most urgent first


def needs_you(m: dict) -> list[dict]:
    """Everything waiting on the owner, most urgent first: the one list behind both the
    dashboard's first section and `swarm inbox`, so they can't disagree.

    Leaves out idle sessions (`swarm ls` and the floor show them), sessions that never
    acted (#454), and questions the owner
    has labelled gov:ruled, whose next step is docs or the planner, not the owner (#469);
    a record PR still shows as a PR.

    Reads only build()'s model, which comes from public GitHub data (GOV-0002, GOV-0004).
    Within a kind, the longest waiting comes first, except that questions past their time
    to live come first among questions (oldest time to live first). Each item: kind, ref,
    title, url, detail, since, for session items session_url, and for a question past its
    time to live past_ttl.
    """
    repo, now, titles = m["repo"], m["now"], m["issue_titles"]

    def issue_url(n):
        return f"https://github.com/{repo}/issues/{n}"

    def session(s):
        return f"{s['role']} session {s['session_id'][:8]}"

    items = []
    acted = [s for s in m["sessions"] if not s.get("never_acted")]   # #454
    for s in acted:
        if s["status"] == "blocked":
            q = s["gov_question"]
            items.append({"kind": "blocked", "ref": f"#{q}", "title": titles.get(q, ""),
                          "url": issue_url(q), "session_url": issue_url(s["tracking_issue"]),
                          "detail": f"{session(s)} is blocked on it"
                                    + (f" (working on #{s['issue']})" if s["issue"] else ""),
                          "since": s["last_ts"]})
    for q in m["gov"]:
        if not q["waiting"] and "gov:ruled" not in q["labels"]:
            # Only shows a lapse; the owner alone adds gov:lapsed (GOV-0006).
            d = ttl_date(q["ttl"])
            past = d if d and d < now.date() else None
            bits = [f"past time to live ({past})" if past
                    else f"time to live {q['ttl']}" if q["ttl"] else "no time to live given"]
            bits += q["labels"]
            items.append({"kind": "question", "ref": f"#{q['number']}", "title": q["title"],
                          "url": q["url"], "detail": ", ".join(bits), "since": q["created_ts"],
                          **({"past_ttl": past} if past else {})})
    for p in m["prs"]:
        if not p["draft"]:
            state = (p.get("needs_owner") or unreviewed(p)
                     or p["review"].replace("_", " ").lower() or "awaiting review")
            closes = ", ".join(f"#{c['number']}" for c in p["closes"])
            items.append({"kind": "pr", "ref": f"PR #{p['number']}", "title": p["title"],
                          "url": p["url"],
                          "detail": state + (f", closes {closes}" if closes else ""),
                          "since": p["created_ts"]})
    for s in acted:
        if s.get("over_cap"):
            items.append({"kind": "over_cap", "ref": session(s), "title": "",
                          "url": issue_url(s["tracking_issue"]),
                          "session_url": issue_url(s["tracking_issue"]),
                          "detail": f"est. {spend.usd(s['cost'])}, cap {spend.usd(s['cap'])}"
                                    + (f", on #{s['issue']}" if s["issue"] else "")
                                    + "; warn only: swarm stop ends it (GOV-0008)",
                          "since": s["last_ts"], "over": s["cost"] / s["cap"]})
    far, far_date = dt.datetime.max.replace(tzinfo=dt.timezone.utc), dt.date.max
    # Over-cap sessions: furthest over first. Questions past their time to live: oldest
    # time to live first, ahead of other questions. Everything else: longest waiting first.
    items.sort(key=lambda i: (NEEDS_KINDS.index(i["kind"]), -i.get("over", 0),
                              i.get("past_ttl", far_date), i["since"] or far))
    return items


NEEDS_LABELS = {"blocked": "blocked", "question": "gov question", "pr": "PR to review",
                "over_cap": "over cap"}
NEEDS_EMPTY = "Nothing is waiting on you."


def needs_line(item: dict, now: dt.datetime) -> str:
    """One item as plain text, without its link. The CLI and the page both show this."""
    title = f" {item['title']}" if item["title"] else ""
    since = (f" · {ago(item['since'], now)}"
             if item["since"] and item["kind"] != "over_cap" else "")
    return f"[{NEEDS_LABELS[item['kind']]}] {item['ref']}{title} · {item['detail']}{since}"


# ---------------------------------------------------------------- rendering

NONE = '<span class="muted">none</span>'


def esc(x) -> str:
    return html.escape("" if x is None else str(x))


def ago(t: dt.datetime | None, now: dt.datetime) -> str:
    if t is None:
        return "never"
    s = max(0, int((now - t).total_seconds()))
    for unit, size in (("d", 86400), ("h", 3600), ("m", 60)):
        if s >= size:
            return f"{s // size}{unit} ago"
    return "just now"


def stamp(t: dt.datetime | None) -> str:
    return t.strftime("%Y-%m-%d %H:%M UTC") if t else ""


TITLE = "Swarm dashboard"


def owner_line(m: dict) -> str:
    """The header's "Owner last acted" line (#402), on every page."""
    return activity.header(m.get("owner_last_acted"), m["now"], ago)


def rfc3339(t: dt.datetime) -> str:
    return t.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def render_crew(m: dict) -> str:
    """crew.html (#1113): one row per role, what each live session is doing, the sessions
    table, the Actions reviewer's sweeps, grants in use and Effort, all drawn client-side from
    state.json's plain fields and redrawn in place (crewpage.py, #1139)."""
    import state   # here, not at the top: state imports this module
    return crewpage.page(m, TITLE, owner_line(m), state.state(m))


def render_governance(m: dict) -> str:
    """governance.html (#1113): the full decision log, open and lapsed gov questions, the
    committees (open, then past), the authority map, precedent in use, and the trends, all
    drawn client-side from state.json's plain fields and redrawn in place (govpage.py, #1140)."""
    import state   # here, not at the top: state imports this module
    return govpage.page(m, TITLE, owner_line(m), state.state(m))


def render_workmap(m: dict) -> str:
    """workmap.html: the Work map, the live Desk's home (#1082)."""
    return workmap_page.page(m, TITLE, owner_line(m), committees.owner_login())


def render_effort(m: dict) -> str:
    """effort.html (#1013): the PRs behind each of Crew's Effort bar segments."""
    return layout.page(effort.FILE, TITLE, m["repo"], m["now"], effort.page_body(m.get("effort"), m["repo"]),
                       owner_line(m))   # no script: it shows the build it came with (#1135)


CREW_FILE = crewpage.FILE
GOVERNANCE_FILE = govpage.FILE

# Retired pages (#1113, and the Bridge #1114): each only sends the browser to its new home.
# The Work map is linked as workmap.html, not /: on Pages, / is index.html, so a redirect to /
# from index.html would loop, and a query on / would be lost in index.html's redirect.
REDIRECTS = {
    "index.html": ("workmap.html", "The desk moved", "The desk is now the Work map."),
    "commissions.html": ("workmap.html?group=goal", "Commissions moved",
                         "Goals and Areas are on the Work map: group by Goal and select one."),
    "agents.html": (CREW_FILE, "Agents moved", "The agents are on Crew."),
    "operations.html": (CREW_FILE, "Operations moved",
                        "Sessions and the Actions reviewer are on Crew; what needs you is on the Work map."),
    "decisions.html": (GOVERNANCE_FILE, "Decisions moved", "The decision log and committees are on Governance."),
    "authority.html": (GOVERNANCE_FILE + "#authority", "The authority map moved",
                       "The authority map is on Governance."),
    "bridge.html": ("./", "The Bridge moved", "The Bridge is now the Work map."),
}


def redirects() -> dict[str, str]:
    """Each retired page, by file name: a page that sends the browser to its new home."""
    return {f: layout.redirect(to, title, text) for f, (to, title, text) in REDIRECTS.items()}


def render(m: dict) -> dict[str, str]:
    """The three top-level pages, in nav order (layout.PAGES), then Effort's drill-down."""
    pages = {"workmap.html": render_workmap, CREW_FILE: render_crew, GOVERNANCE_FILE: render_governance,
             effort.FILE: render_effort}
    return {f: pages[f](m) for f in [*(f for f, _ in layout.PAGES), effort.FILE]}


# ---------------------------------------------------------------- CLI

def default_repo() -> str | None:
    try:
        url = subprocess.run(["git", "-C", str(HERE), "remote", "get-url", "origin"],
                             capture_output=True, text=True, timeout=5).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None
    m = REPO_RE.search(url)
    return m.group(1) if m else None


# ---------------------------------------------------------------- staying inside the rate limit (#392)

# What one run needs, with headroom. Against this repo on 2026-11-04 (#392's PR), a page
# rebuild made 23 REST calls and 19 GraphQL queries (before #392: 258 and 9), and the digest
# 5 and 8. The workflow token's allowance is 1,000 an hour of each, shared with the digest.
# precedent.py (#408) adds about 20 REST calls on a full read and 5 GraphQL queries, and the
# header's repo events (#402, activity.py) 1 to 3 REST calls. The desk's report panel (#712)
# adds 1 or 2 REST calls and its plan panel 3 or 4 GraphQL queries. Grants in use (#713,
# grants.py) adds 1 or 2, plus one per merged or closed PR the merger called in the last 24 hours.
# The trouble panel (#903, trouble.gather without the acts sync) adds about 10 to 15 REST calls
# (open issues, recent comments, the report issue's comments, other repos' Goals) and 15 to 25
# GraphQL queries (open and merged PRs, this week's merges, one scope query per 25 issues).
PAGE_NEEDS = {"core": 140, "graphql": 95}   # +5 for the Work map's PR search (#1081)
DIGEST_NEEDS = {"core": 30, "graphql": 30}
SPACING = dt.timedelta(minutes=5)       # a nudged rebuild waits this long after a published one
WORKFLOW = "dashboard.yml"
NUDGE_ACTOR = "github-actions[bot]"     # digest-nudge.yml's dispatches run as this actor


def low_allowance(needs: dict[str, int]) -> str | None:
    """Why there isn't enough rate-limit allowance left for a run, or None. `gh api rate_limit`
    doesn't count against the allowance. If it can't be read, the run goes ahead."""
    try:
        res = gh_json("api", "rate_limit")["resources"]   # type: ignore[index]
    except (RuntimeError, OSError, subprocess.SubprocessError, ValueError, KeyError, TypeError):
        return None
    for kind, need in needs.items():
        r = res.get(kind) or {}
        if isinstance(r.get("remaining"), int) and r["remaining"] < need:
            reset = dt.datetime.fromtimestamp(r.get("reset", 0), dt.timezone.utc)
            return (f"{kind} API allowance low ({r['remaining']} of {r.get('limit')} left, a run needs "
                    f"about {need}; resets {stamp(reset)})")
    return None


def nudged(env=None) -> bool:
    """A workflow_dispatch from digest-nudge.yml, not a person's dispatch or the schedule."""
    env = os.environ if env is None else env
    actor = env.get("GITHUB_TRIGGERING_ACTOR") or env.get("GITHUB_ACTOR")
    return env.get("GITHUB_EVENT_NAME") == "workflow_dispatch" and actor == NUDGE_ACTOR


PUBLISH_STEP = "deploy-pages"            # the step of a dashboard.yml run that publishes
LOOK_BACK = 5                           # successful runs checked for the last one that published


def last_published(repo: str) -> dt.datetime | None:
    """When dashboard.yml last published: the newest of the last LOOK_BACK successful runs whose
    deploy step succeeded. A run that skipped (spacing or allowance) also ends `success` once
    its upload and deploy steps are conditional, so a run's own status isn't enough. One call
    for the runs, then one jobs call per run until a published one; None if none of them did."""
    runs = gh_json("api", f"repos/{repo}/actions/workflows/{WORKFLOW}/runs?status=success&per_page={LOOK_BACK}")
    for run in runs["workflow_runs"][:LOOK_BACK]:   # type: ignore[index]
        jobs = gh_json("api", f"repos/{repo}/actions/runs/{run['id']}/jobs")
        for job in jobs["jobs"]:   # type: ignore[index]
            for step in job.get("steps") or []:
                if PUBLISH_STEP in (step.get("name") or "") and step.get("conclusion") == "success":
                    return parse_ts(step.get("completed_at") or run["updated_at"])
    return None


def too_soon(repo: str, now: dt.datetime) -> str | None:
    """Why a nudged rebuild should wait, or None: dashboard.yml last published less than
    SPACING ago. Measured from a published run, not a skipped one, so a stream of nudges can't
    keep restarting the wait. If the Actions API can't be read, the rebuild runs."""
    try:
        last = last_published(repo)
    except (RuntimeError, OSError, subprocess.SubprocessError, ValueError, KeyError, TypeError):
        return None
    if last and now - last < SPACING:
        return f"last published {ago(last, now)}; nudged rebuilds wait {SPACING.seconds // 60} minutes"
    return None


STATE_FILE = "state.json"   # the page's data, written beside it (state.py, #400)


def map_data(data: dict, model: dict, now: dt.datetime, days: int = DAYS,
             fetch_prs=None) -> dict:
    """The Work map's data (workmap.py, #1081): {"desk": map.json's dict} or {"error": why}.
    Cost per issue, which GOV-0049 lets both Desks publish, never a total (GOV-0033). It reuses
    this build's data and adds one PR search."""
    import workmap   # here, not at the top: workmap imports this module
    try:
        since = now - dt.timedelta(days=days)
        prs = (fetch_prs or workmap.fetch_prs)(data["repo"], since)
        g = {"data": data, "model": model, "prs": prs, "effort": data.get("effort"), "since": since}
        return {"desk": workmap.desk_file(g, now)}
    except (RuntimeError, OSError, subprocess.SubprocessError, ValueError) as e:
        return {"error": str(e) or type(e).__name__}


def save_map(wm: dict, out_dir: Path) -> str:
    """Write map_data()'s map.json beside the pages. If its read failed, none is written and the
    pages still are (the Work map page says why)."""
    import workmap
    if not wm.get("desk"):
        return f"generate.py: {workmap.FILE} not written: {wm.get('error')}"
    (out_dir / workmap.FILE).write_text(json.dumps(wm["desk"], indent=1) + "\n", encoding="utf-8")
    return f"wrote {workmap.FILE}"


def write_map(data: dict, model: dict, now: dt.datetime, out_dir: Path, days: int = DAYS,
              fetch_prs=None) -> str:
    """map_data() then save_map(): map.json beside the pages."""
    return save_map(map_data(data, model, now, days, fetch_prs), out_dir)


def scripts() -> dict[str, str]:
    """Every script a page loads, by its file name in js/: exactly the text each page hashes."""
    return {workmap_page.JS.name: workmap_page.script(),
            govpage.JS.name: govpage.script(), crewpage.JS.name: crewpage.script()}


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="Render the swarm dashboard's static HTML pages.")
    ap.add_argument("--repo", help="owner/name (default: this checkout's origin)")
    ap.add_argument("--out", default=str(HERE / "out" / "index.html"),
                    help="the desk page; the other pages and fonts/ go beside it")
    ap.add_argument("--days", type=int, default=DAYS, help="include sessions closed in the last N days")
    ap.add_argument("--idle-minutes", type=int, default=IDLE_MINUTES,
                    help="a live session is idle after this long without an event")
    ap.add_argument("--prev", help="carry precedent counts from this state.json, not the Pages "
                                   "copy (the hosted desk, #664)")
    args = ap.parse_args(argv)

    repo = args.repo or default_repo()
    if not repo:
        print("generate.py: can't tell the repo; pass --repo owner/name", file=sys.stderr)
        return 2
    try:   # #1107: every vendored library matches its pinned hash, or no page is written
        vendor = layout.vendored(reserved=scripts())
    except (OSError, ValueError) as e:
        print(f"generate.py: {e}", file=sys.stderr)
        return 1
    now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
    # Exit 0 without writing the page: the last good page stays up and the run isn't a failure.
    skip = (too_soon(repo, now) if nudged() else None) or low_allowance(PAGE_NEEDS)
    if skip:
        print(f"generate.py: skipped, not published: {skip}")
        return 0
    try:
        data = fetch(repo, now, args.days, with_actions=True,
                     with_committees=True, with_questions=True, with_precedent=True,
                     with_activity=True, with_grants=True, with_plan=True, with_trouble=True,
                     prev=Path(args.prev) if args.prev else None)
        data["records"] = precedent.load_records()
        data["effort"] = effort.load()   # #1013: a local file, no API call
    except (RuntimeError, OSError, subprocess.SubprocessError, ValueError) as e:
        print(f"generate.py: {e}", file=sys.stderr)
        return 1
    model = build(data, now, dt.timedelta(minutes=args.idle_minutes), caps=load_caps(),
                  window=args.days, watch_interval=load_watch_interval())
    import state   # here, not at the top: state imports this module
    data_json = json.dumps(state.state(model), indent=1) + "\n"
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    model["workmap"] = map_data(data, model, now, args.days)   # the Work map page carries it (#1082)
    pages = {**render(model), **redirects()}   # retired pages send old links on (#1113, #1114)
    layout.copy_fonts(out.parent)   # before the pages, so a published page never lacks them
    # likewise the scripts the pages load (#1106) and the vendored libraries, checked above (#1107)
    layout.write_scripts(out.parent, scripts() | vendor)
    for name, page in pages.items():
        (out if name == "index.html" else out.parent / name).write_text(page, encoding="utf-8")
    (out.parent / STATE_FILE).write_text(data_json, encoding="utf-8")   # #400
    print(save_map(model["workmap"], out.parent))
    live = sum(s["status"] != "stopped" for s in model["sessions"])
    others = ", ".join(n for n in pages if n != "index.html")
    print(f"wrote {out}, {others}, {STATE_FILE}, {layout.FONTS_DIR}/ and {layout.JS_DIR}/ beside it: "
          f"{live} live / {len(model['sessions'])} sessions, "
          f"{len(model['prs'])} open PRs, {len(model['gov'])} open gov questions")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
