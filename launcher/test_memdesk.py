"""Tests for memdesk.py and `swarm memory desk` (#1192). Run: python3 run_tests.py launcher"""
from __future__ import annotations

import datetime as dt
import json
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import dream as D  # noqa: E402
import lessons as L  # noqa: E402
import memdesk  # noqa: E402
import swarm  # noqa: E402
from test_lessons import lesson_text  # noqa: E402
from test_owner import MODEL  # noqa: E402
from test_swarm import Base  # noqa: E402

REPO = "open-agentos/agentfleetos"
OTHER = "someone/else"
ROOT = HERE.parent


def ep(id_: str, type_: str, **kw) -> dict:
    return {"schema": 1, "id": id_, "type": type_, "at": "2026-11-16T10:00:00Z", "source": None, **kw}


def fixture(d: Path, repo: str = REPO) -> Path:
    """A memory/ directory: a fleet lesson, a dormant one scoped to this repo, and an active one
    scoped to another repo; given and cite episodes here and in the other repo; the last dream's
    lines; the owner model; one open draft and one closed."""
    mem = d / "memory"
    (mem / "lessons").mkdir(parents=True)
    (mem / "episodes").mkdir()
    (mem / "lessons" / "L-0001-run-tests.md").write_text(lesson_text())
    (mem / "lessons" / "L-0002-here.md").write_text(lesson_text(
        id="L-0002", title="A lesson for this repo only.", status="dormant", scope=f"repo:{repo}"))
    (mem / "lessons" / "L-0003-elsewhere.md").write_text(lesson_text(
        id="L-0003", title="A lesson for another repo only.", scope=f"repo:{OTHER}"))
    eps = [
        ep("given:s-9", "given", session_id="s-9", role="builder", model="m", repo=repo, issue=10, pr=None,
           lessons=["L-0001", "L-0003"], source=f"https://github.com/{repo}/issues/10"),
        ep("cite:pr:20", "cite", repo=repo, pr=20, number=20, closes=[10], by="productswarm-builder[bot]",
           lessons=["L-0001", "L-0003"], source=f"https://github.com/{repo}/pull/20", at="2026-11-17T10:00:00Z"),
        ep("cite:pr:30", "cite", repo=repo, pr=30, number=30, closes=[31], by="productswarm-docs[bot]",
           lessons=["L-0003"], source=f"https://github.com/{repo}/pull/30"),
        ep("cite:comment:5", "cite", repo=OTHER, pr=None, number=10, closes=[], by="productswarm-builder[bot]",
           lessons=["L-0001"], source=f"https://github.com/{OTHER}/issues/10#issuecomment-5"),
        ep("ep-note-a", "note", session_id="s-1", role="builder"),
    ]
    (mem / "episodes" / "2026-11-16.jsonl").write_text("".join(json.dumps(e) + "\n" for e in eps))
    (mem / "dream.json").write_text(json.dumps({"last_run": "2026-11-18T03:00:00Z", "lines": {
        "learned": {"proposed": ["L-0004"], "reconfirmed": ["L-0001"]},
        "forgot": {"dormant": ["L-0002"], "retired": [], "episodes": 3},
        "proposing": {"patterns": ["the owner took the default 3 times in spend"], "owner": ["O-0004"]}}}))
    (mem / "owner.md").write_text(MODEL)
    (mem / "escalations.json").write_text(json.dumps({"drafts": [
        {"key": "a", "kind": "standing grant", "title": "Grant x", "evidence": ["e1"], "issue": 50,
         "opened": "2026-11-16", "state": "open"},
        {"key": "b", "kind": "retirement", "title": "Retire y", "evidence": ["e2"], "issue": 51,
         "opened": "2026-11-09", "state": "closed"}]}))
    return mem


class BuildTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.mem = fixture(Path(tmp.name))
        self.d = memdesk.build(ROOT, REPO, memory=self.mem)

    def test_no_lesson_scoped_to_another_repo_anywhere(self):
        self.assertEqual(set(self.d["lessons"]), {"L-0001", "L-0002"})
        self.assertNotIn("L-0003", json.dumps(self.d))
        # From the other repo's side, its own lesson shows and this repo's doesn't.
        other = memdesk.build(ROOT, OTHER, memory=self.mem)
        self.assertEqual(set(other["lessons"]), {"L-0001", "L-0003"})
        self.assertNotIn("L-0002", json.dumps(other))

    def test_lessons_carry_what_memory_show_json_prints(self):
        les = self.d["lessons"]["L-0001"]
        for k in ("title", "status", "scope", "confidence", "uses", "review_by", "body", "sources", "eval", "errors"):
            self.assertIn(k, les)
        self.assertEqual(les["review_by"], "2027-02-10")
        self.assertEqual(les["eval"]["result"], "promoted")
        self.assertEqual([s["id"] for s in les["sources"]], ["ep-note-a", "ep-act"])
        self.assertTrue(les["sources"][0]["found"])
        self.assertFalse(les["sources"][1]["found"])

    def test_used_is_this_repos_given_and_cited(self):
        used = self.d["used"]
        self.assertEqual([(u["type"], u.get("issue"), u.get("pr"), u["lessons"]) for u in used],
                         [("given", 10, None, ["L-0001"]), ("cite", None, 20, ["L-0001"])])
        self.assertEqual(used[1]["role"], "builder")
        self.assertEqual(used[1]["closes"], [10])

    def test_counts_are_counts(self):
        c = self.d["counts"]
        self.assertEqual((c["active"], c["dormant"], c["budget"]), (1, 1, D.BUDGET))
        self.assertEqual(c["roles"]["builder"], 1)
        self.assertEqual(c["roles"]["planner"], 0)

    def test_dream_owner_and_open_drafts(self):
        self.assertEqual(self.d["dream"]["last_run"], "2026-11-18T03:00:00Z")
        self.assertEqual(self.d["dream"]["forgot"]["dormant"], ["L-0002"])
        self.assertEqual([e["id"] for e in self.d["owner"]], ["O-0001", "O-0002", "O-0003"])
        self.assertEqual(self.d["owner"][1]["sources"], ["act:k1", "review:9"])
        self.assertEqual([x["issue"] for x in self.d["drafts"]], [50])

    def test_no_dream_yet(self):
        (self.mem / "dream.json").write_text(json.dumps({"last_run": "2026-11-18T03:00:00Z"}))
        self.assertIsNone(memdesk.build(ROOT, REPO, memory=self.mem)["dream"])
        (self.mem / "dream.json").unlink()
        self.assertIsNone(memdesk.build(ROOT, REPO, memory=self.mem)["dream"])


class DreamLinesTest(unittest.TestCase):
    def test_apply_keeps_the_three_lines(self):
        p = D.Plan(since=None, today=dt.date(2026, 11, 18), new=["x"])
        p.proposed = [{"id": "L-0009", "sources": [], "roles": [], "words": []}]
        p.reconfirmed = [{"id": "L-0001", "by": [], "confidence": 0.8}]
        p.dormant = [{"id": "L-0002", "why": "unused"}]
        p.retired = [{"id": "L-0005", "why": "past review_by"}]
        p.expired = ["e1", "e2"]
        p.promote = [{"pattern": "same answer", "why": "the owner took the default 3 times in spend"}]
        p.owner = [{"id": "O-0004", "sources": [], "links": [], "words": []}]
        with tempfile.TemporaryDirectory() as d:
            mem = Path(d)
            (mem / "lessons").mkdir()
            D.apply(p, [], mem, dt.datetime(2026, 11, 18, 3, tzinfo=dt.timezone.utc))
            got = D.last_lines(mem)
        self.assertEqual(got, {"last_run": "2026-11-18T03:00:00Z",
                               "learned": {"proposed": ["L-0009"], "reconfirmed": ["L-0001"]},
                               "forgot": {"dormant": ["L-0002"], "retired": ["L-0005"], "episodes": 2},
                               "proposing": {"patterns": ["the owner took the default 3 times in spend"],
                                             "owner": ["O-0004"]}})


class CommandTest(Base):
    def test_memory_desk_prints_what_the_desk_reads(self):
        mem = fixture(self.home)
        self.assertEqual(swarm.main(["memory", "desk", "--repo", REPO, "--memory", str(mem), "--json"],
                                    launcher=self.l), 0)
        self.assertEqual(json.loads(self.lines[-1]), memdesk.build(self.root, REPO, memory=mem))
        self.lines.clear()
        self.assertEqual(swarm.main(["memory", "desk", "--repo", REPO, "--memory", str(mem)], launcher=self.l), 0)
        out = "\n".join(self.lines)
        self.assertIn("2 lessons, 1 active, 1 dormant", out)
        self.assertIn("1 open draft gov:question(s)", out)


if __name__ == "__main__":
    unittest.main()
