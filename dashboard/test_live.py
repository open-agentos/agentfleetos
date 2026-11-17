"""Tests for the desk's live refresh: dashboard/live.py and poll.js (#411), which Crew loads, and
Governance's own script, governance.js, which draws and refreshes from plain fields (#1140).
Run: python3 -m unittest discover -s dashboard"""
import base64
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import effort  # noqa: E402
import floor  # noqa: E402
import grants  # noqa: E402
import generate as g  # noqa: E402
import govdraw  # noqa: E402
import govpage  # noqa: E402
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


class TreeTest(unittest.TestCase):
    def test_elements_text_and_svg(self):
        t = live.tree('<p class="x">a &amp; <a href="https://github.com/o/r/issues/1">#1</a>'
                      '<br></p><svg viewBox="0 0 2 2" width="2"><rect x="1" y="0"/><title>t</title></svg>')
        self.assertEqual(t, [
            ["p", {"class": "x"}, "a & ", ["a", {"href": "https://github.com/o/r/issues/1"}, "#1"],
             ["br", {}]],
            ["svg", {"viewBox": "0 0 2 2", "width": "2"}, ["rect", {"x": "1", "y": "0"}],
             ["title", {}, "t"]]])

    def test_text_stays_text(self):
        # Escaped markup in repo text comes back as the characters, never as an element.
        self.assertEqual(live.tree("<span>&lt;script&gt;x&lt;/script&gt;</span>"),
                         [["span", {}, "<script>x</script>"]])

    def test_boolean_attribute_and_local_links(self):
        self.assertEqual(live.tree('<details open><summary>s</summary></details>'
                                   '<a href="decisions.html#x">d</a><a href="#y">y</a>'),
                         [["details", {"open": ""}, ["summary", {}, "s"]],
                          ["a", {"href": "decisions.html#x"}, "d"], ["a", {"href": "#y"}, "y"]])

    def test_refuses_what_isnt_allowed(self):
        for bad in ("<script>x</script>", "<img src=x>", "<iframe></iframe>", "<style>p{}</style>",
                    '<p onclick="x()">p</p>', '<a href="javascript:x()">a</a>',
                    '<a href="//evil.example/">a</a>', '<a href="http://x/">a</a>',
                    '<svg><foreignObject></foreignObject></svg>', "<rect></rect>",
                    "<p><b></p></b>", "<p>open", "<!DOCTYPE html>"):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                live.tree(bad)

    def test_a_bad_panel_is_none_not_a_failed_build(self):
        self.assertEqual(live.trees({"ok": "<p>a</p>", "bad": "<script></script>", "empty": ""}),
                         {"ok": [["p", {}, "a"]], "bad": None, "empty": []})


class EveryPanelTest(unittest.TestCase):
    """Every panel HTML the panels' own tests draw becomes a tree, so no panel silently
    stops refreshing when its markup grows a new tag or attribute."""

    def test_panel_fixtures_convert(self):
        failures = []

        def checked(fn):
            def wrapper(*a, **k):
                out = fn(*a, **k)
                try:
                    live.tree(out)
                except ValueError as e:
                    failures.append(f"{fn.__module__}.{fn.__name__}: {e}")
                return out
            return wrapper

        patches = [mock.patch.object(floor, "render", checked(floor.render)),
                   mock.patch.object(grants, "render", checked(grants.render)),
                   mock.patch.object(effort, "render", checked(effort.render))]
        for p in patches:
            p.start()
        try:
            suite = unittest.defaultTestLoader.loadTestsFromNames(
                ["test_floor", "test_generate", "test_grants", "test_effort"])
            result = unittest.TestResult()
            suite.run(result)
        finally:
            for p in patches:
                p.stop()
        self.assertTrue(result.wasSuccessful(), result.failures + result.errors)
        self.assertEqual(failures, [])


