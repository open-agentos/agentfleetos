"""The dashboard's look and page shell (#401, part 2 of #397).

Colours, fonts and the HTML around every page live here, so the Work map, Crew and
Governance pages can't drift apart. Fonts are IBM Plex (SIL Open Font License, see
static/fonts/LICENSE.txt), self-hosted: generate.py copies them beside the pages, so the
public page loads nothing from a third party. Only the Latin-1 subset of the four faces the
CSS uses is shipped; other characters (arrows, for one) fall back to the system font.

Stdlib only. Every page carries a Content-Security-Policy. Three pages load a script, each a
same-origin file in js/ beside the pages (#1106, option 3 of #1102) that the CSP allows by its
hash and the <script> tag pins with the same hash as its integrity: Crew's (crew.js, #1139),
Governance's (governance.js, #1140) and the Work map's (workmap.js, #1082). Each draws its page
and refreshes it in place from same-origin JSON (GOV-0051).

Third-party libraries (#1107, GOV-0051) are vendored in static/vendor/, each pinned in
static/vendor/manifest.json with its sha256. vendored() checks every file against its entry
before generate.py writes any page; they are then served from js/ like the Desk's own scripts,
and a page that loads one (page(libs=...)) names its hash in the CSP and the tag's integrity.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import html
import json
import re
import shutil
from pathlib import Path

import live

FONTS_SRC = Path(__file__).resolve().parent / "static" / "fonts"
FONTS_DIR = "fonts"          # beside the pages, so the pages link fonts/<file>
JS_DIR = "js"                # beside the pages, so the pages load js/<file> (#1106)
SCRIPT_NAME = re.compile(r"[a-z][a-z0-9_-]*\.js")
VENDOR_SRC = Path(__file__).resolve().parent / "static" / "vendor"   # pinned libraries (#1107)
VENDOR_MANIFEST = "manifest.json"
VENDOR_FIELDS = ("file", "library", "version", "licence", "source", "sha256")
EXACT_VERSION = re.compile(r"\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?")   # 7.9.0, never ^7 or 7.x
SHA256_HEX = re.compile(r"[0-9a-f]{64}")
# (family, weight, file). Only the faces the CSS below uses.
FONTS = (
    ("IBM Plex Sans", 400, "IBMPlexSans-Regular-Latin1.woff2"),
    ("IBM Plex Sans", 600, "IBMPlexSans-SemiBold-Latin1.woff2"),
    ("IBM Plex Mono", 400, "IBMPlexMono-Regular-Latin1.woff2"),
    ("IBM Plex Sans Condensed", 600, "IBMPlexSansCondensed-SemiBold-Latin1.woff2"),
)
FONT_FILES = tuple(f for _, _, f in FONTS) + ("LICENSE.txt",)
# The Latin-1 subset's range, from IBM's split CSS (@ibm/plex-sans fonts/split/woff2).
LATIN1 = ("U+0000, U+000D, U+0020-007E, U+00A0-00FF, U+0131, U+0152-0153, U+02C6, U+02DA, "
          "U+02DC, U+2013-2014, U+2018-201A, U+201C-201E, U+2020-2022, U+2026, U+2030, "
          "U+2039-203A, U+2044, U+20AC, U+2122, U+2212, U+FB01-FB02")

# The three top-level pages, in nav order: (file, name). One nav on every page (#1113).
PAGES = (("workmap.html", "Map"), ("crew.html", "Crew"), ("governance.html", "Governance"))
# Every page the shell draws, by file: the three, and Effort's drill-down from Crew's Effort panel.
NAMES = dict(PAGES) | {"effort.html": "Effort"}

# #397's palette: paper, ink, agents blue, owner amber, and red for live marks and blocks only.
PALETTE = {"paper": "#F4F3EE", "ink": "#1B1B18", "muted": "#66655E", "line": "#D8D6CC",
           "card": "#FBFAF6", "agent": "#1F4FB8", "owner": "#A35A00", "red": "#C2361B",
           "quiet": "#8B8A82"}

FONT_FACES = "\n".join(
    f'@font-face {{ font-family:"{fam}"; font-style:normal; font-weight:{w}; font-display:swap;'
    f' src:url("{FONTS_DIR}/{f}") format("woff2"); unicode-range:{LATIN1}; }}'
    for fam, w, f in FONTS)

CSS = FONT_FACES + "\n:root { " + " ".join(f"--{k}:{v};" for k, v in PALETTE.items()) + """
  --sans:"IBM Plex Sans", system-ui, -apple-system, "Segoe UI", Helvetica, Arial, sans-serif;
  --cond:"IBM Plex Sans Condensed", "IBM Plex Sans", "Arial Narrow", sans-serif;
  --mono:"IBM Plex Mono", ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; }
* { box-sizing:border-box; }
html { background:var(--paper); }
body { margin:0; padding:20px 16px 32px; background:var(--paper); color:var(--ink);
  font:15px/1.5 var(--sans); }
main, header.mast { max-width:1100px; margin:0 auto; }
main { overflow-wrap:anywhere; }
header.mast { display:flex; flex-wrap:wrap; align-items:baseline; gap:4px 16px;
  border-bottom:2px solid var(--ink); padding-bottom:6px; margin-bottom:8px; }
header.mast > span, header.mast .bits > span { min-width:0; overflow-wrap:anywhere; }
header.mast .bits { display:contents; }
header.mast .name { font:600 13px/1 var(--cond); letter-spacing:.08em; text-transform:uppercase; }
header.mast .live { background:var(--red); color:#fff; padding:0 8px; font:600 12px/1.6 var(--cond);
  letter-spacing:.1em; }
header.mast .owner { color:var(--owner); }
header.mast .owner a { color:var(--owner); text-decoration-color:var(--owner); }
h1 { font:600 26px/1.15 var(--cond); margin:12px 0 4px; letter-spacing:.01em; }
h2 { font:600 18px/1.2 var(--cond); margin:32px 0 8px; padding-top:6px;
  border-top:1px solid var(--line); text-transform:uppercase; letter-spacing:.05em; }
h3 { font:600 15px/1.3 var(--sans); margin:18px 0 6px; }
a { color:var(--ink); text-decoration:underline; text-decoration-color:var(--quiet);
  text-underline-offset:2px; }
