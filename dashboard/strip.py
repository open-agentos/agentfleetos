"""The Work map's counts strip and tape (#1114, FEAT-12 under M9 #1080), which retired the Bridge.

The Bridge (bridge.py, #926) was a second home page once the Work map was at `/`. What it showed
now has a place on the Work map (workmap_page.py): the Briefing moved there (#1082), what waits on
the owner is the Needs you list and stuck items the Blocked list (#1084), and each Goal's criteria
show when it's selected (#1115). The rest is here, built from what the desk already reads, so it
costs no API calls of its own:

  - strip(): counts, carried in the page's data and state.json (no longer drawn on the page,
    at the owner's request): Goals and Areas flagged (something under it is stuck, a criterion fails or its date is missed), decisions
    waiting with the oldest one's age, agents working of the live sessions, and the authority
    used in `swarm trouble`'s window. Counts only, never money (GOV-0033).
  - decisions(): what waits on the owner, each issue or PR once, oldest first, as the Bridge
    listed it. Those the Needs you list doesn't already show join it.
  - tape(): at the foot of the page, newest first, at most MAX_TAPE: the daily report (flagged
    when it's late), items `swarm trouble` says are stuck, PRs a role's App merged in the last
    REPORT_DAYS days (SHIPPED, or DELIVERED for a title starting "Brief"), the owner's acts on
    GitHub (Orders received; branch creation and deletion left out) and today's governance
    events (the wire, wire.py). Each item has a time, a role or "owner", and a link, and is a
    template filled from fields, never a summary of anyone's text.

Stdlib only.
"""
from __future__ import annotations

import datetime as dt
import re

import activity
from layout import esc

REPORT_DAYS = 7          # merged PRs on the tape
MAX_TAPE = 20
GH_RE = re.compile(r"https://github\.com/[^\s\"'<>]*")
# Owner events that are acts, not noise: branch creation and deletion are left out.
ORDER_TYPES = ("IssuesEvent", "IssueCommentEvent", "PullRequestEvent", "PullRequestReviewEvent",
               "PullRequestReviewCommentEvent", "PushEvent")
# Two letters per role, for a badge; the lead (planner) is drawn solid.
BADGE = {"planner": "PL", "builder": "BU", "reviewer": "RV", "analyst": "AN", "designer": "DS",
         "merger": "MG", "watch": "WA"}
LEAD = "planner"
ROLE_RE = re.compile(r"(?:app/)?productswarm-([a-z0-9-]+?)(?:\[bot\])?")
# Who did a wire item: the owner rules, lapses, convenes and merges records; the reviewer
# requests changes. Who opened a question isn't in the wire's fields.
WIRE_WHO = {"ruled": "owner", "lapsed": "owner", "record": "owner", "convened": "owner", "red": "reviewer"}
WIRE_WORD = {"opened": "QUESTION", "ruled": "RULED", "lapsed": "LAPSED", "record": "RECORD",
             "red": "CHANGES", "convened": "COMMITTEE"}


# ---------------------------------------------------------------- helpers, from the Bridge

def _ts(s) -> dt.datetime | None:
    if isinstance(s, dt.datetime):
        return s
    try:
        t = dt.datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return t if t.tzinfo else t.replace(tzinfo=dt.timezone.utc)


def role_of(login: str | None) -> str | None:
    m = ROLE_RE.fullmatch(login or "")
    return m.group(1) if m else None


def scopes(trouble: dict | None) -> list[dict]:
    return [s for s in (trouble or {}).get("scopes") or [] if isinstance(s, dict)]


def flagged(s: dict) -> bool:
    return bool(s.get("stuck") or s.get("date_missed")
                or any(c.get("status") == "failing" for c in s.get("progress") or []))


def _short(ref: str | None) -> str:
    """"o/r#100" → "#100"."""
    return "#" + ref.rsplit("#", 1)[1] if ref and "#" in ref else (ref or "")


def lead(title: str | None) -> str:
    """"M3" from "M3: The Desk shows ..."."""
    m = re.match(r"^(\S{1,12}):\s", title or "")
    return m.group(1) if m else ""


def _num(ref: str | None) -> int | None:
    n = re.search(r"#(\d+)\b", ref or "")
    return int(n.group(1)) if n else None


def a(url: str | None, text_html: str) -> str:
    """A link only to github.com; otherwise just the text."""
    if url and GH_RE.fullmatch(url):
        return f'<a href="{esc(url)}">{text_html}</a>'
    return text_html


