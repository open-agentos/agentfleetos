"""Tests for owner.py, the owner model (#1188, FEAT-18; GOV-0052, GOV-0056): its format and
validator, the part each role is given, vetoes, the dream's proposals, the launcher adding a
role's part to its pack, and `swarm memory owner`."""
import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path

import dream as D
import lessons as L
import merger
import owner as O
import swarm
from test_recall import HOME, lesson
from test_swarm import Base

TODAY = dt.date(2026, 11, 18)
OWNER = "mattmcalister"
ROLES = {"planner", "builder", "reviewer", "docs", "designer", "analyst", "librarian"}
HEAD = "# The owner model\n\nPreamble.\n\n    ### O-0099: an example, not an entry\n\n## Entries\n"


def entry(oid: str, title: str, body: str, *, kind="preference", roles=(), sources=("#1150",),
          date="2026-11-17") -> str:
    lines = [f"### {oid}: {title}", f"- kind: {kind}"]
    if roles:
        lines.append(f"- roles: {', '.join(roles)}")
    lines += [f"- sources: {', '.join(sources)}", f"- date: {date}", "", body, ""]
    return "\n".join(lines)


MODEL = HEAD + "\n" + "\n".join([
    entry("O-0001", "Plain words in reports", "Write reports in plain words, the answer first.",
          roles=("docs", "analyst")),
    entry("O-0002", "Short PR bodies", "Keep PR bodies short: what changed and how it was tested.",
          roles=("builder",), sources=("act:k1", "review:9")),
    entry("O-0003", "Weekly check-in shape", "Each Goal gets moved, at risk or slipped, in that order.",
          kind="pattern"),      # untagged: the planner alone
]) + "\n## Vetoed\n"


def act(n: int, what: str, at: str = "2026-11-17T10:00:00Z") -> dict:
    return {"schema": 1, "id": f"act:k{n}", "type": "act", "at": at, "act": "edit", "kind": "c-team",
            "tag": "correction", "what": what, "repo": HOME, "number": n,
            "source": f"https://github.com/{HOME}/issues/{n}#c{n}"}


def ctx(eps) -> L.Context:
    return L.Context(trusted={OWNER}, episodes={e["id"]: e for e in eps}, rulings={}, repo=HOME,
                     today=TODAY, owner=OWNER)


# Two owner corrections that say the same thing, and a session note that isn't the owner's.
EMOJI = [act(1, "removed emoji from the daily report headings, plain headings only"),
         act(2, "took emoji out of the report headings again: plain headings please"),
         {"schema": 1, "id": "note:s1", "type": "note", "at": "2026-11-17T11:00:00Z", "role": "docs",
          "session_id": "s1", "note": {"tried": "emoji report headings plain", "surprised": "none",
                                       "blocked": "none"}, "source": None}]


class Format(unittest.TestCase):
    def test_parse(self):
        m = O.parse(MODEL)
        self.assertEqual([e.id for e in m.entries], ["O-0001", "O-0002", "O-0003"])   # not O-0099
        e = m.entries[1]
        self.assertEqual((e.kind, e.roles, e.sources, e.date), ("preference", ["builder"], ["act:k1", "review:9"],
                                                               "2026-11-17"))
        self.assertEqual(e.body, "Keep PR bodies short: what changed and how it was tested.")
        self.assertEqual(O.validate(m, ROLES, TODAY), [])

    def test_the_repo_file_is_valid(self):
        m = O.load(Path(__file__).resolve().parent.parent / "memory" / O.FILE)
        self.assertEqual(O.validate(m, ROLES, TODAY), [])

    def test_bad_fields(self):
        text = HEAD + entry("O-0001", "X", "Say it.", kind="wish", roles=("chef",), sources=("somewhere",),
                            date="2026-12-25") + "### Untitled\n"
        errs = "\n".join(O.validate(O.parse(text), ROLES, TODAY))
        for want in ("kind must be", "no role 'chef'", "source 'somewhere'", "in the future",
                     "O-NNNN: <title>"):
            self.assertIn(want, errs)


