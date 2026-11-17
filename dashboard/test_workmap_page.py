"""Tests for the Work map page (#1082). Run: python3 -m unittest discover -s dashboard"""
from __future__ import annotations

import datetime as dt
import json
import re
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import generate as g  # noqa: E402
import layout  # noqa: E402
import live  # noqa: E402
import workmap_page as wp  # noqa: E402
from test_bridge import NOW, REPO, model as bridge_model  # noqa: E402


def row(n, title="t", cost=1.0, **kw):
    return {"issue": n, "ref": f"#{n}", "title": title, "cost": cost, "tokens": 10, "lines": 0,
            "outcomes": 0, "days": [{"date": "2026-11-12", "cost": cost, "outcomes": 0}], **kw}


def model(**over) -> dict:
    m = bridge_model()
    m["workmap"] = {"desk": {"schema": 1, "built_at": "2026-11-12T12:00:00Z", "repo": REPO,
                             "method": "list-price equivalent",
                             "windows": {"hour": [], "day": [row(10, "a </script><b>x</b> & y")],
                                         "week": [row(10), row(11)]}}}
    m.update(over)
    return m


def json_block(page: str) -> dict:
    found = re.search(r'<script type="application/json" id="wm-data">(.*?)</script>', page, re.S)
    return json.loads(found.group(1))


class PageTest(unittest.TestCase):
    def test_one_script_allowed_by_its_hash(self):
        page = wp.page(model(), "t", "")
        scripts = re.findall(r"<script>(.*?)</script>", page, re.S)
        self.assertEqual(scripts, [wp.script()])
        self.assertIn(f"script-src {live.script_hash(wp.script())};", page)
        self.assertNotIn("data-built-at", page)   # no live refresh: that's the desk's

    def test_script_builds_nodes_without_html_parsing(self):
        js = re.sub(r"//[^\n]*", "", wp.script())   # the code, not its comments
        for bad in ("innerHTML", "outerHTML", "insertAdjacentHTML", "eval(", "new Function", "fetch(",
                    "XMLHttpRequest", "document.write"):
            self.assertNotIn(bad, js)
        self.assertIn("localStorage", js)
        self.assertIn("try {", js)   # storage is optional

    def test_data_block_carries_the_windows_without_days_and_cannot_close_early(self):
        page = wp.page(model(), "t", "")
        self.assertNotIn("</script><b>", page)
        d = json_block(page)
        self.assertEqual(set(d["windows"]), {"hour", "day", "week"})
        self.assertEqual(d["windows"]["day"][0]["title"], "a </script><b>x</b> & y")
        self.assertNotIn("days", d["windows"]["day"][0])

    def test_no_total_anywhere(self):
        """GOV-0033: per-issue figures only; no amount summed across issues, in the page or its data."""
        page = wp.page(model(), "t", "")
        self.assertNotRegex(wp.render(model()).lower(), r"\btotal")
        d = json_block(page)
        self.assertEqual(set(d), {"built_at", "method", "windows"})
        self.assertNotIn("$", page.split('id="wm-data"')[0])   # no amount in the drawn HTML

    def test_a_failed_read_says_why(self):
        d = json_block(wp.page(model(workmap={"error": "gh api graphql failed"}), "t", ""))
        self.assertEqual(d, {"error": "gh api graphql failed"})
        self.assertEqual(json_block(wp.page(model(workmap=None), "t", "")),
                         {"error": "no map data in this build"})

    def test_controls_with_their_defaults(self):
        html = wp.controls_html()
        for label, opts in (("Group by", "Effort Goal Role Stage"), ("Size", "Cost Tokens Lines changed"),
                            ("Colour", "Yield Velocity Change"), ("Window", "Hour Day Week Month")):
            group = re.search(rf'aria-label="{label}">(.*?)</div>', html).group(1)
            self.assertEqual(re.findall(r">([^<]+)</button>", group), opts.split(" ") if label != "Size"
                             else ["Cost", "Tokens", "Lines changed"])
        pressed = re.findall(r'data-k="(\w+)" data-v="(\w+)" aria-pressed="true"', html)
        self.assertEqual(dict(pressed), wp.DEFAULTS)
        self.assertEqual(wp.DEFAULTS, {"group": "effort", "size": "cost", "colour": "yield", "window": "day"})

    def test_layout_map_then_briefing_then_lists(self):
        html = wp.render(model())
        order = [html.index(x) for x in ("<h1>Work map</h1>", 'class="wm-keyline"', 'class="wm-ctls"',
                                         'id="wm-crumb"', 'id="wm-map"', 'id="wm-legend"', 'aria-label="Selected"',
                                         'aria-label="Briefing"', 'aria-label="Lists"')]
        self.assertEqual(order, sorted(order))
        self.assertIn("with JavaScript off", html)

    def test_links_to_the_bridge_in_the_left_column_and_footer(self):
        page = wp.page(model(), "t", "")
        nav = re.search(r'<nav class="br-nav".*?</nav>', page, re.S).group(0)
        self.assertIn('href="bridge.html"', nav)
        self.assertIn('aria-current="page">Work map', nav)
        foot = re.search(r'<footer class="foot">.*?</footer>', page, re.S).group(0)
        self.assertIn('href="bridge.html"', foot)
        self.assertEqual(layout.PAGES[0], ("workmap.html", "Work map"))
        for href in re.findall(r'href="([^"]+)"', page):
            self.assertRegex(href, r"^(https://github\.com/|[a-z]+\.html)")


class BriefingTest(unittest.TestCase):
    """Moved from test_bridge.py with the Briefing (#1082)."""

    def test_shown_whole_with_its_link(self):
        html = wp.render(model())
        self.assertIn("<p><b>The Desk (M3).</b> The Bridge is &lt;the&gt; front page.</p>", html)
        self.assertIn("<p>3 decisions wait on the Bridge.</p>", html)
        self.assertIn(f'<a href="https://github.com/{REPO}/issues/249#c2">Thu 11-12, 09:00</a>', html)
        self.assertIn('class="br-briefbody"', html)
        self.assertNotIn("None yet today", html)

    def test_an_older_briefing_says_so(self):
        m = model()
        m["report"]["briefing"]["day"] = NOW.date() - dt.timedelta(days=1)
        self.assertIn("None yet today; this is the newest.", wp.render(m))

    def test_none(self):
        self.assertIn("No briefing from the lead in the last few days.", wp.render(model(report=None)))


class GenerateTest(unittest.TestCase):
    def test_map_data_feeds_the_page_and_map_json(self):
        import tempfile
        from test_workmap import gathered
        gd = gathered()
        wm = g.map_data(gd["data"], gd["model"], NOW, fetch_prs=lambda repo, since: [])
        self.assertIn("desk", wm)
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(g.save_map(wm, Path(d)), "wrote map.json")
            self.assertTrue((Path(d) / "map.json").is_file())

        def fail(repo, since):
            raise RuntimeError("no")
        bad = g.map_data(gd["data"], gd["model"], NOW, fetch_prs=fail)
        self.assertEqual(bad, {"error": "no"})
        with tempfile.TemporaryDirectory() as d:
            self.assertIn("not written", g.save_map(bad, Path(d)))
            self.assertFalse((Path(d) / "map.json").exists())


if __name__ == "__main__":
    unittest.main()
