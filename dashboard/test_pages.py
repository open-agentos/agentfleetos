"""Where every panel went when the Desk became three pages (#1113): Map · Crew · Governance.

PANELS lists every panel the seven older pages drew before #1113, by page. Each has a home on
Crew or Governance (HOMES: its page and section) or is retired (RETIRED: where what it showed
went, or why it went). The tests swap each panel's renderer for a marker, draw the pages from
the fixtures the old pages' own tests used, and check that each marker lands in its home's
section and on no other page, and that no retired panel's marker or heading is drawn anywhere.
Governance's panels are drawn client-side (#1140, JS_HOMES): for those, the page must carry the
state.json key the panel draws from and its section be on that page alone.

Run: python3 -m unittest discover -s dashboard
"""
from __future__ import annotations

import json
import re
import sys
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import agents  # noqa: E402
import effort  # noqa: E402
import floor  # noqa: E402
import generate as g  # noqa: E402
import grants  # noqa: E402
import plan  # noqa: E402
import report  # noqa: E402
import reviewer_runs  # noqa: E402
import wire  # noqa: E402
from test_generate import PageTest  # noqa: E402
from test_live import desk_model  # noqa: E402

# Every panel on the pages before #1113, by page (the Work map and effort.html stay as they were).
PANELS = {
    "index.html": ("report", "plan", "trouble", "floor", "grants", "wire", "committee_desk", "effort",
                   "trends", "questions_went", "precedent", "past_committees", "pointer"),
    "operations.html": ("needs_you", "needs_tiles", "sessions", "open_prs", "reviewer", "v3_progress",
                        "spend_per_day"),
    "decisions.html": ("decision_log", "gov_questions", "committee_grids", "past_committee_grids"),
    "authority.html": ("authority_map",),
    "commissions.html": ("commissions",),
    "agents.html": ("agents",),
}

# panel -> (page, section id, the renderer drawing it as (module, function), keyword arguments
# that pick out this call). A panel's marker is "@@<panel>@@".
HOMES = {
    "agents": ("crew.html", "roles", (agents, "render"), {}),
    "floor": ("crew.html", "floor", (floor, "render"), {}),
    "sessions": ("crew.html", "sessions", (g, "session_rows"), {}),
    "reviewer": ("crew.html", "reviewer", (reviewer_runs, "render"), {}),
    "grants": ("crew.html", "grants", (grants, "render"), {}),
    "effort": ("crew.html", "effort", (effort, "render"), {}),
}

# Governance's panels are drawn client-side (#1140): panel -> (page, section id, the state.json
# key governance.js draws it from). The page must carry that key, and the section be its own.
JS_HOMES = {
    "decision_log": ("governance.html", "rulings", "governance"),
    "gov_questions": ("governance.html", "questions", "gov_questions"),
    "committee_desk": ("governance.html", "committees", "committee_desk"),
    "committee_grids": ("governance.html", "committees", "committee_views"),
    "past_committees": ("governance.html", "committees", "past_committees"),
    "past_committee_grids": ("governance.html", "committees", "committee_views"),
    "authority_map": ("governance.html", "authority", "authority"),
    "precedent": ("governance.html", "precedent", "precedent"),
    "trends": ("governance.html", "trends", "trends"),
    "questions_went": ("governance.html", "trends", "questions_went"),
}

# panel -> (where it went, a renderer to check is never drawn or None, text the old panel drew).
RETIRED = {
    "report": ("the Work map's Briefing and tape, and its asks in Needs you (#1114)", (report, "render"),
               "<h2>Today's report</h2>"),
    "plan": ("each Goal's view on the Work map (#1115)", (plan, "render"), '<section class="plan"'),
    "trouble": ("the Work map's strip and each Goal's view (#1114, #1115)", None, "<h2>Trouble</h2>"),
    "wire": ("the Work map's tape (#1114)", (wire, "render"), "<h2>The wire</h2>"),
    "pointer": ("the nav, Map · Crew · Governance", None, 'class="pointer"'),
    "needs_you": ("the Work map's Needs you list, from the same needs_you()", None, '<ol class="inbox">'),
    "needs_tiles": ("the Work map's strip; spent today is a total (GOV-0033)", None, "spent today"),
    "open_prs": ("each role's view on the Work map, and Needs you for those waiting on you", None,
                 "<h2>Open pull requests</h2>"),
    "v3_progress": ("retired: that phase is over", None, "v3 progress"),
    "spend_per_day": ("retired: it shows totals (GOV-0033)", None, "Spend per day"),
    "commissions": ("the Work map grouped by Goal; its drawer is each Goal's view (#1115)", None,
                    "<h1>Commissions</h1>"),
}


