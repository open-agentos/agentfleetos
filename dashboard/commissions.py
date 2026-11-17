"""Each open Goal and Area the owner opened, as the Commissions page drew them (#931, under M3).

The page retired into the Work map (#1113): `commissions.html` sends the browser to the map
grouped by Goal, and selecting a Goal or Area there shows what its focus drawer did
(workmap_page.scope_data, #1115). build() stays as that view's source. It is built from the
model generate.build() already makes, so it costs no API calls of its own:

  - the trouble report (`swarm trouble`, #903): each scope's criteria, what's stuck, what
    waits on the owner and the authority used;
  - the plan (plan.py, #712): each scope's open sub-issues with their go status and PRs;
  - `closed_scopes`: the owner's Goals and Areas closed in the build's window.

Groups, in order, each scope in the first that fits: needs a look (flagged: something stuck, a
failing criterion or a missed date, strip.flagged), waits on you, running (Goals), keep it so
(Areas), then delivered this week (closed in the last DELIVERED_DAYS days).

No cost: GOV-0033 sets no engine total. Stdlib only.
"""
from __future__ import annotations

import datetime as dt
import re

import strip

DELIVERED_DAYS = 7
GROUPS = (("look", "Needs a look"), ("waiting", "Waits on you"), ("running", "Running"),
          ("keep", "Keep it so"), ("delivered", "Delivered this week"))


def _num(ref) -> int | None:
    m = re.search(r"#(\d+)$", str(ref or ""))
    return int(m.group(1)) if m else None


def group(s: dict) -> str:
    if strip.flagged(s):
        return "look"
    if s.get("waiting"):
        return "waiting"
    return "keep" if s.get("type") == "Area" else "running"


def build(m: dict) -> dict:
    """{"now", "repo", "error", "rows": [...]}: one row per scope, in group order."""
    now = m["now"]
    t = m.get("trouble") or {}
    plan = {s["number"]: s for s in (m.get("plan") or {}).get("scopes") or []}
    rows = []
    for s in strip.scopes(t):
        n = _num(s.get("ref"))
        crit = s.get("progress") or []
        p = plan.get(n) or {}
        rows.append({"number": n, "group": group(s), "type": s.get("type") or "",
                     "lead": strip.lead(s.get("title")), "title": re.sub(r"^\S{1,12}:\s+", "", s.get("title") or ""),
                     "url": s.get("url"), "date": s.get("date"), "date_missed": s.get("date_missed"),
                     "criteria": crit, "met": sum(c.get("status") == "met" for c in crit),
                     "stuck": s.get("stuck") or [], "waiting": s.get("waiting") or [],
                     "authority": s.get("authority") or [],
                     "open": p.get("open"), "done": p.get("done"), "subs": p.get("subs") or []})
    if not rows and t.get("scopes") is None:   # the trouble report wasn't read: the plan alone
        for n, p in plan.items():
            rows.append({"number": n, "group": "keep" if p.get("kind") == "Area" else "running",
                         "type": p.get("kind") or "", "lead": p.get("lead") or "", "title": p.get("title") or "",
                         "url": p.get("url"), "date": None, "date_missed": False, "criteria": [], "met": 0,
                         "stuck": [], "waiting": [], "authority": [], "open": p.get("open"),
                         "done": p.get("done"), "subs": p.get("subs") or []})
    since = now - dt.timedelta(days=DELIVERED_DAYS)
    for c in m.get("closed_scopes") or []:
        closed = strip._ts(c.get("closed_at"))
        if closed and closed >= since:
            rows.append({"number": c["number"], "group": "delivered", "type": c.get("type") or "",
                         "lead": strip.lead(c.get("title")),
                         "title": re.sub(r"^\S{1,12}:\s+", "", c.get("title") or ""), "url": c.get("url"),
                         "closed": closed, "date": None, "date_missed": False, "criteria": [], "met": 0,
                         "stuck": [], "waiting": [], "authority": [], "open": None, "done": None, "subs": []})
    order = [g for g, _ in GROUPS]
    rows.sort(key=lambda r: (order.index(r["group"]), r["type"] != "Goal", r["number"] or 0))
    return {"now": now, "repo": m["repo"], "error": t.get("error"), "rows": rows}
