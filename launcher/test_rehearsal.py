"""Tests for rehearsal.py and `swarm memory rehearse` (#1189, FEAT-19: the replay gate)."""
import datetime as dt
import io
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

import lessons as L
import rehearsal as R

ROOT = Path(__file__).resolve().parent.parent
DRILL = ROOT / "evals" / "lessons" / "drill"
REPO = "open-agentos/agentfleetos"
NOW = dt.datetime(2026, 11, 18, 2, 0, tzinfo=dt.timezone.utc)
CFG = {"replay_model": "claude-haiku-5-5", "replay_cap_usd": 0.5, "replays_per_night": 10}


def git(*args, cwd):
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True,
                          text=True).stdout


class FakeModel:
    """A stand-in for `claude -p`: follows the lesson when it is in the system prompt (or
    never, with obey=False), writes PR_BODY.md in the replay's directory, and reports a cost.
    It records every call and, like a model that tried, attempts a push from its directory."""

    def __init__(self, obey=True, cost=(0.10, 0.12), subtype=("success", "success"),
                 always_why=False):
        self.obey, self.cost, self.subtype, self.always_why = obey, cost, subtype, always_why
        self.calls = []

    def __call__(self, argv, cwd, env, stdin):
        n = len(self.calls)
        with_lesson = "--append-system-prompt" in argv
        push = subprocess.run(["git", "push", "origin", "HEAD"], cwd=cwd, capture_output=True,
                              text=True, env={**env, "PATH": os.environ["PATH"]})
        self.calls.append({"argv": argv, "cwd": Path(cwd), "env": env, "stdin": stdin,
                           "with": with_lesson, "remotes": git("remote", cwd=cwd).split(),
                           "push_rc": push.returncode})
        why = self.always_why or (with_lesson and self.obey
                                  and "starts `Why:`" in argv[argv.index("--append-system-prompt") + 1])
        body = ("Why: lessons need a gate.\n\n" if why else "") + "Adds the replay gate.\n"
        (Path(cwd) / "PR_BODY.md").write_text(body)
        return {"subtype": self.subtype[n], "is_error": self.subtype[n] != "success",
                "result": "Wrote PR_BODY.md", "total_cost_usd": self.cost[n]}


