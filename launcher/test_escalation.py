"""Tests for escalation.py and `swarm escalate` (#1191, FEAT-21), over testdata/dream/."""
import datetime as dt
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import episodes
import escalation as E
import lessons as L
import swarm
from test_dream import FIXTURE, MANIFEST, OWNER, RULINGS, TODAY, TRUSTED, ctx

WEDNESDAY = TODAY                      # 2026-11-18
MONDAY = dt.date(2026, 11, 23)
INDEX = """| [GOV-0006](d/x.md) | Only merged records are rulings | governance | authoritative | in-force | 2027-01-31 |
| [GOV-0070](d/y.md) | Always squash a pull request to one commit before merge | code-conventions | authoritative | in-force | 2027-03-01 |
| [GOV-0071](d/z.md) | Heartbeats carry no prompt text | security | authoritative | in-force | 2026-12-10 |
| [GOV-0072](d/w.md) | An old rule | security | authoritative | superseded | 2026-12-10 |
"""


def lesson(lid: str, *, status="active", rehearsed: str | None = "2026-11-01", result="promoted",
           sources=("note:s-1", "review:1"), roles=("builder",), paths=(), title=None,
           confidence=0.6, related=()) -> str:
    reh = f"rehearsal:\n  at: {rehearsed}\n  result: {result}\n" if rehearsed else ""
    return (f"---\nid: {lid}\ntitle: {title or f'Lesson {lid} about the merge queue.'}\nstatus: {status}\n"
            f"scope: fleet\napplies_to:\n  roles: [{', '.join(roles)}]\n  paths: [{', '.join(paths)}]\n"
            f"  situations: []\nsources: [{', '.join(sources)}]\nconfidence: {confidence}\nuses: 0\n"
            f"last_used: 2026-11-12\ncreated: 2026-10-20\nreview_by: 2027-02-01\neval_case: evals/x.toml\n"
            f"{reh}supersedes: []\nrelated_rulings: [{', '.join(related)}]\n---\n\nBody.\n")


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.mem = self.tmp / "memory"
        shutil.copytree(FIXTURE, self.mem)
        shutil.rmtree(self.mem / "lessons")
        (self.mem / "lessons").mkdir()
        (self.tmp / "governance").mkdir()
        (self.tmp / "governance" / "INDEX.md").write_text(INDEX)
        self.rules = E.rulings(self.tmp / "governance" / "INDEX.md")

    def add(self, lid: str, slug="x", **kw):
        (self.mem / "lessons" / f"{lid}-{slug}.md").write_text(lesson(lid, **kw))

    def eps(self, drop=()):
        return [e for e in episodes.load([self.mem / "episodes"]) if e["id"] not in drop]

    def find(self, today=WEDNESDAY, drop=(), cited=None):
        eps = self.eps(drop)
        c = ctx(eps)
        c.today = today
        les = L.load_all(self.mem / "lessons")
        # By default every ruling is cited, so retirement stays out of the way.
        return E.find(les, eps, c, self.rules, set(self.rules) if cited is None else cited)

    def kinds(self, **kw):
        return [d.kind for d in self.find(**kw)[0]]


class StandingGrant(Base):
    def test_the_drills_third_same_way_answer_drafts_one_grant(self):
        self.assertEqual(self.kinds(drop=("answer:3",)), [])
        drafts, _ = self.find()
        self.assertEqual(len(drafts), 1)
        d = drafts[0]
        self.assertEqual((d.kind, d.key, d.domain), ("standing grant", "standing grant:spend", "spend"))
        self.assertEqual(d.evidence, ["answer:1", "answer:2", "answer:3", "#901", "#902", "#903"])
        self.assertIn("issues/903#issuecomment-3", " ".join(d.links))
        self.assertTrue(d.options and d.recommendation.startswith("Option 1") and d.default)

    def test_body_follows_the_template_and_signs(self):
        d = self.find()[0][0]
        b = E.body(d, "claude-sonnet-5-5")
        for h in ("### Domain\n\nspend", "### Context", "### Options", "### Recommendation",
                  "### Default action if unanswered", "### Blocking?", "### Reversibility",
                  "### Blast radius", "### Precedent checked", "### Raised by"):
            self.assertIn(h, b)
        self.assertIn("- answer:3", b)
        self.assertTrue(b.endswith("-- librarian (claude-sonnet-5-5)"))


