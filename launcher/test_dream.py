"""Tests for dream.py and `swarm dream` (#1186, FEAT-16), over the fixture in testdata/dream/."""
import datetime as dt
import json
import re
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import dream as D
import episodes
import lessons as L
import swarm

FIXTURE = Path(__file__).resolve().parent / "testdata" / "dream"
TODAY = dt.date(2026, 11, 18)
OWNER = "mattmcalister"
TRUSTED = {OWNER, "productswarm-builder[bot]", "productswarm-reviewer[bot]",
           "productswarm-designer[bot]", "productswarm-planner[bot]", "productswarm-docs[bot]"}
RULINGS = {"GOV-0047": "superseded", "GOV-0055": "in-force"}
MANIFEST = """
[watch]
interval_minutes = 5
max_live = 2
max_turns = 200
report_issue = 249

[[session]]
role = "planner"
count = 1
model = "{planner}"
spend_cap_usd = 5

[[session]]
role = "librarian"
count = 1
model = "claude-sonnet-5-5"
{cap}
"""


def ctx(eps: list[dict]) -> L.Context:
    return L.Context(trusted=TRUSTED, episodes={e["id"]: e for e in eps}, rulings=RULINGS,
                     repo="open-agentos/agentfleetos", today=TODAY, owner=OWNER)


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.mem = self.tmp / "memory"
        shutil.copytree(FIXTURE, self.mem)

    def load(self):
        eps = episodes.load([self.mem / "episodes"])
        return L.load_all(self.mem / "lessons"), eps

    def plan(self, since: str | None = "2026-11-10T00:00:00Z") -> D.Plan:
        les, eps = self.load()
        return D.plan(les, eps, ctx(eps), since=since, in_repo_ids={e["id"] for e in eps})


class Phases(Base):
    def test_replay_reads_only_new_episodes(self):
        p = self.plan()
        self.assertEqual(len(p.new), 7)
        self.assertEqual(p.by_type, {"act": 1, "answer": 1, "closed-unmerged": 1, "note": 3, "review": 1})
        self.assertEqual(len(self.plan(since=None).new), 15)

    def test_consolidate_proposes_where_two_sources_agree(self):
        p = self.plan()
        self.assertEqual([(c["id"], c["sources"], c["roles"]) for c in p.proposed],
                         [("L-0012", ["note:s-10", "review:100"], ["builder"])])
        self.assertIn("import", p.proposed[0]["words"])
        self.assertEqual(p.proposed[0]["review_by"], "2027-02-16")

    def test_two_notes_alone_arent_a_lesson(self):
        # the designers' two notes agree, but no engine-recorded signal backs them (GOV-0055)
        p = self.plan()
        self.assertEqual(p.unsourced, 1)
        self.assertFalse(any("note:s-11" in c["sources"] for c in p.proposed))

    def test_consolidate_reconfirms_a_matching_lesson(self):
        p = self.plan()
        self.assertEqual(p.reconfirmed, [{"id": "L-0001", "by": ["act:a-5"], "confidence": 0.7}])

    def test_consolidate_merges_near_duplicates_into_the_stronger(self):
        p = self.plan()
        self.assertEqual([(m["keep"], m["drop"], m["supersedes"]) for m in p.merges],
                         [("L-0002", "L-0003", ["L-0003"])])
        self.assertEqual(p.status["L-0003"], "retired")

    def test_reconcile_flags_and_lowers(self):
        flags = {(f["id"], f["why"]) for f in self.plan().flags}
        self.assertEqual(flags, {("L-0004", "contradicts L-0005"), ("L-0005", "contradicts L-0004"),
                                 ("L-0006", "names GOV-0047, which is superseded"),
                                 ("L-0010", "rests on PR #77, closed unmerged (closed:77)")})
        p = self.plan()
        self.assertEqual(p.confidence["L-0004"], 0.4)
        # lessons in tension aren't merged as duplicates
        self.assertFalse(any({m["keep"], m["drop"]} == {"L-0004", "L-0005"} for m in p.merges))

    def test_forget(self):
        p = self.plan()
        self.assertEqual(p.decays, [{"id": "L-0007", "confidence": 0.72}])
        self.assertEqual([d["id"] for d in p.dormant], ["L-0008"])
        self.assertEqual([r["id"] for r in p.retired], ["L-0009"])
        self.assertEqual(p.expired, ["note:s-0"])        # past 30 days, uncited
        self.assertEqual(p.kept_cited, ["note:s-1"])     # past 30 days, but L-0001 cites it

    def test_forget_only_deletes_episodes_in_the_repo(self):
        les, eps = self.load()
        p = D.plan(les, eps, ctx(eps), since="2026-11-10T00:00:00Z", in_repo_ids=set())
        self.assertEqual(p.expired, [])

    def test_budget_moves_the_lowest_ranked_to_dormant(self):
        les_dir = self.mem / "lessons"
        src = (les_dir / "L-0007-idle.md").read_text()
        for i in range(D.BUDGET + 1):   # all reviewer lessons, all used recently
            words = " ".join(f"w{i}x{j}" for j in range(6))
            (les_dir / f"L-{100 + i:04d}-b.md").write_text(
                src.replace("L-0007", f"L-{100 + i:04d}").replace("confidence: 0.8", f"confidence: 0.{10 + i}")
                .replace("last_used: 2026-11-05", "last_used: 2026-11-15")
                .replace("Read the role prompt in full at the start of a session.", f"Lesson {words}.")
                .replace("Start from the role prompt.", words))
        p = self.plan()
        over = [d for d in p.dormant if "budget" in d["why"]]
        # 26 new + L-0007 active for reviewers (L-0008 goes dormant for idling): 2 over
        self.assertEqual([d["id"] for d in over], ["L-0100", "L-0101"])

    def test_rehearse_lists_proposed_lessons_without_an_eval_case(self):
        self.assertEqual([r["id"] for r in self.plan().rehearse], ["L-0011", "L-0012"])

    def test_promote(self):
        pats = {q["pattern"]: q for q in self.plan().promote}
        self.assertEqual(pats["same answer"]["episodes"], ["answer:1", "answer:2", "answer:3"])
        self.assertEqual(pats["outside jurisdiction"]["lesson"], "L-0011")

    def test_no_new_episodes_plans_nothing(self):
        p = self.plan(since="2026-11-18T00:00:00Z")
        self.assertEqual((p.new, p.proposed, p.decays, p.expired), ([], [], [], []))
        self.assertIn("no new episodes", D.report(p))

    def test_report_names_every_phase(self):
        r = D.report(self.plan())
        for h in ("1. Replay", "2. Consolidate", "3. Reconcile", "4. Forget", "5. Rehearse", "6. Promote"):
            self.assertIn(h, r)


