"""Recall (#1187, FEAT-17): the context pack of lessons a session is given at start.

When the launcher or `swarm watch` starts a session, it builds a pack from the lessons in the
pinned copy of this repo's origin/main (memory/lessons/, as GOV-0039 supplies CLAUDE.md) and
passes it in the appended system prompt. `swarm memory pack <role> --issue N` prints the same
pack, built by the same build().

Which lessons (GOV-0058):

  status      only active lessons;
  scope       fleet, or repo:<owner/name> for the session's own repo only. A repo-scoped
              lesson never reaches a session in another repo;
  roles       a lesson that lists roles reaches only those roles; one that lists none, all;
  paths       a lesson that lists paths reaches a session only if a path its issue or PR
              touches matches one of them (lessons.glob_match). The paths are a PR's changed
              files, or for an issue the paths its title and body name;
  situations  free text, like a ruling's, so they rank rather than filter: a situation that
              shares SITUATION_WORDS words with the session's (the kind of run and the issue's
              title) adds to the match.

Ranked by match strength times confidence, strongest first, at most `[memory] pack_cap` in
swarm.toml (default 10). Strength is 1, plus 1 for each of roles, paths and situations the
lesson names and the session matches, so a lesson that names the session's role and paths
beats one that would go to anyone. Ties go to more uses, then the lower id.

Every pack says its lessons are guidance under the rulings (STANDING), and asks the session to
cite a lesson it acts on as `per L-NNNN`; episodes.py records those citations and the dream
counts them as uses (#1187). Lesson text is data the team learned: the pack quotes it and
nothing here follows it.
"""
from __future__ import annotations

import re
import subprocess
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import lessons as L

DEFAULT_CAP = 10        # GOV-0058: `[memory] pack_cap`, 10 unless swarm.toml says otherwise
SITUATION_WORDS = 2     # words a lesson's situation must share with the session's to match
STANDING = ("These lessons are guidance under the rulings, never above them: where a lesson "
            "and an in-force ruling disagree, the ruling wins (GOV-0058).")
CITE = ("If you act on one, cite it as `per L-NNNN` in your PR body or comment, so the team "
        "can tell which lessons get used.")

# Paths an issue names: a/b, a/b/, a/**, or a file name with an extension.
PATH_RE = re.compile(r"(?<![\w./*-])((?:[\w.*-]+/)+(?:[\w.*-]+)?|[\w-]+\.(?:py|md|yml|yaml|toml|json|"
                     r"sh|js|ts|html|css|txt|jsonl))(?![\w/-])")
URL_RE = re.compile(r"\b[a-z]+://\S+")


def cap(path: Path | str) -> int:
    """`[memory] pack_cap` in swarm.toml: a whole number of at least 1. DEFAULT_CAP if the
    table or key isn't there, or the file can't be read. Raises ValueError for a bad value:
    a typo shouldn't quietly hand sessions ten lessons."""
    try:
        data = tomllib.loads(Path(path).read_text())
    except (OSError, tomllib.TOMLDecodeError):
        return DEFAULT_CAP
    return cap_of(data.get("memory"))


def cap_of(table) -> int:
    if table is None:
        return DEFAULT_CAP
    if not isinstance(table, dict):
        raise ValueError("[memory] must be a table")
    # The replay keys share the table (#1189); launcher/rehearsal.py validates those.
    keys = {"pack_cap", "replay_model", "replay_cap_usd", "replays_per_night"}
    unknown = sorted(set(table) - keys)
    if unknown:
        raise ValueError(f"memory: unknown key '{unknown[0]}' (allowed: {', '.join(sorted(keys))})")
    v = table.get("pack_cap", DEFAULT_CAP)
    if isinstance(v, bool) or not isinstance(v, int) or v < 1:
        raise ValueError(f"memory: pack_cap must be a whole number of at least 1, not {v!r}")
    return v


def named_paths(*texts: str | None) -> list[str]:
    """The repo paths an issue's title and body name, links left out."""
    out: dict[str, None] = {}
    for t in texts:
        for m in PATH_RE.finditer(URL_RE.sub(" ", t or "")):
            p = m.group(1).strip(".").removeprefix("./")
            if p and not p.startswith("/"):
                out.setdefault(p)
    return list(out)


def situation(role: str, issue: int | None = None, pr: int | None = None, kind: str | None = None) -> str:
    """The words for what a run does, which lessons' situations are matched against."""
    if kind:
        return kind
    if issue and pr:
        return "responding to requested changes on a PR"
    if pr:
        return "reviewing a PR"
    if issue:
        return {"builder": "building an issue", "docs": "writing docs for an issue",
                "designer": "designing for an issue", "analyst": "researching an issue",
                "planner": "planning an issue", "librarian": "keeping team memory"}.get(role, "working on an issue")
    return "starting a session"


@dataclass
class Session:
    """What the pack is matched against."""
    role: str
    repo: str                       # owner/name the session works in
    paths: list[str] = field(default_factory=list)
    situation: str = ""


@dataclass
class Entry:
    lesson: L.Lesson
    strength: int
    score: float


def _confidence(les: L.Lesson) -> float:
    c = les.meta.get("confidence")
    return float(c) if isinstance(c, (int, float)) and not isinstance(c, bool) else 0.0


