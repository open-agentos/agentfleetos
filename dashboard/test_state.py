"""Tests for dashboard/state.py (#400). Run: python3 -m unittest discover -s dashboard"""
import datetime as dt
import json
import re
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import crewpage  # noqa: E402
import generate as g  # noqa: E402
import state as st  # noqa: E402
from test_generate import NOW, IDLE, REPO, ev, tracking, comment, issue, ts  # noqa: E402
from test_cap import spent, M  # noqa: E402
from test_rate import NUDGE, limits, runs  # noqa: E402

COST_WORDS = ("cost", "usd", "spend")


def model():
    """Priced sessions, one over its cap, a blocked one, a question and a PR: everything
    the page shows, and every place cost could leak from."""
    bot = "productswarm-builder[bot]"
    issues = [tracking(50, "s-over"), tracking(51, "s-blocked"), tracking(52, "s-done", state="closed"),
              issue(4, "Dashboard"), issue(26, "GOV-Q: x?", ["gov:question"])]
    comments = {50: [comment([ev("s-over", "heartbeat", e.pop("minutes_ago"), **e)
                              for e in [spent(M, issue=4)]], login=bot)],
                51: [comment([ev("s-blocked", "blocked", 2, issue=4, gov_question=26,
                                 cost_usd=3.5)])],
                52: [comment([ev("s-done", "stopped", 300, cost_usd=9.0)])]}
    prs = [{"number": 30, "title": "A PR", "url": "https://x/pull/30",
            "author": {"login": "app/productswarm-builder"}, "isDraft": False, "createdAt": ts(5),
            "reviewDecision": "", "closingIssuesReferences": [{"number": 4}], "headRefOid": "abc"}]
    return g.build({"repo": REPO, "issues": issues, "comments": comments, "prs": prs}, NOW, IDLE,
                   caps={"builder": 5.0})


def keys(x, path=""):
    """Every key in a nested dict/list, with its path."""
    if isinstance(x, dict):
        for k, v in x.items():
            yield f"{path}.{k}", k
            yield from keys(v, f"{path}.{k}")
    elif isinstance(x, list):
        for i, v in enumerate(x):
            yield from keys(v, f"{path}[{i}]")


class StateTest(unittest.TestCase):
    def setUp(self):
        self.m = model()
        self.s = st.state(self.m)

    def test_top_level(self):
        self.assertEqual(self.s["schema"], 1)
        self.assertEqual(self.s["repo"], REPO)
        self.assertEqual(self.s["built_at"], "2026-11-02T12:00:00Z")
        for k in ("sessions", "needs_you", "prs", "gov_questions", "governance", "committees",
                  "reviewer_runs"):
            self.assertIn(k, self.s)
        self.assertNotIn("progress", self.s)   # v3 progress retired (#1113)

    def test_is_json(self):
        self.assertEqual(json.loads(json.dumps(self.s)), self.s)

    def test_cost_only_per_session_never_summed(self):
        # Each session's own estimate, cap and over-cap flag, for Crew's Spend column (per
        # #1153's answer, GOV-0056); nothing else, and no total (GOV-0033).
        self.assertTrue(any(s["over_cap"] for s in self.m["sessions"]))   # the fixture is priced
        for mine, theirs in zip(self.s["sessions"], self.m["sessions"]):
            self.assertEqual([mine[k] for k in ("cost", "cap", "over_cap")],
                             [theirs[k] for k in ("cost", "cap", "over_cap")])
        costly = [p for p, k in keys(self.s) if any(w in k.lower() for w in COST_WORDS) or k in ("cap", "over_cap")]
        self.assertTrue(costly)
        self.assertEqual([p for p in costly if not re.fullmatch(r"\.sessions\[\d+\]\.(cost|cap|over_cap)", p)], [])
        self.assertFalse([p for p, k in keys(self.s) if "total" in k.lower() or "sum" in k.lower()])
        self.assertNotIn("over_cap", [i["kind"] for i in self.s["needs_you"]])
        self.assertNotIn("$", json.dumps(self.s))   # figures, never Crew's text

    def test_session_fields_are_ones_the_page_renders(self):
        # crew.js draws Crew's sessions table from these (#1139): it reads every one.
        js = crewpage.JS.read_text(encoding="utf-8")
        seen = set(re.findall(r"\bx\.([a-z_]+)", js[js.index("function sessionRows"):js.index("function sessions(")]))
        for s in self.s["sessions"]:
            self.assertLessEqual(set(s), seen)
        self.assertEqual(set(self.s["sessions"][0]), {*st.SESSION_FIELDS, "issue_title"})

    def test_no_html(self):
        self.assertNotIn("<", json.dumps(self.s))

    def test_timestamps_round_trip(self):
        for s_model, s_state in zip(self.m["sessions"], self.s["sessions"]):
            for k in ("last_ts", "started_ts"):
                self.assertEqual(g.parse_ts(s_state[k]), s_model[k])
        self.assertEqual(g.parse_ts(self.s["built_at"]), NOW)
        self.assertEqual(g.parse_ts(self.s["prs"][0]["created_ts"]), self.m["prs"][0]["created_ts"])

    def test_waiting_sessions_by_id(self):
        q = self.s["gov_questions"][0]
        self.assertEqual((q["number"], q["waiting"]), (26, ["s-blocked"]))

    def test_unknown_types_are_an_error(self):
        with self.assertRaises(TypeError):
            st.plain({"x": object()})

    def test_rfc3339_is_utc(self):
        t = dt.datetime(2026, 11, 2, 13, 0, tzinfo=dt.timezone(dt.timedelta(hours=1)))
        self.assertEqual(st.rfc3339(t), "2026-11-02T12:00:00Z")


