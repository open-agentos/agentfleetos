"""Tests for #1012: the paths baseline, `swarm classify compare` and `swarm classify run effort`,
with no network and no model credential."""
import datetime as dt
import json
import shutil
import tempfile
import unittest
from pathlib import Path

import classifier
import effortrun
import evalrun
from labelset import Item, load_labelset

HERE = Path(__file__).resolve().parent
FIXTURE = HERE / "testdata"
NOW = dt.datetime(2026, 11, 16, 9, 0, tzinfo=dt.timezone.utc)
REPO = "o/r"


def pr(n, title="Add a page", paths=("dashboard/x.py",), body="", labels=(), closes=(), merged=None):
    return {"number": n, "title": title, "body": body,
            "mergedAt": merged or f"2026-11-14T{n % 24:02d}:00:00Z",
            "labels": {"nodes": [{"name": lb} for lb in labels]},
            "files": {"totalCount": len(paths), "nodes": [{"path": p} for p in paths]},
            "closingIssuesReferences": {"nodes": [{"number": c, "title": f"issue {c}",
                                                   "repository": {"nameWithOwner": REPO}}
                                                  for c in closes]}}


def reply(label, fix=False):
    return json.dumps({"label": label, "flags": {"fix": fix}, "evidence": "Title: Add a page"})


class PathsBaselineTest(unittest.TestCase):
    def setUp(self):
        self.ls = load_labelset(HERE / "labelsets" / "effort.yml")

    def label(self, paths_line, body=""):
        item = Item("pr-1", f"Title: x\nLinked issue: none\nPaths touched (9): {paths_line}\n"
                            f"Body:\n{body}", "", "test", "owner")
        return classifier.BASELINES["paths"](self.ls, [], item)

    def test_rules_in_order(self):
        self.assertEqual(self.label("roles/builder.md, launcher/swarm.py").label, "governance")
        self.assertEqual(self.label("governance/decisions/GOV-1.md").label, "governance")
        self.assertEqual(self.label("research/brief.md, dashboard/x.py").label, "knowledge")
        self.assertEqual(self.label("README.md, dashboard/README.md").label, "knowledge")
        self.assertEqual(self.label("dashboard/x.py, dashboard/README.md").label, "capability")
        self.assertEqual(self.label("launcher/swarm.py, and 3 more").label, "upkeep")
        self.assertEqual(self.label("none").label, "upkeep")

    def test_fix_flag_from_references(self):
        self.assertTrue(self.label("launcher/a.py", "Fixes #12").flags["fix"])
        self.assertTrue(self.label("launcher/a.py", "A follow-up to #12.").flags["fix"])
        self.assertFalse(self.label("launcher/a.py", "Closes #12").flags["fix"])

    def test_touched_reads_the_item_format(self):
        self.assertEqual(classifier.touched("Paths touched (5): a.py, b/c.md, and 3 more"),
                         ["a.py", "b/c.md"])


class CompareTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.dir = self.tmp / "classify"
        shutil.copytree(FIXTURE, self.dir)
        self.manifest = self.tmp / "swarm.toml"
        self.manifest.write_text("[classify]\nmodel = \"claude-haiku-5-5\"\n")

    def swap_splits(self):
        """Make the fixture's recorded dev items the test split (the prompt has no split, so
        the recordings still replay)."""
        path = self.dir / "data" / "fixture.jsonl"
        rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
        for r in rows:
            r["split"] = {"dev": "test", "test": "dev"}[r["split"]]
        path.write_text("".join(json.dumps(r) + "\n" for r in rows))

    def test_all_three_side_by_side_and_the_model_chosen_when_it_passes(self):
        self.swap_splits()
        said = []
        use = evalrun.compare("fixture", self.dir, "test", manifest=self.manifest, say=said.append)
        self.assertEqual(use, "model")
        text = (self.dir / "reports" / "fixture.md").read_text()
        for heading in ("## Baseline: majority", "## Baseline: paths", "## The model",
                        "### Per label", "### Confusion matrix", "### Share error by week"):
            self.assertIn(heading, text)
        self.assertIn("**The cache uses:** `model`", text)
        self.assertNotIn(str(self.tmp), text)

    def test_no_recordings_reports_the_model_not_run_and_falls_back_to_paths(self):
        shutil.rmtree(self.dir / "recordings")
        self.swap_splits()
        use = evalrun.compare("fixture", self.dir, "test", manifest=self.manifest, say=lambda s: None)
        self.assertEqual(use, "paths")
        text = (self.dir / "reports" / "fixture.md").read_text()
        self.assertIn("| model | not run | not run | – |", text)
        self.assertIn("Not run: no recording of sample 1", text)

    def test_a_model_that_fails_the_pass_mark_falls_back_to_paths(self):
        self.swap_splits()
        ls = self.dir / "labelsets" / "fixture.yml"
        ls.write_text(ls.read_text().replace("accuracy: 0.", "accuracy: 0.99 #"))
        use, why = evalrun.model_choice("fixture", self.dir, manifest=self.manifest)
        self.assertEqual((use, why.split(" (")[0]), ("paths", "the model"))
        self.assertIn("fails the pass mark", why)


class RunTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.dir = self.tmp / "classify"
        (self.dir / "labelsets").mkdir(parents=True)
        shutil.copy(HERE / "labelsets" / "effort.yml", self.dir / "labelsets")
        self.manifest = self.tmp / "swarm.toml"
        self.manifest.write_text("[classify]\nmodel = \"claude-haiku-5-5\"\n")
        self.prs = [pr(1101, closes=[7]), pr(1102, "Tidy the launcher", ["launcher/a.py"],
                                              body="Fixes #1101")]
        self.goal = {7: "o/r#987"}
        self.calls = []
        self.said = []

    def runner(self, model, system, user, budget):
        self.calls.append(user)
        self.assertLessEqual(budget, effortrun.PER_PR_USD * 2)   # GOV-0045's cap per PR
        return reply("capability"), 0.01

    def goals(self, closes):
        self.resolved = closes
        return {p: next((self.goal[c] for c in cs if c in self.goal), None)
                for p, cs in closes.items()}

    def run_(self, use="paths", **kw):
        return effortrun.run(self.dir, "2026-11-13", REPO, manifest=self.manifest,
                             fetch=lambda repo, since: [dict(p) for p in self.prs],
                             goals=self.goals, runner=kw.get("runner", self.runner), use=use,
                             now=NOW, say=self.said.append)

    def cache(self):
        return json.loads((self.dir / "cache" / "effort.json").read_text())

    def test_paths_cache_is_schema_1_with_goal(self):
        self.assertEqual(self.run_(), 0)
        c = self.cache()
        self.assertEqual((c["schema"], c["labelset"], c["classifier"], c["updated_at"]),
                         (1, "effort", "paths", "2026-11-16T09:00:00Z"))
        e = c["prs"]["1101"]
        self.assertEqual({k: e[k] for k in ("repo", "label", "fix", "fixes", "goal", "labeller")},
                         {"repo": REPO, "label": "capability", "fix": False, "fixes": None,
                          "goal": "o/r#987", "labeller": "paths"})
        e = c["prs"]["1102"]
        self.assertEqual((e["label"], e["fix"], e["fixes"], e["goal"]), ("upkeep", True, 1101, None))
        self.assertEqual(self.calls, [])

    def test_rerun_with_no_new_merges_makes_no_model_calls(self):
        self.assertEqual(self.run_("model"), 0)
        self.assertEqual(len(self.calls), 6)            # 2 PRs, 3 samples each
        self.assertEqual(self.cache()["prs"]["1101"]["labeller"], "model")
        self.calls.clear()
        self.assertEqual(self.run_("model"), 0)
        self.assertEqual(self.calls, [])

    def test_a_changed_goal_makes_no_model_call_and_keeps_the_stored_goal(self):
        self.run_("model")
        self.calls.clear()
        self.goal = {7: "o/r#999"}
        self.assertEqual(self.run_("model"), 0)
        self.assertEqual(self.calls, [])
        self.assertEqual(self.cache()["prs"]["1101"]["goal"], "o/r#987")

    def test_a_changed_text_relabels(self):
        self.run_("model")
        self.calls.clear()
        self.prs[0]["title"] = "Add a better page"
        self.run_("model")
        self.assertEqual(len(self.calls), 3)

    def test_recorded_replies_are_reused_not_called_again(self):
        self.run_("model")
        (self.dir / "cache" / "effort.json").unlink()
        self.calls.clear()
        self.assertEqual(self.run_("model"), 0)
        self.assertEqual(self.calls, [])

    def test_a_kind_label_overrides_the_cache_on_the_next_run(self):
        self.run_("model")
        self.calls.clear()
        self.prs[0]["labels"] = {"nodes": [{"name": "kind:governance"}]}
        self.goal = {7: "o/r#999"}
        self.assertEqual(self.run_("model"), 0)
        self.assertEqual(self.calls, [])
        e = self.cache()["prs"]["1101"]
        self.assertEqual((e["label"], e["labeller"], e["goal"]), ("governance", "owner", "o/r#987"))
        rows = [json.loads(line) for line in
                (self.dir / "data" / "effort.jsonl").read_text().splitlines()]
        self.assertEqual([(r["id"], r["label"], r["labelled_by"], r["split"]) for r in rows],
                         [("pr-1101", "governance", "owner", "dev")])
        self.calls.clear()
        self.assertEqual(self.run_("model"), 0)         # and it stays settled
        self.assertEqual(self.calls, [])
        self.assertEqual(self.cache()["prs"]["1101"]["label"], "governance")

    def test_a_kind_label_on_a_new_pr_still_gets_its_fix_flag(self):
        self.prs[1]["labels"] = {"nodes": [{"name": "kind:capability"}]}
        self.run_()
        e = self.cache()["prs"]["1102"]
        self.assertEqual((e["label"], e["labeller"], e["fix"]), ("capability", "owner", True))

    def test_a_switch_from_paths_to_model_relabels(self):
        self.run_("paths")
        self.run_("model")
        self.assertEqual(len(self.calls), 6)
        self.assertEqual(self.cache()["classifier"], "model")

    def test_the_cap_stops_the_run_and_keeps_what_was_labelled(self):
        def broke(*a):
            if len(self.calls) >= 3:
                raise classifier.ModelError("claude -p ended with error_max_budget_usd")
            return self.runner(*a)
        self.assertEqual(self.run_("model", runner=broke), 1)
        self.assertEqual(list(self.cache()["prs"]), ["1101"])
        self.assertIn("stopped early", self.said[-1])

    def test_with_no_eval_it_uses_paths_and_says_why(self):
        self.assertEqual(self.run_(use=None), 0)
        self.assertEqual(self.cache()["classifier"], "paths")
        self.assertIn("using paths: the model has no complete test-split eval", self.said[0])

    def test_a_bad_since_cant_run(self):
        with self.assertRaises(effortrun.CantRun):
            effortrun.run(self.dir, "last week", fetch=lambda *a: [], goals=self.goals)


if __name__ == "__main__":
    unittest.main()
