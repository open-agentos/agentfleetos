"""Tests for dashboard/workmap.py, the Work map's data (#1081).

Run: python3 -m unittest discover -s dashboard
"""
import datetime as dt
import json
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import generate as g  # noqa: E402
import state  # noqa: E402
import workmap as wm  # noqa: E402
from test_generate import NOW, IDLE, REPO, ev, tracking, comment  # noqa: E402

M = 1_000_000
REVIEWER = {"login": "productswarm-reviewer", "__typename": "Bot"}


def tok(o=0, i=0):
    return {"input": i, "output": o, "cache_read": 0, "cache_creation": 0}


def issue(n, state="open", closed_at=None, title=None):
    return {"number": n, "title": title or f"issue {n}", "state": state, "user": {"login": "o"},
            "labels": [], "html_url": f"https://github.com/{REPO}/issues/{n}", "created_at": "2026-10-01T00:00:00Z",
            "closed_at": closed_at, "body": ""}


def iso(minutes_ago):
    return (NOW - dt.timedelta(minutes=minutes_ago)).strftime("%Y-%m-%dT%H:%M:%SZ")


def plan(subs, blockers=None):
    """plan.fetch()'s trees and go, and plan.build()'s model, for one Goal, #1080, over `subs`
    ({number: go kind}). `blockers` is {number: [blocked-by state, ...]}."""
    data = {"trees": {1080: {"subIssues": {"nodes": [
        {"number": n, "state": "OPEN", "repository": {"nameWithOwner": REPO}} for n in subs]}}},
            "go": {n: {"blockedBy": {"totalCount": len(st), "nodes": [
                {"number": 900 + i, "state": x, "repository": {"nameWithOwner": REPO}}
                for i, x in enumerate(st)]}} for n, st in (blockers or {}).items()}}
    model = {"read": True, "scopes": [{"number": 1080, "kind": "Goal", "lead": "M9", "title": "money",
                                        "subs": [{"number": n, "status": {"kind": k}, "children": []}
                                                 for n, k in subs.items()]}]}
    return data, model


def gathered(sessions=(), issues=(), prs=(), open_prs=(), subs=None, effort=None, since=None,
             blockers=None):
    """gather()'s dict from fixtures. `sessions` is [(sid, events, state)]."""
    tracked = [tracking(900 + i, sid, state=st) for i, (sid, _, st) in enumerate(sessions)]
    data = {"repo": REPO, "issues": [*tracked, *issues],
            "comments": {900 + i: [comment(evs)] for i, (_, evs, _) in enumerate(sessions)},
            "prs": list(open_prs)}
    model = g.build(data, NOW, IDLE)
    if subs is not None:
        data["plan"], model["plan"] = plan(subs, blockers)
    return {"data": data, "model": model, "prs": list(prs), "effort": effort, "since": since}


def rows(m):
    return {r["issue"]: r for r in m["rows"]}


