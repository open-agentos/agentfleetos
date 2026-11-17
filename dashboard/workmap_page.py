"""The Work map page (#1082, FEAT-9 under M9 #1080): where the money goes and what it buys.

`workmap.html` is a squarified treemap of the Work map's data (workmap.py, #1081): one box per
issue, inside one box per group. Since #1082 it is the live Desk's home at `/` (launcher/desk.py);
the Bridge stays at bridge.html. Top to bottom, beside the shared left column (bridge.nav_html):

  - the title and one line saying what size, shade and the markers mean;
  - four controls, segmented buttons: Group by (Effort, Goal, Role, Stage), Size (Cost, Tokens,
    Lines changed), Colour (Yield, Velocity, Change) and Window (Hour, Day, Week, Month). The
    viewer's choices are kept in this browser's localStorage, if it has one;
  - the breadcrumb, the treemap, and the legend under it, beside the Selected panel (#1083):
    one issue's story at the map's height, its six sections each at a fixed height, filled by
    workmap.js from the selected box or from any element with `data-wm-ref` in the page;
  - the Briefing, moved from the Bridge (M8, #1069): the lead's newest briefing, whole;
  - the lists' space (their own features).

Per issue only: a box shows its own figures, and a group header its share of what's shown as a
percentage, never an amount. Nothing on the page sums an amount across issues (GOV-0033). Cost
per issue may be shown on both Desks (GOV-0049).

The map's rows are in the page itself, in a JSON block, so the page draws on GitHub Pages and the
live Desk alike without fetching. One script, `workmap.js`, draws it: generate.py writes it to
js/ beside the pages and the page's CSP allows it by its hash (#1106). It builds nodes with createElement and text nodes, never innerHTML or eval.
With JavaScript off the page says the map needs it, and the Briefing still shows. Each row's
14-day series is the same in every window, so the page carries it once per issue, under `days`:
`dates` (the 14 UTC days, oldest first) and `of` (ref -> [[cost, outcomes], ...]). The Selected
panel's 14-day figure is one issue's own sum, not a sum across issues, so GOV-0033 doesn't bar it.

The Desk reads 14 days of heartbeats, so map.json has the hour, day and week windows. Month
says so and points to `swarm map --window month`. Stdlib only.
"""
from __future__ import annotations

import json
from pathlib import Path

import bridge
import layout
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
KEY_LINE = ("Size is what each issue used in the window. Shade is the colour measure: darker is more. "
            "A folded corner: spend but no outcome. An amber outline: needs you. A red left edge: blocked.")


def script() -> str:
    """workmap.js, exactly as generate.py writes it to js/workmap.js."""
    return JS.read_text(encoding="utf-8")


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
    return {"built_at": desk.get("built_at"), "method": desk.get("method"),
            "windows": {w: [{k: v for k, v in r.items() if k != "days"} for r in rows]
                        for w, rows in windows.items()},
            "days": {"dates": dates, "of": of}}


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
    selecting or clearing changes no size or position anywhere."""
    seg = "".join(f'<span class="wm-sg"><span class="wm-sgbar"></span><span class="wm-sgl">{esc(n)}</span></span>'
                  for _, n in STAGES)
    bars = "".join('<span class="wm-bar"></span>' for _ in range(14))
    nums = "".join(f'<div class="wm-num"><dt>{esc(n)}</dt><dd data-n="{k}">–</dd></div>' for k, n in NUMBERS)
    return ('<aside class="wm-selected wm-sel-empty" id="wm-sel" aria-label="Selected" aria-live="polite">'
            '<div class="wm-ss wm-ss-head"><span class="br-kind">SELECTED</span><span class="mono" id="wm-sel-ref">–</span></div>'
            f'<div class="wm-ss wm-ss-title"><p class="wm-st" id="wm-sel-title">{esc(EMPTY)}</p>'
            '<p class="wm-sc muted" id="wm-sel-ctx">–</p></div>'
            '<div class="wm-ss wm-ss-stage"><p class="wm-sh"><span>Stage</span><span id="wm-sel-stage">–</span></p>'
            f'<div class="wm-sgs" id="wm-sel-sgs">{seg}</div></div>'
            '<div class="wm-ss wm-ss-days"><p class="wm-sh"><span>Cost, last 14 days</span><span class="mono" id="wm-sel-dsum">–</span></p>'
            f'<div class="wm-bars" id="wm-sel-bars">{bars}</div>'
            '<p class="wm-ax mono"><span>14d ago</span><span id="wm-sel-peak">–</span><span>today</span></p></div>'
            '<div class="wm-ss wm-ss-peers"><p class="wm-sh"><span>Yield against its group</span><span id="wm-sel-grp">–</span></p>'
            '<div class="wm-strip" id="wm-sel-strip"><span class="wm-line"></span></div>'
            '<p class="wm-ax mono" id="wm-sel-pax"><span>0</span><span>–</span><span>–</span></p></div>'
            f'<dl class="wm-ss wm-ss-nums" id="wm-sel-nums">{nums}</dl>'
            '</aside>')


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
            f'<span class="muted">from the lead · {bridge._a(br.get("url"), esc(stamp))}</span></div>'
            f'{old}<div class="br-briefbody">{body}</div></section>')


def render(m: dict) -> str:
    """The Work map's <main> content."""
    d = page_data(m.get("workmap"))
    method = (f'<p class="muted method">Cost: {esc(d["method"])}</p>' if d.get("method") else "")
    main = (f'<div class="br-main wm-main"><div class="br-titlebar"><h1>Work map</h1></div>'
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
            '<section class="wm-lists" aria-label="Lists"></section>'
            f'{method}{data_block(d)}</div>')
    return f'<div class="bridge">{bridge.nav_html(FILE, bridge.nav_counts(m))}{main}</div>'


def page(m: dict, title: str, owner_line: str) -> str:
    """workmap.html, in the shared page shell, with workmap.js as its one script."""
    return layout.page(FILE, title, m["repo"], m["now"], render(m), owner_line, script=(JS.name, script()))