def marker(panel: str) -> str:
    return f"<p>@@{panel}@@</p>"


def sections(page: str) -> dict[str, str]:
    """Each top-level <section class="sec" id=...> by id."""
    return dict(re.findall(r'<section class="sec" id="([a-z]+)">(.*?)</section>\n?(?=<section class="sec"|<script|</main>)',
                           page, re.S))


class InventoryTest(unittest.TestCase):
    def test_every_panel_has_a_home_or_is_retired(self):
        panels = [p for ps in PANELS.values() for p in ps]
        self.assertEqual(len(panels), len(set(panels)))
        self.assertEqual(sorted(panels), sorted([*HOMES, *JS_HOMES, *RETIRED]))
        self.assertFalse((set(HOMES) | set(JS_HOMES)) & set(RETIRED))
        for page, *_ in [*HOMES.values(), *JS_HOMES.values()]:
            self.assertIn(page, dict(g.layout.PAGES))

    def test_the_old_pages_redirect(self):
        self.assertLessEqual(set(PANELS), set(g.REDIRECTS))


class PlacementTest(unittest.TestCase):
    """Each panel, drawn from the old pages' fixtures, lands once, in its home section."""

    def render(self, m: dict) -> dict[str, str]:
        by_fn: dict[tuple, list] = {}
        for panel, (_, _, (mod, fn), kw) in HOMES.items():
            by_fn.setdefault((mod, fn), []).append((panel, kw))
        for panel, (_, renderer, _) in RETIRED.items():
            if renderer:
                by_fn.setdefault(renderer, []).append((panel, {}))

        def fake(cases, orig):
            def draw(*a, **k):
                for panel, kw in cases:
                    if all(k.get(x) == v for x, v in kw.items()):
                        return marker(panel)
                return orig(*a, **k)
            return draw

        patches = [mock.patch.object(mod, fn, fake(cases, getattr(mod, fn))) for (mod, fn), cases in by_fn.items()]
        for p in patches:
            p.start()
        try:
            return g.render(m)
        finally:
            for p in patches:
                p.stop()

    def check(self, m: dict):
        pages = self.render(m)
        data = re.search(r'<script type="application/json" id="gov-data">(.*?)</script>', pages["governance.html"])
        carried = json.loads(data.group(1))
        for panel, (home, anchor, key) in JS_HOMES.items():
            with self.subTest(panel):
                self.assertIn(anchor, sections(pages[home]), f"{panel}: no {home}#{anchor}")
                self.assertIn(key, carried, f"{panel}: {home} doesn't carry {key}")
                for f, _ in g.layout.PAGES:
                    if f != home:
                        self.assertNotIn(f'id="{anchor}"', pages[f], f"{panel}'s section also on {f}")
        for panel, (home, anchor, *_) in HOMES.items():
            with self.subTest(panel):
                self.assertIn(marker(panel), sections(pages[home]).get(anchor, ""), f"{panel} not in {home}#{anchor}")
                # On no other of the three pages. (effort.html, Crew's drill-down, repeats the
                # Effort panel's empty state when there's no cache to drill into.)
                for f, _ in g.layout.PAGES:
                    if f != home:
                        self.assertNotIn(marker(panel), pages[f], f"{panel} also on {f}")
        for panel, (_, _, old) in RETIRED.items():
            with self.subTest(panel):
                for name, page in pages.items():
                    self.assertNotIn(marker(panel), page, f"{panel} on {name}")
                    self.assertNotIn(old, page, f"{panel} on {name}")

    def test_from_the_old_pages_fixtures(self):
        self.check(PageTest().model())
        self.check(desk_model())


class OnePlaceTest(unittest.TestCase):
    def test_no_panel_box_or_section_is_on_two_pages(self):
        pages = g.render(desk_model())
        seen: dict[str, str] = {}
        for name, page in pages.items():
            keys = ([f"box {k}" for k in re.findall(r'data-panel="([a-z_]+)"', page)]
                    + [f"section {k}" for k in re.findall(r'<section class="sec" id="([a-z]+)"', page)])
            for key in keys:
                if key == "box mast":   # the masthead's build time and owner line, on every live page
                    continue
                self.assertNotIn(key, seen, f"{key} on {seen.get(key)} and {name}")
                seen[key] = name
        self.assertEqual(set(sections(pages["crew.html"])), {"roles", "floor", "sessions", "reviewer", "grants", "effort"})
        self.assertEqual(set(sections(pages["governance.html"])),
                         {"rulings", "questions", "committees", "authority", "precedent", "trends"})


if __name__ == "__main__":
    unittest.main()
