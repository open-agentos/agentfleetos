"""The top of Crew (#1261): the work in progress, laid out by stage, and what's stuck.

`state(m, tape)` is state.json's `crew_work`, which crew.js draws in `#floor`. Each card's lane
is decided here, once, so the page only draws, as the rest of Crew does.

**Lanes**, the Work map's stage names (workmap.STAGES): Queued, Building, In review, Merging and
Merged · 24h. The open issues are the Work map's day-window rows (map.json's, `m["workmap"]`),
each issue a live session is on, and each issue an open PR closes. Each one's stage is its map
row's `stage`; an issue with no row (built after the map's plan read, say) gets
workmap.stage() from its open PRs and sessions, with no go kind. So a session on an issue
puts it in Building at least, and a non-draft open PR that closes it moves it to In review
(merging once the reviewer approved at head), as the Work map decides. A blocked issue goes
to Blocked and held, not a lane. The Merged lane is the PRs merged in the last 24 hours (the
tape's `SHIPPED`, from `m["merged"]`) and the merger's `merged` calls in the same 24 hours,
one card per PR.

A card in a lane: issue, title, link, role and its badge, the Goal's lead (M10), the open PR
that closes it (a ready one before a draft), the session on it (active first, then blocked,
then idle) with its run or idle time and, while it runs, its events per 5-minute slot and
plain words (floor.py's `activity`) from the floor, and whether it needs the owner: an open PR that closes it needs the owner under
GOV-0011 (generate.needs_owner()) or the merger left it for the owner. (The Work map's marker
also counts every ready PR, which here would mark all of In review.) No
cost: crew.js shows the card's session's own estimate from state.json's `sessions` (GOV-0057),
never a figure for the issue (GOV-0049 covers the Work map only) and never a total (GOV-0033).
Working cards come first in a lane, then needs-you cards, then the newest issue; a lane carries
LANE_MAX cards and how many more there are.

**Panels.** Needs you: the merger's calls left for the owner, newest first (grants.py), NEEDS_MAX
of them and how many more. Blocked and held: blocked issues with what they wait on, then the
watcher's held and skipped items, one row per ref (an issue both blocked and held is one row,
blocked). Failed runs: the watcher's failed list. Recent activity: the tape's newest
ACTIVITY_MAX items. `counts` are the five numbers above the lanes: sessions working now, cards in
the four open lanes, rows in Blocked and held, calls in Needs you, and cards in Merged · 24h.
"""
from __future__ import annotations

import datetime as dt

import generate
import strip
import workmap

LANES = (("queued", "Queued"), ("building", "Building"), ("review", "In review"),
         ("merging", "Merging"), ("merged", "Merged · 24h"))
LANE_MAX = 6
NEEDS_MAX = 7
ACTIVITY_MAX = 8
MERGED_HOURS = 24
FAILED_WORDS = {"no_result": "NO RESULT", "error": "ERR", "at_cap": "AT CAP", "limited": "LIMIT"}
SESSION_ORDER = {"active": 0, "blocked": 1, "idle": 2}


def _ts(v) -> dt.datetime | None:
    if isinstance(v, dt.datetime):
        return v
    try:
        return generate.parse_ts(v) if v else None
    except (TypeError, ValueError):
        return None


def badge(role: str | None) -> str:
    return strip.BADGE.get(role or "", (role or "?")[:2].upper())


def map_rows(m: dict) -> dict[int, dict]:
    """The Work map's day-window rows by issue, or none if the map wasn't read."""
    rows = ((((m.get("workmap") or {}).get("desk") or {}).get("windows") or {}).get("day")) or []
    return {r["issue"]: r for r in rows if isinstance(r.get("issue"), int)}


def _live(m: dict) -> list[dict]:
    return [s for s in m["sessions"] if s["status"] in SESSION_ORDER and not s.get("never_acted")]


def _pr_of(prs: list[dict]) -> dict | None:
    """The open PR a card shows: a ready one before a draft, then the newest."""
    if not prs:
        return None
    p = sorted(prs, key=lambda p: (bool(p.get("draft")), -p["number"]))[0]
    return {"number": p["number"], "draft": bool(p.get("draft"))}


def open_cards(m: dict) -> tuple[list[dict], list[dict]]:
    """(cards in the four open lanes, blocked issues), as module doc."""
    rows = map_rows(m)
    titles = m.get("issue_titles") or {}
    live = _live(m)
    on: dict[int, list[dict]] = {}
    for s in live:
        if s.get("issue"):
            on.setdefault(s["issue"], []).append(s)
    prs_of: dict[int, list[dict]] = {}
    for p in m["prs"]:
        for c in p.get("closes") or []:
            prs_of.setdefault(c["number"], []).append(p)
    left = {x.get("number") for x in ((m.get("grants") or {}).get("calls") or []) if x.get("group") == "left"}
    needs = {c["number"] for p in m["prs"] if p.get("needs_owner") or p["number"] in left
             for c in p.get("closes") or []}
    floor_cards = {c["session_id"]: c for c in (m.get("floor") or {}).get("cards") or []}
    idle = {i["session_id"]: i.get("idle_minutes") for i in (m.get("floor") or {}).get("idle") or []}
    repo = m["repo"]

    cards, blocked = [], []
    for n in sorted({n for n, r in rows.items() if r.get("state") == "open"} | set(on) | set(prs_of)):
        r = rows.get(n)
        ss = sorted(on.get(n, []), key=lambda s: SESSION_ORDER[s["status"]])
        if r is not None and r.get("state") == "open":
            lane = r.get("stage")
        else:
            lane = workmap.stage(None, prs_of.get(n, []), bool(ss), any(s["status"] == "blocked" for s in ss))
        if lane is None:
            continue
        s = ss[0] if ss else None
        goal = (r or {}).get("goal") or {}
        base = {"issue": n, "ref": f"#{n}", "title": (r or {}).get("title") or titles.get(n) or "",
                "url": (r or {}).get("url") or f"https://github.com/{repo}/issues/{n}"}
        if lane == "blocked":
            why = [f"waits on #{b}" for b in (r or {}).get("blocked_by") or []]
            q = next((x.get("gov_question") for x in ss if x["status"] == "blocked" and x.get("gov_question")), None)
            if q:
                why.append(f"on gov question #{q}")
            blocked.append({**base, "kind": "blocked", "why": why or ["blocked"]})
            continue
        role = (s or {}).get("role") or (r or {}).get("role")
        card = {**base, "lane": lane, "role": role, "badge": badge(role) if role else None,
                "lead": goal.get("lead") or None, "pr": _pr_of(prs_of.get(n, [])),
                "needs_you": n in needs, "session": None}
        if s is not None:
            fc = floor_cards.get(s["session_id"]) or {}
            card["session"] = {"session_id": s["session_id"], "status": s["status"],
                               "run_minutes": fc.get("run_minutes"),
                               "idle_minutes": idle.get(s["session_id"]),
                               "events_per_slot": fc.get("events_per_slot") if s["status"] == "active" else None,
                               "activity": fc.get("activity")}
        card["working"] = bool(s and s["status"] == "active")
        cards.append(card)
    return cards, blocked