class AttributionTest(unittest.TestCase):
    def test_switch_splits_tokens_and_spend_before_working_on_is_unattributed(self):
        events = [ev("s1", "session_started", 50, token_counts=tok(o=M)),
                  ev("s1", "working_on", 40, issue=10, token_counts=tok(o=3 * M)),
                  ev("s1", "heartbeat", 30, token_counts=tok(o=4 * M)),
                  ev("s1", "working_on", 20, issue=11, token_counts=tok(o=6 * M)),
                  ev("s1", "heartbeat", 10, token_counts=tok(o=7 * M))]
        m = wm.build(gathered([("s1", events, "open")], [issue(10), issue(11)]), NOW, "day")
        r = rows(m)
        # 3M before the first working_on (incl. its own count), 1M + 2M on #10 up to the switch,
        # 1M on #11 after it. Opus 5.5 output is $20 a million.
        self.assertEqual(r[None]["tokens"], 3 * M)
        self.assertEqual(r[None]["ref"], wm.UNATTRIBUTED)
        self.assertEqual(r[10]["tokens"], 3 * M)
        self.assertAlmostEqual(r[10]["cost"], 60)
        self.assertEqual(r[11]["tokens"], M)
        self.assertAlmostEqual(r[11]["cost"], 20)
        self.assertEqual(r[10]["role"], "builder")
        self.assertIs(m["rows"][-1]["issue"], None)   # unattributed is always last

    def test_unattributed_row_is_there_with_no_spend(self):
        r = rows(wm.build(gathered(), NOW, "day"))
        self.assertEqual(r[None]["tokens"], 0)
        self.assertEqual(r[None]["cost"], 0)

    def test_counts_that_fall_charge_nothing(self):
        cs = wm.charges([ev("s", "heartbeat", 3, token_counts=tok(o=5)),
                         ev("s", "heartbeat", 2, token_counts=tok(o=2)),
                         ev("s", "heartbeat", 1, token_counts=tok(o=7))], "builder")
        self.assertEqual([c["tokens"] for c in cs], [5, 2])

    def test_unknown_model_gives_tokens_no_cost_and_is_flagged(self):
        events = [ev("s1", "working_on", 30, issue=10, token_counts=tok()),
                  {**ev("s1", "heartbeat", 10, token_counts=tok(o=M)), "model": "gpt-9"}]
        m = wm.build(gathered([("s1", events, "open")], [issue(10)]), NOW, "day")
        r = rows(m)[10]
        self.assertEqual(r["tokens"], M)
        self.assertIsNone(r["cost"])
        self.assertEqual(r["unpriced_tokens"], M)
        line = next(x for x in wm.text(m).splitlines() if x.startswith("#10 "))
        self.assertIn(" —* ", line)

    def test_spend_is_bucketed_by_hour_and_windows_sum_them(self):
        events = [ev("s1", "working_on", 60 * 30, issue=10, token_counts=tok()),
                  ev("s1", "heartbeat", 60 * 25, token_counts=tok(o=M)),    # yesterday 11:00
                  ev("s1", "heartbeat", 150, token_counts=tok(o=3 * M)),    # 09:30
                  ev("s1", "heartbeat", -5, token_counts=tok(o=4 * M))]     # 12:05, this hour
        gd = gathered([("s1", events, "open")], [issue(10)])
        hour = wm.build(gd, NOW, "hour")
        self.assertEqual((hour["from"], hour["to"]), ("2026-11-02T12:00:00Z", "2026-11-02T13:00:00Z"))
        self.assertEqual(rows(hour)[10]["tokens"], M)
        self.assertEqual(rows(wm.build(gd, NOW, "day"))[10]["tokens"], 3 * M)
        self.assertEqual(rows(wm.build(gd, NOW, "week"))[10]["tokens"], 4 * M)
        self.assertEqual([d["cost"] for d in rows(hour)[10]["days"][-2:]], [20, 60])