def when(t: dt.datetime | None, now: dt.datetime) -> str:
    """"14:12" today, "Wed 14:12" this week, else "11-03" (UTC)."""
    if t is None:
        return "?"
    t = t.astimezone(dt.timezone.utc)
    if t.date() == now.date():
        return t.strftime("%H:%M")
    if (now - t) < dt.timedelta(days=6):
        return t.strftime("%a %H:%M")
    return t.strftime("%m-%d")


def age(t: dt.datetime | None, now: dt.datetime) -> str:
    if t is None:
        return "age unknown"
    h = (now - t).total_seconds() / 3600
    return f"{h / 24:.0f}d" if h >= 48 else f"{max(h, 0):.0f}h"


def live_sessions(m: dict) -> list[dict]:
    return [s for s in m.get("sessions") or [] if s.get("status") != "stopped" and not s.get("never_acted")]


# ---------------------------------------------------------------- decisions waiting

def decisions(m: dict) -> list[dict]:
    """What waits on the owner, each issue or PR once, oldest first (asks with no age last):
    `swarm trouble`'s waiting items (each scope's, then those under none); open gov questions
    not ruled; sessions blocked on a question; PRs the merger left for the owner in its last
    24 hours of calls, or that GOV-0011 hands to the owner; and the asks in today's daily
    report. Each: scope, ref, url, title, why, since, ttl, and `issues`, the issue numbers it
    is about (a PR's are those it closes)."""
    repo = m["repo"]
    base = f"https://github.com/{repo}"
    prs = {p["number"]: p for p in m.get("prs") or []}
    titles = {**(m.get("issue_titles") or {}), **{n: p.get("title") for n, p in prs.items()}}
    out, seen = [], set()

    def add(n, d, pr=False):
        if n is not None and n in seen:
            return
        if n is not None:
            seen.add(n)
        closes = [c.get("number") for c in (prs.get(n) or {}).get("closes") or [] if c.get("number")]
        issues = closes if pr or n in prs else ([n] if n is not None else [])
        out.append({"ttl": None, "why": "", "issues": issues, **d})

    t = m.get("trouble") or {}
    for s in [*scopes(t), {"waiting": (t.get("outside") or {}).get("waiting") or []}]:
        for x in s.get("waiting") or []:
            if not isinstance(x, dict):
                continue
            # Another repo's PR (owner/name#N, #1292) isn't this repo's #N: no number, so no title
            n = None if "/" in str(x.get("ref") or "") else _num(x.get("ref"))
            title = titles.get(n) if n is not None else None
            add(n, {"scope": lead(s.get("title")) or _short(s.get("ref")) or "no Goal",
                    "ref": x.get("ref") or "", "url": x.get("url"),
                    "title": title or x.get("reason") or "", "why": x.get("reason") if title else "",
                    "since": _ts(x.get("since"))}, pr=x.get("kind") == "pr" or "PR" in (x.get("ref") or ""))
    drafts = {d["issue"]: d for d in (m.get("memory") or {}).get("drafts") or []
              if isinstance(d, dict) and isinstance(d.get("issue"), int)}
    for q in m.get("gov") or []:
        if q.get("waiting") or "gov:ruled" in (q.get("labels") or []):
            continue
        d = drafts.get(q["number"])   # Escalation's drafts are gov questions like any other (#1192)
        add(q["number"], {"scope": "gov question", "ref": f"#{q['number']}", "url": q.get("url"),
                          "title": q.get("title") or "", "since": _ts(q.get("created_ts")), "ttl": q.get("ttl"),
                          "why": f"drafted by the dream: {d.get('kind') or 'a pattern'}" if d else ""})
    for s in m.get("sessions") or []:
        if s.get("status") == "blocked" and not s.get("never_acted") and s.get("gov_question"):
            n = s["gov_question"]
            add(n, {"scope": "gov question", "ref": f"#{n}", "url": f"{base}/issues/{n}",
                    "title": titles.get(n) or "",
                    "why": f"{s.get('role')} session is blocked on it"
                           + (f" (working on #{s['issue']})" if s.get("issue") else ""),
                    "since": _ts(s.get("last_ts"))})
    for c in (m.get("grants") or {}).get("calls") or []:
        if c.get("group") == "left":
            n = c["number"]
            add(n, {"scope": "merger", "ref": f"PR #{n}", "url": c.get("link") or f"{base}/pull/{n}",
                    "title": c.get("title") or titles.get(n) or "", "why": f"left for you: {c.get('reason')}",
                    "since": _ts((prs.get(n) or {}).get("created_ts")) or _ts(c.get("time"))}, pr=True)
    for n, p in prs.items():
        if p.get("needs_owner"):
            add(n, {"scope": "review", "ref": f"PR #{n}", "url": p.get("url"), "title": p.get("title") or "",
                    "why": f"{p['needs_owner']} (GOV-0011)", "since": _ts(p.get("created_ts"))}, pr=True)
    rep = (m.get("report") or {}).get("report") or {}
    for x in rep.get("asks") or []:
        n = x.get("issue")
        add(n, {"scope": "daily report", "ref": f"#{n}" if n else "Ask",
                "url": f"{base}/issues/{n}" if n else rep.get("url"),
                "title": " ".join(y for y in (x.get("lead"), x.get("text")) if y).replace("**", ""),
                "why": "asked in today's daily report", "since": None})
    far = dt.datetime.max.replace(tzinfo=dt.timezone.utc)
    return sorted(out, key=lambda d: d["since"] or far)