def merged_cards(m: dict) -> list[dict]:
    """Merged · 24h: merged PRs and the merger's merged calls, one per PR, newest first."""
    since = m["now"] - dt.timedelta(hours=MERGED_HOURS)
    by: dict[int, dict] = {}
    for p in m.get("merged") or []:
        t = _ts(p.get("merged_at"))
        if not t or t < since or not isinstance(p.get("number"), int):
            continue
        role = strip.role_of(p.get("author"))
        by[p["number"]] = {"pr": p["number"], "title": p.get("title") or "", "url": p.get("url"),
                           "role": role, "badge": badge(role) if role else None, "time": t}
    for x in ((m.get("grants") or {}).get("calls") or []):
        t = _ts(x.get("time"))
        if x.get("group") != "merged" or not t or t < since or not isinstance(x.get("number"), int):
            continue
        if x["number"] not in by:
            by[x["number"]] = {"pr": x["number"], "title": x.get("title") or "", "url": x.get("link"),
                               "role": "merger", "badge": badge("merger"), "time": t}
    return sorted(by.values(), key=lambda c: (c["time"], c["pr"]), reverse=True)


def held(m: dict, blocked: list[dict]) -> list[dict]:
    """Blocked and held: the blocked issues, then the watcher's held and skipped, one row per ref."""
    rows = {b["ref"]: b for b in blocked}
    titles = m.get("issue_titles") or {}
    repo = m["repo"]
    w = m.get("watcher") or {}
    for kind in ("held", "skipped"):
        for x in (w.get(kind) or []) if w.get("status") == "ok" else []:
            ref = x.get("ref") or ""
            reason = x.get("reason") or ""
            why = reason.split(": ", 1)[1] if ": " in reason else (reason or x.get("code") or kind)
            if ref in rows:
                if why not in rows[ref]["why"]:
                    rows[ref]["why"].append(why)
                continue
            n = int(ref.rsplit("#", 1)[1]) if "#" in ref and ref.rsplit("#", 1)[1].isdigit() else None
            pr = ref.startswith("PR ")
            rows[ref] = {"issue": None if pr else n, "ref": ref,
                         "title": "" if pr else titles.get(n) or "",
                         "url": f"https://github.com/{repo}/{'pull' if pr else 'issues'}/{n}" if n else None,
                         "kind": kind, "why": [why]}
    return list(rows.values())


def failed(m: dict) -> list[dict]:
    w = m.get("watcher") or {}
    if w.get("status") != "ok":
        return []
    return [{"ref": f.get("ref"), "kind": f.get("kind"), "ending": f.get("ending"),
             "word": FAILED_WORDS.get(f.get("ending"), "ERR"), "ended": f.get("ended")}
            for f in w.get("failed") or []]


def needs(m: dict) -> list[dict]:
    """The merger's calls left for the owner, newest first."""
    calls = [x for x in ((m.get("grants") or {}).get("calls") or []) if x.get("group") == "left"]
    calls.sort(key=lambda x: _ts(x.get("time")) or dt.datetime.min.replace(tzinfo=dt.timezone.utc), reverse=True)
    return [{k: x.get(k) for k in ("number", "title", "reason", "time", "link")} for x in calls]


def _order(c: dict) -> tuple:
    return (not c["working"], not c["needs_you"], -c["issue"])


def state(m: dict, tape: list[dict] | None = None) -> dict:
    """state.json's `crew_work`."""
    cards, blocked = open_cards(m)
    merged = merged_cards(m)
    lanes = []
    for key, name in LANES:
        mine = merged if key == "merged" else sorted((c for c in cards if c["lane"] == key), key=_order)
        lanes.append({"key": key, "name": name, "cards": mine[:LANE_MAX], "more": max(0, len(mine) - LANE_MAX)})
    stuck = held(m, blocked)
    asks = needs(m)
    return {
        "counts": {"working": sum(s["status"] == "active" for s in _live(m)), "in_progress": len(cards),
                   "blocked": len(stuck), "needs_you": len(asks), "merged": len(merged)},
        "lanes": lanes,
        "needs": asks[:NEEDS_MAX], "needs_more": max(0, len(asks) - NEEDS_MAX),
        "blocked": stuck,
        "failed": failed(m),
        "activity": (tape or [])[:ACTIVITY_MAX],
    }