class OutcomeTest(unittest.TestCase):
    def pr(self, **kw):
        return {"number": 50, "isDraft": False, "state": "MERGED", "headRefOid": "h2",
                "mergedAt": iso(30),
                "closingIssuesReferences": {"nodes": [{"number": 10, "repository": {"nameWithOwner": REPO}}]},
                "reviews": {"nodes": [
                    {"author": REVIEWER, "commit": {"oid": "h1"}, "submittedAt": iso(200)},   # old head
                    {"author": REVIEWER, "commit": {"oid": "h2"}, "submittedAt": iso(90)},
                    {"author": REVIEWER, "commit": {"oid": "h2"}, "submittedAt": iso(80)},    # again
                    {"author": {"login": "someone", "__typename": "User"}, "commit": {"oid": "h2"},
                     "submittedAt": iso(70)}]},
                "commits": {"nodes": [{"commit": {"additions": 10, "deletions": 5, "committedDate": iso(100)}},
                                      {"commit": {"additions": 100, "deletions": 0,
                                                  "committedDate": iso(60 * 24 * 3)}}]}, **kw}

    def test_each_kind_once_in_its_hour(self):
        gd = gathered(issues=[issue(10, "closed", iso(20))], prs=[self.pr()])
        happened = wm.outcomes(gd["prs"], gd["data"]["issues"], REPO)
        self.assertEqual(sorted((o["kind"], wm.hour_of(o["ts"]).hour) for o in happened),
                         [("approved", 10), ("closed", 11), ("merged", 11)])
        r = rows(wm.build(gd, NOW, "day"))[10]
        self.assertEqual(r["outcome_kinds"], {"merged": 1, "approved": 1, "closed": 1})
        self.assertEqual(r["outcomes"], 3)
        self.assertEqual(r["lines"], 15)   # only the commit in the window
        self.assertEqual(r["days"][-1], {"date": "2026-11-02", "cost": 0, "outcomes": 3})
        self.assertNotIn(10, rows(wm.build(gd, NOW, "hour")))   # the 12:00 hour: nothing yet


class StageTest(unittest.TestCase):
    def test_five_stages(self):
        draft = {"draft": True, "reviewer": {}}
        ready = {"draft": False, "reviewer": {"at_head": None}}
        approved = {"draft": False, "reviewer": {"at_head": "APPROVED"}}
        self.assertEqual(wm.stage("waiting", [approved], True, False), "blocked")
        self.assertEqual(wm.stage("go", [], True, True), "blocked")
        self.assertEqual(wm.stage("go", [approved, draft], False, False), "merging")
        self.assertEqual(wm.stage("go", [ready], True, False), "review")
        self.assertEqual(wm.stage("go", [draft], False, False), "building")
        self.assertEqual(wm.stage("go", [], True, False), "building")
        self.assertEqual(wm.stage("go", [], False, False), "queued")
        self.assertIsNone(wm.stage("not_go", [], False, False))

    def test_stage_from_the_build(self):
        open_prs = [{"number": 60, "title": "x", "url": "u", "author": {"login": "app/productswarm-builder"},
                     "isDraft": True, "createdAt": iso(10), "reviewDecision": "",
                     "closingIssuesReferences": [{"number": 11}], "headRefOid": "h"}]
        gd = gathered(issues=[issue(10), issue(11), issue(12)], open_prs=open_prs,
                      subs={10: "go", 11: "go", 12: "waiting"})
        r = rows(wm.build(gd, NOW, "day"))
        self.assertEqual((r[10]["stage"], r[11]["stage"], r[12]["stage"]), ("queued", "building", "blocked"))
        self.assertEqual(r[10]["goal"]["number"], 1080)
        self.assertEqual(r[10]["goal"]["lead"], "M9")

    def test_open_blocker_is_blocked_whatever_the_go_kind(self):
        # plan.status() says `go` for an owner-`ready` issue with an open blocker, and `not_go`
        # for one with an open blocker and another reason (e.g. `hold`): both are blocked.
        open_prs = [{"number": 60, "title": "x", "url": "u", "author": {"login": "app/productswarm-builder"},
                     "isDraft": False, "createdAt": iso(10), "reviewDecision": "",
                     "closingIssuesReferences": [{"number": 12}], "headRefOid": "h"}]
        gd = gathered(issues=[issue(10), issue(11), issue(12), issue(13)], open_prs=open_prs,
                      subs={10: "go", 11: "not_go", 12: "go", 13: "go"},
                      blockers={10: ["OPEN"], 11: ["CLOSED", "OPEN"], 12: ["OPEN"], 13: ["CLOSED"]})
        r = rows(wm.build(gd, NOW, "day"))
        self.assertEqual([r[n]["stage"] for n in (10, 11, 12, 13)], ["blocked", "blocked", "blocked", "queued"])
        # where each stopped (#1083): #12 has a PR ready for review; the others, nothing yet
        self.assertEqual([r[n]["blocked_at"] for n in (10, 11, 12, 13)], ["queued", "queued", "review", None])
        self.assertEqual(wm.stage("go", [], False, False, True), "blocked")