def needs_extra(m: dict) -> list[dict]:
    """The decisions waiting, as the page's JSON block carries them for the Needs you list
    (#1114): each with the map refs it is about, so workmap.js shows only those the list's
    own rows don't already show, after them. Oldest first, as decisions() orders them."""
    now = m["now"]
    return [{"ref": d["ref"], "title": d["title"], "url": d["url"] if d["url"] and GH_RE.fullmatch(d["url"]) else None,
             "scope": d["scope"], "why": d["why"], "ttl": d["ttl"],
             "age": age(d["since"], now) if d["since"] else None,
             "refs": [f"#{n}" for n in d["issues"]]}
            for d in decisions(m)]


# ---------------------------------------------------------------- the strip

def strip(m: dict) -> dict:
    """The counts: open Goals and Areas and how many are flagged (with their numbers, for the
    map's outline), decisions waiting and the oldest one's age, agents working of the live
    sessions, and authority used in `swarm trouble`'s window. No amount (GOV-0033)."""
    t = m.get("trouble") or {}
    ss = scopes(t)
    ds = decisions(m)
    oldest = next((d["since"] for d in ds if d["since"]), None)
    return {"scopes": len(ss), "flagged": [n for s in ss if flagged(s) and (n := _num(s.get("ref")))],
            "decisions": len(ds), "oldest": age(oldest, m["now"]) if oldest else None,
            "decision_refs": sorted({f"#{n}" for d in ds for n in d["issues"]}, key=lambda r: int(r[1:])),
            "working": len((m.get("floor") or {}).get("cards") or []), "agents": len(live_sessions(m)),
            "authority": sum(len(s.get("authority") or []) for s in [*ss, t.get("outside") or {}]),
            "authority_hours": t.get("authority_hours") or 24, "error": t.get("error"),
            "memory": memory_counts(m.get("memory"))}


def memory_counts(mem: dict | None) -> dict | None:
    """Memory used against its budget and lessons dormant (#1192), as counts only (GOV-0033),
    from `swarm memory desk`'s counts: the fullest role's active lessons against the dream's
    per-role budget. None when the build didn't read memory; {"error": True} when it failed."""
    if not isinstance(mem, dict):
        return None
    if mem.get("error"):
        return {"error": True}
    c = mem.get("counts") or {}
    roles = c.get("roles") or {}
    role, used = max(roles.items(), key=lambda kv: (kv[1], kv[0]), default=(None, 0))
    return {"used": used, "role": role, "budget": c.get("budget"), "active": c.get("active") or 0,
            "dormant": c.get("dormant") or 0}


# ---------------------------------------------------------------- the tape

def _item(time, who, kind, text, url, ref=None, flag=False) -> dict:
    return {"time": time, "who": who, "kind": kind, "text": text, "url": url, "ref": ref, "flag": flag}


def orders(m: dict, owner: str | None) -> list[dict]:
    """The owner's acts on GitHub, newest first, branch creation and deletion left out."""
    out = []
    for e in (m.get("activity") or {}).get("events") or []:
        if e.get("type") not in ORDER_TYPES or not activity.by(e, owner) or activity.watcher_edit(e):
            continue
        t = activity.parse_ts(e.get("created_at"))
        if t is None:
            continue
        d = activity.describe(e, m["repo"])
        issue = d["ref"] if e.get("type") in ("IssuesEvent", "IssueCommentEvent") else None
        out.append(_item(t, "owner", "ORDER", d["text"], d["link"], issue))
    return sorted(out, key=lambda o: o["time"], reverse=True)


