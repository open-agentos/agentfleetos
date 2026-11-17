"""The Work map page (#1082, FEAT-9 under M9 #1080): where the money goes and what it buys.

`workmap.html` is a squarified treemap of the Work map's data (workmap.py, #1081): one box per
issue, inside one box per group. Since #1082 it is the live Desk's home at `/` (launcher/desk.py);
it retired the Bridge (#1114). Top to bottom:

  - the title and one line saying what size, shade and the markers mean;
  - the counts strip (strip.py, #1114): Goals and Areas flagged, decisions waiting, agents
    working and authority used. Picking flagged or decisions waiting sets Group by to Goal and
    outlines the matching boxes;
  - four controls, segmented buttons: Group by (Effort, Goal, Role, Stage), Size (Cost, Tokens,
    Lines changed), Colour (Yield, Velocity, Change) and Window (Hour, Day, Week, Month). The
    viewer's choices are kept in this browser's localStorage, if it has one;
  - the breadcrumb, the treemap, and the legend under it, beside the Selected panel (#1083):
    one issue's story at the map's height, its six sections each at a fixed height, filled by
    workmap.js from the selected box or from any element with `data-wm-ref` in the page;
    since #1115 also a Goal, Area or role (the `scopes` and `roles` in the JSON block, from the
    Commissions and Agents drawers' builds), and the URL keeps the view and the selection;
  - the Briefing, moved from the Bridge (M8, #1069): the lead's newest briefing, whole;
  - six lists (#1084), two rows of three: Needs you, Blocked, Spend no outcome, Running hot,
    Gone quiet and Best yield. workmap.py's lists() picks and orders each window's matches for
    each size; workmap.js keeps those in the zoomed group, shows five and counts them all.
    Needs you also lists the decisions waiting its rows don't show (strip.needs_extra, #1114),
    after them, and scrolls inside its five rows' height;
  - the tape (strip.py, #1114): the Bridge's reports and Orders received, and the wire, newest
    first, in a fixed-height box that scrolls inside itself.

Per issue only: a box shows its own figures, and a group header its share of what's shown as a
percentage, never an amount. Nothing on the page sums an amount across issues (GOV-0033). Cost
per issue may be shown on both Desks (GOV-0049).

The map's rows are in the page itself, in a JSON block, so the page draws on GitHub Pages and the
live Desk alike as soon as it loads. Since #1138 workmap.js also fetches same-origin map.json
while the tab is visible and redraws in place from a newer build (GOV-0051). One script, `workmap.js`, draws it: generate.py writes it to
js/ beside the pages and the page's CSP allows it by its hash (#1106). It builds nodes with createElement and text nodes, never innerHTML or eval.
With JavaScript off the page says the map needs it, and the Briefing still shows. Each row's
14-day series is the same in every window, so the page carries it once per issue, under `days`:
`dates` (the 14 UTC days, oldest first) and `of` (ref -> [[cost, outcomes], ...]). The Selected
panel's 14-day figure is one issue's own sum, not a sum across issues, so GOV-0033 doesn't bar it.

The Desk reads 14 days of heartbeats, so map.json has the hour, day and week windows. Month
says so and points to `swarm map --window month`. Stdlib only.
"""
from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path

import agents
import commissions
import layout
import live
import strip
from layout import esc
from report import inline

FILE = "workmap.html"
JS = Path(__file__).resolve().parent / "workmap.js"
RAMP = ("#F3EFE7", "#E2D8C7", "#CBBBA2", "#AE987A", "#8A7458", "#64523E")
CONTROLS = (("group", "Group by", (("effort", "Effort"), ("goal", "Goal"), ("role", "Role"), ("stage", "Stage"))),
            ("size", "Size", (("cost", "Cost"), ("tokens", "Tokens"), ("lines", "Lines changed"))),
            ("colour", "Colour", (("yield", "Yield"), ("velocity", "Velocity"), ("change", "Change"))),
            ("window", "Window", (("hour", "Hour"), ("day", "Day"), ("week", "Week"), ("month", "Month"))))
DEFAULTS = {"group": "effort", "size": "cost", "colour": "yield", "window": "day"}
STAGES = (("queued", "Queued"), ("building", "Building"), ("review", "In review"), ("merging", "Merging"))
EMPTY = "Click a box, or an item in a list below, to see it here."
NUMBERS = (("cost", "Cost"), ("tokens", "Tokens"), ("lines", "Lines"), ("outcomes", "Outcomes"),
           ("yield", "Yield"), ("change", "Change against usual"))