class SkippedBuildTest(unittest.TestCase):
    """A skipped build writes neither the page nor state.json."""

    def run_main(self, env, answers):
        import tempfile, io, os, contextlib  # noqa: E401
        from unittest import mock
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "index.html"
            with mock.patch.dict(os.environ, env, clear=False), \
                    mock.patch.object(g, "gh_json", side_effect=answers), \
                    mock.patch.object(g.precedent, "published", return_value=None), \
                    contextlib.redirect_stdout(io.StringIO()):
                for k in ("GITHUB_EVENT_NAME", "GITHUB_TRIGGERING_ACTOR", "GITHUB_ACTOR"):
                    if k not in env:
                        os.environ.pop(k, None)
                rc = g.main(["--repo", REPO, "--out", str(out)])
            return rc, sorted(p.name for p in Path(tmp).iterdir())

    def test_low_allowance_writes_neither(self):
        self.assertEqual(self.run_main({}, [limits(graphql=3)]), (0, []))

    def test_nudge_too_soon_writes_neither(self):
        stamp = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
        recent = {"jobs": [{"steps": [{"name": "deploy-pages", "conclusion": "success",
                                       "completed_at": stamp}]}]}
        self.assertEqual(self.run_main(NUDGE, [runs(7), recent]), (0, []))


class WatcherStateTest(unittest.TestCase):
    """#459: the watcher's state from the [watch] issue, in state.json as `watcher`."""

    def built(self, *issues):
        return st.state(g.build({"repo": REPO, "issues": list(issues), "comments": {}, "prs": []},
                                NOW, IDLE, watch_interval=5))

    def test_each_list_without_cost(self):
        from test_floor import FULL, watch_issue
        state = dict(FULL)
        state["running"] = [state["running"][0] | {"cost_usd": 4.2}]
        w = self.built(watch_issue(state))["watcher"]
        self.assertEqual(set(w), set(st.WATCHER_FIELDS))
        self.assertEqual((w["status"], w["issue"], w["stale"], w["age_minutes"]), ("ok", 70, False, 1))
        self.assertEqual(w["checked"], "2026-11-02T11:59:00Z")
        self.assertEqual([len(w[k]) for k in ("running", "held", "skipped", "failed")], [1, 1, 1, 1])
        self.assertEqual(w["running"][0], {"ref": "#405", "kind": "build", "role": "builder",
                                           "started": "2026-11-02T11:09:00Z"})
        self.assertEqual(w["held"][0]["reason"], "held: 2 of 2 running")
        # No cost key or figure ("spend_cap_usd" in no_cap's fixed sentence names a setting).
        self.assertNotIn("cost_usd", json.dumps(w))
        self.assertNotIn("4.2", json.dumps(w))

    def test_stale(self):
        from test_floor import pub, watch_issue
        w = self.built(watch_issue(pub(checked_ago=40)))["watcher"]
        self.assertEqual((w["stale"], w["age_minutes"]), (True, 40))

    def test_missing_malformed_and_wrong_author(self):
        from test_floor import FULL, watch_issue
        import watch
        self.assertEqual(self.built(issue(4, "x"))["watcher"], {"status": "missing"})
        self.assertEqual(self.built(watch_issue(None, body=watch.WATCH_MARKER))["watcher"],
                         {"status": "malformed", "issue": 70})
        self.assertEqual(self.built(watch_issue(FULL, login="mallory"))["watcher"],
                         {"status": "not_owner"})

    def test_markers_match(self):
        import floor
        import watch
        self.assertEqual(floor.WATCH_MARKER, watch.WATCH_MARKER)
        self.assertEqual(floor.STALE_CHECKS, watch.STALE_CHECKS)


if __name__ == "__main__":
    unittest.main()