class Validator(unittest.TestCase):
    """Working preferences only: the file is public."""

    def errs(self, body: str) -> str:
        return "\n".join(O.validate(O.parse(HEAD + entry("O-0001", "Mornings", body)), ROLES, TODAY))

    def test_rejects_contact_details_and_personal_data(self):
        for body, why in [
            ("Send urgent things to owner@example.com.", "email address"),
            ("Call +1 (415) 555-0134 if the build breaks.", "phone number"),
            ("Ping @someone on the other site.", "handle"),
            ("Their calendar is at https://cal.example.com/owner.", "outside github.com"),
            ("Courier things to 12 Market Street.", "street address"),
            ("No reports while the owner's kids are home.", "family"),
            ("Quiet weeks around the owner's surgery.", "health"),
            ("Mind the salary talk.", "finances"),
            ("The owner lives in Lisbon, so use its time zone.", "whereabouts"),
            ("Use the owner's phone number for outages.", "contacts"),
        ]:
            with self.subTest(body=body):
                self.assertIn(why, self.errs(body))
                self.assertIn("personal data", self.errs(body))

    def test_working_preferences_pass(self):
        for body in ["Use a sans-serif font family in the Desk.", "Link the parent issue and its child issues.",
                     "Name tech debt plainly.", "Dates as 2026-11-18, never 11/18.",
                     "Cite PRs as https://github.com/open-agentos/agentfleetos/pull/1."]:
            with self.subTest(body=body):
                self.assertEqual(self.errs(body), "")

    def test_rejects_a_rule_over_governance(self):
        self.assertIn("can't", self.errs("Grant the builder permissions to merge."))
        self.assertIn("can't", self.errs("This preference overrides GOV-0011."))

    def test_an_invalid_entry_never_reaches_a_session(self):
        text = MODEL.replace("## Vetoed", entry("O-0004", "Hours", "Reach the owner at owner@example.com.",
                                                roles=("builder",)) + "\n## Vetoed")
        got = O.valid_entries(O.parse(text), ROLES, TODAY)
        self.assertNotIn("O-0004", [e.id for e in got])
        self.assertNotIn("example.com", O.render(O.for_role(got, "planner"), "planner"))


class Roles(unittest.TestCase):
    """The planner gets the whole file; every other role only its tagged entries (GOV-0056)."""

    def test_planner_gets_everything(self):
        es = O.valid_entries(O.parse(MODEL), ROLES, TODAY)
        self.assertEqual([e.id for e in O.for_role(es, "planner")], ["O-0001", "O-0002", "O-0003"])

    def test_other_roles_get_only_tagged_entries_never_untagged(self):
        es = O.valid_entries(O.parse(MODEL), ROLES, TODAY)
        untagged = {e.id for e in es if not e.roles}
        self.assertEqual(untagged, {"O-0003"})
        for role in sorted(ROLES - {"planner"}):
            with self.subTest(role=role):
                got = O.for_role(es, role)
                self.assertTrue(all(role in e.roles for e in got))
                self.assertFalse(untagged & {e.id for e in got})
                self.assertNotIn("O-0003", O.render(got, role))
        self.assertEqual([e.id for e in O.for_role(es, "docs")], ["O-0001"])
        self.assertEqual([e.id for e in O.for_role(es, "builder")], ["O-0002"])

    def test_render_says_preferences_not_rules(self):
        es = O.for_role(O.valid_entries(O.parse(MODEL), ROLES, TODAY), "builder")
        out = O.render(es, "builder")
        self.assertIn("not rules and never outrank a ruling", out)
        self.assertIn("## O-0002: Short PR bodies (preference)", out)
        self.assertEqual(O.render([], "builder"), "")


