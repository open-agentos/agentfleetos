"""Tests for dashboard/lanes.py (#1261): Crew's lanes, panels and counts, and how crew.js draws them.

Run: python3 -m unittest discover -s dashboard
"""
import datetime as dt
import json
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import crewdraw  # noqa: E402
import lanes  # noqa: E402
import state as st  # noqa: E402

NOW = dt.datetime(2026, 11, 18, 12, 0, tzinfo=dt.timezone.utc)
REPO = "o/r"


def ago(minutes):
    return NOW - dt.timedelta(minutes=minutes)


def sess(sid, issue, status="active", role="builder", **kw):
    return {"session_id": sid, "role": role, "model": "m", "status": status, "issue": issue, "pr": None,
            "gov_question": None, "last_ts": ago(1), "started_ts": ago(30), "tracking_issue": 900,
            "cost": 1.5, "cap": 10.0, "over_cap": False, **kw}


def pr(n, closes, draft=False, needs_owner=None):
    return {"number": n, "title": f"PR {n}", "url": f"https://github.com/{REPO}/pull/{n}", "author": "x",
            "draft": draft, "review": "", "created_ts": ago(60), "closes": [{"number": c} for c in closes],
            "needs_owner": needs_owner, "reviewer": {"at_head": None}}


def row(n, stage, title="", **kw):
    return {"issue": n, "ref": f"#{n}", "title": title or f"Issue {n}", "url": f"https://github.com/{REPO}/issues/{n}",
            "state": "open", "stage": stage, "blocked_by": [], "role": None,
            "goal": {"number": 1, "lead": "M10", "title": "M10: x", "kind": "goal"}, **kw}


def model(rows=(), sessions=(), prs=(), merged=(), calls=(), watcher=None, cards=(), idle=()):
    return {"repo": REPO, "now": NOW, "issue_titles": {}, "sessions": list(sessions), "prs": list(prs),
            "merged": list(merged), "grants": {"calls": list(calls)}, "watcher": watcher,
            "floor": {"cards": list(cards), "idle": list(idle)},
            "workmap": {"desk": {"windows": {"day": list(rows)}}}}


def lane_of(out, key):
    return next(x for x in out["lanes"] if x["key"] == key)


def where(out):
    return {c.get("issue", c.get("pr")): x["key"] for x in out["lanes"] for c in x["cards"]}


class LaneTest(unittest.TestCase):
    def test_map_stage_is_the_lane(self):
        out = lanes.state(model([row(1, "queued"), row(2, "building"), row(3, "review"), row(4, "merging"),
                                 row(5, None)]))
        self.assertEqual(where(out), {1: "queued", 2: "building", 3: "review", 4: "merging"})
        self.assertEqual([x["name"] for x in out["lanes"]],
                         ["Queued", "Building", "In review", "Merging", "Merged · 24h"])
        self.assertEqual(lane_of(out, "queued")["cards"][0]["lead"], "M10")

    def test_a_session_with_no_map_row_puts_its_issue_in_building(self):
        # #1249's case: built after the map's plan read, so no row.
        out = lanes.state(model(sessions=[sess("s1", 1249)]))
        self.assertEqual(where(out), {1249: "building"})

    def test_a_ready_pr_moves_a_rowless_issue_to_in_review(self):
        out = lanes.state(model(sessions=[sess("s1", 7)], prs=[pr(70, [7])]))
        self.assertEqual(where(out), {7: "review"})
        self.assertEqual(lane_of(out, "review")["cards"][0]["pr"], {"number": 70, "draft": False})
        out = lanes.state(model(sessions=[sess("s1", 7)], prs=[pr(70, [7], draft=True)]))
        self.assertEqual(where(out), {7: "building"})
        self.assertEqual(lane_of(out, "building")["cards"][0]["pr"], {"number": 70, "draft": True})

    def test_stopped_or_never_acted_sessions_add_nothing(self):
        out = lanes.state(model(sessions=[sess("s1", 8, status="stopped"), sess("s2", 9, never_acted=True)]))
        self.assertEqual(where(out), {})

    def test_session_on_a_card(self):
        fc = {"session_id": "s1", "run_minutes": 18, "events_per_slot": [0, 1, 2, 0, 0, 3]}
        out = lanes.state(model([row(1, "building")], sessions=[sess("s1", 1)], cards=[fc]))
        c = lane_of(out, "building")["cards"][0]
        self.assertTrue(c["working"])
        self.assertEqual(c["session"], {"session_id": "s1", "status": "active", "run_minutes": 18,
                                        "idle_minutes": None, "events_per_slot": [0, 1, 2, 0, 0, 3],
                                        "activity": None})
        out = lanes.state(model([row(1, "building")], sessions=[sess("s1", 1, status="idle")],
                                idle=[{"session_id": "s1", "idle_minutes": 55}]))
        c = lane_of(out, "building")["cards"][0]
        self.assertFalse(c["working"])
        self.assertEqual((c["session"]["idle_minutes"], c["session"]["events_per_slot"]), (55, None))

    def test_working_first_then_needs_you_then_newest(self):
        rows = [row(n, "review") for n in (1, 2, 3, 4)]
        out = lanes.state(model(rows, sessions=[sess("s", 1)], prs=[pr(30, [3], needs_owner="overstep: needs the owner")]))
        self.assertEqual([c["issue"] for c in lane_of(out, "review")["cards"]], [1, 3, 4, 2])

    def test_needs_you_is_the_owner_as_blocker(self):
        out = lanes.state(model([row(1, "review"), row(2, "review"), row(3, "review")],
                                prs=[pr(10, [1]), pr(20, [2], needs_owner="x"), pr(30, [3])],
                                calls=[{"number": 30, "group": "left", "reason": "protected path", "time": ago(5)}]))
        self.assertEqual({c["issue"]: c["needs_you"] for c in lane_of(out, "review")["cards"]},
                         {1: False, 2: True, 3: True})

    def test_a_lane_carries_six_and_says_how_many_more(self):
        out = lanes.state(model([row(n, "queued") for n in range(1, 10)]))
        q = lane_of(out, "queued")
        self.assertEqual((len(q["cards"]), q["more"], out["counts"]["in_progress"]), (6, 3, 9))

    def test_merged_lane_is_one_card_per_pr_in_24h(self):
        merged = [{"number": 5, "title": "a", "url": "u5", "author": "productswarm-builder[bot]", "merged_at": ago(60)},
                  {"number": 6, "title": "old", "url": "u6", "author": "x", "merged_at": ago(25 * 60)}]
        calls = [{"number": 5, "group": "merged", "title": "a", "time": ago(61), "link": "l5"},
                 {"number": 7, "group": "merged", "title": "b", "time": ago(10), "link": "l7"},
                 {"number": 8, "group": "would", "title": "c", "time": ago(10), "link": "l8"}]
        out = lanes.state(model(merged=merged, calls=calls))
        m = lane_of(out, "merged")["cards"]
        self.assertEqual([(c["pr"], c["role"]) for c in m], [(7, "merger"), (5, "builder")])
        self.assertEqual(out["counts"]["merged"], 2)


