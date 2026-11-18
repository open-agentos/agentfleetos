"""The crew: one row per role (#932, under M3; on Crew since #1113), read-only.

Crew (`crew.html`) opens with one row per role (the files in roles/, plus the merger App),
drawn by crew.js from state()'s plain fields (#1139). Each links to that role's view in the
Work map's Selected panel (#1115), which shows what the Agents page's focus drawer did;
`agents.html` sends the browser to Crew. build() is the
source of both, and costs no API calls of its own:

  - sessions (tracking issues and their heartbeat events): who is working, on what, and how
    many sessions each role ran in the build's window;
  - `merged`: PRs a role's App had merged in the window; `prs`: its open PRs, and whether the
    reviewer's latest review at head requested changes;
  - grants: the merger's calls in the last 24 hours, counted for the role whose PR it was.

Groups: working (a live session that is active or blocked; for the merger, a call in the
last 24 hours), then idle. To ask a role something, the owner comments `Ask: <role>: ...` on
the report issue (GOV-0029); the role view says so and links there.

No spend, caps or cost per result (GOV-0033), and no first-pass review rate or reverts: the
build doesn't read merged PRs' reviews. Stdlib only.
"""
from __future__ import annotations

import datetime as dt

import strip

# Where a role's row goes: its role view in the Work map's Selected panel (#1115). workmap.html,
# not /, so the query survives on Pages, where / is index.html's redirect.
MAP_ROLE = "workmap.html?group=role#role-{role}"
# (role, what it does), in the order the page lists them.
ROLES = (("planner", "Runs the plan and writes your daily report"),
         ("builder", "Builds and ships code"),
         ("reviewer", "Reviews every PR against its rubric"),
         ("analyst", "Research and briefs"),
         ("designer", "Specs, and how the product reads to you"),
         ("docs", "Records, rulings and docs"),
         ("merger", "Merges under your standing grant (GOV-0027)"))
CHANGES = "CHANGES_REQUESTED"


def build(m: dict) -> dict:
    now, repo = m["now"], m["repo"]
    titles = m.get("issue_titles") or {}
    prs = m.get("prs") or []
    days = m.get("days") or 14
    since = now - dt.timedelta(days=days)
    merged = sorted((p for p in m.get("merged") or [] if strip.role_of(p.get("author"))
                     and (strip._ts(p.get("merged_at")) or since) >= since),
                    key=lambda p: p.get("merged_at") or "", reverse=True)
    author = {p["number"]: strip.role_of(p.get("author")) for p in merged}
    author.update({p["number"]: strip.role_of(p.get("author")) for p in prs})
    calls = (m.get("grants") or {}).get("calls") or []
    sessions = [s for s in m.get("sessions") or [] if not s.get("never_acted")]
    report_issue = (m.get("report") or {}).get("issue")
    rows = []
    for role, does in ROLES:
        mine = [s for s in sessions if s.get("role") == role]
        live = [s for s in mine if s.get("status") in ("active", "blocked")]
        on = []
        for s in live:
            n = s.get("pr") or s.get("issue")
            if n:
                on.append({"ref": f"PR #{n}" if s.get("pr") else f"#{n}", "title": titles.get(n) or "",
                           "url": f"https://github.com/{repo}/{'pull' if s.get('pr') else 'issues'}/{n}",
                           "status": s.get("status")})
        used = [c for c in calls if (role == "merger" or author.get(c.get("number")) == role)]
        open_prs = [p for p in prs if strip.role_of(p.get("author")) == role]
        working = bool(live) or (role == "merger" and bool(used))
        rows.append({
            "role": role, "does": does, "group": "working" if working else "idle",
            "blocked": any(s.get("status") == "blocked" for s in live), "on": on,
            "merged": [p for p in merged if strip.role_of(p.get("author")) == role],
            "open": open_prs,
            "changes": [p for p in open_prs if (p.get("reviewer") or {}).get("at_head") == CHANGES],
            "sessions": len(mine), "authority": used,
            "last_ts": max((s["last_ts"] for s in mine if s.get("last_ts")), default=None),
            "ask": role != "merger"})
    rows.sort(key=lambda r: r["group"] != "working")
    return {"now": now, "repo": repo, "days": days, "rows": rows,
            "report_issue": report_issue}


# ---------------------------------------------------------------- Crew's rows (#1139)

def _line(r: dict, now: dt.datetime) -> str:
    """The row's second line, as plain text: no links, since the whole row is one."""
    if r["on"]:
        x = r["on"][0]
        verb = "Blocked on" if x["status"] == "blocked" else "On"
        more = f' and {len(r["on"]) - 1} more' if len(r["on"]) > 1 else ""
        return f'{verb} {x["ref"]}' + (f' {x["title"]}' if x["title"] else "") + more
    if r["role"] == "merger" and r["authority"]:
        return f'{len(r["authority"])} call{"s" if len(r["authority"]) != 1 else ""} in the last 24 hours'
    if r["merged"]:
        p = r["merged"][0]
        return f'Last: {p.get("title") or ""}, merged {strip.when(strip._ts(p.get("merged_at")), now)}'
    return "Nothing merged in the window."


def _count(r: dict) -> str:
    """The row's number: merged PRs by its App, or for the merger its calls in the last day."""
    if r["role"] == "merger":
        return f'{len(r["authority"])} calls'
    return f'{len(r["merged"])} merged'


def state(m: dict) -> list[dict]:
    """state.json's `crew_roles` (#1139): Crew's rows as plain fields, working first, for
    crew.js to draw. Each opens its role view on the Work map (MAP_ROLE), the view the Agents
    drawer became (#1115)."""
    b = build(m)
    return [{"role": r["role"], "does": r["does"], "group": r["group"], "lead": r["role"] == strip.LEAD,
             "badge": strip.BADGE.get(r["role"], r["role"][:2].upper()), "line": _line(r, b["now"]),
             "count": _count(r), "href": MAP_ROLE.format(role=r["role"])} for r in b["rows"]]
