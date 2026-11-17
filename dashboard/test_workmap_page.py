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
        scripts = re.findall(r"<script(?! type=\"application/json\")[^>]*>.*?</script>", page, re.S)
        h = live.script_hash(wp.script())
        self.assertEqual(scripts, [f'<script src="js/workmap.js" integrity="{h[1:-1]}"></script>'])
        self.assertIn(f"script-src 'self' {h};", page)
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

    def test_each_issues_14_days_once(self):
        """#1083: the Selected panel's 14 days, once per issue, whatever window it's in."""
        d = json_block(wp.page(model(), "t", ""))
        self.assertEqual(d["days"], {"dates": ["2026-11-12"], "of": {"#10": [[1.0, 0]], "#11": [[1.0, 0]]}})

    def test_no_total_anywhere(self):
        """GOV-0033: per-issue figures only; no amount summed across issues, in the page or its data."""
        page = wp.page(model(), "t", "")
        self.assertNotRegex(wp.render(model()).lower(), r"\btotal")
        d = json_block(page)
        self.assertEqual(set(d), {"built_at", "method", "windows", "days", "lists", "repo", "scopes", "roles"})
        for sc in d["scopes"].values():   # a Goal's view: no amount of its own, only its issues' rows
            self.assertFalse({"cost", "tokens", "total"} & set(sc))
        self.assertEqual(set(d["days"]), {"dates", "of"})   # per issue, keyed by ref
        self.assertNotIn("$", page.split('id="wm-data"')[0])   # no amount in the drawn HTML

    def test_a_failed_read_says_why(self):
        d = json_block(wp.page(model(workmap={"error": "gh api graphql failed"}), "t", ""))
        self.assertEqual(d["error"], "gh api graphql failed")
        self.assertNotIn("windows", d)
        self.assertEqual(json_block(wp.page(model(workmap=None), "t", ""))["error"], "no map data in this build")

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


class SelectedTest(unittest.TestCase):
    """The Selected panel (#1083)."""

    def panel(self) -> str:
        html = wp.render(model())
        return re.search(r'<aside class="wm-selected.*?</aside>', html, re.S).group(0)

    def test_empty_state_has_every_section_in_order(self):
        p = self.panel()
        self.assertIn("wm-sel-empty", p)
        order = [p.index(x) for x in ("wm-ss-head", "wm-ss-title", "wm-ss-stage", "wm-ss-days",
                                      "wm-ss-peers", "wm-ss-nums")]
        self.assertEqual(order, sorted(order))
        self.assertIn(wp.EMPTY, p)
        self.assertEqual(re.findall(r'class="wm-sgl">([^<]+)<', p), ["Queued", "Building", "In review", "Merging"])
        self.assertEqual(p.count('class="wm-bar"'), 14)
        self.assertEqual(re.findall(r'<dt>([^<]+)</dt>', p),
                         ["Cost", "Tokens", "Lines", "Outcomes", "Yield", "Change against usual"])
        self.assertEqual(re.findall(r'data-n="\w+">([^<]*)<', p), ["–"] * 6)

    def test_fixed_heights_so_selection_moves_nothing(self):
        css = layout.CSS
        sel = re.search(r"\.wm-selected \{([^}]*)\}", css).group(1)
        frame = re.search(r"\.wm-frame \{([^}]*)\}", css).group(1)
        height = re.search(r"height:([^;]+);", frame).group(1)
        self.assertIn(f"height:{height};", sel)   # the map's height
        self.assertIn("320px", sel)
        self.assertIn("overflow:hidden", sel)
        heights = {}
        for cls in ("head", "title", "stage", "deps", "days", "peers", "nums"):
            rule = re.search(rf"\.wm-ss-{cls} \{{([^}}]*)\}}", css).group(1)
            heights[cls] = int(re.search(r"(?<![-\w])height:(\d+)px", rule).group(1))
        # the sections, the padding and the border fit the smallest map height
        self.assertLessEqual(sum(heights.values()) + 24 + 2, 460)
        self.assertRegex(css, r"@media \(max-width:900px\) \{ \.wm-selected \{[^}]*height:460px")

    def test_script_fills_the_panel_from_the_map_and_lists(self):
        js = wp.script()
        for x in ("wm-sel", "data-wm-ref", "blocked_at", "idle this window", "needs you",
                  "emptyPanel", "Click a box, or an item in a list below, to see it here."):
            self.assertIn(x, js)
        self.assertEqual(wp.EMPTY, "Click a box, or an item in a list below, to see it here.")


