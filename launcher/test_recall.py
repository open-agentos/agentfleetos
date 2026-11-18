"""Tests for recall.py, the context pack (#1187, FEAT-17; GOV-0058), and its citations: the
launcher supplying the pack, `swarm memory pack`, cite and given episodes, and the dream
counting uses and given-not-used."""
import datetime as dt
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

import dream as D
import episodes
import lessons as L
import manifest
import recall
import swarm
from test_swarm import Base

HOME = "open-agentos/agentfleetos"
SCRATCH = "open-agentos/productswarm-scratch"
UTC = dt.timezone.utc

BODY = """Say the lesson.

## Why

Because.

## Example

An example.
"""


def lesson(d: Path, lid: str, *, status="active", scope="fleet", roles=(), paths=(), situations=(),
           confidence=0.5, uses=0, last_used="", title=None, body=BODY) -> Path:
    """A lesson file in d, in lessons.py's format."""
    lines = ["---", f"id: {lid}", f"title: {title or 'Lesson ' + lid + '.'}", f"status: {status}",
             f"scope: {scope}", "applies_to:", f"  roles: [{', '.join(roles)}]", "  paths:"]
    lines += [f"    - {p}" for p in paths]
    lines += ["  situations:"] + [f"    - {x}" for x in situations]
    lines += ["sources: [ep-a, ep-b]", f"confidence: {confidence}", f"uses: {uses}",
              f"last_used: {last_used}", "created: 2026-11-01", "review_by: 2027-02-01",
              "eval_case: evals/lessons/x.json", "supersedes: []", "related_rulings: []", "---", "", body]
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{lid}-lesson-{lid[2:]}.md"
    p.write_text("\n".join(lines))
    return p