LISTS = (   # (key, heading, one-line description, empty sentence), in reading order (#1084)
    ("needs", "Needs you", "Issues in the needs-you list, largest first, then other decisions waiting.", "Nothing here needs you."),
    ("blocked", "Blocked", "Blocked issues, largest first, with the stage each stopped in.", "Nothing here is blocked."),
    ("spend", "Spend, no outcome", "Size above zero in this window and no outcome, largest first.",
     "Everything here that used something has an outcome."),
    ("hot", "Running hot", "Cost at least 1.5× its usual, highest first.", "Nothing here is at 1.5× its usual or more."),
    ("quiet", "Gone quiet", "Cost under half its usual, or idle now after spend in the next longer window.",
     "Nothing here has gone quiet."),
    ("yield", "Best yield", "Outcomes for their size, highest first.", "Nothing here has an outcome and a size."),
)
KEY_LINE = ("Size is what each issue used in the window. Shade is the colour measure: darker is more. "
            "A folded corner: spend but no outcome. An amber outline: needs you. A red left edge: blocked.")


def script() -> str:
    """workmap.js, exactly as generate.py writes it to js/workmap.js."""
    return JS.read_text(encoding="utf-8")


def live_settings() -> dict:
    """How often an open map fetches map.json and when its LIVE mark greys, in ms: poll.js's
    (live.py), so every Desk page refreshes and goes stale alike (#1138)."""
    return {"every": live.EVERY_SECONDS * 1000, "stale": live.STALE_MINUTES * 60 * 1000}


def page_data(wm: dict | None) -> dict:
    """What the page's JSON block carries: map.json's windows, each row without its `days`, and
    each issue's 14 days once (they don't depend on the window), or the reason the map wasn't read."""
    wm = wm or {}
    desk = wm.get("desk")
    if not desk:
        return {"error": wm.get("error") or "no map data in this build"}
    windows = desk.get("windows") or {}
    dates, of = [], {}
    for rows in windows.values():
        for r in rows:
            ds = r.get("days") or []
            if r.get("ref") in of or not ds:
                continue
            dates = dates or [d.get("date") for d in ds]
            of[r["ref"]] = [[d.get("cost"), d.get("outcomes", 0)] for d in ds]
    import workmap   # here, not at the top: workmap imports generate, which imports this module
    return {"built_at": desk.get("built_at"), "method": desk.get("method"),
            "windows": {w: [{k: v for k, v in r.items() if k != "days"} for r in rows]
                        for w, rows in windows.items()},
            "days": {"dates": dates, "of": of},
            "lists": desk.get("lists") or workmap.desk_lists(windows)}


def _plain(text) -> str:
    """A line of report Markdown as text: the `code` and **bold** marks go."""
    return re.sub(r"\*\*|`", "", str(text or ""))


def _iso(t) -> str | None:
    if isinstance(t, dt.datetime):
        return t.isoformat(timespec="seconds")
    return t if isinstance(t, str) else None


def _items(xs: list[dict]) -> list[dict]:
    return [{"ref": x.get("ref") or "", "url": x.get("url"), "reason": _plain(x.get("reason")),
             "since": _iso(x.get("since"))} for x in xs or []]


def scope_data(m: dict) -> dict:
    """Each open Goal and Area the Selected panel can show (#1115), by number, from what the
    Commissions drawer showed (commissions.build): its done test, what's stuck, what waits on
    the owner, the authority used under it and its open sub-issues. No amount: the page works
    out each issue's share of the Goal from the map's rows, never a sum (GOV-0033)."""
    out = {}
    for r in commissions.build(m)["rows"]:
        if r["group"] == "delivered" or r["number"] is None:
            continue
        out[str(r["number"])] = {
            "number": r["number"], "type": r["type"] or "Goal", "lead": r["lead"], "title": r["title"],
            "url": r["url"], "date": r["date"], "date_missed": bool(r["date_missed"]),
            "criteria": [{"text": _plain(c.get("criterion")), "status": c.get("status"),
                          "detail": _plain(c.get("detail"))} for c in r["criteria"]],
            "met": r["met"], "stuck": _items(r["stuck"]), "waiting": _items(r["waiting"]),
            "authority": _items(r["authority"]),
            "subs": [{"number": x.get("number"), "ref": x.get("ref") or "", "title": x.get("title") or "",
                      "url": x.get("url"), "go": (x.get("status") or {}).get("kind") or "",
                      "status": _plain((x.get("status") or {}).get("text")),
                      "pr": ({"number": x["pr"].get("number"), "url": x["pr"].get("url")} if x.get("pr") else None)}
                     for x in r["subs"]]}
    return out


def _pr(p: dict) -> dict:
    return {"number": p.get("number"), "title": p.get("title") or "", "url": p.get("url"),
            "merged_at": _iso(p.get("merged_at"))}