class ListsTest(unittest.TestCase):
    """The six lists under the Briefing (#1084)."""

    def lists(self) -> str:
        html = wp.render(model())
        return re.search(r'<div class="wm-lists".*?</ol></section></div>', html, re.S).group(0)

    def test_six_lists_in_order_each_empty_until_drawn(self):
        h = self.lists()
        self.assertEqual(re.findall(r'data-list="(\w+)"', h), ["needs", "blocked", "spend", "hot", "quiet", "yield"])
        self.assertEqual(re.findall(r'<h3 class="wm-lh"><span>([^<]+)</span>', h),
                         ["NEEDS YOU", "BLOCKED", "SPEND, NO OUTCOME", "RUNNING HOT", "GONE QUIET", "BEST YIELD"])
        self.assertEqual(h.count('<span class="wm-lc">–</span>'), 6)
        self.assertEqual(h.count('<p class="wm-ld"'), 6)
        self.assertEqual(h.count('<ol class="wm-lol"></ol>'), 6)
        self.assertEqual(len(re.findall(r'data-empty="[^"]+"', h)), 6)
        import workmap
        self.assertEqual(tuple(k for k, *_ in wp.LISTS), workmap.LISTS)

    def test_page_data_carries_each_windows_lists_for_each_size(self):
        m = model()
        m["workmap"]["desk"]["windows"]["day"] = [row(10, needs_you=True, stage="blocked", baseline=0.5),
                                                  row(11, cost=0, tokens=0, baseline=None)]
        m["workmap"]["desk"]["windows"]["hour"] = [row(11, cost=0, tokens=0)]
        d = json_block(wp.page(m, "t", ""))
        self.assertEqual(set(d["lists"]), {"hour", "day", "week"})
        self.assertEqual(set(d["lists"]["day"]), {"cost", "tokens", "lines"})
        day = d["lists"]["day"]["cost"]
        self.assertEqual(day["needs"], [["#10", 1.0, None]])
        self.assertEqual(day["blocked"], [["#10", 1.0, None]])
        self.assertEqual(day["hot"], [["#10", 2.0, 0.5]])
        # idle in the hour after spend in the day: #10, not on the hour's map; #11 spent nothing
        self.assertEqual(d["lists"]["hour"]["cost"]["quiet"], [["#10", None, 1.0]])

    def test_fixed_heights_so_nothing_moves(self):
        css = layout.CSS
        ol = re.search(r"\.wm-lol \{([^}]*)\}", css).group(1)
        self.assertIn("height:250px", ol)
        self.assertIn("overflow:hidden", ol)
        self.assertIn("height:50px", re.search(r"\.wm-lol li \{([^}]*)\}", css).group(1))
        self.assertIn("height:50px", re.search(r"\.wm-li \{([^}]*)\}", css).group(1))
        for cls in ("wm-lh", "wm-ld"):
            rule = re.search(rf"\.{cls} \{{([^}}]*)\}}", css).group(1)
            self.assertRegex(rule, r"(?<![-\w])height:\d+px")
            self.assertIn("white-space:nowrap", rule)
        self.assertIn("text-overflow:ellipsis", re.search(r"\.wm-ln \{([^}]*)\}", css).group(1))

    def test_three_then_two_then_one_column(self):
        css = layout.CSS
        self.assertRegex(css, r"\.wm-lists \{[^}]*grid-template-columns:repeat\(3, minmax\(0, 1fr\)\)")
        self.assertRegex(css, r"@media \(max-width:900px\) \{ \.wm-lists \{ grid-template-columns:repeat\(2, minmax\(0, 1fr\)\)")
        self.assertRegex(css, r"@media \(max-width:600px\) \{ \.wm-lists \{ grid-template-columns:minmax\(0, 1fr\)")

    def test_script_draws_the_lists_and_selects_from_them(self):
        js = wp.script()
        for x in ("drawLists", "data-wm-ref", "var SHOW = 5", "st.zoom", "findRow(it[0])", '"idle"',
                  "wm-lf-you", "wm-lf-blk", '" · was "', "which the Desk doesn't read"):
            self.assertIn(x, js)
        self.assertIn("function draw() { drawMap(); drawLists(); }", js)
class GoalsRolesLinksTest(unittest.TestCase):
    """#1115 (FEAT-13): a Goal, Area or role in the Selected panel, what an issue holds up, and links."""

    def test_goal_data_from_the_commissions_drawer(self):
        d = json_block(wp.page(model(), "t", ""))
        self.assertTrue(d["scopes"])
        sc = next(iter(d["scopes"].values()))
        for k in ("number", "type", "title", "url", "criteria", "met", "stuck", "waiting", "authority", "subs"):
            self.assertIn(k, sc)
        for c in sc["criteria"]:
            self.assertNotIn("**", c["text"])

    def test_role_data_from_the_agents_drawer(self):
        d = json_block(wp.page(model(), "t", ""))
        self.assertEqual(set(d["roles"]["of"]), {r for r, _ in __import__("agents").ROLES})
        r = d["roles"]["of"]["builder"]
        for k in ("does", "on", "merged", "open", "changes", "sessions", "calls", "ask"):
            self.assertIn(k, r)
        self.assertFalse(d["roles"]["of"]["merger"]["ask"])

    def test_panel_swaps_views_inside_the_same_fixed_box(self):
        p = re.search(r'<aside class="wm-selected.*?</aside>', wp.render(model()), re.S).group(0)
        self.assertEqual(p.count("wm-ss-i "), 5)   # stage, deps, days, peers, numbers
        self.assertIn('id="wm-sel-alt"', p)
        self.assertIn('id="wm-sel-by"', p)
        self.assertIn('id="wm-sel-blocks"', p)
        css = layout.CSS
        self.assertIn(".wm-sel-other .wm-ss-i { display:none; }", css)
        self.assertRegex(css, r"\.wm-sel-other \.wm-alt \{[^}]*min-height:0; overflow:auto")

    def test_script_keeps_the_view_in_the_url(self):
        js = wp.script()
        for x in ("URLSearchParams", "pushState", "replaceState", "popstate", "#issue-", "goal-", "role-",
                  'window: "w"', "data-wm-sel", "wm-gi", "wm-dep", "blocked_by", "unmeasured: not known to be on track",
                  "Ask: "):
            self.assertIn(x, js)
        # the URL is read after localStorage, so it wins
        self.assertLess(js.index("localStorage.getItem"), js.index("readUrl();"))


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
