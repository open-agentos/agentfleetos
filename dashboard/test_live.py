"""Tests for the Desk's live refresh: dashboard/live.py's shared settings and CSP, and the pages'
own scripts, crew.js (#1139) and governance.js (#1140), which draw and refresh from plain
fields. poll.js and its node trees retired with #1135.
Run: python3 -m unittest discover -s dashboard"""
import base64
import hashlib
import json
import re
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import crewdraw  # noqa: E402
import crewpage  # noqa: E402
import generate as g  # noqa: E402
import govdraw  # noqa: E402
import govpage  # noqa: E402
import layout  # noqa: E402
import live  # noqa: E402
import state as st  # noqa: E402
from test_floor import model as floor_model  # noqa: E402
from test_generate import REPO, ev  # noqa: E402


def desk_model():
    return floor_model({"a": [ev("a", "working_on", 40, issue=1)],
                        "b": [ev("b", "heartbeat", 2, issue=392, tools=["Edit"])]})


def script_of(page: str) -> tuple[str, str]:
    """The one script tag's (src, integrity); a page carries no inline script (#1106)."""
    found = re.findall(r"<script\b[^>]*>.*?</script>", page, re.S)
    assert len(found) == 1, found
    m = re.fullmatch(r'<script src="([^"]+)" integrity="([^"]+)"></script>', found[0])
    assert m, found[0]
    return m[1], m[2]


def csp_of(page: str) -> dict[str, list[str]]:
    content = re.search(r'<meta http-equiv="Content-Security-Policy" content="([^"]*)">', page)[1]
    return {d.split()[0]: d.split()[1:] for d in content.split("; ")}


class PageTest(unittest.TestCase):
    """poll.js retired (#1135): each page draws itself and redraws in place; no page reloads itself."""

    def setUp(self):
        self.m = desk_model()
        self.pages = g.render(self.m)

    def test_no_page_loads_poll_js(self):
        for name, page in self.pages.items():
            self.assertNotIn("poll.js", page, name)
            self.assertNotIn("data-built-at", page, name)
        self.assertNotIn("poll.js", g.scripts())
        self.assertFalse(hasattr(live, "tree"))
        self.assertNotIn("desk", st.state(self.m))   # the node trees went with it
        self.assertNotIn("<script", self.pages["effort.html"].lower())
        self.assertEqual(csp_of(self.pages["effort.html"])["script-src"], ["'none'"])

    def test_csp_comes_before_anything_it_governs(self):
        for name in ("crew.html", "governance.html", "workmap.html"):
            head = self.pages[name].split("</head>")[0]
            self.assertLess(head.index("Content-Security-Policy"), head.index("<style>"), name)

    def test_no_page_reloads_itself(self):
        # The Work map, Crew and Governance redraw in place (#1138-#1140, #1135); effort.html has
        # no script and shows the build it came with.
        for name, page in self.pages.items():
            self.assertNotIn('http-equiv="refresh"', page, name)
        self.assertFalse(hasattr(layout, "REFRESH_SECONDS"))

    def test_state_json_carries_the_work_maps_other_parts(self):
        # What map.json doesn't carry, so workmap.js can redraw it from state.json (#1135).
        d = st.state(self.m)["workmap"]
        self.assertEqual(set(d), {"strip", "needs_extra", "scopes", "roles", "briefing", "tape", "memory"})
        self.assertEqual(json.loads(json.dumps(d)), d)   # plain JSON

    def test_the_masthead_keeps_its_page_name(self):
        # Only the mark, build time and owner line redraw, so each page keeps its own name.
        for name, title in (("crew.html", "Crew"), ("governance.html", "Governance"), ("workmap.html", "Map")):
            head = self.pages[name].split('<header class="mast">')[1].split("</header>")[0]
            self.assertIn(f"AgentFleetOS · {title}</span>", head.split('data-panel="mast"')[0], name)