class Apply(Base):
    def test_apply_writes_the_mechanical_changes(self):
        p = self.plan()
        les, _ = self.load()
        now = dt.datetime(2026, 11, 18, 3, 0, tzinfo=dt.timezone.utc)
        D.apply(p, les, self.mem, now)
        after = {x.id: x for x in L.load_all(self.mem / "lessons")}
        self.assertEqual(after["L-0001"].meta["confidence"], 0.7)
        self.assertEqual(after["L-0007"].meta["confidence"], 0.72)
        self.assertEqual(after["L-0003"].status, "retired")
        self.assertEqual(after["L-0002"].meta["supersedes"], ["L-0003"])
        self.assertEqual(after["L-0008"].status, "dormant")
        self.assertEqual(after["L-0009"].status, "retired")
        self.assertFalse(any(x.errors for x in after.values()))
        self.assertFalse((self.mem / "episodes" / "2026-10-05.jsonl").exists())
        self.assertTrue((self.mem / "episodes" / "2026-10-10.jsonl").exists())
        self.assertEqual(D.last_run(self.mem), "2026-11-18T03:00:00Z")
        self.assertIn("L-0008", (self.mem / "INDEX.md").read_text())
        # the next plan reads from the new last run: nothing new
        les, eps = self.load()
        self.assertEqual(D.plan(les, eps, ctx(eps), since=D.last_run(self.mem)).new, [])

    def test_applied_lessons_still_validate(self):
        les, _ = self.load()
        D.apply(self.plan(), les, self.mem, dt.datetime(2026, 11, 18, tzinfo=dt.timezone.utc))
        eps = episodes.load([self.mem / "episodes"])
        c = ctx(eps)
        c.root = Path(__file__).resolve().parent.parent
        c.rulings = {"GOV-0055": "in-force"}
        errs = [e for x in L.load_all(self.mem / "lessons") if x.id not in ("L-0006",)
                for e in L.validate(x, c)]
        self.assertEqual(errs, [])

    def test_set_fields_replaces_a_block_list(self):
        text = "---\nid: L-0001\nsources:\n  - a\n  - b\nuses: 0\n---\nbody\n"
        out = D.set_fields(text, {"sources": "[a, b, c]", "status": "dormant"})
        self.assertEqual(out, "---\nid: L-0001\nsources: [a, b, c]\nuses: 0\nstatus: dormant\n---\nbody\n")