def role_data(m: dict) -> dict:
    """Each role the Selected panel can show (#1115), by name, from what the Agents drawer
    showed (agents.build): what it does and is on now, its merged and open PRs and those with
    changes requested at head, its sessions (each one's start, so the page can count a window),
    the merger's calls on its PRs in the last 24 hours, and where to ask it something (GOV-0029)."""
    a = agents.build(m)
    sessions = [s for s in m.get("sessions") or [] if not s.get("never_acted")]
    out = {}
    for r in a["rows"]:
        out[r["role"]] = {
            "role": r["role"], "does": r["does"], "working": r["group"] == "working", "blocked": r["blocked"],
            "on": [{"ref": x["ref"], "title": x["title"], "url": x["url"], "status": x["status"]} for x in r["on"]],
            "merged": [_pr(p) for p in r["merged"]], "open": [_pr(p) for p in r["open"]],
            "changes": [_pr(p) for p in r["changes"]],
            "sessions": sorted(_iso(s.get("started_ts") or s.get("last_ts")) or "" for s in sessions
                               if s.get("role") == r["role"]),
            "calls": [{"number": c.get("number"), "url": c.get("link"), "group": c.get("group") or "",
                       "reason": _plain(c.get("reason"))} for c in r["authority"]],
            "last_ts": _iso(r["last_ts"]), "ask": r["ask"]}
    return {"days": a["days"], "report_issue": a["report_issue"], "of": out}


