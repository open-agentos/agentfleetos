"""Tests for commissions.build (#931), the Work map's Goal view source since #1113. Run: python3 -m unittest discover -s dashboard"""
from __future__ import annotations

import datetime as dt
import json
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import commissions as cm  # noqa: E402
from test_strip import NOW, REPO, item, model, scope  # noqa: E402

TROUBLE = json.loads((HERE.parent / "launcher" / "testdata" / "trouble.json").read_text())


def plan_scope(n, lead, title, kind="Goal", open_=2, done=3, subs=()):
    return {"number": n, "kind": kind, "lead": lead, "title": title, "url": f"https://github.com/{REPO}/issues/{n}",
            "open": open_, "done": done, "unread": False, "subs": list(subs)}


def cmodel(**over):
    m = model()
    m["trouble"]["scopes"].append(scope(687, "Engine host stays up", progress=[("uptime", "met")]) | {"type": "Area"})
    m["plan"] = {"read": True, "not_plan": [], "scopes": [
        plan_scope(685, "M3", "The Desk shows the plan and the report", subs=[
            {"number": 931, "ref": "#931", "title": "Commissions page", "url": f"https://github.com/{REPO}/issues/931",
             "status": {"kind": "go", "text": "go"}, "pr": {"number": 933, "url": f"https://github.com/{REPO}/pull/933"}}]),
        plan_scope(686, "M4", "Readiness review")]}
    m["closed_scopes"] = [
        {"number": 684, "title": "M2: Merges under delegation", "url": f"https://github.com/{REPO}/issues/684",
         "type": "Goal", "closed_at": "2026-11-10T12:00:00Z"},
        {"number": 600, "title": "M0: Old", "url": "u", "type": "Goal", "closed_at": "2026-10-01T00:00:00Z"}]
    return m | over


class BuildTest(unittest.TestCase):
    def test_groups_in_order(self):
        rows = cm.build(cmodel())["rows"]
        self.assertEqual([(r["number"], r["group"]) for r in rows],
                         [(686, "look"), (685, "waiting"), (683, "running"), (687, "keep"), (684, "delivered")])

    def test_plan_counts_and_subs_join_the_trouble_scope(self):
        r = next(r for r in cm.build(cmodel())["rows"] if r["number"] == 685)
        self.assertEqual((r["lead"], r["title"], r["open"], r["done"], r["met"]),
                         ("M3", "The Desk shows the plan and the report", 2, 3, 1))
        self.assertEqual(r["subs"][0]["ref"], "#931")

    def test_falls_back_to_the_plan_when_trouble_failed(self):
        rows = cm.build(cmodel(trouble={"error": "boom"}))["rows"]
        self.assertEqual([(r["number"], r["group"]) for r in rows], [(685, "running"), (686, "running"), (684, "delivered")])


if __name__ == "__main__":
    unittest.main()