class Command(Base):
    def run_swarm(self, *argv, planner="claude-opus-5-5", cap="spend_cap_usd = 3"):
        out = []
        launcher = mock.Mock()
        launcher.out = out.append
        launcher.home = self.tmp / "home"
        launcher.root = self.tmp
        launcher.clock.return_value = 0.0
        launcher.live.return_value = []
        launcher.start.return_value = True
        man = self.tmp / "swarm.toml"
        man.write_text(MANIFEST.format(planner=planner, cap=cap))
        (self.tmp / "roles").mkdir(exist_ok=True)
        for r in ("planner", "librarian"):
            (self.tmp / "roles" / f"{r}.md").write_text("x")
        with mock.patch.object(L, "trusted_logins", lambda: TRUSTED), \
             mock.patch.object(L, "in_force_rulings", lambda: RULINGS), \
             mock.patch.object(L, "today", lambda: TODAY), \
             mock.patch("swarm.owner_login", lambda *a: OWNER), \
             mock.patch("manifest._roles_dir", lambda d: self.tmp / "roles"):
            code = swarm.main(["dream", "--memory", str(self.mem), "--manifest", str(man),
                               "--repo", "open-agentos/agentfleetos", *argv], launcher)
        return code, "\n".join(out), launcher

    def test_dry_run_plans_and_starts_nothing_for_real(self):
        code, out, launcher = self.run_swarm("--dry-run")
        self.assertEqual(code, 0)
        self.assertIn("propose L-0012", out)
        (entry, _live, dry), = [c.args for c in launcher.start.call_args_list]
        self.assertTrue(dry)
        self.assertEqual((entry.role, entry.issue, entry.budget_usd, entry.max_turns, entry.by),
                         ("librarian", 249, 3, 200, "watch"))
        self.assertEqual(entry.dream, "2026-11-10T00:00:00Z")

    def test_first_run_opener_commands_parse(self):
        # No dream.json yet: the opener's commands must still be ones swarm dream accepts.
        (self.mem / "dream.json").unlink()
        code, _, launcher = self.run_swarm("--dry-run")
        self.assertEqual(code, 0)
        (entry, _live, _dry), = [c.args for c in launcher.start.call_args_list]
        self.assertEqual(entry.dream, swarm.DREAM_FROM_START)
        cmds = re.findall(r"launcher/swarm dream (--.*?) (?:for|to) ",
                          swarm.opener("librarian", 249, dream=entry.dream))
        self.assertEqual([c.split()[0] for c in cmds], ["--dry-run", "--apply"])
        self.assertNotIn("--since", " ".join(cmds))
        for cmd in cmds:
            code, _, _ = self.run_swarm(*cmd.split())
            self.assertEqual(code, 0, cmd)

    def test_a_real_start_is_one_capped_run(self):
        code, _, launcher = self.run_swarm("--issue", "1186")
        self.assertEqual(code, 0)
        (entry, _live, dry), = [c.args for c in launcher.start.call_args_list]
        self.assertFalse(dry)
        self.assertEqual((entry.issue, entry.budget_usd), (1186, 3))

    def test_no_new_episodes_no_model_call_no_pr(self):
        code, out, launcher = self.run_swarm("--since", "2026-11-18")
        self.assertEqual(code, 0)
        self.assertIn("no new episodes", out)
        launcher.start.assert_not_called()
        self.assertFalse(any((self.tmp / "memory" / "lessons").glob("L-0012*")))

    def test_refuses_without_a_cap(self):
        code, out, launcher = self.run_swarm(cap="")
        self.assertEqual(code, 1)
        self.assertIn("spend_cap_usd", out)
        launcher.start.assert_not_called()

    def test_refuses_on_the_planners_model(self):
        code, out, launcher = self.run_swarm(planner="claude-sonnet-5-5")
        self.assertEqual(code, 1)
        self.assertIn("planner's model", out)
        launcher.start.assert_not_called()

    def test_apply_touches_only_memory(self):
        self.run_swarm("--since", "2026-11-18")   # writes the manifest and roles, applies nothing
        before = {p: p.read_bytes() for p in self.tmp.rglob("*") if p.is_file() and "memory" not in p.parts}
        code, out, launcher = self.run_swarm("--apply")
        self.assertEqual(code, 0)
        launcher.start.assert_not_called()
        after = {p: p.read_bytes() for p in self.tmp.rglob("*") if p.is_file() and "memory" not in p.parts}
        self.assertEqual(after, before)
        self.assertIn("L-0003-closes-once-again.md: status retired", out)

    def test_json(self):
        code, out, _ = self.run_swarm("--dry-run", "--json")
        plan = json.loads(out[:out.index("\n}") + 2])
        self.assertEqual(plan["proposed"][0]["id"], "L-0012")

    def test_since_takes_a_date_or_a_stamp(self):
        self.assertEqual(swarm.since_stamp("2026-11-10"), "2026-11-10T00:00:00Z")
        self.assertEqual(swarm.since_stamp("2026-11-10T03:00:00Z"), "2026-11-10T03:00:00Z")

    def test_opener_names_the_dream(self):
        o = swarm.opener("librarian", 1186, dream="2026-11-10T00:00:00Z")
        self.assertIn("swarm dream --apply --since 2026-11-10T00:00:00Z", o)
        self.assertIn("issue #1186", o)
        self.assertIn("touches only memory/", o)


if __name__ == "__main__":
    unittest.main()