class PanelTest(unittest.TestCase):
    W = {"status": "ok", "held": [{"ref": "#895", "code": "limit", "reason": "held: 2 of 2 running"},
                                  {"ref": "PR #30", "code": "live", "reason": "held: a session is live on it"}],
         "skipped": [{"ref": "#439", "code": "no_cap", "reason": "skipped: the role has no cap"}],
         "failed": [{"ref": "#51", "kind": "build", "ending": "no_result", "ended": ago(90)},
                    {"ref": "#52", "kind": "review", "ending": "error", "ended": ago(5)}]}

    def test_blocked_and_held_once_per_issue(self):
        # #895 is a blocked map row and a watcher hold: one row, blocked.
        out = lanes.state(model([row(895, "blocked", blocked_by=[890])], watcher=self.W))
        self.assertEqual([(b["ref"], b["kind"], b["why"]) for b in out["blocked"]], [
            ("#895", "blocked", ["waits on #890", "2 of 2 running"]),
            ("PR #30", "held", ["a session is live on it"]),
            ("#439", "skipped", ["the role has no cap"])])
        self.assertEqual(out["counts"]["blocked"], 3)
        self.assertEqual(where(out), {})   # blocked work isn't in a lane

    def test_blocked_on_a_gov_question(self):
        out = lanes.state(model(sessions=[sess("s", 12, status="blocked", gov_question=40)]))
        self.assertEqual(out["blocked"][0]["why"], ["on gov question #40"])

    def test_failed_runs(self):
        out = lanes.state(model(watcher=self.W))
        self.assertEqual([(f["word"], f["ref"]) for f in out["failed"]], [("NO RESULT", "#51"), ("ERR", "#52")])

    def test_no_watcher_lists_unless_ok(self):
        out = lanes.state(model(watcher={"status": "missing"}))
        self.assertEqual((out["blocked"], out["failed"]), ([], []))

    def test_needs_you_newest_first_seven_then_more(self):
        calls = [{"number": n, "group": "left", "title": "t", "reason": "r", "time": ago(n), "link": "l"}
                 for n in range(1, 11)] + [{"number": 99, "group": "merged", "time": ago(1)}]
        out = lanes.state(model(calls=calls))
        self.assertEqual([x["number"] for x in out["needs"]], [1, 2, 3, 4, 5, 6, 7])
        self.assertEqual((out["needs_more"], out["counts"]["needs_you"]), (3, 10))

    def test_activity_is_the_tapes_newest(self):
        tape = [{"kind": "SHIPPED", "text": str(i)} for i in range(12)]
        self.assertEqual(len(lanes.state(model(), tape)["activity"]), lanes.ACTIVITY_MAX)

    def test_counts_working_sessions(self):
        out = lanes.state(model(sessions=[sess("a", 1), sess("b", None), sess("c", 2, status="idle")]))
        self.assertEqual(out["counts"]["working"], 2)