class EffortTest(unittest.TestCase):
    def cache(self):
        return {"prs": {"50": {"label": "upkeep", "merged_at": "2026-11-01T00:00:00Z"},
                        "51": {"label": "capability", "merged_at": "2026-11-01T05:00:00Z"},
                        "52": {"label": "knowledge"}, "53": {"label": "governance"}}}

    def test_most_recently_merged_then_most_recent_then_unclassified(self):
        self.assertEqual(wm.effort_of({50, 51, 53}, self.cache(), REPO), "capability")
        self.assertEqual(wm.effort_of({52, 53}, self.cache(), REPO), "governance")
        self.assertEqual(wm.effort_of({99}, self.cache(), REPO), wm.UNCLASSIFIED)
        self.assertEqual(wm.effort_of(set(), None, REPO), wm.UNCLASSIFIED)

    def test_unclassified_in_the_map(self):
        r = rows(wm.build(gathered(issues=[issue(10)], subs={10: "go"}), NOW, "day"))
        self.assertEqual(r[10]["effort"], wm.UNCLASSIFIED)


class RowsTest(unittest.TestCase):
    def test_rows_and_fields(self):
        gd = gathered(issues=[issue(10), issue(20), issue(30, "closed", iso(60)),
                              issue(40, "closed", iso(60 * 24 * 3))], subs={10: "go"})
        m = wm.build(gd, NOW, "day")
        self.assertEqual([r["issue"] for r in m["rows"]], [10, 30, None])   # not #20, not #40
        fields = {"issue", "ref", "title", "url", "state", "cost", "unpriced_tokens", "tokens", "lines",
                  "outcomes", "outcome_kinds", "goal", "effort", "role", "stage", "blocked_at",
                  "needs_you", "baseline", "days", "blocked_by", "blocks"}
        for r in m["rows"]:
            self.assertEqual(set(r), fields)
            self.assertEqual(len(r["days"]), 14)

    def test_baseline_is_the_mean_of_four_windows_before(self):
        events = [ev("s1", "working_on", 60 * 24 * 3, issue=10, token_counts=tok()),
                  ev("s1", "heartbeat", 60 * 30, token_counts=tok(o=2 * M))]   # yesterday: $40
        gd = gathered([("s1", events, "open")], [issue(10)], subs={10: "go"},
                      since=NOW - dt.timedelta(days=14))
        self.assertAlmostEqual(rows(wm.build(gd, NOW, "day"))[10]["baseline"], 10)
        gd["since"] = NOW - dt.timedelta(days=2)
        m = wm.build(gd, NOW, "day")
        self.assertIsNone(rows(m)[10]["baseline"])
        self.assertFalse(m["baseline_covered"])

    def test_needs_you(self):
        prs = [{"number": 60, "title": "x", "url": "u", "author": {"login": "app/productswarm-builder"},
                "isDraft": False, "createdAt": iso(10), "reviewDecision": "",
                "closingIssuesReferences": [{"number": 10}], "headRefOid": "h"}]
        r = rows(wm.build(gathered(issues=[issue(10), issue(11)], open_prs=prs,
                                   subs={10: "go", 11: "go"}), NOW, "day"))
        self.assertTrue(r[10]["needs_you"])
        self.assertFalse(r[11]["needs_you"])