def tape(m: dict, owner: str | None) -> list[dict]:
    """The tape's items, newest first, at most MAX_TAPE. Each: time, who (a role or "owner"),
    kind (the word shown), text (a template from fields), url, ref (the issue it is about, as
    "#N", or None) and flag."""
    now, out = m["now"], []
    r = m.get("report") or {}
    if r.get("state") == "posted" and r.get("report"):
        rep = r["report"]
        n = len(rep.get("asks") or [])
        out.append(_item(_ts(rep.get("posted")), LEAD, "REPORT",
                         "Daily report posted: " + (f"{n} ask{'s' if n != 1 else ''} of you" if n else "no asks of you"),
                         rep.get("url")))
    elif r.get("state") == "late":
        due = f"{r['daily_at']:%H:%M}" if r.get("daily_at") else "its usual time"
        out.append(_item(now, LEAD, "LATE", f"No daily report yet today: it was due at {due}", None, flag=True))
    t = m.get("trouble") or {}
    for s in [*scopes(t), {"title": "", "ref": "", "stuck": (t.get("outside") or {}).get("stuck") or []}]:
        for x in s.get("stuck") or []:
            if isinstance(x, dict):
                where = lead(s.get("title")) or _short(s.get("ref")) or "no Goal"
                ref = x.get("ref") or ""
                issue = f"#{_num(ref)}" if _num(ref) and not ref.startswith("PR") and x.get("kind") != "pr" else None
                out.append(_item(_ts(x.get("since")), "watch", "STUCK", f"{ref} is stuck, under {where}",
                                 x.get("url"), issue, flag=True))
    since = now - dt.timedelta(days=REPORT_DAYS)
    for p in m.get("merged") or []:
        role, t_ = role_of(p.get("author")), _ts(p.get("merged_at"))
        if not role or not t_ or t_ < since:
            continue
        brief = (p.get("title") or "").lower().startswith("brief")
        out.append(_item(t_, role, "DELIVERED" if brief else "SHIPPED",
                         f"PR #{p.get('number')} merged: {p.get('title') or ''}", p.get("url")))
    out += orders(m, owner)
    for w in (m.get("wire") or {}).get("items") or []:
        n = w.get("number")
        out.append(_item(w.get("time"), WIRE_WHO.get(w.get("kind"), "gov"), WIRE_WORD.get(w.get("kind"), "GOV"),
                         w.get("text") or "", w.get("link"), f"#{n}" if n and w.get("kind") != "red" else None))
    epoch = dt.datetime.min.replace(tzinfo=dt.timezone.utc)
    return sorted(out, key=lambda x: x["time"] or epoch, reverse=True)[:MAX_TAPE]


def tape_html(items: list[dict], now: dt.datetime, on_map: set[str]) -> str:
    """The tape: a fixed-height box that scrolls inside itself. An item about an issue on the
    map picks it in the Selected panel (`data-wm-sel`); every item links to GitHub."""
    head = ('<div class="br-colh"><h2 class="br-h">Tape</h2>'
            '<span class="muted">reports, merges, your acts and governance, newest first</span></div>')
    if not items:
        return (f'<section class="tp" aria-label="Tape">{head}<div class="tp-box">'
                '<p class="muted tp-none">Nothing on the tape yet.</p></div></section>')
    rows = []
    for x in items:
        t = x["time"]
        stamp = (f'<time class="mono muted" datetime="{t.astimezone(dt.timezone.utc):%Y-%m-%dT%H:%M:%SZ}">'
                 f'{esc(when(t, now))}</time>' if t else '<span class="mono muted">?</span>')
        kind = f'<span class="tp-k{" sp-red" if x["flag"] else ""}">{esc(x["kind"])}</span>'
        who = f'<span class="tp-w">{esc(x["who"])}</span>'
        if x["ref"] and x["ref"] in on_map:
            text = (f'<button type="button" class="tp-t wm-pick" data-wm-sel="{esc(x["ref"])}" '
                    f'aria-controls="wm-sel" title="Show {esc(x["ref"])} in the Selected panel">{esc(x["text"])}</button>')
        else:
            text = f'<span class="tp-t">{esc(x["text"])}</span>'
        link = a(x["url"], "on GitHub") if x["url"] and GH_RE.fullmatch(x["url"]) else '<span class="muted">no link</span>'
        rows.append(f'<li class="tp-i"><span class="tp-m">{stamp}{who}{kind}</span>{text}'
                    f'<span class="tp-l">{link}</span></li>')
    return f'<section class="tp" aria-label="Tape">{head}<div class="tp-box"><ol class="tp-ol">{"".join(rows)}</ol></div></section>'
