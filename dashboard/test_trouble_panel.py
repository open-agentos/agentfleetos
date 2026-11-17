"""Tests for the trouble report the Desk reads (#903): generate.py builds `swarm trouble`'s
report without the owner-acts sync. Its panel retired (#1113); the Work map's strip and each
Goal's view show it (#1114, #1115)."""
from __future__ import annotations

import datetime as dt
import json
import sys
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import generate as g  # noqa: E402
import state as st  # noqa: E402

sys.path.insert(0, str(HERE.parent / "launcher"))
import trouble  # noqa: E402

REPORT = json.loads((HERE.parent / "launcher" / "testdata" / "trouble.json").read_text())
NOW = dt.datetime(2026, 11, 12, 12, 0, tzinfo=dt.timezone.utc)


def model(t) -> dict:
    m = {k: None for k in ("report", "plan", "floor", "watcher", "grants", "wire", "trends",
                           "questions_went", "precedent", "committees")}
    return m | {"repo": "o/r", "trouble": t}


class FetchTest(unittest.TestCase):
    def test_reads_without_the_acts_sync(self):
        seen = {}

        def gather(launcher, repo, owner, manifest_path, **kw):
            seen.update(kw, repo=repo)
            return "data"

        with mock.patch.object(trouble, "gather", gather), \
                mock.patch.object(trouble, "report", lambda d: {"scopes": [], "from": d}):
            r = g.fetch_trouble("o/r", NOW)
        self.assertEqual(r, {"scopes": [], "from": "data"})
        self.assertEqual(seen, {"now": NOW, "sync_acts": False, "repo": "o/r"})

    def test_github_down_is_an_error_not_a_failed_build(self):
        with mock.patch.object(trouble, "gather", side_effect=RuntimeError("gh: rate limited")):
            self.assertEqual(g.fetch_trouble("o/r", NOW), {"error": "gh: rate limited"})

    def test_state_json_carries_no_spend(self):
        # The trouble panel retired (#1113): each Goal's view on the Work map shows it (#1115).
        from test_live import desk_model
        r = json.loads(json.dumps(REPORT))
        r["scopes"][0]["spend_usd"] = 98.76
        s = st.state(desk_model() | {"trouble": r})
        self.assertNotIn("trouble", s["desk"])
        self.assertNotIn("trouble", s)
        self.assertNotIn("98.76", json.dumps(s))   # GOV-0014: no cost in state.json


if __name__ == "__main__":
    unittest.main()