class Monday(Base):
    def test_midweek_candidates_wait_for_monday(self):
        drafts, held = self.find()
        b = E.batch(drafts, held, [], WEDNESDAY)
        self.assertEqual((b.open_now, [d.key for d in b.waiting]), ([], ["standing grant:spend"]))
        self.assertIn("waits for Monday 2026-11-23", E.report(b))
        b = E.batch(*self.find(today=MONDAY), [], MONDAY)
        self.assertEqual([d.key for d in b.open_now], ["standing grant:spend"])
        self.assertEqual(b.waiting, [])


class Guardrails(Base):
    def setUp(self):
        super().setUp()
        self.paths = ("governance/decisions/",)

    def test_a_mature_lesson_escalates(self):
        self.add("L-0001", paths=self.paths)
        drafts, held = self.find(drop=("answer:3",))
        self.assertEqual([(d.kind, d.domain) for d in drafts], [("jurisdiction", "governance")])
        self.assertEqual(drafts[0].evidence, ["L-0001", "note:s-1", "review:1"])
        self.assertEqual(held, [])

    def held(self, **kw):
        kw.setdefault("paths", self.paths)
        self.add("L-0001", **kw)
        drafts, held = self.find(drop=("answer:3",))
        self.assertEqual(drafts, [])
        return " ".join(held[0]["why"]) if held else ""

    def test_under_14_days_never_escalates(self):
        self.assertIn("active 13 days, under 14", self.held(rehearsed="2026-11-05"))

    def test_unrehearsed_never_escalates(self):
        self.assertIn("no passing rehearsal", self.held(rehearsed=None))
        self.assertIn("no passing rehearsal", self.held(result="demoted"))
        self.held(status="proposed", rehearsed=None)   # proposed: not even considered

    def test_single_sourced_never_escalates(self):
        self.assertIn("at least two sources", self.held(sources=("review:1",)))

    def test_untrusted_content_alone_never_escalates(self):
        eps = self.eps(drop=("answer:3",))
        for e in eps:
            if e["id"] == "review:1":
                e["by"] = "outsider"
        self.add("L-0001", paths=self.paths)
        c = ctx(eps)
        drafts, held = E.find(L.load_all(self.mem / "lessons"), eps, c, self.rules, set(self.rules))
        self.assertEqual(drafts, [])
        self.assertIn("outsider", " ".join(held[0]["why"]))

    def test_the_owner_model_never_escalates(self):
        self.assertIn("owner model", self.held(paths=("governance/x.md", "memory/owner.md")))


class Patterns(Base):
    def test_amendment_for_a_confirmed_lesson_against_a_ruling(self):
        self.add("L-0001", title="Never squash a pull request to one commit before merge.",
                 confidence=0.8, related=("GOV-0070",))
        drafts, _ = self.find(drop=("answer:3",))
        self.assertEqual([(d.kind, d.key) for d in drafts], [("amendment", "amendment:L-0001:GOV-0070")])
        # not yet confirmed enough
        self.add("L-0001", title="Never squash a pull request to one commit before merge.",
                 confidence=0.6, related=("GOV-0070",))
        self.assertEqual(self.kinds(drop=("answer:3",)), [])

    def test_retirement_for_an_uncited_ruling_near_review(self):
        drafts, _ = self.find(drop=("answer:3",), cited={"GOV-0006"})
        self.assertEqual([d.key for d in drafts], ["retirement:GOV-0071"])   # not 0070 (far), not 0072

    def test_cited_rulings(self):
        self.add("L-0001", related=("GOV-0071",))
        les = L.load_all(self.mem / "lessons")
        self.assertEqual(E.cited_rulings(les, [], ["per GOV-0070"]), {"GOV-0070", "GOV-0071"})

    def test_role_prompt_is_proposed_never_opened(self):
        for i in range(3):
            self.add(f"L-000{i + 1}", slug=f"s{i}")
        drafts, held = self.find(today=MONDAY, drop=("answer:3",))
        b = E.batch(drafts, held, [], MONDAY)
        self.assertEqual(b.open_now, [])
        self.assertEqual([d.key for d in b.proposals], ["role prompt:builder"])
        self.assertIn("GOV-0059", E.report(b))