a:hover { text-decoration-color:var(--ink); }
.muted { color:var(--muted); }
code, .mono, .num, .stamp { font-family:var(--mono); font-size:13px; }
.needs { display:flex; flex-wrap:wrap; gap:8px; margin:16px 0 0; }
.needs div { background:var(--card); border:1px solid var(--line); padding:8px 12px; }
.needs b { font:600 20px/1 var(--cond); margin-right:6px; }
.needs .hot { border-color:var(--owner); }
ol.inbox { margin:0; padding-left:24px; }
ol.inbox li { padding:4px 0; border-bottom:1px solid var(--line); }
ol.inbox li::marker { color:var(--owner); font-weight:600; }
ol.inbox li.k-blocked::marker { color:var(--red); }
.scroll { overflow-x:auto; }
.scroll, .scroll * { overflow-wrap:normal; }
table { border-collapse:collapse; width:100%; }
th, td { text-align:left; padding:6px 10px 6px 0; border-bottom:1px solid var(--line); vertical-align:top; }
th { font:600 12px/1.3 var(--cond); color:var(--muted); text-transform:uppercase;
  letter-spacing:.05em; white-space:nowrap; }
.pill { display:inline-block; padding:0 8px; font:600 12px/1.6 var(--cond); letter-spacing:.04em;
  text-transform:uppercase; color:#fff; white-space:nowrap; }
.s-active { background:var(--agent); } .s-idle { background:var(--owner); }
.s-blocked { background:var(--red); } .s-stopped { background:var(--quiet); }
.num { text-align:right; white-space:nowrap; }
table.narrow { width:auto; min-width:240px; }
.method { max-width:720px; font-size:13px; }
table.grid td { min-width:160px; }
.now { font-weight:600; }
.id { white-space:nowrap; }
details summary { cursor:pointer; margin:12px 0 4px; color:var(--muted); }
ul.findings { margin:0 0 10px; padding-left:20px; max-width:760px; }
ul.findings li { padding:2px 0; }
table.precedent { width:auto; }
table.precedent th, table.precedent td { padding:4px 6px; }
table.precedent td.num { min-width:34px; }
.pointer { margin:28px 0 0; padding:10px 12px; border-left:3px solid var(--agent); background:var(--card); }
.desk { margin:16px 0 0; }
.desk .band { display:flex; flex-wrap:wrap; align-items:baseline; gap:4px 14px; padding:10px 14px;
  background:var(--ink); color:var(--paper); font:600 14px/1.4 var(--cond);
  text-transform:uppercase; letter-spacing:.05em; }
.desk .band a { color:var(--paper); text-decoration-color:var(--quiet); }
.desk .band .q { text-transform:none; letter-spacing:0; font:600 16px/1.3 var(--sans); flex:1 1 240px; }
.desk .band .live { background:var(--red); color:#fff; padding:0 8px; letter-spacing:.1em; }
.desk .seats { display:grid; grid-template-columns:repeat(auto-fit, minmax(220px, 1fr));
  gap:1px; background:var(--line); border:1px solid var(--line); border-top:0; }
.desk .seat { background:var(--card); padding:12px 14px; min-width:0; }
.desk .seat.up { box-shadow:inset 0 3px 0 var(--agent); }
.desk .who { font:600 12px/1.3 var(--cond); text-transform:uppercase; letter-spacing:.05em; }
.desk .who .muted { text-transform:none; letter-spacing:0; font-family:var(--sans); }
.desk .reco { font:600 24px/1.15 var(--cond); color:var(--agent); margin:8px 0 4px; }
.desk .reco.none { color:var(--quiet); font-size:18px; }
.desk .swing { font:600 12px/1.3 var(--cond); text-transform:uppercase; letter-spacing:.04em;
  color:var(--muted); }
.desk blockquote { margin:8px 0 6px; font-size:14px; }
.desk .when { font:13px/1.4 var(--mono); }
.desk .bar { display:flex; align-items:center; gap:12px; padding:10px 14px; background:var(--card);
  border:1px solid var(--line); border-top:0; font:600 16px/1.2 var(--cond);
  text-transform:uppercase; letter-spacing:.05em; }
.desk .marks { display:flex; gap:3px; }
.desk .marks span { width:28px; height:10px; background:var(--line); }
.desk .marks span.on { background:var(--agent); }
.floor { display:grid; grid-template-columns:repeat(auto-fill, minmax(240px, 1fr)); gap:10px; }
.floor .card { background:var(--card); border:1px solid var(--line); border-left:4px solid var(--agent);
  padding:10px 12px; }
.floor .card.s-blocked { border-left-color:var(--red); }
.floor .role { font:600 15px/1.2 var(--cond); color:var(--agent); text-transform:uppercase;
  letter-spacing:.05em; }
.floor .what { font-weight:600; margin:4px 0 2px; }
.floor .spark { display:block; margin:6px 0 2px; }
.floor .spark .bar { fill:var(--agent); } .floor .spark .zero { fill:var(--line); }
.floor .used, .idle { font-size:13px; }
.watcher ul { margin:0; padding-left:20px; font-size:14px; } .watcher .stale { color:var(--red); }
ul.trends { list-style:none; margin:0; padding:0; }
ul.trends li { display:flex; align-items:center; gap:12px; padding:8px 0;
  border-bottom:1px solid var(--line); font-size:16px; }
ul.trends li.few { color:var(--muted); }
ul.trends svg.spark { flex:none; fill:none; stroke:var(--agent); stroke-width:1.5; }
ul.trends svg.spark circle { fill:var(--agent); stroke:none; }
ol.wire { list-style:none; margin:0; padding:0; max-width:760px; }
ol.wire li { padding:6px 0; border-bottom:1px solid var(--line); font-size:16px; }
ol.wire time { font:600 14px/1 var(--cond); color:var(--muted); margin-right:8px; }
ol.wire li.ruled time, ol.wire li.lapsed time, ol.wire li.convened time { color:var(--owner); }
ol.wire li.red time { color:var(--red); }
ol.grants { list-style:none; margin:0 0 8px; padding:0; max-width:760px; }
ol.grants li { padding:6px 0; border-bottom:1px solid var(--line); font-size:16px; overflow-wrap:anywhere; }
ol.grants time { font-family:var(--mono); }
.grants-mode { margin:0 0 6px; }
h3.left, ol.grants.left a { color:var(--owner); }
ul.went { list-style:none; margin:0; padding:0; }
ul.went li { display:flex; align-items:center; gap:12px; padding:8px 0;
  border-bottom:1px solid var(--line); font-size:16px; }
.went-bar { flex:none; display:flex; width:120px; height:10px; gap:2px; background:var(--line); }
.went-bar span { min-width:3px; }
.went-bar .agents, .went-bar .record { background:var(--agent); }
.went-bar .owner, .went-bar .direction { background:var(--owner); }
.went-bar .committee { background:var(--ink); }
.went-bar .other, .went-bar .lapsed { background:var(--quiet); }
.went-bar .open, .went-bar .nothing { background:var(--line); outline:1px solid var(--quiet); outline-offset:-1px; }
.pasts { display:grid; grid-template-columns:repeat(auto-fit, minmax(260px, 1fr)); gap:12px; }
.past { background:var(--card); border:1px solid var(--line); padding:12px 14px; min-width:0; }
.past .rec { font:600 20px/1.2 var(--cond); }
.past .q { font-size:13px; color:var(--muted); }
.past blockquote { margin:8px 0; font-size:14px; }
.past .call { font:600 14px/1.3 var(--cond); text-transform:uppercase; letter-spacing:.05em;
  color:var(--agent); }
.past .call.split { color:var(--ink); }
.past ul { margin:6px 0 0; padding:0; list-style:none; font-size:13px; color:var(--muted); }
header.mast .live.stale { background:var(--quiet); }
.report .lead { font-size:17px; margin:4px 0; } .report .lead a { font-weight:600; }
.report .stamp { color:var(--muted); margin-left:6px; white-space:nowrap; }
.report .ask, .report .ask a, ol.asks a { color:var(--owner); text-decoration-color:var(--owner); }
ol.asks { margin:4px 0 8px; padding-left:22px; } ol.asks li { padding:3px 0; }
ol.asks li::marker { color:var(--owner); font-weight:600; }
.plan .scope h3 { margin:16px 0 4px; } .plan .scope h3 .muted { font:400 13px/1 var(--sans); margin-left:6px; }
.plan ul.subs, .plan ul.subs ul { list-style:none; margin:0; padding:0; }
.plan ul.subs ul { padding-left:18px; border-left:2px solid var(--line); margin:2px 0 4px 4px; }
.plan ul.subs li { padding:3px 0; overflow-wrap:anywhere; }
.plan .st { font:600 13px/1.3 var(--cond); margin-left:4px; }
.plan .st.go { color:var(--agent); } .plan .st.waiting { color:var(--ink); }
.plan .st.not_go { color:var(--owner); } .plan .st.unknown { color:var(--muted); }
.plan .pr { font:13px/1.3 var(--mono); margin-left:6px; }
.w-agent { color:var(--agent); font-weight:600; } .w-owner { color:var(--owner); font-weight:600; }
.w-other { color:var(--quiet); }
table.authority td:first-child { min-width:200px; }
nav.top { max-width:1100px; margin:0 auto 4px; display:flex; flex-wrap:wrap; gap:4px 18px;
  font:600 13px/1.6 var(--cond); text-transform:uppercase; letter-spacing:.06em; }
nav.top .here { text-decoration:none; color:var(--muted); }
.sec { scroll-margin-top:12px; }
/* The rail (#1249): a right-hand column that shows its base (the Work map's Briefing) and slides
   a drawer (the Selected panel) over it while something is selected. page(rail=True) widens the
   page for it; `.rail-open` on the rail opens the drawer. The covered side is visibility:hidden,
   once the slide is over, so nothing in it can be focused. Under 900px the base stays in the
   flow and the drawer is a bottom sheet, up to 75vh. */
body.has-rail main, body.has-rail header.mast, body.has-rail nav.top { max-width:1440px; }
.rail { position:sticky; top:12px; min-width:0; overflow:hidden; }
.rail-base, .rail-over { position:absolute; inset:0; transition:transform .28s ease, visibility 0s linear 0s; }
.rail-base { overflow:auto; }
.rail-base:focus { outline:none; }
.rail-over { transform:translateX(100%); visibility:hidden; transition:transform .28s ease, visibility 0s linear .28s; }
.rail-open .rail-over { transform:none; visibility:visible; transition:transform .28s ease, visibility 0s linear 0s; }
.rail-open .rail-base { visibility:hidden; transition:visibility 0s linear .28s; }
@media (max-width:900px) {
  .rail { position:static; overflow:visible; }
  .rail-base { position:static; overflow:visible; }
  .rail-open .rail-base { visibility:visible; }
  .rail-over { position:fixed; inset:auto 0 0 0; z-index:20; max-height:75vh; overflow:auto;
    transform:translateY(100%); box-shadow:0 -6px 18px rgba(27,27,24,.18); }
  .rail-open .rail-over { transform:none; } }
@media (prefers-reduced-motion:reduce) { .rail-base, .rail-over, .rail-open .rail-base, .rail-open .rail-over {
  transition:none; } }
/* Shared by the Work map and Crew, from the Bridge (#926, retired in #1114). */
.br-main { flex:999 1 520px; min-width:0; display:flex; flex-direction:column; gap:26px; }
.br-titlebar { display:flex; flex-wrap:wrap; align-items:baseline; gap:4px 16px; }
.br-titlebar h1 { font-size:30px; margin:12px 0 0; }
.br-brief { background:var(--card); border:1px solid var(--line); border-radius:10px; padding:14px 18px; }
.br-briefbody { max-width:68ch; }
.br-briefbody p { margin:10px 0 0; line-height:1.55; }
.br-colh { display:flex; flex-wrap:wrap; align-items:baseline; justify-content:space-between; gap:4px 10px;
  padding-bottom:8px; border-bottom:1px solid var(--line); font-size:13px; }
h2.br-h { font:600 20px/1.2 var(--cond); margin:0; padding:0; border:0; text-transform:none; letter-spacing:0; }
h2.br-h.owner, .br-kind.owner { color:var(--owner); }
.br-kind { font:11px/1.4 var(--mono); letter-spacing:.06em; color:var(--muted); }
.br-kind time { font-size:11px; }
.br-title { font-weight:600; }
.br-red { color:var(--red); }
.br-av { width:32px; height:32px; border-radius:8px; flex:none; display:flex; align-items:center;
  justify-content:center; font:12px var(--mono); background:#E1E7F5; color:var(--agent); }
.br-av.lead { background:var(--agent); color:#fff; }
.br-dot { width:9px; height:9px; border-radius:50%; flex:none; align-self:center; background:var(--quiet); }
.br-dot.agent { background:var(--agent); } .br-dot.owner { background:var(--owner); }
.br-dot.red { background:var(--red); }
/* The Commissions page (#931): a list and a focus drawer shown by :target, no script. */
.cm-wrap { flex:999 1 520px; min-width:0; display:flex; flex-wrap:wrap; gap:24px; align-items:flex-start; }
.cm-main { flex:3 1 400px; min-width:0; }
.cm-grp { font:11px/1.4 var(--mono); letter-spacing:.06em; color:var(--muted); margin:20px 0 0;
  padding-bottom:6px; border-bottom:1px solid var(--line); }
.cm-grp.br-red { color:var(--red); } .cm-grp.owner { color:var(--owner); }
a.cm-row { display:flex; flex-wrap:wrap; gap:6px 16px; align-items:center; padding:12px 8px;
  border-bottom:1px solid #E4E2D9; text-decoration:none; color:var(--ink); }
a.cm-row:hover { background:var(--card); }
.cm-name { flex:1 1 220px; min-width:0; display:flex; flex-direction:column; } .cm-name .muted { font-size:13px; }
.cm-bars { display:flex; align-items:center; gap:8px; width:120px; }
.cm-bar { display:block; flex:1; height:5px; background:#E4E2D9; border-radius:3px; overflow:hidden; }
.cm-fill { display:block; height:100%; background:var(--agent); }
.cm-of, .cm-bar-none { font-size:12px; }
.cm-word { min-width:80px; font-size:13px; color:var(--muted); } .cm-word.br-red { color:var(--red); }
.cm-word.owner { color:var(--owner); }
.cm-aside { flex:2 1 300px; min-width:0; max-width:420px; background:var(--card); border:1px solid var(--line);
  border-radius:10px; padding:14px 18px; position:sticky; top:12px; }
.cm-drawer { display:none; } .cm-drawer:target { display:block; }
.cm-aside:has(.cm-drawer:target) .cm-pick { display:none; }
.cm-crumb { margin:4px 0 0; font-size:13px; } h2.cm-dtitle { font-size:22px; margin:2px 0 6px; }
.cm-pill { font:12px/1 var(--mono); padding:3px 8px; border-radius:999px; color:#fff; background:var(--ink); }
.cm-pill.red { background:var(--red); } .cm-pill.owner { background:var(--owner); }
.cm-pill.agent { background:var(--agent); }
.cm-sec { border-top:1px solid #E4E2D9; padding:10px 0 4px; margin:10px 0 0; }
.cm-sec .br-kind { margin:0 0 4px; }
ul.cm-list { margin:0; padding:0; list-style:none; font-size:14px; } ul.cm-list li { padding:4px 0; }
ul.cm-list li.status-failing b { color:var(--red); } ul.cm-list li.status-met b { color:var(--agent); }
ul.cm-list .st { font:600 13px/1.3 var(--cond); } ul.cm-list .st.go { color:var(--agent); }
ul.cm-list .st.not_go { color:var(--owner); }
/* The Agents page (#932): Commissions' list and drawer, with a badge per role. */
.br-av.idle { background:#EDEBE3; color:var(--muted); }
ul.cm-list .owner { color:var(--owner); }
a.cm-row .br-av { align-self:flex-start; }
.ag-n { font-size:13px; min-width:80px; }
.ag-head { display:flex; gap:10px; align-items:center; margin:6px 0; } .ag-head .cm-dtitle { margin:0; }
.ag-tiles { display:grid; grid-template-columns:repeat(2, minmax(0, 1fr)); gap:8px; }
.ag-tile { background:#fff; border:1px solid #E4E2D9; border-radius:8px; padding:8px 10px; display:flex;
  flex-direction:column; gap:2px; font-size:13px; } .ag-tile .mono { font-size:18px; }
/* Effort (#1013): a stacked bar per open Goal, the fix share hatched, and the capability line. */
.ef-goal { margin:10px 0 0; } .ef-name { font-weight:600; }
.ef-row { display:flex; align-items:center; gap:8px; margin:3px 0; }
.ef-when { flex:none; width:96px; font-size:13px; }
.ef-bar { flex:1 1 auto; min-width:0; display:flex; height:14px; background:var(--line); }
.ef-n { flex:none; min-width:24px; text-align:right; }
.ef-seg { display:block; height:100%; min-width:3px; border-right:1px solid var(--paper); }
.ef-capability { background:var(--agent); } .ef-governance { background:var(--owner); }
.ef-knowledge { background:var(--ink); } .ef-upkeep { background:var(--quiet); }
.ef-fix { display:block; height:100%;
  background:repeating-linear-gradient(135deg, var(--paper) 0 2px, transparent 2px 5px); }
.ef-legend { display:flex; flex-wrap:wrap; gap:4px 14px; font-size:13px; margin:6px 0; }
.ef-key { display:inline-block; width:12px; height:12px; margin-right:5px; vertical-align:-1px; }
.ef-trend h3 { margin-top:16px; }
svg.ef-line { display:block; max-width:100%; height:auto; fill:none; stroke:var(--agent); stroke-width:1.5; }
svg.ef-line circle { fill:var(--agent); stroke:none; }
/* The Work map (#1082): workmap_page.py and workmap.js. One warm ramp; markers by shape too. */
.wm-keyline { margin:4px 0 0; font-size:14px; color:var(--muted); max-width:80ch; }
.wm-ctls { display:flex; flex-wrap:wrap; gap:10px 22px; }
.wm-ctl { display:flex; flex-direction:column; gap:4px; min-width:0; }
.wm-ctl .br-kind { margin:0; }
.wm-seg { display:flex; flex-wrap:wrap; border:1px solid var(--ink); width:max-content; max-width:100%; }
.wm-seg button { font:13px/1 var(--sans); padding:7px 10px; border:0; border-right:1px solid var(--ink);
  background:var(--card); color:var(--ink); cursor:pointer; }
.wm-seg button:last-child { border-right:0; }
.wm-seg button[aria-pressed="true"] { background:var(--ink); color:var(--paper); }
.wm-seg button:disabled { cursor:default; }
.wm-seg button:focus-visible, .wm-gh:focus-visible, .wm-back:focus-visible { outline:3px solid var(--agent); outline-offset:1px; }
.wm-top { display:grid; grid-template-columns:minmax(0, 2fr) minmax(340px, 1fr); gap:16px 20px; align-items:start; }
.wm-mapcol { min-width:0; }
/* The Work map's rail (#1249): as tall as the map frame plus the legend, beside the frame. */
.wm-top > .rail { margin-top:30px; height:calc(clamp(460px, 68vh, 640px) + 72px); }
@media (max-width:900px) { .wm-top { display:flex; flex-direction:column; align-items:stretch; }
  .wm-top > .rail { order:-1; margin-top:0; height:auto; } }
.wm-crumb { margin:0 0 6px; height:24px; font:13px/24px var(--mono); white-space:nowrap; overflow:hidden;
  text-overflow:ellipsis; }
.wm-back { font:inherit; padding:0; border:0; background:none; color:var(--ink); text-decoration:underline;
  text-decoration-color:var(--quiet); text-underline-offset:2px; cursor:pointer; }
.wm-frame { position:relative; height:clamp(460px, 68vh, 640px); }
.wm-map { position:absolute; inset:0; overflow:hidden; background:var(--line); }
.wm-empty { margin:0; padding:16px; }
.wm-g { position:absolute; border:1px solid var(--paper); }
.wm-gh { position:absolute; left:0; top:0; right:0; height:20px; display:flex; justify-content:space-between;
  gap:6px; padding:0 6px; border:0; background:var(--ink); color:var(--paper); font:600 12px/20px var(--cond);
  text-transform:uppercase; letter-spacing:.04em; text-align:left; cursor:zoom-in; overflow:hidden;
  white-space:nowrap; }
.wm-gh:disabled { cursor:default; }
.wm-gn { overflow:hidden; text-overflow:ellipsis; min-width:0; } .wm-gp { flex:none; font-family:var(--mono); }
.wm-box { position:absolute; overflow:hidden; border:1px solid var(--paper); padding:3px 6px 3px 8px;
  display:flex; flex-direction:column; gap:1px; color:var(--ink); cursor:pointer; }
.wm-box.wm-dark { color:var(--paper); }
.wm-box:focus-visible { outline:3px solid var(--agent); outline-offset:-3px; z-index:2; }
.wm-t { font:600 12px/1.3 var(--sans); white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.wm-m { font:11px/1.3 var(--mono); white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.wm-hatch { background:repeating-linear-gradient(135deg, #F3EFE7 0 4px, #E2D8C7 4px 8px); }
.wm-needs { box-shadow:inset 0 0 0 3px var(--owner); }
.wm-blocked { box-shadow:inset 5px 0 0 0 var(--red); }
.wm-needs.wm-blocked { box-shadow:inset 5px 0 0 0 var(--red), inset 0 0 0 3px var(--owner); }
.wm-fold { position:absolute; top:0; right:0; width:12px; height:12px;
  background:linear-gradient(to bottom left, var(--paper) 50%, #64523E 50%); }
.wm-sel::after { content:""; position:absolute; inset:2px; border:2px dashed var(--ink); pointer-events:none; }
.wm-dark.wm-sel::after { border-color:var(--paper); }
.wm-tip { position:absolute; z-index:5; max-width:min(340px, 100%); display:flex; flex-direction:column; gap:2px;
  padding:8px 10px; background:var(--card); border:1px solid var(--ink); font-size:13px; pointer-events:none;
  overflow-wrap:anywhere; }
.wm-tip .mono { font-size:12px; } .wm-tip[hidden] { display:none; }
.wm-legend { height:64px; overflow:hidden; display:flex; flex-wrap:wrap; align-content:flex-start;
  gap:4px 14px; margin-top:8px; font-size:12px; }
.wm-ramp, .wm-key { display:inline-flex; align-items:center; gap:4px; }
.wm-ramp { gap:0; } .wm-ramp .wm-end { padding:0 6px; }
.wm-sw { display:inline-block; width:16px; height:12px; position:relative; }
.wm-key .wm-sw { background:#E2D8C7; }
.wm-key .wm-k-fold { background:linear-gradient(to bottom left, var(--paper) 50%, #64523E 50%) top right / 8px 8px no-repeat, #E2D8C7; }
.wm-key .wm-k-needs { box-shadow:inset 0 0 0 3px var(--owner); }
.wm-key .wm-k-blocked { box-shadow:inset 5px 0 0 0 var(--red); }
.wm-key .wm-k-sel { outline:2px dashed var(--ink); outline-offset:-2px; }
/* The Selected panel (#1083): every section a fixed height, so selecting or clearing an issue
   moves nothing. Since #1249 it fills the rail's drawer (340px to 480px wide, the rail's height);
   on a phone it is the bottom sheet, 460px tall. */
.wm-selected { width:100%; height:100%; box-sizing:border-box; overflow:hidden; display:flex; flex-direction:column;
  justify-content:space-between; background:var(--card); border:1px solid var(--line); padding:12px 14px; }
@media (max-width:900px) { .wm-selected { height:460px; } }
.wm-ss { flex:none; overflow:hidden; margin:0; }
.wm-ss p { margin:0; }
.wm-ss-head { height:20px; display:flex; justify-content:space-between; align-items:center; }
.wm-ss-head { gap:10px; }
.wm-ss-head .br-kind { margin:0; padding:0; flex:none; }
.wm-ss-head .wm-back { flex:none; font-size:13px; }
.wm-ss-head .mono { font-size:13px; flex:1 1 0; min-width:0; text-align:right; }
.wm-ss-title { height:58px; }
.wm-st { height:38px; font:600 14px/19px var(--sans); overflow:hidden; display:-webkit-box;
  -webkit-line-clamp:2; -webkit-box-orient:vertical; overflow-wrap:anywhere; }
.wm-sel-empty .wm-st { font-weight:400; color:var(--muted); }
.wm-sc { height:20px; font-size:12px; line-height:20px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.wm-flag { color:var(--owner); font-weight:600; }
.wm-sh { height:18px; display:flex; justify-content:space-between; gap:8px; font:600 11px/18px var(--cond);
  text-transform:uppercase; letter-spacing:.04em; white-space:nowrap; }
.wm-sh span:first-child { flex:none; }
.wm-sh span:last-child { flex:1 1 0; text-align:right; overflow:hidden; text-overflow:ellipsis; min-width:0; text-transform:none;
  letter-spacing:0; font-family:var(--mono); font-weight:400; }
.wm-ss-stage { height:50px; }
.wm-sgs { display:flex; gap:3px; margin-top:4px; }
.wm-sg { flex:1 1 0; min-width:0; display:flex; flex-direction:column; gap:2px; }
.wm-sgbar { height:12px; background:var(--paper); box-shadow:inset 0 0 0 1px var(--line); }
.wm-sgl { height:14px; font-size:11px; line-height:14px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; color:var(--muted); }
.wm-sg-past .wm-sgbar { background:#E2D8C7; box-shadow:none; }
.wm-sg-now .wm-sgbar { background:#8A7458; box-shadow:none; }
.wm-sg-now .wm-sgl { color:var(--ink); font-weight:600; }
.wm-sg-stop .wm-sgbar { background:repeating-linear-gradient(135deg, var(--red) 0 3px, var(--paper) 3px 6px); box-shadow:none; }
.wm-sg-stop .wm-sgl { color:var(--red); font-weight:600; }
.wm-ss-days { height:104px; }
.wm-bars { height:62px; display:flex; align-items:flex-end; gap:2px; margin-top:4px;
  border-bottom:1px solid var(--quiet); padding-bottom:8px; position:relative; }
.wm-bar { flex:1 1 0; min-width:0; position:relative; height:100%; }
.wm-bar i { position:absolute; left:0; right:0; bottom:0; background:#AE987A; }
.wm-bar.wm-today i { background:#64523E; }
.wm-bar b { position:absolute; left:50%; bottom:-7px; width:5px; height:5px; margin-left:-2.5px;
  border-radius:50%; background:var(--ink); }
.wm-sel-empty .wm-bar i { background:var(--line); }
.wm-ax { height:16px; display:flex; font-size:11px; line-height:16px; color:var(--muted); white-space:nowrap; }
.wm-ax span { flex:1 1 0; min-width:0; overflow:hidden; text-overflow:ellipsis; text-align:center; }
.wm-ax span:first-child { text-align:left; } .wm-ax span:last-child { text-align:right; }
.wm-ss-peers { height:62px; }
.wm-strip { position:relative; height:24px; margin:2px 6px 0; }
.wm-strip .wm-line { position:absolute; left:0; right:0; top:11px; height:1px; background:var(--quiet); }
.wm-strip .wm-pd { position:absolute; top:8px; width:7px; height:7px; margin-left:-3.5px; border-radius:50%;
  background:#CBBBA2; }
.wm-strip .wm-med { position:absolute; top:4px; width:2px; height:16px; margin-left:-1px; background:var(--muted); }
.wm-strip .wm-me { position:absolute; top:5px; width:13px; height:13px; margin-left:-6.5px; border-radius:50%;
  background:var(--ink); box-shadow:0 0 0 2px var(--card); }
.wm-ss-peers .wm-ax { margin:0 0; }
.wm-ss-nums { height:96px; display:grid; grid-template-columns:1fr 1fr; grid-auto-rows:32px; gap:0 12px; }
.wm-num { min-width:0; } .wm-num dt { font-size:11px; line-height:14px; color:var(--muted); white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.wm-num dd { margin:0; font:13px/18px var(--mono); white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.wm-brief { width:100%; min-height:100%; }
/* The Work map's lists (#1084): six of them, each exactly five 50px rows tall, whatever is in it. */
.wm-lists { display:grid; grid-template-columns:repeat(3, minmax(0, 1fr)); gap:20px 24px; margin-top:20px; }
@media (max-width:900px) { .wm-lists { grid-template-columns:repeat(2, minmax(0, 1fr)); } }
@media (max-width:600px) { .wm-lists { grid-template-columns:minmax(0, 1fr); } }
.wm-list { min-width:0; }
.wm-lh { display:flex; justify-content:space-between; gap:8px; height:22px; margin:0; border-bottom:1px solid var(--ink);
  font:600 12px/22px var(--cond); letter-spacing:.06em; white-space:nowrap; overflow:hidden; }
.wm-lh span:first-child { min-width:0; overflow:hidden; text-overflow:ellipsis; }
.wm-lc { flex:none; font-family:var(--mono); letter-spacing:0; }
.wm-ld { height:20px; margin:2px 0 0; font-size:12px; line-height:20px; color:var(--muted);
  white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.wm-lol { list-style:none; margin:0; padding:0; height:250px; overflow:hidden; }
.wm-lol li { height:50px; margin:0; }
.wm-li { display:grid; grid-template-columns:minmax(0, 1fr) auto; grid-template-rows:28px 20px; column-gap:10px;
  width:100%; height:50px; box-sizing:border-box; padding:0 4px; margin:0; border:0; border-bottom:1px solid var(--line);
  background:none; color:var(--ink); font:inherit; text-align:left; cursor:pointer; }
.wm-li:hover { background:var(--card); }
.wm-li[aria-pressed="true"] { outline:2px dashed var(--ink); outline-offset:-2px; }
.wm-li:focus-visible { outline:3px solid var(--agent); outline-offset:-3px; }
.wm-lt { display:flex; align-items:center; gap:6px; min-width:0; font:600 13px/28px var(--sans); }
.wm-ln { flex:0 1 auto; min-width:0; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.wm-lf { flex:none; padding:0 4px; border:1px solid currentColor; font:600 10px/14px var(--cond);
  letter-spacing:.04em; text-transform:uppercase; }
.wm-lf-you { color:var(--owner); } .wm-lf-blk { color:var(--red); }
.wm-lv { font-size:13px; line-height:28px; white-space:nowrap; text-align:right; }
.wm-lx { grid-column:1 / -1; font-size:12px; line-height:20px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.wm-lnone { padding:10px 4px 0; font-size:13px; }
/* #1115: what an issue waits on and holds up, and a Goal, Area or role in place of an issue's
   sections, scrolling inside the same fixed box. */
.wm-ss-deps { height:40px; }
.wm-dl { height:20px; display:flex; gap:8px; font-size:12px; line-height:20px; white-space:nowrap; overflow:hidden; }
.wm-dl > span:first-child { flex:none; width:62px; color:var(--muted); }
.wm-dl > span:last-child { flex:1 1 0; min-width:0; overflow:hidden; text-overflow:ellipsis; }
.wm-pick { font:12px/1.3 var(--mono); padding:0; border:0; background:none; color:var(--ink);
  text-decoration:underline; text-decoration-color:var(--quiet); text-underline-offset:2px; cursor:pointer; }
.wm-dl .wm-pick { margin-right:6px; }
.wm-pick:focus-visible, .wm-gi:focus-visible { outline:3px solid var(--agent); outline-offset:1px; }
.wm-alt { display:none; }
.wm-sel-other .wm-ss-i { display:none; }
.wm-sel-other .wm-alt { display:block; flex:1 1 0; min-height:0; overflow:auto; margin-top:6px; font-size:13px; }
.wm-alt .wm-sh { margin-top:8px; }
.wm-alt ul { list-style:none; margin:2px 0 0; padding:0; }
.wm-alt li { margin:0 0 3px; overflow-wrap:anywhere; }
.wm-alt .wm-ok { color:var(--muted); }
.wm-alt .wm-bad { color:var(--red); }
.wm-tiles { display:grid; grid-template-columns:1fr 1fr; gap:2px 12px; margin-top:2px; }
.wm-gi { flex:none; width:16px; height:16px; margin-top:2px; padding:0; border:1px solid var(--paper);
  border-radius:50%; background:none; color:var(--paper); font:600 11px/14px var(--mono); cursor:pointer; }
.wm-gh.wm-gh-i { padding-right:26px; }
.wm-g .wm-gi { position:absolute; right:4px; top:0; z-index:1; }
.wm-dep::before { content:""; position:absolute; inset:1px; border:1px dashed var(--ink); pointer-events:none; }
.wm-dark.wm-dep::before { border-color:var(--paper); }
.wm-key .wm-k-dep { outline:1px dashed var(--ink); outline-offset:-2px; }
/* #1114: the counts strip (one line, wrapping on a phone) and the tape (a fixed-height box that
   scrolls inside itself), which retired the Bridge. The strip's pick outlines boxes on the map. */
.sp { display:flex; flex-wrap:wrap; gap:4px 18px; align-items:baseline; font-size:14px; line-height:28px; }
.sp-i { white-space:nowrap; }
.sp-pick { font:inherit; line-height:26px; padding:0 8px; border:1px solid var(--line); background:var(--card);
  color:var(--ink); cursor:pointer; }
.sp-pick:disabled { cursor:default; }
.sp-pick[aria-pressed="true"] { border-color:var(--ink); background:var(--ink); color:var(--paper); }
.sp-pick:focus-visible { outline:3px solid var(--agent); outline-offset:1px; }
.sp-red { color:var(--red); } .sp-owner { color:var(--owner); }
.sp-pick[aria-pressed="true"].sp-red, .sp-pick[aria-pressed="true"].sp-owner { color:var(--paper); }
.wm-box.wm-mark { outline:2px solid var(--ink); outline-offset:-6px; }
.wm-dark.wm-mark { outline-color:var(--paper); }
.wm-markg { position:absolute; box-sizing:border-box; border:3px solid var(--red); pointer-events:none; z-index:1; }
.wm-list[data-list="needs"] .wm-lol { overflow-y:auto; }
a.wm-li { text-decoration:none; }
.tp { width:100%; margin-top:20px; }
.tp-box { height:360px; overflow-y:auto; border-bottom:1px solid var(--line); }
.tp-ol { list-style:none; margin:0; padding:0; }
.tp-i { display:flex; flex-wrap:wrap; gap:2px 12px; align-items:baseline; padding:7px 0;
  border-bottom:1px solid #E4E2D9; font-size:14px; }
.tp-m { flex:none; display:flex; gap:10px; align-items:baseline; width:260px; }
.tp-m time, .tp-m > .mono { width:70px; flex:none; }
.tp-w { width:70px; flex:none; font-size:13px; }
.tp-k { font:11px/1.4 var(--mono); letter-spacing:.06em; color:var(--muted); }
.tp-k.sp-red { color:var(--red); }
.tp-t { flex:1 1 240px; min-width:0; overflow-wrap:anywhere; }
button.tp-t { font:inherit; text-align:left; font-size:14px; }
.tp-l { flex:none; font-size:13px; }
.tp-none { padding:10px 0; margin:0; }
@media (max-width:600px) { .tp-m { width:auto; } .tp-t { flex-basis:100%; } }
"""


def esc(x) -> str:
    return html.escape("" if x is None else str(x))


def nav(current: str) -> str:
    """Map · Crew · Governance (#1113); the current one is marked, not linked away from."""
    links = []
    for file, name in PAGES:
        if file == current:
            links.append(f'<span class="here" aria-current="page">{esc(name)}</span>')
        else:
            links.append(f'<a href="{esc(file)}">{esc(name)}</a>')
    return "".join(links)


def built_mark(built: dt.datetime) -> str:
    """The red LIVE mark and the build time (#402). A static page can't know how old it is
    when viewed; the page's script reads the `datetime` attribute to grey the mark once the data
    is stale."""
    t = built.astimezone(dt.timezone.utc)
    return (f'<span class="live">LIVE</span><span class="muted">built <time class="stamp" '
            f'datetime="{t.strftime("%Y-%m-%dT%H:%M:%SZ")}" title="{t.strftime("%Y-%m-%d %H:%M UTC")}">'
            f'{t.strftime("%H:%M")} UTC</time></span>')



def mast_live(built: dt.datetime, owner: str = "") -> str:
    """The masthead's changing part: the LIVE mark and build time, and `owner`, the owner's last
    act as HTML (#402). The page's script redraws it; the page name around it stays."""
    return f"{built_mark(built)}{owner}"


def masthead(current: str, repo: str, built: dt.datetime, owner: str = "", live_box: bool = False) -> str:
    """What's inside the page's <header>: the page name, the repo, then mast_live(). With
    `live_box`, that part is the `data-panel="mast"` box the page's script redraws."""
    bits = mast_live(built, owner)
    if live_box:
        bits = f'<span class="bits" data-panel="mast">{bits}</span>'
    return (f'<span class="name">AgentFleetOS · {esc(NAMES[current])}</span>'
            f'<span class="muted">{esc(repo)}</span>{bits}')


def page(current: str, title: str, repo: str, built: dt.datetime, body: str, owner: str = "",
         script: tuple[str, str] | None = None, libs: dict[str, bytes] | None = None,
         live_mast: bool = False, rail: bool = False) -> str:
    """One whole page in the shared shell: head (noindex, CSP, CSS), masthead (#402), the nav
    (Map · Crew · Governance, #1113), then the body. `script` is the page's own script as (file
    name, text), e.g. the Work map's (#1082). The page loads it from js/ (write_scripts puts it
    there) and the CSP allows it by its hash. No page reloads itself (#1135): the Work map,
    Crew and Governance redraw in place from same-origin JSON, and effort.html, which has no
    script, shows the build it came with. `libs` are
    vendored libraries the page loads before its own script, as layout.libs() returns them
    (#1107): each is served from js/ too and allowed by its hash. With `live_mast`, the
    masthead's changing part is a `data-panel="mast"` box for the page's own script to redraw
    (Governance's, #1140). With `rail`, the page is wider (1440px, not 1100px) for a rail()
    beside its main column (#1249); only the Work map has one so far."""
    name = NAMES[current]
    js = script[1] if script else None
    libs = libs or {}
    return "\n".join(part for part in [
        '<!doctype html><html lang="en"><head><meta charset="utf-8">',
        f'<meta http-equiv="Content-Security-Policy" content="{live.csp(js, tuple(libs.values()))}">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        '<meta name="robots" content="noindex, nofollow">',  # published publicly; see #33
        f"<title>{esc(name)} · {esc(title)} · {esc(repo)}</title><style>{CSS}</style></head>"
        + ('<body class="has-rail">' if rail else "<body>"),
        f'<header class="mast">{masthead(current, repo, built, owner, live_box=live_mast)}</header>',
        f'<nav class="top" aria-label="Pages">{nav(current)}</nav>',
        f"<main>{body}</main>",
        *(script_tag(f, b) for f, b in libs.items()),
        script_tag(*script) if script else None,
        "</body></html>\n",
    ] if part is not None)


def rail(base: str, over: str) -> str:
    """The right-hand rail (#1249): `base` (HTML) shows by default, and `over` (HTML) is a drawer
    that slides in over it while the rail has the `rail-open` class, which the page's script
    sets. Each side is in its own box filling the rail; the base box takes focus (tabindex -1)
    so a script can hand focus back to it when the drawer closes. Use it with page(rail=True)."""
    return ('<div class="rail" data-rail>'
            f'<div class="rail-base" tabindex="-1">{base}</div>'
            f'<div class="rail-over">{over}</div></div>')


def redirect(to: str, title: str, text: str) -> str:
    """A retired page (#1113, as bridge.html for #1114): it only sends the browser to `to`, a
    page beside it, with a link for a browser that doesn't follow the refresh."""
    return ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
            '<meta name="robots" content="noindex, nofollow">'
            f'<meta http-equiv="refresh" content="0; url={esc(to)}">'
            f'<title>{esc(title)}</title></head><body>'
            f'<p>{esc(text)} <a href="{esc(to)}">Go there</a>.</p></body></html>\n')


def script_tag(file: str, js: str | bytes) -> str:
    """The tag that loads js/<file>, pinned to its hash: the browser runs it only if the bytes it
    fetched are the ones the page was built with."""
    if not SCRIPT_NAME.fullmatch(file):
        raise ValueError(f"not a script file name: {file!r}")
    return f'<script src="{JS_DIR}/{file}" integrity="{live.script_hash(js)[1:-1]}"></script>'


def write_scripts(out_dir: Path, scripts: dict[str, str | bytes]) -> int:
    """Write each script (file name -> text, or a vendored library's checked bytes) into
    out_dir/js, exactly what a page's hash names. Returns the bytes written."""
    dest = Path(out_dir) / JS_DIR
    dest.mkdir(parents=True, exist_ok=True)
    size = 0
    for file, js in scripts.items():
        if not SCRIPT_NAME.fullmatch(file):
            raise ValueError(f"not a script file name: {file!r}")
        data = js if isinstance(js, bytes) else js.encode("utf-8")
        (dest / file).write_bytes(data)
        size += len(data)
    return size


def copy_fonts(out_dir: Path) -> int:
    """Copy the font files (and their licence) into out_dir/fonts. Returns the bytes copied."""
    dest = Path(out_dir) / FONTS_DIR
    dest.mkdir(parents=True, exist_ok=True)
    size = 0
    for f in FONT_FILES:
        shutil.copyfile(FONTS_SRC / f, dest / f)
        size += (dest / f).stat().st_size
    return size


def vendored(src: Path | None = None, reserved=()) -> dict[str, bytes]:
    """Check the vendored libraries in static/vendor/ against manifest.json and return each
    file's bytes by name (#1107, GOV-0051). Raises ValueError naming every problem: a file that
    differs from its recorded sha256, a file with no entry, an entry with no file, an entry
    missing a field or with a loose version, and a name that isn't a plain script name or that
    one of the Desk's own scripts (`reserved`) already uses. generate.py calls this before it
    writes any page, so a mismatch fails the build."""
    src = Path(src or VENDOR_SRC)
    entries = json.loads((src / VENDOR_MANIFEST).read_text(encoding="utf-8")).get("files")
    if not isinstance(entries, list):
        raise ValueError(f"{VENDOR_MANIFEST}: needs a \"files\" list")
    problems, listed = [], {}
    for i, e in enumerate(entries):
        if not (isinstance(e, dict) and set(e) == set(VENDOR_FIELDS)
                and all(isinstance(e[k], str) and e[k] for k in VENDOR_FIELDS)):
            problems.append(f"entry {i}: needs exactly {', '.join(VENDOR_FIELDS)}, each non-empty text")
            continue
        f = e["file"]
        if not SCRIPT_NAME.fullmatch(f):
            problems.append(f"{f!r}: not a script file name (lower case, [a-z0-9_-], .js)")
        elif f in listed:
            problems.append(f"{f}: listed twice")
        elif f in reserved:
            problems.append(f"{f}: the name of one of the Desk's own scripts")
        elif not SHA256_HEX.fullmatch(e["sha256"]):
            problems.append(f"{f}: sha256 isn't 64 lower-case hex digits")
        elif not EXACT_VERSION.fullmatch(e["version"]):
            problems.append(f"{f}: version {e['version']!r} isn't one exact version")
        elif not e["source"].startswith("https://"):
            problems.append(f"{f}: source isn't an https:// URL")
        else:
            listed[f] = e
    on_disk = {p.name: p for p in src.iterdir() if p.name != VENDOR_MANIFEST}
    named = {e["file"] for e in entries if isinstance(e, dict) and isinstance(e.get("file"), str)}
    for f in sorted(set(on_disk) - named):
        problems.append(f"{f}: no manifest entry")
    for f in sorted(named - set(on_disk)):
        problems.append(f"{f}: manifest entry with no file")
    found = {}
    for f in sorted(set(listed) & set(on_disk)):
        p = on_disk[f]
        if not p.is_file() or p.is_symlink():
            problems.append(f"{f}: not a plain file")
            continue
        data = p.read_bytes()
        if hashlib.sha256(data).hexdigest() != listed[f]["sha256"]:
            problems.append(f"{f}: differs from its recorded sha256")
        else:
            found[f] = data
    if problems:
        raise ValueError(f"vendored libraries don't match {src.name}/{VENDOR_MANIFEST}: "
                         + "; ".join(problems))
    return found


def libs(*files: str, src: Path | None = None) -> dict[str, bytes]:
    """The checked bytes of the vendored libraries a page loads, in load order, for
    page(libs=...). Raises ValueError for a file the manifest doesn't list."""
    have = vendored(src)
    missing = [f for f in files if f not in have]
    if missing:
        raise ValueError(f"not a vendored library: {', '.join(missing)}")
    return {f: have[f] for f in files}
