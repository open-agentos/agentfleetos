"""Tests for dashboard/grants.py (#713). Run: python3 -m unittest discover -s dashboard"""
import datetime as dt
import json
import re
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "launcher"))
import crewdraw  # noqa: E402
import crewpage  # noqa: E402
import grants  # noqa: E402
import state  # noqa: E402

REPO = "open-agentos/agentfleetos"
BASE = f"https://github.com/{REPO}"
NOW = dt.datetime(2026, 11, 9, 15, 0, tzinfo=dt.timezone.utc)
SHA = "0123456789abcdef0123456789abcdef01234567"
MERGER = grants.MERGER


def ts(minutes_ago: float) -> str:
    return (NOW - dt.timedelta(minutes=minutes_ago)).strftime("%Y-%m-%dT%H:%M:%SZ")


def comment(n, body, minutes_ago, user=MERGER, cid=None, kind="pull"):
    cid = cid or n * 1000 + int(minutes_ago)
    return {"user": {"login": user}, "body": body, "created_at": ts(minutes_ago),
            "html_url": f"{BASE}/{kind}/{n}#issuecomment-{cid}",
            "issue_url": f"https://api.github.com/repos/{REPO}/issues/{n}"}


def would(kind="standing grant"):
    return f"Would merge ({kind}) at {SHA}.\n\n-- merger"


def merged(kind="standing grant"):
    return f"Merged under {kind} (GOV-0027) at {SHA}.\n\n-- merger"


def enqueued(kind="standing grant"):
    return f"Enqueued under {kind} (GOV-0027) at {SHA}.\n\n-- merger"


def left(reason):
    return f"Left for the owner at {SHA}: {reason}.\n\n-- merger"


def render(g_, repo=REPO) -> str:
    """The panel as crew.js draws it from state.json's `grants` (#1139)."""
    d = crewdraw.base(repo=repo, grants=state.plain(grants.state(g_)))
    return crewdraw.draw(d)["grants"]


needs_node = unittest.skipUnless(crewdraw.NODE, "node isn't installed")


def built(comments, titles=None, mode="shadow", merged=()):
    return grants.build({"comments": comments, "titles": titles or {}, "merged": list(merged),
                         "mode": mode}, NOW)


class MergerBodiesTest(unittest.TestCase):
    """The panel reads exactly what launcher/merger.py writes."""

    def test_matches_the_mergers_own_bodies(self):
        import merger
        d = merger.Decision(number=701, head=SHA, verdict=merger.GRANT)
        self.assertEqual(grants.MERGER, merger.MERGER)
        for body, group, reason in (
                (merger.would_body(d), "would", "standing grant"),
                (merger.merged_body(d), "merged", "standing grant"),
                (merger.enqueued_body(d), "enqueued", "standing grant"),
                (merger.left_body(merger.Decision(number=701, head=SHA,
                                                  verdict="miss: the reviewer hasn't approved at head")),
                 "left", "the reviewer hasn't approved at head")):
            got = grants.call(comment(701, body, 5))
            self.assertEqual((got["group"], got["reason"]), (group, reason), body)


class BuildTest(unittest.TestCase):
    def test_latest_call_per_pr_wins_newest_first(self):
        g_ = built([comment(701, would(), 300), comment(701, merged(), 60),
                    comment(653, left("not opened by productswarm-builder[bot]"), 120),
                    comment(702, would("approved ask"), 30)],
                   titles={701: "Desk panel", 653: "Docs"})
        self.assertEqual([(x["number"], x["group"]) for x in g_["calls"]],
                         [(702, "would"), (701, "merged"), (653, "left")])
        self.assertEqual(g_["calls"][1]["title"], "Desk panel")
        self.assertIsNone(g_["calls"][0]["title"])
        self.assertEqual(g_["calls"][2]["reason"], "not opened by productswarm-builder[bot]")
        self.assertTrue(g_["read"])
        self.assertEqual(g_["mode"], "shadow")

    def test_only_the_merger_on_prs_in_the_last_24_hours(self):
        g_ = built([comment(1, would(), 60, user="productswarm-builder[bot]"),
                    comment(2, would(), 60, kind="issues"),
                    comment(3, would(), 25 * 60),
                    comment(4, would(), -5),                       # after the build: not yet
                    comment(5, "Would merge? Not a call.\n\n-- merger", 60),
                    comment(6, would(), 23 * 60)])
        self.assertEqual([x["number"] for x in g_["calls"]], [6])

    def test_unread_and_unknown_mode(self):
        g_ = grants.build({"comments": None, "titles": {}, "mode": None}, NOW)
        self.assertFalse(g_["read"])
        self.assertIsNone(g_["mode"])
        self.assertEqual(grants.build({"comments": [], "mode": "sideways"}, NOW)["mode"], None)