class Vetoes(Base):
    def entry(self, state, evidence):
        return {"key": "standing grant:spend", "issue": 950, "opened": "2026-11-09",
                "state": state, "evidence": evidence}

    def test_a_vetoed_draft_isnt_reopened_for_the_same_evidence(self):
        drafts, held = self.find(today=MONDAY)
        same = self.entry("closed", drafts[0].evidence)
        b = E.batch(drafts, held, [same], MONDAY)
        self.assertEqual((b.open_now, len(b.blocked)), ([], 1))
        self.assertIn("already drafted as #950 (closed)", E.report(b))

    def test_new_evidence_may_reopen_a_closed_draft_but_not_an_open_one(self):
        drafts, held = self.find(today=MONDAY)
        older = [x for x in drafts[0].evidence if x not in ("answer:3", "#903")]
        self.assertEqual(len(E.batch(drafts, held, [self.entry("closed", older)], MONDAY).open_now), 1)
        self.assertEqual(E.batch(drafts, held, [self.entry("open", older)], MONDAY).open_now, [])


class Counts(Base):
    def test_report_counts_drafts_opened_each_week(self):
        ledger = [{"key": "a", "opened": "2026-11-16"}, {"key": "b", "opened": "2026-11-16"},
                  {"key": "c", "opened": "2026-11-09"}]
        b = E.batch([], [], ledger, WEDNESDAY)
        self.assertEqual(b.weeks[:2], [("2026-11-16", 2), ("2026-11-09", 1)])
        self.assertIn("week of 2026-11-16: 2, week of 2026-11-09: 1", E.report(b))


class Retirement(Base):
    """A ruling the repo's own files cite is never offered for retirement (#1247 review)."""
    def batch(self, files, commits=(), git=None):
        eps = self.eps(("answer:3",))
        c = ctx(eps)
        c.today = WEDNESDAY
        les = L.load_all(self.mem / "lessons")
        with mock.patch.object(swarm, "_git", git or (lambda *a: None)):
            return swarm.escalation_batch(self.mem, les, eps, c, self.tmp, ledger=[],
                                          commits=None if git else list(commits), files=files)

    def write(self, rel, text):
        (self.tmp / rel).parent.mkdir(parents=True, exist_ok=True)
        (self.tmp / rel).write_text(text)

    def test_a_ruling_cited_only_in_a_tracked_file_isnt_offered_for_retirement(self):
        self.write("roles/builder.md", "Heartbeats stay small (per GOV-0071).")
        self.assertEqual([d.key for d in self.batch(files=[]).waiting], ["retirement:GOV-0071"])
        self.assertEqual(self.batch(files=["roles/builder.md"]).waiting, [])

    def test_its_own_record_the_index_and_memory_dont_count_as_citing(self):
        self.write("governance/decisions/GOV-0071-heartbeats.md", "# GOV-0071\nSee GOV-0070.")
        self.write("memory/escalations.json", '{"drafts": [{"key": "retirement:GOV-0071"}]}')
        files = ["governance/decisions/GOV-0071-heartbeats.md", "governance/INDEX.md",
                 "memory/escalations.json", "missing.md"]
        self.assertEqual(E.cited_in_files(self.tmp, files), {"GOV-0070"})
        (d,) = self.batch(files=files).waiting
        self.assertEqual(d.key, "retirement:GOV-0071")
        self.assertIn("no tracked file", d.context)
        self.assertNotIn("nothing on record uses it", d.recommendation)

    def test_unlisted_files_offer_nothing_for_retirement_and_say_why(self):
        with mock.patch.object(swarm, "tracked_files", lambda root: None):
            b = self.batch(files=None)
        self.assertEqual(b.waiting, [])
        self.assertIn("warning: couldn't list the repo's tracked files", E.report(b))

    def test_a_shallow_history_is_reported_not_hidden(self):
        def git(root, *argv):
            return "true\n" if argv[0] == "rev-parse" else ""
        b = self.batch(files=[], git=git)
        self.assertIn("warning: this checkout's history is shallow", E.report(b))
        self.assertIn("shallow", " ".join(b.as_json()["warnings"]))
        b = self.batch(files=[], git=lambda root, *argv: "false\n" if argv[0] == "rev-parse" else "")
        self.assertEqual(b.warnings, [])