class NoTotalTest(unittest.TestCase):
    """GOV-0033: no total and no sum across issues in either format, map.json or state.json."""

    def gd(self):
        events = [ev("s1", "working_on", 50, issue=10, token_counts=tok()),
                  ev("s1", "heartbeat", 40, token_counts=tok(o=M)),       # #10: $20
                  ev("s1", "working_on", 30, issue=11, token_counts=tok(o=M)),
                  ev("s1", "heartbeat", 20, token_counts=tok(o=1.5 * M))]  # #11: $10
        return gathered([("s1", events, "open")], [issue(10), issue(11)])

    def keys(self, x):
        if isinstance(x, dict):
            return set(x) | {k for v in x.values() for k in self.keys(v)}
        if isinstance(x, list):
            return {k for v in x for k in self.keys(v)}
        return set()

    def test_no_total_in_json_or_text(self):
        m = wm.build(self.gd(), NOW, "day")
        self.assertFalse({k for k in self.keys(m) if "total" in k.lower() or "sum" in k.lower()})
        out = wm.text(m)
        self.assertNotIn("total", out.lower())
        self.assertNotIn("$30", out)        # #10 + #11
        self.assertNotIn("1,500,000", out)  # their tokens
        self.assertIn("$20.00", out)
        self.assertIn("$10.00", out)
        desk = wm.desk_file(self.gd(), NOW)
        self.assertFalse({k for k in self.keys(desk) if "total" in k.lower() or "sum" in k.lower()})
        self.assertEqual(set(desk["windows"]), set(wm.DESK_WINDOWS))

    def test_state_json_carries_no_map_or_cost(self):
        s = state.state(self.gd()["model"])
        for x in s["sessions"]:   # each session's own estimate is the only cost (GOV-0055)
            x.pop("cost", None)
        st = json.dumps(s)
        self.assertNotIn("cost", st)
        self.assertNotIn("unattributed", st)

    def test_write_map_beside_the_pages_and_survives_a_failed_read(self):
        gd = self.gd()
        with tempfile.TemporaryDirectory() as d:
            msg = g.write_map(gd["data"], gd["model"], NOW, Path(d), fetch_prs=lambda repo, since: [])
            self.assertEqual(msg, "wrote map.json")
            m = json.loads((Path(d) / "map.json").read_text())
            self.assertEqual(m["windows"]["day"][-1]["ref"], wm.UNATTRIBUTED)

            def fail(repo, since):
                raise RuntimeError("no")
            (Path(d) / "map.json").unlink()
            self.assertIn("not written", g.write_map(gd["data"], gd["model"], NOW, Path(d), fetch_prs=fail))
            self.assertFalse((Path(d) / "map.json").exists())


class DaysNeededTest(unittest.TestCase):
    def test_window_and_baseline_or_14_days(self):
        self.assertEqual(wm.days_needed("day"), 14)
        self.assertEqual(wm.days_needed("week"), 36)
        self.assertEqual(wm.days_needed("month"), 151)


def lr(n, cost=1.0, tokens=100, lines=10, outcomes=0, baseline=None, **kw):
    """A map row for the lists' tests."""
    return {"issue": n, "ref": f"#{n}", "title": f"issue {n}", "cost": cost, "tokens": tokens,
            "lines": lines, "outcomes": outcomes, "baseline": baseline, "needs_you": False,
            "stage": None, **kw}


def refs(xs):
    return [x[0] for x in xs]