def data_block(d: dict) -> str:
    """The JSON block. `<`, `>` and `&` are escaped so no title can close the element."""
    text = (json.dumps(d, separators=(",", ":"))
            .replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026"))
    return f'<script type="application/json" id="wm-data">{text}</script>'


def controls_html() -> str:
    out = []
    for key, label, options in CONTROLS:
        buttons = "".join(
            f'<button type="button" data-k="{key}" data-v="{v}" '
            f'aria-pressed="{"true" if DEFAULTS[key] == v else "false"}" disabled>{esc(name)}</button>'
            for v, name in options)
        out.append(f'<div class="wm-ctl"><span class="br-kind">{esc(label.upper())}</span>'
                   f'<div class="wm-seg" role="group" aria-label="{esc(label)}">{buttons}</div></div>')
    return f'<div class="wm-ctls">{"".join(out)}</div>'


def selected_html() -> str:
    """The Selected panel (#1083) in its empty state: every section, at its fixed height, with
    placeholders. workmap.js fills the same nodes for a selected issue and empties them again, so
    selecting or clearing changes no size or position anywhere. A Goal, Area or role (#1115)
    shows in `wm-alt` in place of the issue's sections (`wm-ss-i`), inside the same fixed box,
    scrolling within it: the panel's size doesn't change with what's selected."""
    seg = "".join(f'<span class="wm-sg"><span class="wm-sgbar"></span><span class="wm-sgl">{esc(n)}</span></span>'
                  for _, n in STAGES)
    bars = "".join('<span class="wm-bar"></span>' for _ in range(14))
    nums = "".join(f'<div class="wm-num"><dt>{esc(n)}</dt><dd data-n="{k}">–</dd></div>' for k, n in NUMBERS)
    return ('<aside class="wm-selected wm-sel-empty" id="wm-sel" aria-label="Selected" aria-live="polite">'
            '<div class="wm-ss wm-ss-head"><span class="br-kind" id="wm-sel-kind">SELECTED</span><span class="mono" id="wm-sel-ref">–</span></div>'
            f'<div class="wm-ss wm-ss-title"><p class="wm-st" id="wm-sel-title">{esc(EMPTY)}</p>'
            '<p class="wm-sc muted" id="wm-sel-ctx">–</p></div>'
            '<div class="wm-ss wm-ss-i wm-ss-stage"><p class="wm-sh"><span>Stage</span><span id="wm-sel-stage">–</span></p>'
            f'<div class="wm-sgs" id="wm-sel-sgs">{seg}</div></div>'
            '<div class="wm-ss wm-ss-i wm-ss-deps"><p class="wm-dl"><span>Waits on</span><span id="wm-sel-by">–</span></p>'
            '<p class="wm-dl"><span>Holds up</span><span id="wm-sel-blocks">–</span></p></div>'
            '<div class="wm-ss wm-ss-i wm-ss-days"><p class="wm-sh"><span>Cost, last 14 days</span><span class="mono" id="wm-sel-dsum">–</span></p>'
            f'<div class="wm-bars" id="wm-sel-bars">{bars}</div>'
            '<p class="wm-ax mono"><span>14d ago</span><span id="wm-sel-peak">–</span><span>today</span></p></div>'
            '<div class="wm-ss wm-ss-i wm-ss-peers"><p class="wm-sh"><span>Yield against its group</span><span id="wm-sel-grp">–</span></p>'
            '<div class="wm-strip" id="wm-sel-strip"><span class="wm-line"></span></div>'
            '<p class="wm-ax mono" id="wm-sel-pax"><span>0</span><span>–</span><span>–</span></p></div>'
            f'<dl class="wm-ss wm-ss-i wm-ss-nums" id="wm-sel-nums">{nums}</dl>'
            '<div class="wm-ss wm-alt" id="wm-sel-alt"></div>'
            '</aside>')


def lists_html() -> str:
    """The six lists (#1084) in their empty state: each heading, its count, its line and a list
    at the height of five rows. workmap.js fills the counts and rows for the window, zoom and
    size; the heights are fixed, so nothing moves when it does."""
    out = []
    for key, name, line, empty in LISTS:
        out.append(f'<section class="wm-list" data-list="{key}" data-empty="{esc(empty)}" aria-label="{esc(name)}">'
                   f'<h3 class="wm-lh"><span>{esc(name.upper())}</span><span class="wm-lc">–</span></h3>'
                   f'<p class="wm-ld" title="{esc(line)}">{esc(line)}</p>'
                   '<ol class="wm-lol"></ol></section>')
    return f'<div class="wm-lists" id="wm-lists" aria-label="Lists">{"".join(out)}</div>'


def briefing_html(briefing: dict | None, now) -> str:
    """The lead's newest briefing, whole, moved from the Bridge (M8, #1069): one paragraph per
    chapter, a link to its comment, and a note when it's from before today."""
    br = briefing
    if not br:
        return ('<section class="br-brief wm-brief" aria-label="Briefing"><div class="br-colh">'
                '<h2 class="br-h">Briefing</h2></div>'
                '<p class="muted">No briefing from the lead in the last few days.</p></section>')
    today = now.astimezone(br["posted"].tzinfo).date() if br.get("posted") else None
    stamp = f'{br["day"]:%a %m-%d}' + (f', {br["posted"]:%H:%M}' if br.get("posted") else "")
    old = ('<p class="muted">None yet today; this is the newest.</p>'
           if today and br["day"] < today else "")
    body = "".join(f"<p>{inline(p)}</p>" for p in br.get("paras") or [])
    return ('<section class="br-brief wm-brief" aria-label="Briefing"><div class="br-colh">'
            '<h2 class="br-h">Briefing</h2>'
            f'<span class="muted">from the lead · {strip.a(br.get("url"), esc(stamp))}</span></div>'
            f'{old}<div class="br-briefbody">{body}</div></section>')


def render(m: dict, owner: str | None = None) -> str:
    """The Work map's <main> content."""
    pd = page_data(m.get("workmap"))
    on_map = {r.get("ref") for rows in (pd.get("windows") or {}).values() for r in rows if r.get("issue") is not None}
    sp = strip.strip(m)
    d = {**pd, "repo": m["repo"], "scopes": scope_data(m), "roles": role_data(m),
         "strip": {"flagged": sp["flagged"], "decisions": sp["decision_refs"]},
         "needs_extra": strip.needs_extra(m), "live": live_settings()}
    method = (f'<p class="muted method">Cost: {esc(d["method"])}</p>' if d.get("method") else "")
    return (f'<div class="br-main wm-main"><div class="br-titlebar"><h1>Work map</h1></div>'
            f'{strip.strip_html(sp)}'
            f'<p class="wm-keyline">{esc(KEY_LINE)}</p>'
            f'{controls_html()}'
            '<div class="wm-top"><section class="wm-mapcol" aria-label="Work map">'
            '<p class="wm-crumb" id="wm-crumb">All effort types</p>'
            '<div class="wm-frame"><div class="wm-map" id="wm-map"><p class="wm-empty muted" id="wm-nojs">'
            'The Work map is drawn by a script in the page; with JavaScript off it can\'t show.</p></div>'
            '<div class="wm-tip" id="wm-tip" role="tooltip" hidden></div></div>'
            '<div class="wm-legend" id="wm-legend"></div></section>'
            f'{selected_html()}</div>'
            f'{briefing_html((m.get("report") or {}).get("briefing"), m["now"])}'
            f'{lists_html()}'
            f'{strip.tape_html(strip.tape(m, owner), m["now"], on_map)}'
            f'{method}{data_block(d)}</div>')


def page(m: dict, title: str, owner_line: str, owner: str | None = None) -> str:
    """workmap.html, in the shared page shell, with workmap.js as its one script."""
    return layout.page(FILE, title, m["repo"], m["now"], render(m, owner), owner_line, script=(JS.name, script()))
