"""Tests for the crew's roles (#932; on Crew since #1113). Run: python3 -m unittest discover -s dashboard"""
from __future__ import annotations

import datetime as dt
import json
import re
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import agents  # noqa: E402
import crewdraw  # noqa: E402
from test_strip import NOW, REPO, model  # noqa: E402


def amodel(**over):
    m = model()
    m["sessions"] = [
        {"role": "builder", "status": "active", "issue": 894, "pr": None, "last_ts": NOW - dt.timedelta(minutes=5)},
        {"role": "builder", "status": "stopped", "issue": 890, "pr": 923, "last_ts": NOW - dt.timedelta(hours=3)},
        {"role": "analyst", "status": "blocked", "issue": 692, "pr": None, "gov_question": 905,
         "last_ts": NOW - dt.timedelta(hours=1)},
        {"role": "planner", "status": "idle", "issue": None, "pr": None, "last_ts": NOW - dt.timedelta(hours=2)},
        {"role": "reviewer", "status": "active", "never_acted": True, "issue": 1, "pr": None, "last_ts": NOW}]
    m["issue_titles"] = {894: "M4 drill", 692: "Checklist brief"}
    m["prs"] = [{"number": 940, "title": "Drill fixes", "url": f"https://github.com/{REPO}/pull/940",
                 "author": "app/productswarm-builder", "reviewer": {"at_head": "CHANGES_REQUESTED"}},
                {"number": 941, "title": "Spec", "url": "u", "author": "app/productswarm-designer",
                 "reviewer": {"at_head": "APPROVED"}}]
    m["grants"] = {"calls": [{"number": 925, "group": "merged", "reason": "GOV-0027", "link": f"https://github.com/{REPO}/pull/925#c"},
                             {"number": 940, "group": "left", "reason": "protected path", "link": f"https://github.com/{REPO}/pull/940#d"}]}
    m["report"]["issue"] = 249
    return m | over


class BuildTest(unittest.TestCase):
    def rows(self, **over):
        return {r["role"]: r for r in agents.build(amodel(**over))["rows"]}

    def test_one_row_per_role_working_first(self):
        rows = agents.build(amodel())["rows"]
        self.assertEqual(len(rows), len(agents.ROLES))
        self.assertEqual([r["role"] for r in rows if r["group"] == "working"], ["builder", "analyst", "merger"])

    def test_what_each_is_on_and_its_record(self):
        r = self.rows()
        self.assertEqual([x["ref"] for x in r["builder"]["on"]], ["#894"])
        self.assertEqual((len(r["builder"]["merged"]), len(r["builder"]["open"]), len(r["builder"]["changes"]),
                          r["builder"]["sessions"]), (1, 1, 1, 2))
        self.assertTrue(r["analyst"]["blocked"])
        self.assertEqual(r["designer"]["group"], "idle")
        self.assertEqual(len(r["designer"]["merged"]), 1)   # the Brief, merged yesterday

    def test_authority_counts_for_the_prs_author_and_all_for_the_merger(self):
        r = self.rows()
        self.assertEqual([c["number"] for c in r["builder"]["authority"]], [925, 940])
        self.assertEqual(len(r["merger"]["authority"]), 2)
        self.assertEqual(r["planner"]["authority"], [])

    def test_a_session_that_never_acted_doesnt_count(self):
        self.assertEqual(self.rows()["reviewer"]["group"], "idle")


def drawn(m) -> str:
    """Crew's roles as crew.js draws them from state.json's `crew_roles` (#1139)."""
    return crewdraw.draw(crewdraw.base(built_at="2026-11-05T12:00:00Z", crew_roles=json.loads(
        json.dumps(agents.state(m), default=str))))["roles"]


class StateTest(unittest.TestCase):
    def test_plain_fields_working_first(self):
        rows = agents.state(amodel())
        self.assertEqual([r["role"] for r in rows][:3], ["builder", "analyst", "merger"])
        r = {x["role"]: x for x in rows}
        self.assertEqual(r["builder"]["line"], "On #894 M4 drill")
        self.assertEqual(r["analyst"]["line"], "Blocked on #692 Checklist brief")
        self.assertEqual(r["merger"]["line"], "2 calls in the last 24 hours")
        self.assertEqual((r["merger"]["count"], r["builder"]["count"]), ("2 calls", "1 merged"))
        self.assertEqual((r["planner"]["badge"], r["planner"]["lead"]), ("PL", True))
        self.assertNotIn("<", json.dumps(rows))   # no HTML


@unittest.skipUnless(crewdraw.NODE, "node isn't installed")
class RenderTest(unittest.TestCase):
    def test_rows_open_the_work_maps_role_view(self):
        # #1113: the drawer became the Work map's role view (#1115); each row links there.
        html = drawn(amodel())
        roles = re.findall(r'class="cm-row" href="workmap.html\?group=role#role-([a-z]+)"', html)
        self.assertEqual(sorted(roles), sorted(r for r, _ in agents.ROLES))
        self.assertNotIn("cm-drawer", html)
        self.assertIn("WORKING · 3", html)
        self.assertIn("IDLE · 4", html)
        self.assertIn("3 working · 4 idle · Thu 05 Nov, 12:00 UTC", html)
        self.assertIn('<span class="br-av lead" aria-hidden="true">PL</span>', html)

    def test_rows_hold_no_link_inside_their_link(self):
        html = drawn(amodel())
        for row in re.findall(r'<a class="cm-row".*?</a>', html):
            self.assertEqual(row.count("<a "), 1)

    def test_repo_text_stays_text(self):
        m = amodel()
        m["issue_titles"][894] = "<img src=x>"
        self.assertIn("On #894 &lt;img src=x&gt;", drawn(m))

    def test_empty_model(self):
        empty = {"repo": REPO, "now": NOW, "sessions": [], "prs": [], "merged": [], "grants": None,
                 "report": None, "trouble": None, "plan": None}
        html = drawn(empty)
        self.assertIn("Nothing merged in the window.", html)
        self.assertIn("IDLE · 7", html)


if __name__ == "__main__":
    unittest.main()