class ListsTest(unittest.TestCase):
    """The Work map's six lists (#1084)."""

    UNATTRIBUTED = {**lr(None, cost=9.0, baseline=1.0), "issue": None, "ref": "unattributed"}

    def test_needs_you_and_blocked_largest_first_whatever_their_size(self):
        rows = [lr(1, cost=1.0, needs_you=True), lr(2, cost=3.0, needs_you=True, stage="blocked"),
                lr(3, cost=0, tokens=0, lines=0, needs_you=True), lr(4, cost=5.0, stage="blocked"),
                lr(5, cost=9.0), self.UNATTRIBUTED]
        out = wm.lists(rows, "cost")
        self.assertEqual(out["needs"], [["#2", 3.0, None], ["#1", 1.0, None], ["#3", 0, None]])
        self.assertEqual(refs(out["blocked"]), ["#4", "#2"])
        # the size picks the order
        rows[0]["lines"], rows[1]["lines"] = 50, 5
        self.assertEqual(refs(wm.lists(rows, "lines")["needs"]), ["#1", "#2", "#3"])

    def test_spend_no_outcome_needs_a_size_above_zero(self):
        rows = [lr(1, cost=2.0), lr(2, cost=4.0, outcomes=1), lr(3, cost=0, tokens=50, lines=0),
                lr(4, cost=None, tokens=70), self.UNATTRIBUTED]
        self.assertEqual(refs(wm.lists(rows, "cost")["spend"]), ["#1"])   # #3 has no cost, #4 none priced
        self.assertEqual(refs(wm.lists(rows, "tokens")["spend"]), ["#1", "#4", "#3"])
        self.assertEqual(refs(wm.lists(rows, "lines")["spend"]), ["#1", "#4"])

    def test_running_hot_from_1_5_times_usual(self):
        rows = [lr(1, cost=1.5, baseline=1.0), lr(2, cost=1.49, baseline=1.0), lr(3, cost=4.0, baseline=1.0),
                lr(4, cost=3.0, baseline=0), lr(5, cost=3.0), lr(6, cost=None, baseline=1.0), self.UNATTRIBUTED]
        out = wm.lists(rows, "cost")["hot"]
        self.assertEqual(out, [["#3", 4.0, 1.0], ["#1", 1.5, 1.0]])   # no usual, or no price: not in it
        self.assertEqual(wm.lists(rows, "tokens")["hot"], out)       # cost against usual, whatever the size

    def test_gone_quiet_under_half_of_usual(self):
        rows = [lr(1, cost=0.5, baseline=1.0), lr(2, cost=0.49, baseline=1.0), lr(3, cost=0.1, baseline=2.0),
                lr(4, cost=0.1, baseline=0), lr(5, cost=0.1), self.UNATTRIBUTED]
        self.assertEqual(wm.lists(rows, "cost")["quiet"], [["#3", 0.05, 2.0], ["#2", 0.49, 1.0]])

    def test_gone_quiet_takes_idle_issues_with_spend_in_the_longer_window(self):
        idle = dict(cost=0, tokens=0, lines=0, outcomes=0)
        rows = [lr(1, cost=0.2, baseline=1.0), lr(2, baseline=0.5, **idle), lr(3, **idle), lr(9, cost=1.0)]
        longer = [lr(2, cost=3.0, lines=40), lr(3, cost=0, tokens=0, lines=0, outcomes=1),
                  lr(4, cost=1.0, lines=7), lr(5, cost=6.0, lines=1), lr(9, cost=2.0),
                  {**lr(None, cost=5.0), "ref": "unattributed"}]
        out = wm.lists(rows, "cost", longer)["quiet"]
        # idle first, the largest longer-window figure first; #3 only had an outcome; #9 isn't idle
        self.assertEqual(out, [["#5", None, 6.0], ["#2", None, 3.0], ["#4", None, 1.0], ["#1", 0.2, 1.0]])
        self.assertEqual(refs(wm.lists(rows, "lines", longer)["quiet"]), ["#2", "#4", "#5", "#1"])
        # with no longer window, only the share of usual counts: #2 spent nothing, against a usual
        self.assertEqual(wm.lists(rows, "cost")["quiet"], [["#2", 0.0, 0.5], ["#1", 0.2, 1.0]])

    def test_best_yield_per_size(self):
        rows = [lr(1, cost=2.0, outcomes=1), lr(2, cost=1.0, outcomes=2), lr(3, cost=0, outcomes=3),
                lr(4, cost=5.0), self.UNATTRIBUTED]
        self.assertEqual(wm.lists(rows, "cost")["yield"], [["#2", 200.0, None], ["#1", 50.0, None]])
        self.assertEqual(refs(wm.lists(rows, "tokens")["yield"]), ["#3", "#2", "#1"])
        self.assertEqual(wm.lists(rows, "tokens")["yield"][0][1], 30000.0)   # 3 per 100 tokens, per million

    def test_an_issue_may_be_in_several_and_counts_are_every_match(self):
        r = lr(1, cost=4.0, baseline=1.0, needs_you=True, stage="blocked")
        rows = [r] + [lr(n, cost=float(n), needs_you=True) for n in range(2, 9)]
        out = wm.lists(rows, "cost")
        for key in ("needs", "blocked", "spend", "hot"):
            self.assertIn("#1", refs(out[key]), key)
        self.assertEqual(len(out["needs"]), 8)   # all of them: the page shows five
        self.assertEqual(set(out), set(wm.LISTS))

    def test_desk_lists_per_window_and_size_with_no_month(self):
        idle = dict(cost=0, tokens=0, lines=0, outcomes=0)
        windows = {"hour": [lr(1, **idle)], "day": [lr(1), lr(2, **idle)], "week": [lr(1), lr(2), lr(3, **idle)]}
        d = wm.desk_lists(windows)
        self.assertEqual(set(d), {"hour", "day", "week"})
        self.assertEqual(set(d["day"]), set(wm.SIZES))
        self.assertEqual(refs(d["hour"]["cost"]["quiet"]), ["#1"])    # hour -> day
        self.assertEqual(refs(d["day"]["cost"]["quiet"]), ["#2"])     # day -> week
        self.assertEqual(refs(d["week"]["cost"]["quiet"]), [])        # week -> month: the Desk reads none
        self.assertEqual(wm.LONGER, {"hour": "day", "day": "week", "week": "month"})