@needs_node
class QueueTest(unittest.TestCase):
    """#746: under a merge queue the merger enqueues and GitHub merges later."""

    def test_enqueued_then_merged_once_it_lands(self):
        cs = [comment(701, enqueued(), 60), comment(702, enqueued("approved ask"), 30)]
        g_ = built(cs, mode="live")
        self.assertEqual([(x["number"], x["group"]) for x in g_["calls"]],
                         [(702, "enqueued"), (701, "enqueued")])
        html = render(g_)
        self.assertIn('<h3 class="enqueued">Enqueued</h3>', html)
        self.assertIn("enqueued under approved ask, ", html)

        g_ = built(cs, mode="live", merged=[701])
        self.assertEqual([(x["number"], x["group"], x["queued"]) for x in g_["calls"]],
                         [(702, "enqueued", True), (701, "merged", True)])
        html = render(g_)
        self.assertIn("merged under standing grant via the queue, ", html)
        self.assertLess(html.index('<h3 class="merged">'), html.index('<h3 class="enqueued">'))
        self.assertIs(grants.state(g_)["calls"][1]["queued"], True)

    def test_a_direct_merge_isnt_marked_queued(self):
        g_ = built([comment(701, merged(), 60)], merged=[701])
        self.assertFalse(g_["calls"][0]["queued"])
        self.assertNotIn("via the queue", render(g_))

    def test_fetch_reads_whether_closed_prs_merged(self):
        def gh_json(_api, path):
            n = int(path.rsplit("/", 1)[1])
            return {"title": f"PR {n}", "pull_request": {"merged_at": "2026-11-09T14:30:00Z" if n == 701 else None}}

        raw = grants.fetch(REPO, NOW, lambda p, jq=".[]": [comment(701, enqueued(), 60),
                                                           comment(703, enqueued(), 50),
                                                           comment(702, enqueued(), 40)],
                           gh_json, {702: "Open one"})
        self.assertEqual(raw["merged"], [701])
        groups = {x["number"]: x["group"] for x in grants.build(raw, NOW)["calls"]}
        self.assertEqual(groups, {701: "merged", 702: "enqueued", 703: "enqueued"})


@needs_node
class RenderTest(unittest.TestCase):
    def test_lines_groups_and_links(self):
        g_ = built([comment(701, merged(), 60, cid=11),
                    comment(702, would(), 30, cid=12),
                    comment(653, left("touches ops/ & needs <you>"), 120, cid=13)],
                   titles={701: "Desk panel"}, mode="live")
        html = render(g_)
        self.assertIn("<h2>Grants in use</h2>", html)
        self.assertIn(grants.MODES["live"], html)
        self.assertIn(f'<a href="{BASE}/pull/701">#701</a> Desk panel: '
                      f'<a href="{BASE}/pull/701#issuecomment-11">merged under standing grant, '
                      f'<time datetime="2026-11-09T14:00:00Z">14:00</time></a>', html)
        self.assertIn("would merge (standing grant), ", html)
        self.assertIn("left for you: touches ops/ &amp; needs &lt;you&gt;, ", html)
        self.assertNotIn(SHA, html)
        self.assertNotIn("-- merger", html)
        order = [html.index(h) for h in ("<h3 class=\"merged\">Merged</h3>",
                                         "<h3 class=\"would\">Would merge (shadow)</h3>",
                                         "<h3 class=\"left\">Left for you</h3>")]
        self.assertEqual(order, sorted(order))

    def test_states(self):
        quiet = render(built([]))
        self.assertIn(grants.MODES["shadow"], quiet)
        self.assertIn("No merger calls in the last 24 hours.", quiet)
        unread = render(grants.build({"comments": None, "mode": "off"}, NOW))
        self.assertIn("The merger is off.", unread)
        self.assertIn("Couldn't read the merger's calls.", unread)
        self.assertNotIn("No merger calls", unread)
        self.assertIn(grants.UNKNOWN_MODE,
                      render(grants.build({"comments": [], "mode": None}, NOW)))
        self.assertEqual(render(None), "")


class FetchTest(unittest.TestCase):
    def test_reads_comments_since_and_titles_of_closed_prs_only(self):
        paths, calls = [], []

        def gh_items(path, jq=".[]"):
            paths.append(path)
            return [comment(701, merged(), 60), comment(702, would(), 30),
                    comment(9, "hello", 10, user="someone")]

        def gh_json(*args):
            calls.append(args)
            return {"title": "Merged one"}

        raw = grants.fetch(REPO, NOW, gh_items, gh_json, {702: "Open one"})
        self.assertEqual(paths, [f"repos/{REPO}/issues/comments?since=2026-11-08T15:00:00Z&per_page=100"])
        self.assertEqual(calls, [("api", f"repos/{REPO}/issues/701")])
        self.assertEqual(raw["titles"], {701: "Merged one", 702: "Open one"})
        self.assertEqual(len(raw["comments"]), 2)
        self.assertIn(raw["mode"], (*grants.MODES, None))

    def test_unreadable_comments_and_titles(self):
        def boom(*a, **k):
            raise RuntimeError("gh api failed")

        self.assertIsNone(grants.fetch(REPO, NOW, boom, boom, {})["comments"])
        raw = grants.fetch(REPO, NOW, lambda p, jq=".[]": [comment(701, merged(), 60)], boom, {})
        self.assertEqual(raw["titles"], {})
        self.assertEqual(built(raw["comments"])["calls"][0]["title"], None)

    def test_mode_reads_the_committed_swarm_toml(self):
        self.assertIn(grants.mode(), grants.MODES)


class CrewTest(unittest.TestCase):
    def test_on_crew_after_the_reviewer_and_in_state(self):
        m = {"repo": REPO, "grants": built([comment(701, would(), 60)])}
        names = list(crewpage.SECTIONS)   # #1113
        self.assertEqual(names.index("grants"), names.index("reviewer") + 1)
        self.assertIn("grants", crewpage.KEYS)
        s = state.plain({"grants": grants.state(m["grants"])})
        self.assertEqual(json.loads(json.dumps(s)), s)
        self.assertEqual(s["grants"]["calls"][0]["number"], 701)
        self.assertEqual(s["grants"]["calls"][0]["time"], "2026-11-09T14:00:00Z")
        self.assertTrue(re.match(r"https://", s["grants"]["calls"][0]["link"]))
        self.assertEqual(s["grants"]["mode_text"], grants.MODES["shadow"])


if __name__ == "__main__":
    unittest.main()