class StateTest(unittest.TestCase):
    def test_no_cost_and_plain(self):
        m = model([row(1, "building")], sessions=[sess("s1", 1)])
        text = json.dumps(st.plain(lanes.state(m)))
        for word in ("cost", "usd", "spend", "1.5"):
            self.assertNotIn(word, text)   # crew.js shows the session's own, from `sessions`

    def test_without_a_map(self):
        m = model(sessions=[sess("s1", 3)])
        m.pop("workmap")
        self.assertEqual(where(lanes.state(m)), {3: "building"})


def page(m, **over):
    d = crewdraw.base(built_at="2026-11-18T12:00:00Z", repo=REPO,
                      crew_work=json.loads(json.dumps(st.plain(lanes.state(m)))),
                      sessions=json.loads(json.dumps(st.plain(m["sessions"]))), **over)
    return crewdraw.draw(d)["floor"]


@unittest.skipUnless(crewdraw.NODE, "node isn't installed")
class DrawTest(unittest.TestCase):
    def test_a_running_card(self):
        fc = {"session_id": "s1", "run_minutes": 18, "events_per_slot": [0, 1, 2, 0, 0, 3]}
        html = page(model([row(1244, "building", title="Lanes")], sessions=[sess("s1", 1244)],
                          prs=[pr(1250, [1244], draft=True)], cards=[fc]))
        self.assertIn('<span class="cw-badge on" title="builder">BU</span>', html)
        self.assertIn('<span class="cw-live" title="running" aria-label="running"></span>', html)
        self.assertIn('<a href="https://github.com/o/r/pull/1250">PR #1250</a><span class="muted"> draft</span>', html)
        self.assertIn('title="this session\'s own spend (est.)">$1.50</span>', html)
        self.assertIn('<span class="cw-run">running 18m</span>', html)   # no activity words given
        self.assertIn("<svg", html)
        self.assertIn('<span class="mono muted">M10</span>', html)

    def test_the_dot_goes_when_the_session_stops(self):
        fc = {"session_id": "s1", "run_minutes": 18, "events_per_slot": [0, 1, 2, 0, 0, 3]}
        first = crewdraw.base(built_at="2026-11-18T12:00:00Z", repo=REPO, crew_work=json.loads(json.dumps(st.plain(
            lanes.state(model([row(1, "building")], sessions=[sess("s1", 1)], cards=[fc]))))))
        later = crewdraw.base(built_at="2026-11-18T12:00:15Z", repo=REPO, crew_work=json.loads(json.dumps(st.plain(
            lanes.state(model([row(1, "queued")], sessions=[sess("s1", 1, status="stopped")]))))))
        got = crewdraw.run(first, served=later, clock="2026-11-18T12:00:15Z")
        self.assertIn("cw-live", got["first"]["floor"])
        self.assertNotIn("cw-live", got["after"]["floor"])

    def test_needs_you_card_and_empty_lanes(self):
        html = page(model([row(1, "review")], prs=[pr(10, [1], needs_owner="x")]))
        self.assertIn('<div class="cw-card wm-needs">', html)   # the Map's mark (#1273)
        self.assertIn('<span class="cw-needs">needs you</span>', html)
        self.assertEqual(html.count('<p class="cw-none">none</p>'), 4)

    def test_more_and_panels(self):
        calls = [{"number": n, "group": "left", "title": "t", "reason": "r", "time": ago(n), "link": "https://x/l"}
                 for n in range(1, 10)]
        html = page(model([row(n, "queued") for n in range(1, 9)], calls=calls, watcher=PanelTest.W))
        self.assertIn('<p class="cw-more">+2 more</p>', html)
        self.assertIn('<a href="governance.html">+2 more on Governance</a>', html)
        self.assertIn('<span class="cw-fail">NO RESULT</span>', html)
        self.assertIn('<span class="cw-ring" aria-hidden="true"></span>', html)

    def test_a_blocked_session_card_takes_the_maps_red_edge(self):
        work = st.plain(lanes.state(model([row(1, "building")], sessions=[sess("s1", 1)])))
        work = json.loads(json.dumps(work))
        card = next(c for ln in work["lanes"] for c in ln["cards"])
        card["session"]["status"], card["working"] = "blocked", False
        html = crewdraw.draw(crewdraw.base(built_at="2026-11-18T12:00:00Z", repo=REPO, crew_work=work))["floor"]
        self.assertIn('<div class="cw-card wm-blocked">', html)

    def test_repo_text_stays_text(self):
        html = page(model([row(1, "queued", title="<script>x</script>")]))
        self.assertIn('<div class="cw-title">&lt;script&gt;x&lt;/script&gt;</div>', html)
        self.assertNotIn("<script>", html)


if __name__ == "__main__":
    unittest.main()
