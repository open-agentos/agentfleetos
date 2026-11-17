"""Tests for `swarm map` (#1081): the CLI over dashboard/workmap.py."""
import datetime as dt
import json
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import swarm  # noqa: E402

REPO = "o/r"


class Out:
    def __init__(self):
        self.lines = []

    def out(self, s):
        self.lines.append(s)


def fake_gather(seen):
    def gather(repo, now, window, idle_minutes):
        seen.append((repo, window, idle_minutes))
        g = swarm.dashboard()
        data = {"repo": repo, "issues": [], "comments": {}, "prs": []}
        return {"data": data, "model": g.build(data, now, dt.timedelta(minutes=idle_minutes)),
                "prs": [], "effort": None, "since": None}
    return gather


class MapTest(unittest.TestCase):
    def test_json_and_text(self):
        seen, out = [], Out()
        self.assertEqual(swarm.work_map(out, REPO, "week", as_json=True, gather=fake_gather(seen)), 0)
        m = json.loads(out.lines[-1])
        self.assertEqual(m["window"], "week")
        self.assertEqual([r["ref"] for r in m["rows"]], ["unattributed"])
        self.assertEqual(seen, [(REPO, "week", 15)])
        self.assertEqual(swarm.work_map(out, REPO, "day", gather=fake_gather(seen)), 0)
        self.assertIn("unattributed", out.lines[-1])
        self.assertNotIn("total", out.lines[-1].lower())

    def test_parser_knows_map(self):
        with self.assertRaises(SystemExit) as e:
            swarm.main(["map", "--help"])
        self.assertEqual(e.exception.code, 0)
        with self.assertRaises(SystemExit) as e:
            swarm.main(["map", "--window", "year"])
        self.assertEqual(e.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