class CrewPageTest(unittest.TestCase):
    """crew.html draws itself client-side from plain fields (#1139)."""

    def setUp(self):
        self.m = desk_model()
        self.page = g.render(self.m)["crew.html"]

    def test_loads_only_its_own_script_by_hash(self):
        js = crewpage.script()
        digest = base64.b64encode(hashlib.sha256(js.encode("utf-8")).digest()).decode()
        tags = re.findall(r'<script src="([^"]+)" integrity="([^"]+)"></script>', self.page)
        self.assertEqual(tags, [("js/crew.js", f"sha256-{digest}")])
        csp = csp_of(self.page)
        self.assertEqual(csp["script-src"], ["'self'", f"'sha256-{digest}'"])
        self.assertEqual(csp["default-src"], ["'none'"])
        self.assertEqual(csp["connect-src"], ["'self'"])
        self.assertNotIn('http-equiv="refresh"', self.page)   # it redraws in place (#1135)

    def test_carries_plain_data_not_trees_or_html(self):
        block = re.search(r'<script type="application/json" id="crew-data">(.*?)</script>', self.page, re.S)[1]
        self.assertNotIn("<", block)   # escaped: no title can close the block
        data = json.loads(block)
        self.assertEqual(data, json.loads(json.dumps(crewpage.data(st.state(self.m)))))
        self.assertNotIn("desk", data)
        for key in crewpage.KEYS:
            self.assertIn(key, data)
        # Each session's spend comes from state.json's sessions (#1153); the page adds only the method.
        self.assertNotIn("spend", data)
        self.assertEqual(set(data) - set(crewpage.KEYS), {"spend_method"})

    def test_script_reads_plain_fields_never_markup_or_code(self):
        js = crewpage.script()
        for bad in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "eval",
                    "Function(", "DOMParser", "createContextualFragment", "srcdoc", "import(",
                    "XMLHttpRequest", "localStorage", "cookie", "poll.js"):
            self.assertNotIn(bad, js, bad)
        self.assertNotRegex(js, r'\.desk\b|\["desk"\]')   # never the node trees
        self.assertEqual(re.findall(r'fetch\("([^"?]*)', js), ["state.json"])
        self.assertNotRegex(js, r"/\*[A-Z_]+\*/")   # every placeholder filled in

    def test_shell_has_every_section_empty_and_says_it_needs_javascript(self):
        for sec in crewpage.SECTIONS:
            self.assertIn(f'<section class="sec" id="{sec}"></section>', self.page)
        self.assertIn('Crew needs JavaScript. The sessions\' tracking issues and the pull requests are on '
                      f'<a href="https://github.com/{REPO}/issues">GitHub</a>', self.page)   # GOV-0051
        self.assertNotIn("data-panel=\"floor\"", self.page)


