"""Tests for episodes (#1184, FEAT-14): session notes, the engine's signals, act tags and
retags, the scrubber and the prompt cut, `swarm acts` by kind and `swarm memory episodes`."""
from __future__ import annotations

import datetime as dt
import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import acts  # noqa: E402
import episodes  # noqa: E402
import ledger  # noqa: E402
import stophook  # noqa: E402
import swarm  # noqa: E402

UTC = dt.timezone.utc
OWNER = "owner"
BOT = "productswarm-builder[bot]"
REPO = "o/r"
SID = "sid-1"
NOW = dt.datetime(2026, 11, 17, 18, 0, tzinfo=UTC)
PROMPT = ("You are the builder for AgentFleetOS. Read CLAUDE.md, PRODUCT.md and roles/builder.md, "
          "then work on issue #7.")


class Tmp(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.home = Path(tmp.name)
        (self.home / "launcher").mkdir()


# ---------------------------------------------------------------- scrubbing and the prompt

class ScrubTest(unittest.TestCase):
    def test_tokens_env_values_emails_and_home_paths_are_stripped(self):
        env = {"MY_SETTING": "hunter2-very-private-value", "SHORT": "abc"}
        note = {"tried": "Pushed with ghp_" + "a" * 36 + " and sk-ant-api03-" + "b" * 40 + ".",
                "surprised": "GH_TOKEN=xyz123secret broke; mail me at someone@example.com.",
                "blocked": "Value hunter2-very-private-value in /Users/someone/.config/gh/hosts.yml "
                           "and ~/notes.txt and /home/ci/x."}
        ep = episodes.note_episode(session_id=SID, role="builder", model="m", repo=REPO, issue=7,
                                   pr=None, note=note, paths=[], prompt="", at=NOW)
        out = Path(tempfile.mkdtemp())
        self.assertEqual(episodes.write(out, [ep], env=episodes.env_values(env)), 1)
        line = (out / "2026-11-17.jsonl").read_text()
        for secret in ("ghp_", "sk-ant", "xyz123secret", "someone@example.com", "hunter2",
                       "/Users/someone", "~/notes", "/home/ci"):
            self.assertNotIn(secret, line)
        got = json.loads(line)["note"]
        self.assertIn("[redacted]", got["tried"])
        self.assertIn("GH_TOKEN=[redacted]", got["surprised"])
        self.assertIn("[email]", got["surprised"])
        self.assertIn("[env]", got["blocked"])
        self.assertIn("[path]", got["blocked"])
        self.assertIn("abc", episodes.scrub("abc", episodes.env_values(env)))   # short values stay

    def test_env_values_are_stripped_from_text_only(self):
        ep = {"schema": 1, "id": "x", "type": "act", "at": "2026-11-17T00:00:00Z", "repo": "o/agentfleet",
              "source": "https://github.com/o/agentfleet/issues/1", "what": "edited o/agentfleet"}
        got = episodes.clean(ep, ["o/agentfleet"])
        self.assertEqual((got["repo"], got["source"], got["what"]),
                         ("o/agentfleet", "https://github.com/o/agentfleet/issues/1", "edited [env]"))

    def test_repo_paths_and_shas_stay(self):
        text = "Touched launcher/acts.py at 0123456789abcdef0123456789abcdef01234567."
        self.assertEqual(episodes.scrub(text), text)

    def test_a_note_that_quotes_the_prompt_is_cut(self):
        note = {"tried": "I was told: read CLAUDE.md, PRODUCT.md and roles/builder.md, then work on issue #7.",
                "surprised": "none", "blocked": "The tests for the stop hook were slow."}
        ep = episodes.note_episode(session_id=SID, role="builder", model="m", repo=REPO, issue=7,
                                   pr=None, note=note, paths=[], prompt=PROMPT, at=NOW)
        self.assertEqual(ep["note"]["tried"], episodes.CUT)
        self.assertEqual(ep["note"]["blocked"], "The tests for the stop hook were slow.")
        self.assertEqual(ep["note"]["surprised"], "none")

    def test_a_few_shared_words_are_not_a_quote(self):
        self.assertEqual(episodes.cut_prompt("I read CLAUDE.md first.", PROMPT), "I read CLAUDE.md first.")


# ---------------------------------------------------------------- the note, through the stop hook

class FakeGitHub:
    def __init__(self, closing=(), files=()):
        self.closing, self.files = list(closing), list(files)

    def gh(self):
        def get(path):
            return {"state": "open", "labels": [{"name": "ready"}]} if path.endswith("/issues/7") else None

        def items(path):
            if path.endswith("/files?per_page=100"):
                return [{"filename": f} for f in self.files]
            if "/events" in path:
                return [{"event": "labeled", "label": {"name": "ready"}, "actor": {"login": OWNER},
                         "created_at": "2026-11-17T10:00:00Z"}]
            return []
        return stophook.GitHub(get=get, items=items,
                               closing_prs=lambda repo, n: [{"number": p} for p in self.closing])


class NoteTest(Tmp):
    def setUp(self):
        super().setUp()
        self.work = self.home / "wt"
        self.work.mkdir()
        e = swarm.Started(name="builder-1", role="builder", model="claude-x", session_id=SID,
                          started=NOW.timestamp() - 600, issue=7, by="watch")
        (self.home / "launcher" / "sessions.json").write_text(json.dumps([e.__dict__]))
        transcript = self.home / "t.jsonl"
        transcript.write_text(json.dumps({"type": "user", "message": {"role": "user", "content": PROMPT}}) + "\n")
        self.payload = {"session_id": SID, "cwd": str(self.work), "transcript_path": str(transcript)}
        self.g = FakeGitHub(closing=[50], files=["launcher/acts.py", "launcher/episodes.py"]).gh()

    def stop(self, active=False):
        return stophook.decide({**self.payload, "stop_hook_active": active}, self.home, REPO, self.g,
                               owner=lambda: OWNER, now=lambda: NOW)

    def episodes(self):
        return episodes.load([episodes.outbox(self.home)])

    def test_a_run_that_ends_normally_writes_one_note_episode(self):
        out = self.stop()
        self.assertEqual(out["decision"], "block")
        self.assertIn(episodes.NOTE_FILE, out["reason"])
        self.assertEqual(self.episodes(), [])
        (self.work / episodes.NOTE_FILE).write_text(json.dumps(
            {"tried": "Added the tagger.", "surprised": "none", "blocked": "GitHub search lagged."}))
        self.assertIsNone(self.stop(active=True))
        self.assertIsNone(self.stop(active=True))          # a second stop writes nothing more
        [ep] = self.episodes()
        self.assertEqual((ep["type"], ep["session_id"], ep["role"], ep["model"], ep["repo"], ep["issue"]),
                         ("note", SID, "builder", "claude-x", REPO, 7))
        self.assertEqual(ep["note"], {"tried": "Added the tagger.", "surprised": "none",
                                      "blocked": "GitHub search lagged."})
        self.assertFalse(ep["no_note"])
        self.assertEqual(ep["paths"], ["launcher/acts.py", "launcher/episodes.py"])
        self.assertEqual(ep["source"], f"https://github.com/{REPO}/issues/7")
        self.assertFalse((self.work / episodes.NOTE_FILE).exists())

    def test_a_run_that_ends_without_a_note_is_marked_no_note(self):
        self.assertEqual(self.stop()["decision"], "block")
        self.assertIsNone(self.stop(active=True))           # asked once, never again
        [ep] = self.episodes()
        self.assertTrue(ep["no_note"])
        self.assertIsNone(ep["note"])

    def test_a_note_quoting_the_prompt_is_cut_before_it_is_written(self):
        self.stop()
        (self.work / episodes.NOTE_FILE).write_text(json.dumps(
            {"tried": "Read CLAUDE.md, PRODUCT.md and roles/builder.md, then work on issue #7.",
             "surprised": "none", "blocked": "none"}))
        self.stop(active=True)
        [ep] = self.episodes()
        self.assertEqual(ep["note"]["tried"], episodes.CUT)
        self.assertNotIn("PRODUCT.md and roles", (episodes.outbox(self.home) / "2026-11-17.jsonl").read_text())

    def test_asking_for_the_note_keeps_git_from_committing_it(self):
        # A repo whose .gitignore doesn't list the note (another org repo, GOV-0036).
        subprocess.run(["git", "init", "-q", str(self.work)], check=True)
        self.stop()
        self.stop()                                          # asked once; excluded once
        exclude = (self.work / ".git" / "info" / "exclude").read_text().splitlines()
        self.assertEqual(exclude.count(f"/{episodes.NOTE_FILE}"), 1)
        (self.work / episodes.NOTE_FILE).write_text("{}")
        status = subprocess.run(["git", "status", "--porcelain", "--untracked-files=all"], cwd=self.work,
                                capture_output=True, text=True, check=True).stdout
        self.assertNotIn(episodes.NOTE_FILE, status)

    def test_an_actions_run_is_not_asked(self):
        e = swarm.Started(name="reviewer-1", role="reviewer", model="m", session_id=SID, started=0,
                          pr=50, by="actions")
        (self.home / "launcher" / "sessions.json").write_text(json.dumps([e.__dict__]))
        self.g = stophook.GitHub(get=lambda p: {"state": "closed"}, items=lambda p: [],
                                 closing_prs=lambda r, n: [])
        self.assertIsNone(self.stop())
        self.assertEqual(self.episodes(), [])


# ---------------------------------------------------------------- signals

class SignalTest(unittest.TestCase):
    def test_changes_requested_review_revert_and_unmerged_close(self):
        pr = {"number": 50, "html_url": "https://github.com/o/r/pull/50", "title": "Add x", "state": "open"}
        reviews = [{"id": 1, "state": "CHANGES_REQUESTED", "submitted_at": "2026-11-17T10:00:00Z",
                    "user": {"login": "productswarm-reviewer[bot]"}, "body": "Add a test for the retag.",
                    "html_url": "https://github.com/o/r/pull/50#pullrequestreview-1", "commit_id": "abc"},
                   {"id": 2, "state": "APPROVED", "submitted_at": "2026-11-17T11:00:00Z"}]
        [ep] = episodes.from_pr(pr, reviews)
        self.assertEqual((ep["type"], ep["asked"], ep["by"]),
                         ("review", "Add a test for the retag.", "productswarm-reviewer[bot]"))
        self.assertTrue(ep["source"].endswith("#pullrequestreview-1"))
        revert = {"number": 51, "title": 'Revert "Add x"', "merged_at": "2026-11-17T12:00:00Z",
                  "state": "closed", "html_url": "https://github.com/o/r/pull/51"}
        self.assertEqual([(e["type"], e["source"]) for e in episodes.from_pr(revert, [])],
                         [("revert", "https://github.com/o/r/pull/51")])
        closed = {"number": 52, "title": "Try y", "merged_at": None, "state": "closed",
                  "closed_at": "2026-11-17T13:00:00Z", "html_url": "https://github.com/o/r/pull/52"}
        self.assertEqual([(e["type"], e["source"]) for e in episodes.from_pr(closed, [])],
                         [("closed-unmerged", "https://github.com/o/r/pull/52")])

    def test_failed_and_capped_runs(self):
        rows = [{"session_id": "a", "ending": "error", "ended": "2026-11-17T10:00:00+00:00", "issue": 7,
                 "pr": None, "name": "builder-1", "ref": "#7"},
                {"session_id": "b", "ending": "ended at cap", "ended": "2026-11-17T11:00:00+00:00",
                 "issue": 7, "pr": 50, "name": "reviewer-1", "ref": "PR #50"},
                {"session_id": "c", "ending": "done", "ended": "2026-11-17T12:00:00+00:00", "issue": 7}]
        eps = episodes.from_runs(rows, REPO)
        self.assertEqual([(e["outcome"], e["source"]) for e in eps],
                         [("failed", "https://github.com/o/r/issues/7"), ("at cap", "https://github.com/o/r/pull/50")])

    def test_gov_question_answers_and_whether_the_owner_took_the_default(self):
        q = {"number": 9, "body": "### Domain\n\narchitecture\n\n### Recommendation\n\nOption 2, because.\n"}

        def ans(body):
            return episodes.from_answer(q, {"id": 5, "created_at": "2026-11-17T10:00:00Z", "body": body,
                                            "html_url": "https://github.com/o/r/issues/9#issuecomment-5"})
        self.assertIs(ans("Option 2. Record: yes")["took_default"], True)
        self.assertIs(ans("Option 1 confirmed.")["took_default"], False)
        self.assertIs(ans("Go with your recommendation.")["took_default"], True)
        self.assertIsNone(ans("Ask the planner first.")["took_default"])
        self.assertEqual(ans("x")["domain"], "architecture")
        self.assertTrue(ans("x")["source"].endswith("#issuecomment-5"))

    def test_sweep_records_each_signal_once_with_a_source_link(self):
        tmp = Path(tempfile.mkdtemp())
        state, out = tmp / "launcher", tmp / "out"
        state.mkdir()
        db = acts.connect(state)
        db.execute("INSERT INTO acts (key, at, act, kind, what, repo, number, url, tag) VALUES "
                   "('o/r:event:1', '2026-11-17T09:00:00Z', 'label', 'other', 'labelled ready', 'o/r', 7, "
                   "'https://github.com/o/r/issues/7', 'approval')")
        db.commit()
        db.close()
        ledger.record(state, [{"session_id": "a", "ending": "error", "ended": "2026-11-17T10:00:00+00:00",
                               "ref": "#7"}], {})
        def gh_json(*args):
            raise AssertionError(args)

        def gh_items(path, jq=".[]"):
            if path.startswith("search/issues"):
                return [{"number": 50, "title": 'Revert "x"', "state": "closed",
                         "pull_request": {"merged_at": "2026-11-17T12:00:00Z"},
                         "html_url": "https://github.com/o/r/pull/50"}]
            if path.endswith("reviews?per_page=100"):
                return []
            if "labels=gov:question" in path:
                return [{"number": 9, "body": "### Recommendation\n\nOption 1\n"}]
            if "/issues/9/comments" in path:
                return [{"id": 5, "user": {"login": OWNER}, "created_at": "2026-11-17T13:00:00Z",
                         "body": "Option 1.", "html_url": "https://github.com/o/r/issues/9#issuecomment-5"}]
            if "/issues/comments?since=" in path:
                return []
            raise AssertionError(path)
        since = dt.datetime(2026, 11, 17, tzinfo=UTC)
        apps = {"productswarm-builder[bot]"}
        self.assertEqual(episodes.sweep(out, state, REPO, OWNER, since, gh_json, gh_items, apps), 4)
        self.assertEqual(episodes.sweep(out, state, REPO, OWNER, since, gh_json, gh_items, apps), 0)
        eps = episodes.load([out])
        self.assertEqual(sorted(e["type"] for e in eps), ["act", "answer", "revert", "run"])
        self.assertTrue(all(e["source"] for e in eps))
        self.assertEqual(next(e for e in eps if e["type"] == "act")["tag"], "approval")


class WatchSweepTest(unittest.TestCase):
    def test_hourly_with_an_overlapping_window_and_never_in_dry_run(self):
        import types
        import watch
        calls, t = [], [0.0]
        w = types.SimpleNamespace(dry_run=False, swept_at=None, swept_since=None, clock=lambda: t[0],
                                  sweep=lambda *a: calls.append(a[4]) or 0, repo=REPO, owner=OWNER,
                                  launcher=types.SimpleNamespace(home=Path("/h"), dir=Path("/h/launcher")),
                                  once=lambda line: None)
        watch.Watch.record_episodes(w, NOW)
        t[0] = 600
        watch.Watch.record_episodes(w, NOW + dt.timedelta(minutes=10))          # within the hour: no sweep
        t[0] = 3700
        later = NOW + dt.timedelta(hours=1, minutes=2)
        watch.Watch.record_episodes(w, later)
        self.assertEqual(calls, [NOW - watch.EPISODES_LOOKBACK, NOW - watch.EPISODES_OVERLAP])
        w.dry_run, t[0] = True, 99999
        watch.Watch.record_episodes(w, later + dt.timedelta(hours=3))
        self.assertEqual(len(calls), 2)


# ---------------------------------------------------------------- act tags

class RuleTest(unittest.TestCase):
    def test_each_rule(self):
        t = acts.rule_tag
        self.assertEqual(t("label", label="ready"), acts.APPROVAL)
        self.assertEqual(t("label", label="ready", added=False), acts.CORRECTION)
        self.assertEqual(t("review", state="APPROVED"), acts.APPROVAL)
        self.assertEqual(t("merge"), acts.APPROVAL)
        self.assertEqual(t("edit"), acts.CORRECTION)
        self.assertEqual(t("label", label="kind:bug"), acts.CORRECTION)
        self.assertEqual(t("label", label="hold"), acts.CORRECTION)
        self.assertEqual(t("close"), acts.CORRECTION)
        self.assertEqual(t("merge", revert=True), acts.CORRECTION)
        self.assertEqual(t("comment", repeat=True), acts.REPEAT)
        self.assertEqual(t("comment", repeat=False), acts.GENUINE)
        self.assertEqual(t("comment"), acts.GENUINE)
        self.assertEqual(t("open"), acts.GENUINE)
        self.assertEqual(t("label", label="priority"), acts.GENUINE)
        self.assertEqual(t("review", state="CHANGES_REQUESTED"), acts.GENUINE)

    def test_retag_lines(self):
        self.assertEqual(acts.retags_in("Thanks.\nRetag o/r:event:1: correction\nretag https://x/y genuine call"),
                         [("o/r:event:1", "correction"), ("https://x/y", "genuine call")])
        self.assertEqual(acts.retags_in("We should retag this later."), [])


Q_BODY = "### Domain\n\n{d}\n\n### Context\n\nx\n"
ISSUES = {
    7: {"number": 7, "user": {"login": BOT}, "labels": [], "node_id": "I7", "created_at": "2026-11-01T00:00:00Z",
        "html_url": "https://github.com/o/r/issues/7"},
    8: {"number": 8, "user": {"login": BOT}, "labels": [], "pull_request": {}, "node_id": "P8",
        "html_url": "https://github.com/o/r/pull/8"},
    20: {"number": 20, "user": {"login": BOT}, "labels": [{"name": "gov:question"}, {"name": "gov:ruled"}],
         "state": "closed", "title": "GOV-Q: Where does the learning loop's memory live?",
         "body": Q_BODY.format(d="architecture"), "created_at": "2026-11-01T00:00:00Z"},
    21: {"number": 21, "user": {"login": BOT}, "labels": [{"name": "gov:question"}], "state": "open",
         "title": "GOV-Q: Where should the learning loop's memory live?",
         "body": Q_BODY.format(d="architecture"), "created_at": "2026-11-10T00:00:00Z"},
    22: {"number": 22, "user": {"login": BOT}, "labels": [{"name": "gov:question"}], "state": "open",
         "title": "GOV-Q: Where should the learning loop's memory live?",
         "body": Q_BODY.format(d="security"), "created_at": "2026-11-10T00:00:00Z"},
}
COMMENTS = {
    31: {"user": {"login": OWNER}, "created_at": "2026-11-17T10:00:00Z", "body": "Option 1.",
         "html_url": "https://github.com/o/r/issues/21#issuecomment-31"},
    32: {"user": {"login": OWNER}, "created_at": "2026-11-17T10:05:00Z", "body": "Option 1.",
         "html_url": "https://github.com/o/r/issues/22#issuecomment-32"},
    33: {"user": {"login": OWNER}, "created_at": "2026-11-17T11:00:00Z",
         "body": "Retag https://github.com/o/r/issues/22#issuecomment-32: correction",
         "html_url": "https://github.com/o/r/issues/7#issuecomment-33"},
    34: {"user": {"login": BOT}, "node_id": "C34", "html_url": "https://github.com/o/r/issues/7#issuecomment-34"},
}
EVENTS = {7: [{"id": 41, "event": "labeled", "label": {"name": "kind:bug"}, "actor": {"login": OWNER},
               "created_at": "2026-11-17T09:00:00Z"},
              {"id": 42, "event": "closed", "actor": {"login": OWNER}, "commit_id": None,
               "created_at": "2026-11-17T09:30:00Z"}],
          8: [{"id": 43, "event": "closed", "actor": {"login": OWNER}, "commit_id": None,
               "created_at": "2026-11-17T09:40:00Z"}],
          20: [{"id": 44, "event": "closed", "actor": {"login": OWNER}, "commit_id": None,
                "state_reason": "completed", "created_at": "2026-11-17T09:50:00Z"}]}
PULLS = {8: {"merged_at": None},
         9: {"merged_by": {"login": OWNER}, "merged_at": "2026-11-17T12:00:00Z", "title": 'Revert "Add x"',
             "html_url": "https://github.com/o/r/pull/9"}}
EDITS = {"I7": {"author": {"login": BOT}, "editor": {"login": OWNER}, "lastEditedAt": "2026-11-17T08:00:00Z"},
         "C34": {"author": {"login": BOT}, "editor": {"login": OWNER}, "lastEditedAt": "2026-11-17T08:30:00Z"},
         "P8": {"author": {"login": BOT}, "editor": {"login": BOT}, "lastEditedAt": "2026-11-17T08:40:00Z"}}


class FakeAPI:
    def gh_json(self, *args):
        if args[1] == "graphql":
            node = args[-1].split("=", 1)[1]
            return {"data": {"node": EDITS[node]}}
        p = args[1].split("?")[0].split("/")[3:]
        if p[:2] == ["issues", "comments"]:
            return COMMENTS[int(p[2])]
        if p[0] == "issues":
            return ISSUES[int(p[1])]
        if p[0] == "pulls" and len(p) == 2:
            return PULLS[int(p[1])]
        raise AssertionError(args)

    def gh_items(self, path, jq=".[]"):
        if "labels=gov:question" in path:
            return [ISSUES[n] for n in (20, 21, 22)]
        p = path.split("?")[0].split("/")[3:]
        if p[0] == "issues" and p[2] == "events":
            return EVENTS.get(int(p[1]), [])
        if p[0] == "pulls" and p[2] == "files":
            return [{"filename": "launcher/x.py"}]
        raise AssertionError(path)


LEADS = [("issues", "labeled", 7, None), ("issues", "closed", 7, None), ("pull_request", "closed", 8, None),
         ("issues", "edited", 7, None), ("issue_comment", "edited", 7, "34"), ("pull_request", "edited", 8, None),
         ("pull_request", "merged", 9, None), ("issue_comment", "created", 21, "31"),
         ("issue_comment", "created", 22, "32"), ("issue_comment", "created", 7, "33")]


class SyncCase(Tmp):
    def sync(self, leads=LEADS):
        db = acts.connect(self.home / "launcher")
        for i, (event, action, n, ref) in enumerate(leads):
            acts.record_lead(db, f"d{i}", event, (action, REPO, n, ref, OWNER), NOW)
        db.commit()
        db.close()
        api = FakeAPI()
        errors = acts.sync(self.home / "launcher", OWNER, None, api.gh_json, api.gh_items, lambda f: False, NOW)
        self.assertEqual(errors, [])
        return {a["what"] + f" #{a['number']}": a for a in acts.stored(self.home / "launcher")}


class ReaderTest(SyncCase):
    def test_each_act_is_tagged_by_its_rule(self):
        got = {k: a["tag"] for k, a in self.sync().items()}
        self.assertEqual(got["labelled kind:bug #7"], acts.CORRECTION)
        self.assertEqual(got["closed #7"], acts.CORRECTION)                   # a veto
        self.assertEqual(got["closed unmerged #8"], acts.CORRECTION)
        self.assertEqual(got["edited an agent's issue #7"], acts.CORRECTION)
        self.assertEqual(got["edited an agent's comment #7"], acts.CORRECTION)
        self.assertEqual(got["merged a revert #9"], acts.CORRECTION)
        self.assertEqual(got["commented #21"], acts.REPEAT)       # same domain, much the same title as #20
        self.assertIsNone(got["retagged #7"])
        self.assertNotIn("edited an agent's PR #8", got)          # the bot edited it last, not the owner

    def test_closing_an_answered_question_is_not_a_veto(self):
        # GOVERNANCE.md §6: the owner closes a question once it is answered. That's routine.
        api = FakeAPI()
        reader = acts.Reader(OWNER, None, api.gh_json, api.gh_items, lambda f: False)
        self.assertEqual(reader.read("issues", "closed", REPO, 20, None), [])
        self.assertNotIn("closed #20", self.sync(LEADS + [("issues", "closed", 20, None)]))

    def test_a_question_in_another_domain_is_a_genuine_call(self):
        acts_ = self.sync(LEADS[:-1])
        self.assertEqual(acts_["commented #22"]["tag"], acts.GENUINE)
        self.assertFalse(acts_["commented #22"]["retagged"])

    def test_the_owners_retag_overrides_the_tagger(self):
        a = self.sync()["commented #22"]
        self.assertEqual(a["tag"], acts.CORRECTION)
        self.assertTrue(a["retagged"])
        [r] = acts.retags(self.home / "launcher")
        self.assertEqual((r["target"], r["tag"]), ("https://github.com/o/r/issues/22#issuecomment-32", "correction"))
        eps = episodes.from_acts(acts.stored(self.home / "launcher"), acts.retags(self.home / "launcher"))
        self.assertIn("retag", {e["type"] for e in eps})
        self.assertEqual(next(e for e in eps if e["id"] == "act:o/r:comment:32")["tag"], acts.CORRECTION)

    def test_a_retag_by_key_works_too(self):
        db = acts.connect(self.home / "launcher")
        acts.record_lead(db, "x", "issue_comment", ("created", REPO, 7, "35", OWNER), NOW)
        db.commit()
        db.close()
        COMMENTS[35] = {**COMMENTS[33], "body": "Retag o/r:event:41: genuine call",
                        "created_at": "2026-11-17T11:30:00Z"}
        self.addCleanup(COMMENTS.pop, 35)
        self.assertEqual(self.sync()["labelled kind:bug #7"]["tag"], acts.GENUINE)

    def test_no_comment_body_is_stored(self):
        self.sync()
        db = sqlite3.connect(self.home / "launcher" / "swarm.db")
        dump = "\n".join(db.iterdump())
        db.close()
        self.assertNotIn("Option 1.", dump)


class CommandTest(SyncCase):
    def launcher(self):
        self.lines: list[str] = []
        return swarm.Launcher(self.home, root=self.home / "repo", out=self.lines.append)

    def test_swarm_acts_reports_counts_by_kind_for_any_window(self):
        self.sync()
        toml = self.home / "swarm.toml"
        toml.write_text('[[session]]\nrole = "builder"\nmodel = "m"\n')
        api = FakeAPI()
        launcher = self.launcher()
        with unittest.mock.patch.object(acts, "backfill", lambda *a, **k: []):
            swarm.owner_acts(launcher, REPO, toml, None, True, now=NOW, tz=UTC, owner=OWNER,
                             gh_json=api.gh_json, gh_items=api.gh_items, since=dt.date(2026, 11, 16))
        out = json.loads("\n".join(self.lines))
        self.assertEqual([d["day"] for d in out["days"]], ["2026-11-17", "2026-11-16"])
        self.assertEqual(out["by_kind"], {"approval": 0, "correction": 7, "repeat answer": 1, "genuine call": 0})
        self.lines.clear()
        with unittest.mock.patch.object(acts, "backfill", lambda *a, **k: []):
            swarm.owner_acts(launcher, REPO, toml, dt.date(2026, 11, 17), False, now=NOW, tz=UTC,
                             owner=OWNER, gh_json=api.gh_json, gh_items=api.gh_items)
        self.assertIn("By kind over these days: approval 0, correction 7, repeat answer 1, genuine call 0",
                      "\n".join(self.lines))

    def test_swarm_memory_episodes_filters(self):
        launcher = self.launcher()
        eps = [episodes.note_episode(session_id="a", role="builder", model="m", repo=REPO, issue=7, pr=None,
                                     note=None, paths=[], prompt="", at=NOW),
               episodes.note_episode(session_id="b", role="reviewer", model="m", repo=REPO, issue=None, pr=8,
                                     note={"tried": "x", "surprised": "none", "blocked": "none"}, paths=[],
                                     prompt="", at=NOW - dt.timedelta(days=3)),
               {"schema": 1, "id": "act:k", "type": "act", "at": "2026-11-17T09:00:00Z", "tag": "correction",
                "what": "edited", "repo": REPO, "number": 7, "source": "u"}]
        episodes.write(episodes.outbox(self.home), eps, env=[])
        self.assertEqual(swarm.main(["memory", "episodes", "--json"], launcher), 0)
        self.assertEqual(len(json.loads("\n".join(self.lines))), 3)
        for argv, ids in ((["--role", "reviewer"], ["note:b"]), (["--since", "2026-11-16"], ["act:k", "note:a"]),
                          (["--kind", "correction"], ["act:k"]), (["--kind", "note"], ["note:b", "note:a"])):
            self.lines.clear()
            swarm.main(["memory", "episodes", "--json", *argv], launcher)
            self.assertEqual([e["id"] for e in json.loads("\n".join(self.lines))], ids, argv)
        self.lines.clear()
        swarm.main(["memory", "episodes"], launcher)
        self.assertIn("builder (m) on #7: no note", "\n".join(self.lines))


if __name__ == "__main__":
    unittest.main()