class PageTest(unittest.TestCase):
    """Crew carries the live refresh (#1113; the desk did, #411). Governance draws itself (#1140)."""
    LIVE = ("crew.html",)

    def setUp(self):
        self.m = desk_model()
        self.pages = g.render(self.m)
        self.panels = {"crew.html": g.crew_panels(self.m)}

    def test_csp_hash_matches_the_script(self):
        js = live.script()
        digest = base64.b64encode(hashlib.sha256(js.encode("utf-8")).digest()).decode()
        for name in self.LIVE:
            src, integrity = script_of(self.pages[name])
            self.assertEqual(src, "js/poll.js", name)   # same-origin, beside the page (#1106)
            csp = csp_of(self.pages[name])
            self.assertEqual(csp["script-src"], ["'self'", f"'sha256-{digest}'"], name)   # that script, nothing else
            self.assertEqual(integrity, f"sha256-{digest}", name)
            self.assertEqual(csp["default-src"], ["'none'"], name)
            self.assertEqual(csp["connect-src"], ["'self'"], name)

    def test_csp_comes_before_anything_it_governs(self):
        for name in self.LIVE:
            head = self.pages[name].split("</head>")[0]
            self.assertLess(head.index("Content-Security-Policy"), head.index("<style>"), name)

    def test_script_builds_nodes_never_markup_or_code(self):
        js = live.script()
        for bad in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "eval",
                    "Function(", "DOMParser", "createContextualFragment", "srcdoc", "import(",
                    "XMLHttpRequest", "localStorage", "cookie"):
            self.assertNotIn(bad, js, bad)
        self.assertEqual(re.findall(r'fetch\("([^"?]*)', js), ["state.json"])
        self.assertNotRegex(js, r"/\*[A-Z_]+\*/")   # every placeholder filled in
        self.assertIn('querySelectorAll("header.mast .live")', js)   # #402's mark

    def test_only_crew_polls_desk_trees(self):
        self.assertNotIn("<script", self.pages["effort.html"].lower())
        self.assertEqual(csp_of(self.pages["effort.html"])["script-src"], ["'none'"])
        self.assertNotIn("poll.js", self.pages["workmap.html"])
        self.assertNotIn("poll.js", self.pages["governance.html"])   # #1140

    def test_static_page_is_complete_without_the_script(self):
        # Each panel is drawn in full inside its box, and the meta refresh stays.
        for name in self.LIVE:
            page = self.pages[name]
            for panel, fragment in self.panels[name].items():
                self.assertIn(f'<div data-panel="{panel}">{fragment}</div>', page, panel)
            self.assertIn('<meta http-equiv="refresh" content="300">', page, name)
            self.assertIn('<body data-built-at="2026-11-02T12:00:00Z">', page, name)
        self.assertIn("<h2>On the floor</h2>", self.pages["crew.html"])

    def test_the_masthead_keeps_its_page_name(self):
        # Only the mark, build time and owner line redraw, so each page keeps its own name.
        for name, title in (("crew.html", "Crew"), ("governance.html", "Governance")):
            head = self.pages[name].split('<header class="mast">')[1].split("</header>")[0]
            self.assertIn(f"AgentFleetOS · {title}</span>", head.split('data-panel="mast"')[0], name)
        self.assertNotIn("AgentFleetOS", json.dumps(st.state(self.m)["desk"]["mast"]))

    def test_state_carries_every_box_on_crew(self):
        s = st.state(self.m)
        boxes = set()
        for name in self.LIVE:
            boxes |= set(re.findall(r'data-panel="([^"]+)"', self.pages[name]))
        self.assertEqual(sorted(s["desk"]), sorted(boxes))
        self.assertTrue(all(isinstance(t, list) for t in s["desk"].values()), s["desk"])
        self.assertEqual(s["desk"]["floor"], live.tree(g.crew_panels(self.m)["floor"]))
        self.assertEqual(json.loads(json.dumps(s)), s)
        self.assertFalse(set(s["desk"]) & {"committee_desk", "past_committees", "precedent", "trends",
                                           "questions_went"})   # Governance's left the trees (#1140)


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
        self.assertNotIn("data-built-at", self.page)   # that's poll.js's


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


NODE = shutil.which("node")

