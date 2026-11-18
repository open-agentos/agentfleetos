"""Tests for the Work map's strip and tape (#1114), which retired the Bridge.
Run: python3 -m unittest discover -s dashboard"""
from __future__ import annotations

import datetime as dt
import json
import re
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import strip  # noqa: E402
import workmap_page as wp  # noqa: E402

# The Bridge's own test fixtures (test_bridge.py, #926), kept for the Work map's tests.
REPO = "o/r"
OWNER = "owner"
NOW = dt.datetime(2026, 11, 12, 12, 0, tzinfo=dt.timezone.utc)
TROUBLE = json.loads((HERE.parent / "launcher" / "testdata" / "trouble.json").read_text())


def scope(n, title, progress=(), stuck=(), waiting=(), authority=(), date_missed=False):
    return {"ref": f"{REPO}#{n}", "type": "Goal", "title": title, "url": f"https://github.com/{REPO}/issues/{n}",
            "date": None, "date_missed": date_missed,
            "progress": [{"criterion": c, "status": s, "detail": ""} for c, s in progress],
            "stuck": list(stuck), "waiting": list(waiting), "authority": list(authority)}


def item(ref, reason, hours, url=None):
    since = (NOW - dt.timedelta(hours=hours)).isoformat()
    return {"kind": "pr", "ref": ref, "url": url or f"https://github.com/{REPO}/pull/{ref.split('#')[-1]}",
            "reason": reason, "since": since, "age_hours": hours}