class LinksTest(unittest.TestCase):
    """#1115 (FEAT-13): what each issue waits on and holds up."""

    def test_blocked_by_from_a_waits_on_line(self):
        waits = {**issue(10), "body": "Do it.\n**Waits on:** #11 and #12. Then #13 can go.\n"}
        gd = gathered(issues=[waits, issue(11), issue(12), issue(13)], subs={10: "go", 11: "go", 12: "go", 13: "go"})
        r = rows(wm.build(gd, NOW, "day"))
        self.assertEqual(r[10]["blocked_by"], [11, 12])   # the first sentence only, as swarm watch reads it
        self.assertEqual(r[11]["blocks"], [10])
        self.assertEqual(r[13]["blocks"], [])
        self.assertEqual(r[None]["blocked_by"], [])

    def test_blocked_by_from_a_sub_issue_link_but_not_the_goal(self):
        gd = gathered(issues=[issue(10), issue(11)], subs={10: "go"})
        gd["data"]["plan"]["trees"][1080]["subIssues"]["nodes"][0]["subIssues"] = {"nodes": [
            {"number": 11, "state": "OPEN", "repository": {"nameWithOwner": REPO}},
            {"number": 12, "state": "CLOSED", "repository": {"nameWithOwner": REPO}},
            {"number": 13, "state": "OPEN", "repository": {"nameWithOwner": "other/repo"}}]}
        r = rows(wm.build(gd, NOW, "day"))
        self.assertEqual(r[10]["blocked_by"], [11])   # not the closed #12, nor another repo's #13
        self.assertEqual(r[10]["blocks"], [])         # the Goal, #1080, isn't held up by its tree here

    def test_blocked_by_from_a_github_dependency(self):
        gd = gathered(issues=[issue(10)], subs={10: "go"}, blockers={10: ["OPEN", "CLOSED"]})
        r = rows(wm.build(gd, NOW, "day"))
        self.assertEqual(r[10]["blocked_by"], [900])

    def test_a_closed_issue_holds_nothing_up(self):
        waits = {**issue(10), "body": "**Waits on:** #11"}
        by, holds = wm.links([waits, issue(11, "closed", iso(60))], None, REPO)
        self.assertEqual((by, holds), ({}, {}))


if __name__ == "__main__":
    unittest.main()
