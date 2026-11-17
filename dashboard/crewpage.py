"""crew.html (#1113), drawn client-side from state.json (#1139, stage 2 of #1135).

The page carries a shell: its six sections, empty, and the slice of state.json it draws from
in a `<script type="application/json">` block (`<`, `>` and `&` escaped). `crew.js`, served
as `js/crew.js` and allowed by its hash, draws every section from that block's plain fields
with `createElement` and text nodes (no `innerHTML`, no `eval`, no HTML from repo text), then
fetches same-origin `state.json` every 15 seconds while the tab is visible and redraws in
place when its `built_at` is newer. It doesn't read `state.json["desk"]` or load `poll.js`.
With JavaScript off the page shows a notice and a GitHub link (per GOV-0051).

Each session's spend estimate, cap and over-cap flag come from state.json too (per #1153's
answer, GOV-0055), so the Spend column redraws in place with the rest. The block adds only the
method sentence under the table.
"""
from __future__ import annotations

import html
from pathlib import Path

import layout
import live
import spend
import workmap_page

FILE = "crew.html"
JS = Path(__file__).resolve().parent / "crew.js"
DATA_ID = "crew-data"

# The sections, in page order: each the brief's links land on (#1113).
SECTIONS = ("roles", "floor", "sessions", "reviewer", "grants", "effort")

# What the page draws from: state.json's keys, read the same way from the page's block and
# from each newer state.json.
KEYS = ("schema", "built_at", "repo", "owner_last_acted", "idle_minutes", "sessions", "crew_roles",
        "floor", "watcher", "reviewer_runs", "grants", "effort")


def data(state: dict) -> dict:
    """The page's slice of state.json, plus the Spend column's method sentence."""
    return {**{k: state.get(k) for k in KEYS}, "spend_method": spend.METHOD}


def script() -> str:
    """crew.js with its settings filled in: exactly what generate.py writes to js/crew.js, so
    its hash is the one the page's CSP names."""
    return (JS.read_text(encoding="utf-8")
            .replace("/*EVERY*/0", str(live.EVERY_SECONDS * 1000))
            .replace("/*STALE*/0", str(live.STALE_MINUTES * 60 * 1000)))


def body(d: dict) -> str:
    """The shell. With JavaScript off it shows a short notice and links to GitHub (per GOV-0051)."""
    sections = "\n".join(f'<section class="sec" id="{s}"></section>' for s in SECTIONS)
    gh = f"https://github.com/{html.escape(d.get('repo') or '')}/issues"
    return ('<noscript><h1>Crew</h1><p class="muted">Crew needs JavaScript. The sessions\' tracking '
            f'issues and the pull requests are on <a href="{gh}">GitHub</a>.</p></noscript>\n'
            f"{sections}\n{workmap_page.data_block(d, DATA_ID)}")


def page(m: dict, title: str, owner_line: str, state: dict) -> str:
    """The whole page. `state` is state.state(m), what the build writes to state.json."""
    return layout.page(FILE, title, m["repo"], m["now"], body(data(state)), owner_line,
                       script=(JS.name, script()), live_mast=True)