def event(kind, action, n, hours, actor=OWNER, **payload):
    p = {"action": action, "issue": {"number": n, "html_url": f"https://github.com/{REPO}/issues/{n}"}, **payload}
    return {"type": kind, "actor": {"login": actor}, "payload": p,
            "created_at": (NOW - dt.timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%SZ")}


def model(**over) -> dict:
    trouble = {"authority_hours": 24, "outside": {"stuck": [], "waiting": [], "authority": []},
               "scopes": [
                   scope(685, "M3: The Desk shows the plan and the report",
                         progress=[("state questions", "met"), ("fixture test", "progress")],
                         waiting=[item("PR #930", "overstep: needs the owner", 5)],
                         authority=[item("PR #925", "merged under GOV-0027", 3)]),
                   scope(686, "M4: Readiness review", progress=[("drill", "failing")],
                         stuck=[item("PR #894", "changes requested, no push, nothing restarts it", 30)]),
                   scope(683, "M1: Daily report runs without the owner", progress=[("report", "met")])]}
    m = {"repo": REPO, "now": NOW, "trouble": trouble,
         "floor": {"cards": [{"role": "builder"}], "idle": [{"role": "planner"}]},
         "sessions": [{"status": "active"}, {"status": "idle"}, {"status": "stopped"}],
         "gov": [{"number": 901, "title": "Which login may the desk use?", "url": f"https://github.com/{REPO}/issues/901",
                  "labels": [], "created_ts": NOW - dt.timedelta(days=3), "ttl": "2026-11-20", "waiting": []},
                 {"number": 902, "title": "Ruled already", "url": "u", "labels": ["gov:ruled"],
                  "created_ts": NOW, "ttl": None, "waiting": []}],
         "report": {"state": "posted", "daily_at": dt.time(9, 0),
                    "report": {"line": "**Daily report, Thu 11-12.** Two merged.", "url": f"https://github.com/{REPO}/issues/249#c1",
                               "posted": NOW - dt.timedelta(hours=3), "asks": [{"lead": "a"}]},
                    "briefing": {"day": NOW.date(), "posted": NOW - dt.timedelta(hours=3),
                                 "url": f"https://github.com/{REPO}/issues/249#c2", "line": "Briefing, Thu 2026-11-12",
                                 "paras": ["**The Desk (M3).** The Bridge is <the> front page.",
                                           "3 decisions wait on the Bridge."]}},
         "merged": [{"number": 925, "title": "Desk: trouble panel", "url": f"https://github.com/{REPO}/pull/925",
                     "author": "productswarm-builder[bot]", "merged_at": "2026-11-12T09:30:00Z"},
                    {"number": 920, "title": "Brief: state questions", "url": f"https://github.com/{REPO}/pull/920",
                     "author": "productswarm-designer[bot]", "merged_at": "2026-11-11T16:00:00Z"},
                    {"number": 800, "title": "old", "url": "u", "author": "productswarm-builder[bot]",
                     "merged_at": "2026-10-01T00:00:00Z"},
                    {"number": 921, "title": "owner's own", "url": "u", "author": OWNER,
                     "merged_at": "2026-11-12T10:00:00Z"}],
         "activity": {"events": [
             event("IssuesEvent", "labeled", 903, 1, label={"name": "ready"}),
             event("IssueCommentEvent", "created", 888, 2,
                   comment={"html_url": f"https://github.com/{REPO}/issues/888#c2"}),
             event("IssuesEvent", "labeled", 5, 1, actor="someone-else", label={"name": "ready"}),
             {"type": "CreateEvent", "actor": {"login": OWNER}, "payload": {"ref_type": "branch", "ref": "x"},
              "created_at": "2026-11-12T11:00:00Z"}]},
         "plan": None, "prs": [{"number": 930, "title": "Fix the merger"}], "issue_titles": {}}
    return m | over



def page_model(**over) -> dict:
    m = model(**over)
    m["workmap"] = {"desk": {"schema": 1, "built_at": "2026-11-12T12:00:00Z", "repo": REPO, "method": "m",
                             "windows": {"hour": [], "day": [{"issue": 903, "ref": "#903", "title": "On the map",
                                                             "cost": 1.0, "tokens": 5, "lines": 0, "outcomes": 0,
                                                             "days": []}], "week": []}}}
    return m


def json_block(page: str) -> dict:
    return json.loads(re.search(r'<script type="application/json" id="wm-data">(.*?)</script>', page, re.S).group(1))


def tape_of(page: str) -> str:
    return re.search(r'<section class="tp".*?</section>', page, re.S).group(0)


# What the Bridge showed on these fixtures: bridge.build()'s output, recorded by the first
# commit of #1114 while bridge.py was still there, before its render code went.
BRIDGE = {"status": {"commissions": 3, "flagged": 1, "working": 1, "agents": 2, "authority": 1},
          "decisions": ["#901", "PR #930", "Ask"],
          "report_urls": ["https://github.com/o/r/pull/925", "https://github.com/o/r/issues/249#c1",
                          "https://github.com/o/r/pull/920", "https://github.com/o/r/pull/894"],
          "order_urls": ["https://github.com/o/r/issues/903", "https://github.com/o/r/issues/888#c2"],
          "flights": ["685", "686", "683"]}


class BridgeItemsOnTheWorkMapTest(unittest.TestCase):
    """Every item the Bridge showed appears on /: in a list, the Briefing or the tape
    (#1114's first criterion). In flight is each Goal's criteria, shown when it is selected
    (FEAT-13, #1115), from the page's `scopes`."""

    def setUp(self):
        self.page = wp.page(page_model(), "t", "", OWNER)
        self.data = json_block(self.page)

    def test_decisions_are_in_the_needs_you_list(self):
        self.assertEqual([d["ref"] for d in self.data["needs_extra"]], BRIDGE["decisions"])

    def test_reports_and_orders_are_on_the_tape(self):
        tape = tape_of(self.page)
        for url in BRIDGE["report_urls"] + BRIDGE["order_urls"]:
            self.assertIn(f'href="{url}"', tape)
        self.assertIn("PR #894 is stuck", tape)

    def test_in_flight_is_each_goals_selection(self):
        self.assertEqual(sorted(self.data["scopes"]), sorted(BRIDGE["flights"]))

    def test_the_briefing_is_on_the_page(self):
        self.assertIn('aria-label="Briefing"', self.page)
        self.assertIn("3 decisions wait on the Bridge.", self.page)


class StripTest(unittest.TestCase):
    def test_counts_and_what_the_picks_outline(self):
        s = strip.strip(model())
        self.assertEqual((s["scopes"], s["flagged"], s["decisions"], s["working"], s["agents"], s["authority"]),
                         (3, [686], 3, 1, 2, 1))
        self.assertEqual(s["oldest"], "3d")
        self.assertEqual(s["decision_refs"], ["#901"])   # PR #930 closes nothing known here

    def test_a_pr_waiting_outlines_the_issues_it_closes(self):
        m = model(prs=[{"number": 930, "title": "Fix the merger", "closes": [{"number": 77}]}])
        self.assertEqual(strip.strip(m)["decision_refs"], ["#77", "#901"])

    def test_no_strip_on_the_page(self):
        # The owner took the counts line off the top of the Work map; its counts stay in state.json.
        page = wp.page(page_model(), "t", "", OWNER)
        self.assertNotIn('<section class="sp"', page)
        order = [page.index(x) for x in ("<h1>Work map</h1>", 'class="wm-ctls"',
                                         'aria-label="Lists"', '<section class="tp"')]
        self.assertEqual(order, sorted(order))


class TapeTest(unittest.TestCase):
    def test_newest_first_with_a_role_or_owner_and_a_link(self):
        items = strip.tape(model(), OWNER)
        times = [x["time"] for x in items]
        self.assertEqual(times, sorted(times, reverse=True))
        self.assertEqual([(x["who"], x["kind"]) for x in items],
                         [("owner", "ORDER"), ("owner", "ORDER"), ("builder", "SHIPPED"), ("planner", "REPORT"),
                          ("designer", "DELIVERED"), ("watch", "STUCK")])
        self.assertTrue(all(x["url"] for x in items))

    def test_templates_not_text(self):
        items = {x["kind"]: x for x in strip.tape(model(), OWNER)}
        self.assertEqual(items["REPORT"]["text"], "Daily report posted: 1 ask of you")
        self.assertNotIn("Two merged", items["REPORT"]["text"])
        self.assertEqual(items["STUCK"]["text"], "PR #894 is stuck, under M4")

    def test_late_report_is_flagged(self):
        items = strip.tape(model(report={"state": "late", "daily_at": dt.time(9, 0), "report": None}), OWNER)
        late = [x for x in items if x["kind"] == "LATE"][0]
        self.assertTrue(late["flag"])
        self.assertEqual(late["text"], "No daily report yet today: it was due at 09:00")

    def test_branch_noise_and_others_acts_left_out(self):
        texts = [x["text"] for x in strip.orders(model(), OWNER)]
        self.assertEqual(texts, ["labelled #903 ready", "commented on #888"])

    def test_wire_items_with_who(self):
        w = {"items": [{"kind": "ruled", "time": NOW - dt.timedelta(minutes=5), "number": 901,
                        "text": "Owner ruled on #901", "link": f"https://github.com/{REPO}/issues/901"},
                       {"kind": "red", "time": NOW - dt.timedelta(minutes=9), "number": 930,
                        "text": "Reviewer requested changes on PR #930", "link": f"https://github.com/{REPO}/pull/930"}]}
        items = strip.tape(model(wire=w), OWNER)
        self.assertEqual([(x["who"], x["kind"], x["ref"]) for x in items[:2]],
                         [("owner", "RULED", "#901"), ("reviewer", "CHANGES", None)])

    def test_at_most_twenty(self):
        merged = [{"number": 1000 + i, "title": f"PR {i}", "url": f"https://github.com/{REPO}/pull/{1000 + i}",
                   "author": "productswarm-builder[bot]", "merged_at": (NOW - dt.timedelta(minutes=i)).isoformat()}
                  for i in range(30)]
        self.assertEqual(len(strip.tape(model(merged=merged), OWNER)), strip.MAX_TAPE)

    def test_an_item_about_an_issue_on_the_map_selects_it(self):
        tape = tape_of(wp.page(page_model(), "t", "", OWNER))
        self.assertIn('data-wm-sel="#903"', tape)       # on the map: picks it
        self.assertNotIn('data-wm-sel="#888"', tape)    # not on the map: a link only
        self.assertIn('href="https://github.com/o/r/issues/888#c2"', tape)

    def test_tape_is_text_not_markup(self):
        m = model(merged=[{"number": 925, "title": "<b>x</b>", "url": f"https://github.com/{REPO}/pull/925",
                           "author": "productswarm-builder[bot]", "merged_at": "2026-11-12T09:30:00Z"}])
        tape = tape_of(wp.page(dict(page_model(), merged=m["merged"]), "t", "", OWNER))
        self.assertNotIn("<b>x</b>", tape)
        self.assertIn("&lt;b&gt;x&lt;/b&gt;", tape)

    def test_empty(self):
        self.assertIn("Nothing on the tape yet.", strip.tape_html([], NOW, set()))


class FixedLayoutTest(unittest.TestCase):
    """The tape keeps its height and position: a fixed-height box that scrolls inside itself."""

    def test_css(self):
        import layout
        css = layout.CSS
        self.assertRegex(css, r"\.tp-box \{ height:360px; overflow-y:auto;")
        self.assertRegex(css, r'\.wm-list\[data-list="needs"\] \.wm-lol \{ overflow-y:auto; \}')


if __name__ == "__main__":
    unittest.main()