class Command(Base):
    def run_swarm(self, *argv, today=WEDNESDAY, states=None):
        out, opened = [], []
        launcher = mock.Mock()
        launcher.out = out.append
        launcher.home = self.tmp / "home"
        launcher.root = self.tmp
        man = self.tmp / "swarm.toml"
        man.write_text(MANIFEST.format(planner="claude-opus-5-5", cap="spend_cap_usd = 3"))
        (self.tmp / "roles").mkdir(exist_ok=True)
        for r in ("planner", "librarian"):
            (self.tmp / "roles" / f"{r}.md").write_text("x")

        def open_question(repo, title, body):
            opened.append((repo, title, body))
            return 960 + len(opened)

        args = swarm.argparse.Namespace(memory=str(self.mem), manifest=str(man), model=None,
                                        as_json="--json" in argv, open="--open" in argv,
                                        list="--list" in argv)
        with mock.patch.object(L, "trusted_logins", lambda: TRUSTED), \
             mock.patch.object(L, "in_force_rulings", lambda: RULINGS), \
             mock.patch.object(L, "today", lambda: today), \
             mock.patch("swarm.owner_login", lambda *a: OWNER), \
             mock.patch("manifest._roles_dir", lambda d: self.tmp / "roles"):
            code = swarm.escalate(launcher, args, "open-agentos/agentfleetos", commits=["GOV-0071"], files=[],
                                  state_of=lambda repo, n: (states or {}).get(n),
                                  open_question=open_question)
        return code, "\n".join(out), opened

    def test_open_midweek_opens_nothing(self):
        code, out, opened = self.run_swarm("--open")
        self.assertEqual((code, opened), (0, []))
        self.assertIn("1 draft(s) wait for the check-in batch", out)
        self.assertEqual(E.load_ledger(self.mem), [])

    def test_open_on_monday_opens_once_and_records(self):
        code, out, opened = self.run_swarm("--open", today=MONDAY)
        self.assertEqual(code, 0)
        (repo, title, body), = opened
        self.assertIn("standing grant for spend", title)
        self.assertIn("-- librarian (claude-sonnet-5-5)", body)
        (row,) = E.load_ledger(self.mem)
        self.assertEqual((row["issue"], row["opened"], row["state"]), (961, "2026-11-23", "open"))
        # the next Monday, still open: not drafted again
        _, _, again = self.run_swarm("--open", today=MONDAY + dt.timedelta(days=7), states={961: "open"})
        self.assertEqual(again, [])
        # vetoed (closed) with no new evidence: still not drafted again
        _, out, again = self.run_swarm("--open", today=MONDAY + dt.timedelta(days=7), states={961: "closed"})
        self.assertEqual(again, [])
        self.assertEqual(E.load_ledger(self.mem)[0]["state"], "closed")

    def test_list_shows_open_drafts_for_the_check_in(self):
        E.save_ledger(self.mem, [{"key": "k", "title": "T1", "issue": 961, "evidence": ["answer:1"]},
                                 {"key": "k2", "title": "T2", "issue": 962, "evidence": []}])
        code, out, _ = self.run_swarm("--list", states={962: "closed"})
        self.assertEqual(code, 0)
        self.assertIn("1 open draft", out)
        self.assertIn("#961 T1", out)
        self.assertNotIn("T2", out)

    def test_dream_report_carries_the_escalation_section(self):
        import test_dream
        t = test_dream.Command("test_json")
        t.tmp, t.mem = self.tmp, self.mem
        _, out, _ = t.run_swarm("--dry-run")
        self.assertIn("Escalation:", out)
        self.assertIn("Drafts opened per week", out)


if __name__ == "__main__":
    unittest.main()