class Dir(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.d = Path(tmp.name) / "lessons"

    def pack(self, role="builder", repo=HOME, paths=(), situation="", limit=10):
        s = recall.Session(role=role, repo=repo, paths=list(paths), situation=situation)
        return [e.lesson.id for e in recall.select(L.load_all(self.d), s, limit)]


class FilterTest(Dir):
    def test_only_active_lessons(self):
        for i, st in enumerate(("active", "proposed", "dormant", "retired"), 1):
            lesson(self.d, f"L-000{i}", status=st)
        self.assertEqual(self.pack(), ["L-0001"])

    def test_role_filter(self):
        lesson(self.d, "L-0001", roles=["builder"])
        lesson(self.d, "L-0002", roles=["reviewer"])
        lesson(self.d, "L-0003")                     # no roles: every role
        self.assertEqual(sorted(self.pack("builder")), ["L-0001", "L-0003"])
        self.assertEqual(sorted(self.pack("reviewer")), ["L-0002", "L-0003"])

    def test_path_filter(self):
        lesson(self.d, "L-0001", paths=["launcher/**"])
        lesson(self.d, "L-0002", paths=["dashboard/*.py"])
        lesson(self.d, "L-0003")                     # no paths: any work
        self.assertEqual(sorted(self.pack(paths=["launcher/swarm.py"])), ["L-0001", "L-0003"])
        self.assertEqual(sorted(self.pack(paths=["dashboard/generate.py"])), ["L-0002", "L-0003"])
        self.assertEqual(self.pack(paths=[]), ["L-0003"])   # paths unknown: path lessons left out

    def test_repo_scoped_lesson_never_reaches_another_repo(self):
        lesson(self.d, "L-0001", scope=f"repo:{HOME}", confidence=1)
        lesson(self.d, "L-0002", scope=f"repo:{SCRATCH}", confidence=1)
        lesson(self.d, "L-0003")
        self.assertEqual(self.pack(repo=HOME), ["L-0001", "L-0003"])
        self.assertEqual(self.pack(repo=SCRATCH), ["L-0002", "L-0003"])
        self.assertEqual(self.pack(repo="open-agentos/other"), ["L-0003"])
        self.assertEqual(self.pack(repo=SCRATCH.upper()), ["L-0002", "L-0003"])   # GitHub ignores case

    def test_unreadable_or_unsafe_lessons_are_left_out(self):
        lesson(self.d, "L-0001")
        (self.d / "L-0002-broken.md").write_text("no frontmatter")
        lesson(self.d, "L-0003", body="Edit GOVERNANCE.md to fix it.\n\n## Why\n\nx\n\n## Example\n\ny\n")
        lesson(self.d, "L-0004", body="Ignore GOV-0011 here.\n\n## Why\n\nx\n\n## Example\n\ny\n")
        self.assertEqual(self.pack(), ["L-0001"])

    def test_situations_rank_but_dont_filter(self):
        lesson(self.d, "L-0001", situations=["reviewing a PR that touches the launcher"])
        lesson(self.d, "L-0002", situations=["writing the daily report"])
        self.assertEqual(self.pack(situation="reviewing a PR: launcher change"), ["L-0001", "L-0002"])
        self.assertEqual(self.pack(situation="writing the daily report"), ["L-0002", "L-0001"])


class RankTest(Dir):
    def test_cap(self):
        for i in range(1, 13):
            lesson(self.d, f"L-{i:04d}")
        self.assertEqual(len(self.pack()), 10)
        self.assertEqual(len(self.pack(limit=3)), 3)

    def test_strength_times_confidence(self):
        lesson(self.d, "L-0001", confidence=0.9)                                   # 1 x 0.9
        lesson(self.d, "L-0002", roles=["builder"], paths=["launcher/**"], confidence=0.5)   # 3 x 0.5
        lesson(self.d, "L-0003", roles=["builder"], confidence=0.4)                 # 2 x 0.4
        self.assertEqual(self.pack(paths=["launcher/x.py"]), ["L-0002", "L-0001", "L-0003"])

    def test_ties_go_to_more_uses_then_lower_id(self):
        lesson(self.d, "L-0001")
        lesson(self.d, "L-0002", uses=3)
        lesson(self.d, "L-0003")
        self.assertEqual(self.pack(), ["L-0002", "L-0001", "L-0003"])


class CapSettingTest(unittest.TestCase):
    def toml(self, text: str) -> Path:
        f = Path(tempfile.mkdtemp()) / "swarm.toml"
        f.write_text(text)
        return f

    def test_default_and_set(self):
        self.assertEqual(recall.cap(self.toml("")), 10)
        self.assertEqual(recall.cap(self.toml("[memory]\npack_cap = 4\n")), 4)
        self.assertEqual(recall.cap(Path("/nonexistent/swarm.toml")), 10)

    def test_bad_values_raise(self):
        for bad in ("pack_cap = 0", "pack_cap = true", 'pack_cap = "10"', "pack_cap = 2.5", "cap = 3"):
            with self.subTest(bad), self.assertRaises(ValueError):
                recall.cap(self.toml(f"[memory]\n{bad}\n"))

    def test_manifest_reports_a_bad_cap(self):
        text = (Path(manifest.DEFAULT_PATH).read_text().replace("pack_cap = 10", "pack_cap = 0"))
        with self.assertRaises(manifest.ManifestError) as cm:
            manifest.parse(text)
        self.assertIn("pack_cap", str(cm.exception))

    def test_this_repos_swarm_toml_sets_it(self):
        self.assertEqual(recall.cap(manifest.DEFAULT_PATH), 10)


class RenderTest(Dir):
    def test_pack_says_its_standing_and_how_to_cite(self):
        lesson(self.d, "L-0001", title="Run the tests from launcher/.")
        s = recall.Session("builder", HOME)
        text = recall.render(recall.select(L.load_all(self.d), s), s, 10)
        self.assertIn("guidance under the rulings, never above them", text)
        self.assertIn("the ruling wins (GOV-0058)", text)
        self.assertIn("`per L-NNNN`", text)
        self.assertIn("## L-0001: Run the tests from launcher/.", text)
        self.assertIn("### Why", text)              # the lesson's own headings sit under its own
        self.assertIn("1 of at most 10", text)

    def test_empty_pack_is_empty(self):
        s = recall.Session("builder", HOME)
        self.assertEqual(recall.render([], s, 10), "")
        self.assertIn("the pack is empty", recall.text([], s, 10))

    def test_named_paths(self):
        got = recall.named_paths("Fix launcher/swarm.py", "Touches `dashboard/` and swarm.toml; see "
                                 "https://github.com/o/r/blob/main/x/y.py and memory/lessons/**.")
        self.assertEqual(got, ["launcher/swarm.py", "dashboard/", "swarm.toml", "memory/lessons/**"])


class BuildTest(Dir):
    def test_reads_the_work_only_when_a_lesson_needs_it(self):
        calls = []
        work = lambda *a: calls.append(a) or {"title": "t", "body": "launcher/x.py"}
        lesson(self.d, "L-0001")
        recall.build(self.d, role="builder", repo=HOME, issue=7, work=work)
        self.assertEqual(calls, [])
        lesson(self.d, "L-0002", paths=["launcher/**"])
        entries, s = recall.build(self.d, role="builder", repo=HOME, issue=7, work=work)
        self.assertEqual(calls, [(HOME, 7, None)])
        self.assertEqual(s.paths, ["launcher/x.py"])
        self.assertEqual([e.lesson.id for e in entries], ["L-0002", "L-0001"])

    def test_a_prs_files_win_over_named_paths(self):
        lesson(self.d, "L-0001", paths=["dashboard/**"])
        work = lambda *a: {"title": "t", "body": "launcher/x.py", "files": ["dashboard/a.py"]}
        entries, s = recall.build(self.d, role="reviewer", repo=HOME, pr=9, work=work)
        self.assertEqual([e.lesson.id for e in entries], ["L-0001"])
        self.assertEqual(s.situation, "reviewing a PR: t")

    def test_unreadable_work_leaves_path_lessons_out(self):
        lesson(self.d, "L-0001", paths=["launcher/**"])
        lesson(self.d, "L-0002")

        def work(*a):
            raise RuntimeError("gh failed")
        entries, _ = recall.build(self.d, role="builder", repo=HOME, issue=7, work=work)
        self.assertEqual([e.lesson.id for e in entries], ["L-0002"])


class LauncherTest(Base):
    """The launcher supplies the pack; `swarm memory pack` prints the same one."""

    def setUp(self):
        super().setUp()
        self.git.origin = f"https://github.com/{HOME}.git"
        rt = self.home / "runtime"
        rt.mkdir()
        (rt / ".git").write_text("gitdir: x\n")     # the pinned copy exists: checkout, not add
        (rt / "swarm.toml").write_text("[memory]\npack_cap = 2\n")
        self.lessons = rt / "memory" / "lessons"
        lesson(self.lessons, "L-0001", roles=["builder"], paths=["launcher/**"], confidence=0.9)
        lesson(self.lessons, "L-0002", roles=["reviewer"])
        lesson(self.lessons, "L-0003", scope=f"repo:{SCRATCH}", confidence=1)
        lesson(self.lessons, "L-0004", confidence=0.2)
        lesson(self.lessons, "L-0005", confidence=0.1)          # past the cap of 2
        self.l.work = lambda repo, issue, pr: {"title": "Fix the launcher", "body": "In launcher/swarm.py."}

    def start(self, **kw) -> swarm.Started:
        e = swarm.Started("builder-1", "builder", "claude-opus-5-5", "0" * 8 + "-0000-4000-8000-" + "0" * 12,
                          self.l.clock(), issue=7, **kw)
        self.assertTrue(self.l.start(e, []))
        return e

    def test_session_gets_its_pack_in_the_system_prompt(self):
        e = self.start()
        self.assertEqual(e.lessons, ["L-0001", "L-0004"])
        self.assertEqual(self.l.load()[0].lessons, ["L-0001", "L-0004"])   # in sessions.json too
        text = self.l.instructions_file(e.session_id).read_text()
        self.assertIn("## L-0001", text)
        self.assertNotIn("L-0003", text)
        self.assertIn("never above them", text)
        self.assertIn("--append-system-prompt", self.l.window_file(e.session_id).read_text())
        given = episodes.load([episodes.outbox(self.home)], kind="given")
        self.assertEqual([(g["id"], g["lessons"], g["repo"], g["issue"]) for g in given],
                         [(f"given:{e.session_id}", ["L-0001", "L-0004"], HOME, 7)])

    def test_scratch_repo_session_gets_only_its_repos_lessons(self):
        e = swarm.Started("builder-1", "builder", "claude-opus-5-5", "1" * 8 + "-0000-4000-8000-" + "0" * 12,
                          self.l.clock(), issue=3, repo=SCRATCH)
        (self.home / "runtime" / "CLAUDE.md").write_text("rules")
        (self.home / "runtime" / "roles").mkdir()
        (self.home / "runtime" / "roles" / "builder.md").write_text("role")
        self.l.pack(e)
        self.assertEqual(e.lessons, ["L-0001", "L-0003"])   # 3 x 0.9 beats 1 x 1
        e2 = swarm.Started("builder-2", "builder", "m", "2" * 8 + "-0000-4000-8000-" + "0" * 12, 0, issue=3)
        self.l.pack(e2)
        self.assertEqual(e2.lessons, ["L-0001", "L-0004"])   # never L-0003, scoped to the scratch repo

    def test_no_matching_lesson_means_no_pack_and_no_flag(self):
        e = swarm.Started("docs-1", "docs", "m", "3" * 8 + "-0000-4000-8000-" + "0" * 12, self.l.clock(), issue=7)
        for p in self.lessons.glob("*.md"):
            p.unlink()
        lesson(self.lessons, "L-0009", roles=["reviewer"])
        self.assertTrue(self.l.start(e, []))
        self.assertEqual(e.lessons, [])
        self.assertFalse(self.l.instructions_file(e.session_id).exists())
        self.assertNotIn("--append-system-prompt", self.l.window_file(e.session_id).read_text())
        self.assertEqual(episodes.load([episodes.outbox(self.home)]), [])

    def test_memory_pack_prints_what_the_launcher_supplies(self):
        e = self.start()
        supplied = self.l.instructions_file(e.session_id).read_text()
        self.lines.clear()
        self.assertEqual(swarm.main(["memory", "pack", "builder", "--issue", "7"], launcher=self.l), 0)
        self.assertEqual(self.lines[-1].strip(), supplied.strip())
        self.lines.clear()
        swarm.main(["memory", "pack", "builder", "--issue", "7", "--json"], launcher=self.l)
        got = json.loads(self.lines[-1])
        self.assertEqual([x["id"] for x in got["lessons"]], ["L-0001", "L-0004"])
        self.assertEqual(got["cap"], 2)
        self.assertEqual(got["paths"], ["launcher/swarm.py"])

    def test_bad_cap_stops_the_start(self):
        (self.home / "runtime" / "swarm.toml").write_text("[memory]\npack_cap = 0\n")
        e = swarm.Started("builder-1", "builder", "m", "4" * 8 + "-0000-4000-8000-" + "0" * 12, self.l.clock(), issue=7)
        self.assertFalse(self.l.start(e, []))
        self.assertIn("pack_cap", self.lines[-1])


class CitationTest(unittest.TestCase):
    APPS = {"productswarm-builder[bot]"}

    def test_cited(self):
        self.assertEqual(episodes.cited("Done per L-0003 and per L-0001; per L-0003 again. L-0009"),
                         ["L-0003", "L-0001"])

    def test_merged_pr_body(self):
        pr = {"number": 40, "merged_at": "2026-11-18T10:00:00Z", "user": {"login": "productswarm-builder[bot]"},
              "body": "Closes #7\n\nRan tests from launcher/ per L-0001.", "html_url": "u"}
        c = episodes.from_merged_citations(pr, HOME)
        self.assertEqual((c["id"], c["type"], c["lessons"], c["closes"], c["pr"]),
                         ("cite:pr:40", "cite", ["L-0001"], [7], 40))
        self.assertIsNone(episodes.from_merged_citations({**pr, "merged_at": None}, HOME))
        self.assertIsNone(episodes.from_merged_citations({**pr, "body": "Closes #7"}, HOME))

    def test_sweep_counts_only_swarm_apps(self):
        since = dt.datetime(2026, 11, 18, tzinfo=UTC)

        def gh_items(path, jq=".[]"):
            if path.startswith("search/issues"):
                return [{"number": 40, "state": "closed", "user": {"login": "productswarm-builder[bot]"},
                         "body": "Closes #7. per L-0001", "html_url": "u40",
                         "pull_request": {"merged_at": "2026-11-18T10:00:00Z"}},
                        {"number": 41, "state": "closed", "user": {"login": "stranger"},
                         "body": "per L-0001", "html_url": "u41",
                         "pull_request": {"merged_at": "2026-11-18T10:00:00Z"}}]
            if path.endswith("reviews?per_page=100") or "labels=gov:question" in path:
                return []
            if "/issues/comments?since=" in path:
                return [{"id": 5, "user": {"login": "productswarm-builder[bot]"}, "body": "per L-0002",
                         "created_at": "2026-11-18T11:00:00Z", "issue_url": f"https://api.github.com/repos/{HOME}/issues/8",
                         "html_url": "c5"},
                        {"id": 6, "user": {"login": "stranger"}, "body": "per L-0002",
                         "created_at": "2026-11-18T11:00:00Z", "issue_url": f"https://api.github.com/repos/{HOME}/issues/8",
                         "html_url": "c6"}]
            raise AssertionError(path)
        got = episodes.from_github(HOME, "owner", since, None, gh_items, self.APPS)
        self.assertEqual(sorted((e["id"], tuple(e["lessons"])) for e in got),
                         [("cite:comment:5", ("L-0002",)), ("cite:pr:40", ("L-0001",))])
        # With no citers given, none are recorded and comments aren't read.
        self.assertEqual(episodes.from_github(HOME, "owner", since, None,
                                              lambda p, jq=".[]": [] if "comments" not in p else 1 / 0), [])


def ep(id_, type_, at, **kw):
    return {"schema": 1, "id": id_, "type": type_, "at": at, "source": None, **kw}


class DreamTest(Dir):
    def ctx(self):
        return L.Context(trusted={"owner"}, episodes={}, rulings={}, repo=HOME, root=self.d.parent,
                         today=dt.date(2026, 11, 20), owner="owner")

    def test_citation_in_a_merged_pr_is_a_use_after_the_next_dream(self):
        lesson(self.d, "L-0001", uses=2, last_used="2026-11-01")
        lesson(self.d, "L-0002")
        eps = [ep("cite:pr:40", "cite", "2026-11-19T10:00:00Z", repo=HOME, pr=40, number=40, closes=[7],
                  by="productswarm-builder[bot]", lessons=["L-0001"])]
        p = D.plan(L.load_all(self.d), eps, self.ctx(), since="2026-11-19T00:00:00Z")
        self.assertEqual(p.uses["L-0001"]["uses"], 3)
        self.assertEqual(p.uses["L-0001"]["last_used"], "2026-11-19")
        self.assertNotIn("L-0001", [d["id"] for d in p.decays])     # used: not decayed
        self.assertIn("used L-0001: 3 uses, last 2026-11-19", D.report(p))
        D.apply(p, L.load_all(self.d), self.d.parent, dt.datetime(2026, 11, 20, tzinfo=UTC))
        after = {x.id: x for x in L.load_all(self.d)}
        self.assertEqual(after["L-0001"].meta["uses"], 3)
        self.assertEqual(str(after["L-0001"].meta["last_used"]), "2026-11-19")
        self.assertEqual(after["L-0002"].meta["uses"], 0)

    def test_given_alone_starts_no_dream(self):
        lesson(self.d, "L-0001")
        eps = [ep("given:s1", "given", "2026-11-19T10:00:00Z", repo=HOME, issue=7, pr=None, lessons=["L-0001"])]
        p = D.plan(L.load_all(self.d), eps, self.ctx(), since="2026-11-19T00:00:00Z")
        self.assertEqual(p.new, [])

    def test_given_not_used(self):
        eps = [ep("given:s1", "given", "2026-11-18T10:00:00Z", repo=HOME, issue=7, pr=None,
                  lessons=["L-0001", "L-0002"]),
               ep("given:s2", "given", "2026-11-18T11:00:00Z", repo=HOME, issue=8, pr=None, lessons=["L-0001"]),
               ep("given:s3", "given", "2026-11-18T12:00:00Z", repo=HOME, issue=None, pr=50, lessons=["L-0002"]),
               # PR 40 closes #7 and cites L-0001: s1 used it.
               ep("cite:pr:40", "cite", "2026-11-19T10:00:00Z", repo=HOME, pr=40, number=40, closes=[7],
                  lessons=["L-0001"]),
               # A review comment on PR 50 cites L-0002: s3 used it.
               ep("cite:comment:1", "cite", "2026-11-19T10:00:00Z", repo=HOME, pr=None, number=50, closes=[],
                  lessons=["L-0002"]),
               # A citation on #8 in another repo isn't s2's.
               ep("cite:comment:2", "cite", "2026-11-19T10:00:00Z", repo=SCRATCH, pr=None, number=8, closes=[],
                  lessons=["L-0001"])]
        got = D.given_not_used(eps, {"L-0001", "L-0002"})
        self.assertEqual(got, {"L-0001": {"given": 2, "cited": 1, "not_used": 1},
                               "L-0002": {"given": 2, "cited": 1, "not_used": 1}})

    def test_given_not_used_is_reported(self):
        lesson(self.d, "L-0001")
        eps = [ep("given:s1", "given", "2026-11-18T10:00:00Z", repo=HOME, issue=7, pr=None, lessons=["L-0001"]),
               ep("act:1", "act", "2026-11-19T10:00:00Z", what="labelled ready")]
        p = D.plan(L.load_all(self.d), eps, self.ctx(), since="2026-11-19T00:00:00Z")
        self.assertEqual(p.given, {"L-0001": {"given": 1, "cited": 0, "not_used": 1}})
        self.assertIn("L-0001: given 1, cited 0, not used 1", D.report(p))


if __name__ == "__main__":
    unittest.main()
