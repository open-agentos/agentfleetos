"""Test helper (#1139): run crew.js in node against govdraw's fake DOM and read back what it drew.

Crew's panels are drawn client-side, so their tests give the script the data the page carries
(crewpage.data(): the slice of state.json, plus the Spend column's method sentence) and check the markup it
builds, serialised with text and attribute values escaped as html.escape() does.

`draw(data)` returns {section: html} for the six sections, plus "mast". `page(m)` draws a
model's Crew page and returns all six sections joined, for tests that look for text anywhere
on it. `run(...)` is govdraw.run for Crew. Tests skip when node isn't installed (`NODE`).
"""
from __future__ import annotations

import json

import crewpage
import govdraw

NODE = govdraw.NODE


def run(data: dict, **kw) -> dict:
    return govdraw.run(data, page=crewpage, **kw)


def draw(data: dict) -> dict:
    """{section: html} as crew.js draws `data`, plus "mast"."""
    out = run(data)["first"]
    out.pop("stale")
    # The fake DOM escapes ' as html.escape() does; the old renderers wrote it as is.
    return {k: v.replace("&#x27;", "'") for k, v in out.items()}


def page_data(m: dict) -> dict:
    """The data a model's Crew page carries, as JSON would hand it to the script."""
    import state
    return json.loads(json.dumps(crewpage.data(state.state(m))))


def page(m: dict) -> str:
    """A model's Crew page as crew.js draws it: the six sections, joined."""
    d = draw(page_data(m))
    return "\n".join(d[s] for s in crewpage.SECTIONS)


def base(**over) -> dict:
    """A minimal page slice: every key empty, with `over` on top."""
    d = {"schema": 1, "built_at": "2026-11-05T10:00:00Z", "repo": "o/r",
         "owner_last_acted": {"status": "unknown"}, "idle_minutes": 15, "sessions": [], "crew_roles": [],
         "floor": None, "watcher": None, "reviewer_runs": {"window_days": 7, "unreviewed": [], "error": "x"},
         "grants": None, "effort": None, "crew_work": None, "spend_method": "M."}
    d.update(over)
    return json.loads(json.dumps(d, default=str))