@unittest.skipUnless(crewdraw.NODE, "node isn't installed")
class CrewScriptTest(unittest.TestCase):
    """crew.js itself, run in node against a fake DOM."""
    BASE = "2026-11-05T10:00:00Z"
    SESSION = {"session_id": "abcdef0123", "role": "builder", "model": "m", "status": "active", "issue": 7,
               "pr": None, "gov_question": None, "last_event": "heartbeat", "last_ts": "2026-11-05T09:59:00Z",
               "started_ts": "2026-11-05T09:00:00Z", "tracking_issue": 50, "issue_title": "<b>not markup</b>"}

    def test_draws_at_load_then_only_newer_data(self):
        page = crewdraw.base(built_at=self.BASE)
        newer = crewdraw.base(built_at="2026-11-05T10:01:00Z", sessions=[self.SESSION | {"cost": 1.2}])
        del newer["spend_method"]   # state.json doesn't carry it
        got = crewdraw.run(page, served=newer, clock="2026-11-05T10:01:00Z")
        self.assertIn("No live sessions.", got["first"]["sessions"])          # drawn from the page's block
        self.assertEqual(got["fetched"], [["state.json", "no-store"]])
        s = got["after"]["sessions"]
        self.assertIn("&lt;b&gt;not markup&lt;/b&gt;", s)                     # redrawn in place; text stays text
        self.assertIn('<td class="num">$1.20</td>', s)                        # spend redrawn in place (#1153)
        self.assertIn("2m ago", s)
        self.assertIn('datetime="2026-11-05T10:01:00Z"', got["after"]["mast"])
        older = crewdraw.run(page, served={**newer, "built_at": "2026-11-05T09:00:00Z"}, clock="2026-11-05T10:01:00Z")
        self.assertEqual(older["after"]["sessions"], older["first"]["sessions"])   # never backwards
        junk = crewdraw.run(page, served={"schema": 1, "built_at": "2026-11-05T10:01:00Z"}, clock="2026-11-05T10:01:00Z")
        self.assertEqual(junk["after"], junk["first"])                         # not Crew's data: ignored

    def test_unsafe_links_are_text(self):
        grants_ = {"mode": "live", "mode_text": "The merger is live.", "read": True, "calls": [
            {"number": 7, "title": "t", "group": "merged", "queued": False, "reason": "r",
             "time": "2026-11-05T09:00:00Z", "link": "javascript:alert(1)"}]}
        html = crewdraw.draw(crewdraw.base(grants=grants_))["grants"]
        self.assertIn("merged under r, <time", html)
        self.assertNotIn("javascript:", html)

    def test_a_section_that_fails_keeps_what_it_showed(self):
        got = crewdraw.draw(crewdraw.base(crew_work={"counts": {}, "lanes": None}))
        self.assertEqual(got["floor"], "static")   # the rest still draw
        self.assertIn("<h2>Sessions</h2>", got["sessions"])

    def test_spend_reads_as_spend_usd_writes_it(self):
        import spend
        costs = [None, 0, 0.004, 0.005, 0.01, 0.125, 0.375, 0.625, 2.875, 0.994, 0.995, 1.2, 15, 1234.5, 1234567.891]
        rows = [self.SESSION | {"session_id": f"s{i:09d}", "cost": c, "cap": 15.0, "over_cap": i == 11}
                for i, c in enumerate(costs)]
        html = crewdraw.draw(crewdraw.base(sessions=rows))["sessions"]
        got = re.findall(r'<td class="num">([^<]*)', html)
        self.assertEqual(got, [spend.usd(c).replace("<", "&lt;") for c in costs])
        self.assertEqual(html.count("over cap $15.00"), 1)

    def test_greys_the_live_mark_when_stale(self):
        page = crewdraw.base(built_at=self.BASE)
        got = crewdraw.run(page, served=crewdraw.base(built_at=self.BASE), clock="2026-11-05T10:20:00Z")
        self.assertTrue(got["after"]["stale"])
        got = crewdraw.run(page, served=crewdraw.base(built_at="2026-11-05T10:19:00Z"), clock="2026-11-05T10:20:00Z")
        self.assertFalse(got["after"]["stale"])


class GovernancePageTest(unittest.TestCase):
    """governance.html draws itself client-side from plain fields (#1140)."""

    def setUp(self):
        self.m = desk_model()
        self.page = g.render(self.m)["governance.html"]

    def test_loads_only_its_own_script_by_hash(self):
        js = govpage.script()
        digest = base64.b64encode(hashlib.sha256(js.encode("utf-8")).digest()).decode()
        tags = re.findall(r'<script src="([^"]+)" integrity="([^"]+)"></script>', self.page)
        self.assertEqual(tags, [("js/governance.js", f"sha256-{digest}")])
        csp = csp_of(self.page)
        self.assertEqual(csp["script-src"], ["'self'", f"'sha256-{digest}'"])
        self.assertEqual(csp["connect-src"], ["'self'"])

    def test_carries_plain_data_not_trees_or_html(self):
        block = re.search(r'<script type="application/json" id="gov-data">(.*?)</script>', self.page, re.S)[1]
        self.assertNotIn("<", block)   # escaped: no title can close the block
        data = json.loads(block)
        self.assertEqual(data, json.loads(json.dumps(govpage.data(st.state(self.m)))))
        self.assertNotIn("desk", data)
        for key in govpage.KEYS:
            self.assertIn(key, data)

    def test_script_reads_plain_fields_never_markup_or_code(self):
        js = govpage.script()
        for bad in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "eval",
                    "Function(", "DOMParser", "createContextualFragment", "srcdoc", "import(",
                    "XMLHttpRequest", "localStorage", "cookie", "poll.js"):
            self.assertNotIn(bad, js, bad)
        self.assertNotRegex(js, r'\.desk\b|\["desk"\]')   # never the node trees
        self.assertEqual(re.findall(r'fetch\("([^"?]*)', js), ["state.json"])
        self.assertNotRegex(js, r"/\*[A-Z_]+\*/")   # every placeholder filled in

    def test_shell_has_every_section_empty_and_says_it_needs_javascript(self):
        for sec in govpage.SECTIONS:
            self.assertIn(f'<section class="sec" id="{sec}"></section>', self.page)
        self.assertIn('Governance needs JavaScript. The rulings, jurisdictions and questions are on '
                      f'<a href="https://github.com/{REPO}/tree/main/governance">GitHub</a>', self.page)   # GOV-0051
        head = self.page.split('<header class="mast">')[1].split("</header>")[0]
        self.assertIn("AgentFleetOS · Governance</span>", head.split('data-panel="mast"')[0])
        self.assertNotIn("data-built-at", self.page)   # poll.js's, retired (#1135)