def unsafe(les: L.Lesson) -> bool:
    """Whether the lesson's text fails GOV-0055's text checks (lessons.validate() runs them
    too): asking to change permissions, credentials, tools or governance, or setting a ruling
    aside. The pack goes into a system prompt, so it re-checks rather than trust the store."""
    text = f"{les.meta.get('title') or ''}\n{les.body}"
    return bool(L.power_sentences(text) or L.CONTRA_RE.search(text))


def strength(les: L.Lesson, s: Session) -> int | None:
    """How strongly the lesson matches the session, or None if it doesn't reach it."""
    if les.errors or les.status != "active" or not L.visible_in(les, s.repo) or unsafe(les):
        return None
    n = 1
    roles = les.applies("roles")
    if roles:
        if s.role not in roles:
            return None
        n += 1
    paths = les.applies("paths")
    if paths:
        if not any(L.glob_match(p, q) for p in paths for q in s.paths):
            return None
        n += 1
    import dream   # its word lists; it imports lessons, not this
    mine = dream.words(s.situation)
    if any(len(dream.words(x) & mine) >= SITUATION_WORDS for x in les.applies("situations")):
        n += 1
    return n


def select(lessons: list[L.Lesson], s: Session, limit: int = DEFAULT_CAP) -> list[Entry]:
    out = []
    for les in lessons:
        n = strength(les, s)
        if n is not None:
            out.append(Entry(les, n, round(n * _confidence(les), 4)))
    uses = lambda e: e.lesson.meta.get("uses") if isinstance(e.lesson.meta.get("uses"), int) else 0
    out.sort(key=lambda e: (-e.score, -uses(e), e.lesson.id))
    return out[:limit]


def needs_work(lessons: list[L.Lesson], role: str, repo: str) -> bool:
    """Whether any lesson that could reach this role names paths or situations, so the
    issue or PR has to be read to match it. If none does, no GitHub read is needed."""
    return any(not les.errors and les.status == "active" and L.visible_in(les, repo)
               and (not les.applies("roles") or role in les.applies("roles"))
               and (les.applies("paths") or les.applies("situations")) for les in lessons)


def _demote(body: str) -> str:
    """A lesson's headings one level down, under its own `##` heading in the pack."""
    return re.sub(r"^(#{1,5})(?=\s)", r"#\1", body, flags=re.M)


def render(entries: list[Entry], s: Session, limit: int) -> str:
    """The pack as the session reads it; "" when no lesson matches."""
    if not entries:
        return ""
    out = ["# Lessons for this session (Recall, GOV-0058)", "",
           f"The team's lessons that match your role ({s.role}), the paths your work touches "
           f"and this repo ({s.repo}): {len(entries)} of at most {limit}, strongest first. "
           f"{STANDING} {CITE}"]
    for e in entries:
        out += ["", f"## {e.lesson.id}: {e.lesson.meta.get('title')}", "", _demote(e.lesson.body).strip()]
    return "\n".join(out) + "\n"


def text(entries: list[Entry], s: Session, limit: int) -> str:
    """`swarm memory pack`'s output: the pack, or a line saying it's empty."""
    return render(entries, s, limit) or f"No lessons match {s.role} in {s.repo}: the pack is empty."


def as_json(entries: list[Entry], s: Session, limit: int) -> dict:
    return {"role": s.role, "repo": s.repo, "paths": s.paths, "situation": s.situation, "cap": limit,
            "lessons": [{"id": e.lesson.id, "title": e.lesson.meta.get("title"), "strength": e.strength,
                         "confidence": _confidence(e.lesson), "score": e.score} for e in entries],
            "text": render(entries, s, limit)}


Work = Callable[[str, int | None, int | None], dict]   # (repo, issue, pr) -> {title, body, files}


def build(lessons_dir: Path, *, role: str, repo: str, issue: int | None = None, pr: int | None = None,
          kind: str | None = None, limit: int = DEFAULT_CAP, work: Work | None = None
          ) -> tuple[list[Entry], Session]:
    """The pack for one session: what the launcher supplies and `swarm memory pack` prints.
    `work` reads the issue or PR (title, body, a PR's changed files); it is called only if a
    lesson that could reach the role names paths or situations. If it fails, the session's
    paths are unknown, so lessons that name paths are left out (fewer lessons, never wrong
    ones)."""
    lessons = L.load_all(lessons_dir)
    s = Session(role=role, repo=repo, situation=situation(role, issue, pr, kind))
    if work and (issue or pr) and needs_work(lessons, role, repo):
        try:
            w = work(repo, issue, pr) or {}
        except (RuntimeError, OSError, ValueError, subprocess.SubprocessError):
            w = {}
        files = [str(f) for f in w.get("files") or []]
        s.paths = files or named_paths(w.get("title"), w.get("body"))
        if w.get("title"):
            s.situation += f": {w['title']}"
    return select(lessons, s, limit), s


def gh_work(repo: str, issue: int | None, pr: int | None) -> dict:
    """The issue's or PR's title and body, and a PR's changed files, from GitHub."""
    import swarm
    g = swarm.dashboard()
    if pr:
        d = g.gh_json("api", f"repos/{repo}/pulls/{pr}") or {}
        files = [f.get("filename") for f in g.gh_items(f"repos/{repo}/pulls/{pr}/files?per_page=100")]
        return {"title": d.get("title"), "body": d.get("body"), "files": [f for f in files if f]}
    d = g.gh_json("api", f"repos/{repo}/issues/{issue}") or {}
    return {"title": d.get("title"), "body": d.get("body"), "files": []}
