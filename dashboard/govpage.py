"""governance.html (#1113), drawn client-side from state.json (#1140, stage 3 of #1135).

The page carries a shell: its six sections, empty, and the slice of state.json it draws from
in a `<script type="application/json">` block (`<`, `>` and `&` escaped). `governance.js`,
served as `js/governance.js` and allowed by its hash, draws every section from that block's
plain fields with `createElement` and text nodes (no `innerHTML`, no `eval`, no HTML from repo
text), then fetches same-origin `state.json` every 15 seconds while the tab is visible and
redraws in place when its `built_at` is newer. It doesn't read `state.json["desk"]` or load
`poll.js`. With JavaScript off the page shows a notice and a GitHub link (per GOV-0051).
"""
from __future__ import annotations

import html
from pathlib import Path

import layout
import live
import workmap_page

FILE = "governance.html"
JS = Path(__file__).resolve().parent / "governance.js"
DATA_ID = "gov-data"

# The sections, in page order: each the brief's links land on (#1113).
SECTIONS = ("rulings", "questions", "committees", "authority", "precedent", "trends")

# What the page draws from: state.json's keys, read the same way from the page's block and
# from each newer state.json.
KEYS = ("schema", "built_at", "repo", "owner_last_acted", "sessions", "governance", "gov_questions",
        "committee_desk", "past_committees", "committee_views", "authority", "precedent", "trends",
        "questions_went")


def data(state: dict) -> dict:
    """The page's slice of state.json."""
    return {k: state.get(k) for k in KEYS}


def script() -> str:
    """governance.js with its settings filled in: exactly what generate.py writes to
    js/governance.js, so its hash is the one the page's CSP names."""
    return (JS.read_text(encoding="utf-8")
            .replace("/*EVERY*/0", str(live.EVERY_SECONDS * 1000))
            .replace("/*STALE*/0", str(live.STALE_MINUTES * 60 * 1000)))


def body(d: dict) -> str:
    """The shell. With JavaScript off it shows a short notice and links to GitHub (per GOV-0051)."""
    sections = "\n".join(f'<section class="sec" id="{s}"></section>' for s in SECTIONS)
    gh = f"https://github.com/{html.escape(d.get('repo') or '')}/tree/main/governance"
    return ("<h1>Governance</h1>\n"
            '<noscript><p class="muted">Governance needs JavaScript. The rulings, jurisdictions and '
            f'questions are on <a href="{gh}">GitHub</a>.</p></noscript>\n'
            f"{sections}\n{workmap_page.data_block(d, DATA_ID)}")


def page(m: dict, title: str, owner_line: str, state: dict) -> str:
    """The whole page. `state` is state.state(m), what the build writes to state.json."""
    return layout.page(FILE, title, m["repo"], m["now"], body(data(state)), owner_line,
                       script=(JS.name, script()), live_mast=True)