# A fake DOM just big enough for poll.js: elements, text, fragments, two selectors,
# a fetch that serves whatever `served` holds, and a hand-cranked clock and interval.
HARNESS = r"""
const fs = require("fs");
const [scriptPath, casesPath] = process.argv.slice(2);
const js = fs.readFileSync(scriptPath, "utf8");
const cases = JSON.parse(fs.readFileSync(casesPath, "utf8"));
function el(tag, ns) {
  return { tag, ns: ns || null, attrs: {}, children: [], classes: new Set(),
    setAttribute(k, v) { this.attrs[k] = String(v); },
    getAttribute(k) { return k in this.attrs ? this.attrs[k] : null; },
    appendChild(c) { if (c.frag) { this.children.push(...c.children); } else { this.children.push(c); } return c; },
    removeChild(c) { this.children.splice(this.children.indexOf(c), 1); },
    get firstChild() { return this.children[0] || null; },
    classList: null };
}
function dump(n) { return n.text !== undefined ? n.text : [n.tag, n.attrs, ...n.children.map(dump)]; }
(async () => {
  const out = [];
  for (const c of cases) {
    const body = el("body"); body.attrs["data-built-at"] = c.page_built_at;
    const live = el("span"); live.classList = { toggle(k, on) { on ? live.classes.add(k) : live.classes.delete(k); } };
    const panel = el("div"); panel.attrs["data-panel"] = "floor"; panel.children.push({ text: "static" });
    let now = Date.parse(c.clock), tick = null, fetched = [];
    global.Date = class extends Date { static now() { return now; } };
    global.document = {
      body, hidden: false,
      createElement: (t) => el(t), createElementNS: (ns, t) => el(t, ns),
      createTextNode: (t) => ({ text: t }), createDocumentFragment: () => Object.assign(el("#frag"), { frag: true }),
      querySelectorAll: (s) => s === "[data-panel]" ? [panel] : s === "header.mast .live" ? [live] : [],
    };
    global.fetch = (url, opts) => { fetched.push([url.split("?")[0], opts.cache]);
      return Promise.resolve({ ok: true, json: () => Promise.resolve(c.served) }); };
    global.setInterval = (fn, ms) => { tick = fn; out.interval = ms; };
    new Function(js)();
    const staleAtLoad = live.classes.has("stale");
    now += c.advance_ms; tick();
    await new Promise((r) => setTimeout(r, 0)); await new Promise((r) => setTimeout(r, 0));
    out.push({ name: c.name, staleAtLoad, stale: live.classes.has("stale"), fetched,
      panel: panel.children.map(dump), built_at: body.attrs["data-built-at"] });
  }
  console.log(JSON.stringify(out));
})();
"""


@unittest.skipUnless(NODE, "node isn't installed")
class ScriptBehaviourTest(unittest.TestCase):
    """poll.js itself, run in node against a fake DOM."""

    def run_cases(self, cases):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "poll.js").write_text(live.script(), encoding="utf-8")
            (Path(d) / "cases.json").write_text(json.dumps(cases), encoding="utf-8")
            (Path(d) / "harness.js").write_text(HARNESS, encoding="utf-8")
            r = subprocess.run([NODE, str(Path(d) / "harness.js"), str(Path(d) / "poll.js"),
                                str(Path(d) / "cases.json")], capture_output=True, text=True, timeout=30)
        self.assertEqual(r.returncode, 0, r.stderr)
        return {c["name"]: c for c in json.loads(r.stdout)}

    def state(self, built_at, floor_tree):
        return {"schema": 1, "built_at": built_at, "desk": {"floor": floor_tree}}

    def test_refresh(self):
        new = [["h2", {}, "On the floor"], ["p", {"class": "x"}, "<b>not markup</b>"],
               ["svg", {"viewBox": "0 0 1 1"}, ["rect", {"x": "0"}]]]
        evil = [["p", {}, "ok"], ["script", {}, "alert(1)"]]
        bad_link = [["a", {"href": "javascript:alert(1)"}, "x"]]
        base = {"page_built_at": "2026-11-05T10:00:00Z", "clock": "2026-11-05T10:01:00Z",
                "advance_ms": 15000}
        got = self.run_cases([
            {**base, "name": "newer", "served": self.state("2026-11-05T10:01:00Z", new)},
            {**base, "name": "older", "served": self.state("2026-11-05T09:00:00Z", new)},
            {**base, "name": "script", "served": self.state("2026-11-05T10:01:00Z", evil)},
            {**base, "name": "link", "served": self.state("2026-11-05T10:01:00Z", bad_link)},
            {**base, "name": "stale", "clock": "2026-11-05T10:20:00Z",
             "served": self.state("2026-11-05T09:00:00Z", new)},
            {**base, "name": "fresh_again", "clock": "2026-11-05T10:20:00Z",
             "served": self.state("2026-11-05T10:19:00Z", new)},
        ])
        n = got["newer"]
        self.assertEqual(n["fetched"], [["state.json", "no-store"]])
        self.assertEqual(n["panel"], new)                     # redrawn as nodes; text stays text
        self.assertEqual(n["built_at"], "2026-11-05T10:01:00Z")
        self.assertFalse(n["stale"])
        self.assertEqual(got["older"]["panel"], ["static"])   # never moves backwards
        self.assertEqual(got["script"]["panel"], ["static"])  # a refused node keeps the panel
        self.assertEqual(got["link"]["panel"], ["static"])
        self.assertTrue(got["stale"]["staleAtLoad"])          # 20 minutes old: greyed
        self.assertTrue(got["stale"]["stale"])
        self.assertFalse(got["fresh_again"]["stale"])         # new data brings it back


if __name__ == "__main__":
    unittest.main()