class Tmp(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.mem = Path(tmp.name) / "memory"
        self.mem.mkdir()
        self.path = self.mem / O.FILE
        self.path.write_text(MODEL)


class Veto(Tmp):
    def test_veto_removes_the_entry(self):
        O.veto(self.path, "O-0001", TODAY)
        m = O.parse(self.path.read_text())
        self.assertEqual([e.id for e in m.entries], ["O-0002", "O-0003"])
        self.assertEqual([(v.id, v.date) for v in m.vetoed], [("O-0001", "2026-11-18")])
        self.assertIn("Plain words in reports", m.vetoed[0].text)
        self.assertEqual(O.validate(m, ROLES, TODAY), [])
        self.assertEqual(O.for_role(O.valid_entries(m, ROLES, TODAY), "docs"), [])
        self.assertEqual(swarm.owner_part(self.mem.parent, "docs"), "")

    def test_veto_a_proposal_needs_its_words(self):
        with self.assertRaises(ValueError):
            O.veto(self.path, "O-0007", TODAY)
        O.veto(self.path, "O-0007", TODAY, "No emoji in headings")
        O.veto(self.path, "O-0008", TODAY, "Something else")
        self.assertEqual([v.id for v in O.parse(self.path.read_text()).vetoed], ["O-0007", "O-0008"])
        with self.assertRaises(ValueError):
            O.veto(self.path, "O-0007", TODAY, "again")

    def test_a_vetoed_entry_still_in_entries_is_left_out(self):
        self.path.write_text(MODEL + "\n- O-0001, 2026-11-18: Plain words\n")
        m = O.load(self.path)
        self.assertIn("O-0001: both an entry and vetoed", "\n".join(O.validate(m, ROLES, TODAY)))
        self.assertNotIn("O-0001", [e.id for e in O.valid_entries(m, ROLES, TODAY)])


class Dream(Tmp):
    """The librarian proposes in the dream report; nothing reaches a session until the owner adds it."""

    def plan(self, eps, today=TODAY, since="2026-11-17T00:00:00Z"):
        c = ctx(eps)
        c.today = today
        return D.plan([], eps, c, since=since, owner_model=O.load(self.path))

    def test_proposal_in_report_with_sources_but_not_in_any_pack(self):
        p = self.plan(EMOJI)
        self.assertEqual([(c["id"], c["sources"]) for c in p.owner], [("O-0004", ["act:k1", "act:k2"])])
        report = D.report(p)
        self.assertIn("7. Owner model: 1 proposed entry", report)
        self.assertIn("propose O-0004 from act:k1, act:k2", report)
        self.assertIn(f"https://github.com/{HOME}/issues/1#c1", report)
        self.assertIn("None reaches a session until the owner adds it", report)
        for role in ROLES:   # the file is unchanged, so no session sees it
            self.assertNotIn("emoji", swarm.owner_part(self.mem.parent, role).lower())
        self.assertEqual(self.path.read_text(), MODEL)
        # Once the owner adds it, the roles it's tagged for get it.
        self.path.write_text(MODEL.replace("## Vetoed", entry(
            "O-0004", "No emoji in headings", "Report headings are plain words, no emoji.",
            roles=("docs",), sources=("act:k1", "act:k2")) + "\n## Vetoed"))
        self.assertIn("No emoji", swarm.owner_part(self.mem.parent, "docs"))
        self.assertIn("No emoji", swarm.owner_part(self.mem.parent, "planner"))
        self.assertNotIn("No emoji", swarm.owner_part(self.mem.parent, "builder"))
        self.assertEqual(self.plan(EMOJI).owner, [])    # and it isn't proposed again

    def test_one_owner_episode_or_only_old_ones_propose_nothing(self):
        self.assertEqual(self.plan(EMOJI[:1] + EMOJI[2:]).owner, [])
        self.assertEqual(self.plan(EMOJI, since="2026-11-18T00:00:00Z").owner, [])

    def test_a_veto_holds_the_same_proposal_back_for_30_days(self):
        O.veto(self.path, "O-0004", TODAY, "No emoji in the daily report headings: plain headings only")
        p = self.plan(EMOJI)
        self.assertEqual(p.owner, [])
        self.assertEqual(p.owner_held, [{"sources": ["act:k1", "act:k2"], "veto": "O-0004", "until": "2026-12-18"}])
        self.assertIn("like O-0004, vetoed; not proposed before 2026-12-18", D.report(p))
        later = [act(1, EMOJI[0]["what"], "2026-12-18T10:00:00Z"), act(2, EMOJI[1]["what"], "2026-12-18T11:00:00Z")]
        self.assertEqual(self.plan(later, today=dt.date(2026, 12, 17), since="2026-12-01T00:00:00Z").owner, [])
        again = self.plan(later, today=dt.date(2026, 12, 18), since="2026-12-01T00:00:00Z").owner
        self.assertEqual([c["id"] for c in again], ["O-0005"])   # past the veto's id too

    def test_vetoing_an_entry_holds_it_back_too(self):
        self.path.write_text(MODEL.replace("## Vetoed", entry(
            "O-0004", "No emoji in report headings", "Plain report headings, no emoji.") + "\n## Vetoed"))
        self.assertEqual(self.plan(EMOJI).owner, [])        # an entry says it already
        O.veto(self.path, "O-0004", TODAY)
        p = self.plan(EMOJI)
        self.assertEqual((p.owner, [h["veto"] for h in p.owner_held]), ([], ["O-0004"]))

    def test_owner_cited_episodes_are_kept_past_retention(self):
        old = [act(1, "x", "2026-09-01T00:00:00Z"), act(5, "y", "2026-09-01T00:00:00Z"),
               act(6, "new thing entirely", "2026-11-17T12:00:00Z")]
        self.path.write_text(MODEL.replace("act:k1, review:9", "act:k1"))
        p = self.plan(old)
        self.assertIn("act:k1", p.kept_cited)
        self.assertIn("act:k5", p.expired)


class Merger(unittest.TestCase):
    def test_owner_model_is_a_protected_path(self):
        self.assertTrue(merger.is_protected("memory/owner.md"))
        self.assertFalse(merger.is_protected("memory/lessons/L-0001-x.md"))


class LauncherTest(Base):
    """The launcher adds the role's part of the owner model to the pack, as test_recall's
    LauncherTest sets the pinned copy up."""

    def setUp(self):
        super().setUp()
        self.git.origin = f"https://github.com/{HOME}.git"
        rt = self.home / "runtime"
        rt.mkdir()
        (rt / ".git").write_text("gitdir: x\n")
        (rt / "swarm.toml").write_text("[memory]\npack_cap = 2\n")
        self.lessons = rt / "memory" / "lessons"
        lesson(self.lessons, "L-0001", roles=["builder"], confidence=0.9)
        self.l.work = lambda repo, issue, pr: {"title": "Fix the launcher", "body": "In launcher/swarm.py."}
        (rt / "roles").mkdir(exist_ok=True)
        for r in ROLES:
            (rt / "roles" / f"{r}.md").write_text("role")
        (rt / "memory" / O.FILE).write_text(MODEL)

    def start(self) -> swarm.Started:
        e = swarm.Started("builder-1", "builder", "claude-opus-5-5", "0" * 8 + "-0000-4000-8000-" + "0" * 12,
                          self.l.clock(), issue=7)
        self.assertTrue(self.l.start(e, []))
        return e

    def test_builder_session_gets_its_tagged_entries_after_the_lessons(self):
        e = self.start()
        text = self.l.instructions_file(e.session_id).read_text()
        self.assertLess(text.index("## L-0001"), text.index("## O-0002"))
        self.assertNotIn("O-0001", text)
        self.assertNotIn("O-0003", text)

    def test_owner_part_without_lessons(self):
        for p in self.lessons.glob("*.md"):
            p.unlink()
        e = swarm.Started("planner-1", "planner", "m", "5" * 8 + "-0000-4000-8000-" + "0" * 12, self.l.clock(), issue=7)
        self.assertTrue(self.l.start(e, []))
        text = self.l.instructions_file(e.session_id).read_text()
        for oid in ("O-0001", "O-0002", "O-0003"):
            self.assertIn(oid, text)

    def test_memory_pack_prints_what_the_launcher_supplies(self):
        e = self.start()
        supplied = self.l.instructions_file(e.session_id).read_text()
        self.lines.clear()
        self.assertEqual(swarm.main(["memory", "pack", "builder", "--issue", "7"], launcher=self.l), 0)
        self.assertEqual(self.lines[-1].strip(), supplied.strip())
        self.lines.clear()
        swarm.main(["memory", "pack", "builder", "--issue", "7", "--json"], launcher=self.l)
        self.assertIn("O-0002", json.loads(self.lines[-1])["owner"])

    def test_memory_owner_command(self):
        mem = str(self.home / "runtime" / "memory")
        self.lines.clear()
        self.assertEqual(swarm.main(["memory", "owner", "--memory", mem, "--check"], launcher=self.l), 0)
        self.assertIn("3 entries valid", self.lines[-1])
        self.lines.clear()
        swarm.main(["memory", "owner", "--memory", mem], launcher=self.l)
        out = "\n".join(self.lines)
        self.assertIn("O-0003: Weekly check-in shape (pattern; for planner only", out)
        self.lines.clear()
        swarm.main(["memory", "owner", "--memory", mem, "--role", "docs", "--json"], launcher=self.l)
        self.assertEqual([x["id"] for x in json.loads(self.lines[-1])["entries"]], ["O-0001"])
        self.lines.clear()
        self.assertEqual(swarm.main(["memory", "owner", "--memory", mem, "veto", "O-0002"], launcher=self.l), 0)
        self.assertIn("vetoed O-0002", self.lines[-1])
        self.assertEqual(swarm.main(["memory", "owner", "--memory", mem, "veto"], launcher=self.l), 2)

if __name__ == "__main__":
    unittest.main()