class Base(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.home = self.tmp / "home"
        # the source repo: a local clone, as the engine has
        self.src = self.tmp / "src"
        self.src.mkdir()
        git("init", "-q", cwd=self.src)
        (self.src / "README.md").write_text("hello\n")
        (self.src / "launcher").mkdir()
        (self.src / "launcher" / "x.py").write_text("x = 1\n")
        git("add", "-A", cwd=self.src)
        git("-c", "user.name=t", "-c", "user.email=t@example.invalid", "commit", "-qm", "one",
            cwd=self.src)
        git("remote", "add", "origin", str(self.tmp / "nowhere.git"), cwd=self.src)
        self.sha = git("rev-parse", "HEAD", cwd=self.src).strip()
        # the repo root the lessons and cases live in: the drill's lesson and case, at our commit
        self.root = self.tmp / "root"
        (self.root / "evals" / "lessons" / "drill").mkdir(parents=True)
        self.store = self.root / "memory" / "lessons"
        self.store.mkdir(parents=True)
        case = (DRILL / "L-9001.toml").read_text().replace(
            "38be0c7f06ef9900d5fc4bc1bd5a9760f7a142cb", self.sha)
        (self.root / "evals" / "lessons" / "drill" / "L-9001.toml").write_text(case)
        self.lesson_file = self.store / "L-9001-pr-body-opens-with-why.md"
        shutil.copy(DRILL / self.lesson_file.name, self.lesson_file)

    def lesson(self) -> L.Lesson:
        return L.load(self.lesson_file)

    def rehearse(self, model, cfg=CFG, env=None):
        return R.rehearse(self.lesson(), home=self.home, cfg=cfg, source_for=lambda r: self.src,
                          runner=model, env=env if env is not None else {"PATH": "/usr/bin"},
                          now=lambda: NOW, root=self.root)

    def ledger(self):
        return [json.loads(x) for x in R.ledger_path(self.home).read_text().splitlines()]


class GateTest(Base):
    def test_drill_planted_correction_fails_without_and_passes_with(self):
        """Acceptance: the drill's planted correction produces a lesson whose case fails
        without it and passes with it, so it is promoted."""
        model = FakeModel()
        r = self.rehearse(model)
        self.assertEqual((r.result, r.status), (R.PROMOTED, "active"))
        self.assertEqual([c["with"] for c in model.calls], [False, True])
        self.assertFalse(r.without["passed"])
        self.assertTrue(r.with_["passed"])
        les = self.lesson()
        self.assertEqual(les.errors, [])
        self.assertEqual(les.status, "active")
        reh = les.meta["rehearsal"]
        self.assertEqual((reh["result"], reh["without"], reh["with"]), ("promoted", "fail", "pass"))
        self.assertEqual((reh["cost_without_usd"], reh["cost_with_usd"]), (0.1, 0.12))
        self.assertEqual(reh["hash"], R.lesson_hash(les, self.root / les.meta["eval_case"]))
        self.assertEqual(reh["model"], "claude-haiku-5-5")
        self.assertEqual(reh["at"], "2026-11-18")
        # the rest of the file is as it was
        before = (DRILL / self.lesson_file.name).read_text()
        after = self.lesson_file.read_text()
        self.assertEqual(after.split("rehearsal:")[1].split("---", 1)[1], before.split("---", 2)[2])
        self.assertEqual(after.replace("status: active", "status: proposed").split("rehearsal:")[0],
                         before.split("\n---\n")[0] + "\n")

    def test_case_that_fails_with_the_lesson_stays_proposed(self):
        """Acceptance: a lesson whose case fails with it stays proposed."""
        r = self.rehearse(FakeModel(obey=False))
        self.assertEqual((r.result, r.status), (R.KEPT, "proposed"))
        les = self.lesson()
        self.assertEqual(les.status, "proposed")
        self.assertEqual(les.meta["rehearsal"]["result"], "kept")
        self.assertEqual(les.meta["rehearsal"]["with"], "fail")
        self.assertIn("doesn't match", r.note)
        # and the validator won't take a hand edit to active
        les.meta["status"] = "active"
        ctx = L.Context(set(), {}, {}, REPO, root=self.root, today=dt.date(2026, 11, 18), owner="o")
        self.assertTrue(any("passing rehearsal" in e for e in L.validate(les, ctx)))

    def test_both_pass_promotes_only_if_it_costs_nothing_extra(self):
        r = self.rehearse(FakeModel(always_why=True, cost=(0.10, 0.10)))
        self.assertEqual(r.result, R.PROMOTED)
        shutil.copy(DRILL / self.lesson_file.name, self.lesson_file)
        r = self.rehearse(FakeModel(always_why=True, cost=(0.10, 0.11)))
        self.assertEqual((r.result, r.status), (R.KEPT, "proposed"))

    def test_changed_active_lesson_reruns_and_is_demoted_if_it_fails(self):
        self.rehearse(FakeModel())
        self.assertEqual(R.due([self.lesson()], REPO, self.root), [])
        # an edit to the lesson makes it due again
        text = self.lesson_file.read_text().replace("before any heading", "before any heading at all")
        self.lesson_file.write_text(text)
        self.assertEqual([x.id for x in R.due([self.lesson()], REPO, self.root)], ["L-9001"])
        r = self.rehearse(FakeModel(obey=False))
        self.assertEqual((r.result, r.status), (R.DEMOTED, "proposed"))
        self.assertEqual(self.lesson().status, "proposed")
        # rerun at the same hash: not due; a changed case makes it due
        self.assertEqual(R.due([self.lesson()], REPO, self.root), [])
        case = self.root / "evals" / "lessons" / "drill" / "L-9001.toml"
        case.write_text(case.read_text() + "\n# edited\n")
        self.assertEqual(len(R.due([self.lesson()], REPO, self.root)), 1)

    def test_confirmed_when_an_active_lessons_rerun_passes(self):
        self.rehearse(FakeModel())
        self.lesson_file.write_text(self.lesson_file.read_text().replace("one sentence", "a sentence"))
        r = self.rehearse(FakeModel())
        self.assertEqual((r.result, r.status), (R.CONFIRMED, "active"))

    def test_due_skips_retired_unreadable_and_caseless(self):
        self.lesson_file.write_text(self.lesson_file.read_text().replace("status: proposed", "status: retired"))
        self.assertEqual(R.due([self.lesson()], REPO, self.root), [])
        self.lesson_file.write_text(self.lesson_file.read_text().replace(
            "status: retired", "status: proposed").replace(
            "eval_case: evals/lessons/drill/L-9001.toml", "eval_case:"))
        self.assertEqual(R.due([self.lesson()], REPO, self.root), [])
        self.assertEqual(R.due([self.lesson()], "open-agentos/other", self.root), [])


class SafetyTest(Base):
    def test_a_replay_never_pushes_comments_or_labels(self):
        """Acceptance: no shell (so no git or gh), no hooks or settings, no remote to push
        to, no GitHub or git credentials, and the source repo is untouched."""
        model = FakeModel()
        env = {"PATH": "/usr/bin", "ANTHROPIC_API_KEY": "sk-test", "GH_TOKEN": "t",
               "GITHUB_TOKEN": "t", "GH_CONFIG_DIR": "/home/x/.config/gh", "GH_HOST": "x",
               "CLAUDE_CODE_OAUTH_TOKEN": "t", "SSH_AUTH_SOCK": "/tmp/s", "GIT_ASKPASS": "x"}
        refs = git("show-ref", cwd=self.src)
        self.rehearse(model, env=env)
        for c in model.calls:
            argv = c["argv"]
            self.assertIn("--bare", argv)          # no hooks, CLAUDE.md, plugins or OAuth
            self.assertIn("--restricted", argv)    # no shell or web; settings files ignored
            self.assertIn("--strict-mcp-config", argv)
            tools = argv[argv.index("--tools") + 1].split(",")
            self.assertEqual(tools, ["Read", "Edit", "Write", "Glob", "Grep"])
            self.assertNotIn("bypassPermissions", argv)
            self.assertEqual(c["remotes"], [])
            self.assertNotEqual(c["push_rc"], 0)
            self.assertNotEqual(c["cwd"].resolve(), self.src.resolve())
            self.assertFalse(c["cwd"].exists())    # deleted after the run
            env_ = c["env"]
            for k in ("GH_TOKEN", "GITHUB_TOKEN", "GH_HOST", "CLAUDE_CODE_OAUTH_TOKEN",
                      "SSH_AUTH_SOCK", "GIT_ASKPASS"):
                self.assertNotIn(k, env_)
            self.assertEqual(env_["ANTHROPIC_API_KEY"], "sk-test")
            self.assertEqual(env_["GIT_TERMINAL_PROMPT"], "0")
            self.assertNotEqual(env_["GH_CONFIG_DIR"], "/home/x/.config/gh")
        self.assertEqual(git("show-ref", cwd=self.src), refs)
        self.assertEqual(git("status", "--porcelain", cwd=self.src), "")

    def test_the_lesson_reaches_only_the_with_run(self):
        model = FakeModel()
        self.rehearse(model)
        without, with_ = (c["argv"] for c in model.calls)
        self.assertNotIn("--append-system-prompt", without)
        pack = with_[with_.index("--append-system-prompt") + 1]
        self.assertIn("L-9001: Open every PR body", pack)
        self.assertIn("the ruling wins", pack)
        self.assertEqual(model.calls[0]["stdin"], model.calls[1]["stdin"])


class CapTest(Base):
    def test_each_replay_is_capped_and_its_cost_recorded_against_the_lesson(self):
        """Acceptance: each replay's cost is recorded against its lesson."""
        model = FakeModel()
        self.rehearse(model)
        for c in model.calls:
            self.assertEqual(c["argv"][c["argv"].index("--max-budget-usd") + 1], "0.5")
            self.assertEqual(c["argv"][c["argv"].index("--model") + 1], "claude-haiku-5-5")
        rows = self.ledger()
        self.assertEqual([(r["lesson"], r["arm"], r["cost_usd"], r["passed"]) for r in rows],
                         [("L-9001", "without", 0.1, False), ("L-9001", "with", 0.12, True)])

    def test_a_replay_at_its_cap_stops_the_rehearsal(self):
        """Acceptance: the run stops at the cap. A replay that hits --max-budget-usd is
        inconclusive, the other isn't paid for, and the lesson stays as it was."""
        model = FakeModel(subtype=("error_max_budget_usd", "success"), cost=(0.51, 0.1))
        r = self.rehearse(model)
        self.assertEqual(len(model.calls), 1)
        self.assertEqual((r.result, r.status), (R.INCONCLUSIVE, "proposed"))
        self.assertIn("without: at cap", r.note)
        les = self.lesson()
        self.assertEqual((les.meta["rehearsal"]["without"], les.meta["rehearsal"]["with"]),
                         ("at cap", "skipped"))
        self.assertEqual(les.meta["rehearsal"]["cost_without_usd"], 0.51)
        self.assertEqual([r["ending"] for r in self.ledger()], ["at cap"])
        # inconclusive stays due
        self.assertEqual(len(R.due([les], REPO, self.root)), 1)

    def test_the_nightly_count_stops_replays(self):
        R.ledger_path(self.home).parent.mkdir(parents=True)
        rows = [{"at": "2026-11-18T01:00:00+00:00", "lesson": "L-0001"}] * 9
        rows.append({"at": "2026-11-17T23:59:00+00:00", "lesson": "L-0001"})  # last night
        R.ledger_path(self.home).write_text("".join(json.dumps(x) + "\n" for x in rows))
        model = FakeModel()
        r = self.rehearse(model)
        self.assertEqual(r.result, "waits")
        self.assertEqual(model.calls, [])
        self.assertEqual(self.lesson().status, "proposed")
        self.assertNotIn("rehearsal", self.lesson().meta)
        r = self.rehearse(model, cfg={**CFG, "replays_per_night": 11})
        self.assertEqual(r.result, R.PROMOTED)


class FormatTest(Base):
    def test_the_committed_drill_is_well_formed(self):
        case = R.load_case(DRILL / "L-9001.toml")
        self.assertEqual(case.lesson, "L-9001")
        les = L.load(DRILL / "L-9001-pr-body-opens-with-why.md")
        self.assertEqual(les.errors, [])
        self.assertEqual(R.case_path(les), DRILL / "L-9001.toml")
        self.assertEqual(les.status, "proposed")
        # the commit is on main, so the live drill can replay it
        rc = subprocess.run(["git", "cat-file", "-e", case.commit + "^{commit}"], cwd=ROOT,
                            capture_output=True).returncode
        if rc != 0:
            self.skipTest("the drill's commit isn't in this clone")

    def test_case_errors(self):
        p = self.root / "bad.toml"
        good = (self.root / "evals" / "lessons" / "drill" / "L-9001.toml").read_text()
        for edit, msg in ((lambda s: s.replace(self.sha, self.sha[:7]), "full commit sha"),
                          (lambda s: 'surprise = 1\n' + s, "unknown key surprise"),
                          (lambda s: s.replace("changed =", "touched ="), "check.touched"),
                          (lambda s: s.replace('lesson = "L-9001"', 'lesson = "9001"'), "isn't L-NNNN"),
                          (lambda s: s + "reply_matches = ['(']\n", "isn't a regular expression"),
                          (lambda s: s.replace('changed = ["PR_BODY.md"]', "changed = []"),
                           "non-empty list")):
            p.write_text(edit(good))
            with self.assertRaises(R.RehearsalError) as cm:
                R.load_case(p)
            self.assertIn(msg, str(cm.exception))

    def test_eval_case_outside_the_repo_is_refused(self):
        self.lesson_file.write_text(self.lesson_file.read_text().replace(
            "eval_case: evals/lessons/drill/L-9001.toml", "eval_case: ../../etc/x.toml"))
        r = self.rehearse(FakeModel())
        self.assertEqual(r.result, "error")
        self.assertIn("must be a path in the repo", r.note)

    def test_check(self):
        o = R.Outcome("all done", "+++ b/a.md\n+hi\n", ["a.md", "launcher/x.py"], 0.1, "done")
        self.assertEqual(R.run_check({"reply_matches": ["done"], "changed": ["*.md"]}, o), (True, []))
        ok, why = R.run_check({"reply_lacks": ["done"], "unchanged": ["launcher/**"],
                               "diff_matches": ["^\\+bye"]}, o)
        self.assertFalse(ok)
        self.assertEqual(len(why), 3)

    def test_hash_written_as_a_string(self):
        les = self.lesson()
        R.write_result(les, "proposed", {"hash": "012345678901", "result": "kept", "note": "a: b"})
        meta = self.lesson().meta["rehearsal"]
        self.assertEqual(meta["hash"], "012345678901")
        self.assertEqual(meta["note"], "a: b")
        R.write_result(self.lesson(), "proposed", {"result": "kept"})
        self.assertEqual(self.lesson().meta["rehearsal"], {"result": "kept"})

    def test_settings(self):
        p = self.tmp / "swarm.toml"
        p.write_text("")
        self.assertEqual(R.settings(p), R.DEFAULTS)
        p.write_text("[memory]\nreplay_cap_usd = 0.25\nreplays_per_night = 4\n")
        self.assertEqual(R.settings(p)["replay_cap_usd"], 0.25)
        for bad in ("replay_cap_usd = 0", "replay_cap_usd = 50", "replays_per_night = -1",
                    "replays_per_night = 2.5", 'replay_model = ""'):
            p.write_text(f"[memory]\n{bad}\n")
            with self.assertRaises(R.RehearsalError):
                R.settings(p)
        self.assertEqual(R.settings(ROOT / "swarm.toml"), R.DEFAULTS)

    def test_report(self):
        r = self.rehearse(FakeModel())
        text = R.report_text([r, R.Result("L-0002", "waits", note="it waits")], NOW.date())
        self.assertIn("## Rehearsals, 2026-11-18", text)
        self.assertIn("- L-9001: promoted (now active). Without it: fail, $0.10; with it: pass, $0.12.", text)
        self.assertIn("- L-0002: waits: it waits", text)
        self.assertIn("No lessons were due.", R.report_text([], NOW.date()))


class CliTest(Base):
    def run_swarm(self, *argv, env=None):
        import swarm
        out = []
        launcher = swarm.Launcher(self.home, root=self.src, out=out.append)
        model = FakeModel()
        with mock.patch.dict(os.environ, env or {}, clear=False), \
             mock.patch.object(R, "claude_runner", model), \
             mock.patch.object(R, "ROOT", self.root), \
             mock.patch.multiple(L, LESSONS=self.store, INDEX=self.root / "memory" / "INDEX.md"):
            if env is None:
                os.environ.pop("ANTHROPIC_API_KEY", None)
            code = swarm.main(list(argv), launcher)
        return code, "\n".join(out), model

    def test_refuses_without_the_engine_key(self):
        code, out, model = self.run_swarm("memory", "rehearse", "--repo", REPO)
        self.assertEqual(code, 2)
        self.assertIn("ANTHROPIC_API_KEY isn't set", out)
        self.assertEqual(model.calls, [])

    def test_rehearses_due_lessons_and_updates_the_index(self):
        manifest = self.tmp / "swarm.toml"
        manifest.write_text("[memory]\nreplays_per_night = 10\n")
        code, out, model = self.run_swarm("memory", "rehearse", "--repo", REPO, "--manifest",
                                          str(manifest), env={"ANTHROPIC_API_KEY": "sk-test"})
        self.assertEqual(code, 0, out)
        self.assertIn("- L-9001: promoted (now active)", out)
        self.assertEqual(len(model.calls), 2)
        self.assertIn("L-9001", (self.root / "memory" / "INDEX.md").read_text())

    def test_named_lesson_must_be_proposed_or_active(self):
        code, out, _ = self.run_swarm("memory", "rehearse", "L-0404", "--repo", REPO,
                                      env={"ANTHROPIC_API_KEY": "sk-test"})
        self.assertEqual(code, 1)
        self.assertIn("no lesson L-0404", out)


if __name__ == "__main__":
    unittest.main()