@unittest.skipUnless(govdraw.NODE, "node isn't installed")
class GovernanceScriptTest(unittest.TestCase):
    """governance.js itself, run in node against a fake DOM."""
    BASE = "2026-11-05T10:00:00Z"

    def served(self, built_at, **over):
        return govdraw.base(built_at=built_at, **over)

    def test_draws_at_load_then_only_newer_data(self):
        page = govdraw.base(built_at=self.BASE)
        newer = self.served("2026-11-05T10:01:00Z", gov_questions=[{
            "number": 7, "title": "<b>not markup</b>", "url": "https://github.com/o/r/issues/7", "labels": [],
            "domain": None, "shape": None, "shape_suggested": False, "blocking": None,
            "created_ts": "2026-11-05T09:00:00Z", "ttl": None, "ttl_date": None, "days_left": None,
            "past_ttl": False, "waiting": []}])
        got = govdraw.run(page, served=newer, clock="2026-11-05T10:01:00Z")
        self.assertIn("Open gov questions (0)", got["first"]["questions"])   # drawn from the page's block
        self.assertEqual(got["fetched"], [["state.json", "no-store"]])
        q = got["after"]["questions"]
        self.assertIn("Open gov questions (1)", q)                            # redrawn in place
        self.assertIn("&lt;b&gt;not markup&lt;/b&gt;", q)                    # text stays text
        self.assertIn("1h ago", q)
        self.assertIn('datetime="2026-11-05T10:01:00Z"', got["after"]["mast"])
        older = govdraw.run(page, served=self.served("2026-11-05T09:00:00Z", gov_questions=newer["gov_questions"]),
                            clock="2026-11-05T10:01:00Z")
        self.assertEqual(older["after"]["questions"], older["first"]["questions"])   # never backwards
        junk = govdraw.run(page, served={"schema": 1, "built_at": "2026-11-05T10:01:00Z"}, clock="2026-11-05T10:01:00Z")
        self.assertEqual(junk["after"], junk["first"])                        # not Governance's data: ignored

    def test_unsafe_links_are_text(self):
        q = {"number": 7, "title": "t", "url": "javascript:alert(1)", "labels": [], "domain": None, "shape": None,
             "shape_suggested": False, "blocking": None, "created_ts": None, "ttl": None, "ttl_date": None,
             "days_left": None, "past_ttl": False, "waiting": []}
        html = govdraw.draw(govdraw.base(gov_questions=[q]))["questions"]
        self.assertIn("<td>#7 t</td>", html)
        self.assertNotIn("javascript:", html)

    def test_a_section_that_fails_keeps_what_it_showed(self):
        got = govdraw.draw(govdraw.base(authority={"error": None, "domains": None}))
        self.assertEqual(got["authority"], "static")   # the rest still draw
        self.assertIn("<h2>Rulings</h2>", got["rulings"])

    def test_greys_the_live_mark_when_stale(self):
        page = govdraw.base(built_at=self.BASE)
        got = govdraw.run(page, served=self.served(self.BASE), clock="2026-11-05T10:20:00Z")
        self.assertTrue(got["after"]["stale"])
        got = govdraw.run(page, served=self.served("2026-11-05T10:19:00Z"), clock="2026-11-05T10:20:00Z")
        self.assertFalse(got["after"]["stale"])


if __name__ == "__main__":
    unittest.main()
