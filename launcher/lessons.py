"""Lessons: the format and the store (#1185, FEAT-15).

One lesson per file, `memory/lessons/L-NNNN-<slug>.md` (public in this repo, per GOV-0052),
with frontmatter modelled on the ruling format and a body that says the lesson, why, and an
example. Lessons cite as `per L-NNNN`.

This module:
  - parses a lesson file (a small YAML subset, the one decision records use);
  - validates it, including GOV-0055's source rules (option 1 of #1151);
  - lists and shows lessons (`swarm memory lessons`, `swarm memory show`);
  - generates `memory/INDEX.md` (`swarm memory index`), one row per active or dormant lesson.

Episodes (#1184, FEAT-14) are read with episodes.load(), from `memory/episodes/` and, until
#1199's record merges, the engine's outbox. Only these fields of an episode are used:

  id          the id a lesson's `sources` names
  type        "note" for a session's own note; an engine-recorded signal if in ENGINE_TYPES
  by          who wrote a review, revert or unmerged PR
  role        the role whose session wrote a note: its App, productswarm-<role>[bot]
  session_id  the session that wrote a note, or whose run failed
  source      the signal's source link
  at          when it was recorded (shown, not checked)

An act, retag or answer is the owner's by construction (episodes.py records only theirs), and
a run comes from the engine's own runs ledger. See author().

Nothing here reads a lesson's or an episode's text as instructions: they are data.
"""
from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MEMORY = ROOT / "memory"
LESSONS = MEMORY / "lessons"
EPISODES = MEMORY / "episodes"
INDEX = MEMORY / "INDEX.md"
GOV_INDEX = ROOT / "governance" / "INDEX.md"

STATUSES = ("proposed", "active", "dormant", "retired")
REQUIRED = ("id", "title", "status", "scope", "applies_to", "sources", "confidence", "uses",
            "last_used", "created", "review_by", "eval_case", "supersedes", "related_rulings")
# Episode types the engine records with no model call (FEAT-14's signals). GOV-0055 needs at
# least one source of these: "an owner act, a review outcome, a revert, a failed run".
# Anything else, including a type this list doesn't know, is not an engine-recorded signal.
# These are episodes.TYPES less "note", listed here so a type episodes.py adds later doesn't
# count until someone adds it.
ENGINE_TYPES = frozenset({"act", "retag", "review", "revert", "closed-unmerged", "run", "answer"})
OWNER_TYPES = frozenset({"act", "retag", "answer"})   # recorded only for the owner's own acts
ENGINE = "the engine"   # a run's author: the runs ledger, written by swarm watch itself

FILE_RE = re.compile(r"^(L-\d{4})-([a-z0-9]+(?:-[a-z0-9]+)*)\.md$")
ID_RE = re.compile(r"^L-\d{4}$")
GOV_RE = re.compile(r"^GOV-\d{4}$")
SCOPE_RE = re.compile(r"^(fleet|repo:[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)$")
GOV_ROW_RE = re.compile(r"^\|\s*\[(GOV-\d{4})\]\([^)]*\)\s*\|.*\|\s*([a-z-]+)\s*\|\s*[^|]*\|\s*$")

# A lesson may not tell a session to change permissions, credentials, tools or governance
# (GOV-0055). Any sentence that pairs a change verb with one of these targets is refused,
# negated or not ("never edit GOVERNANCE.md" too): rulings already say that, and a rule a
# model can argue its way around isn't one.
POWER_VERBS = (r"change|edit|modify|update|alter|rewrite|replace|grant|give|add|remove|delete|"
               r"drop|widen|loosen|relax|raise|lift|disable|enable|turn\s+off|turn\s+on|bypass|"
               r"skip|override|ignore|work\s+around|rotate|export|unset|set|swap|switch|install|allow")
POWER_TARGETS = (r"permissions?|credentials?|GH_TOKEN|GITHUB_TOKEN|GH_CONFIG_DIR|"
                 r"(?:access|auth|api|app|bot|github|gh)\s+tokens?|secrets?|api[\s_-]?keys?|"
                 r"passwords?|ssh[\s_-]?keys?|git\s+credential\S*|allowed[\s_-]?tools|"
                 r"tool\s+(?:list|allowlist|permissions?|access)|allowlists?|"
                 r"settings(?:\.local)?\.json|--dangerously\S*|sandbox|"
                 r"GOVERNANCE\.md|jurisdictions(?:\.yml)?|governance(?!\s+question)|gov:ruled|"
                 r"`?ready`?\s+label|rulesets?|branch\s+protection|CODEOWNERS|"
                 r"\.github/workflows|workflow\s+files?|ops/")
POWER_RE = re.compile(rf"\b(?:{POWER_VERBS})\b[^.!?\n]*?(?:{POWER_TARGETS})"
                      rf"|(?:{POWER_TARGETS})[^.!?\n]*?\b(?:{POWER_VERBS})\b", re.IGNORECASE)
# A lesson is guidance under the rulings: it may not set one aside.
CONTRA_RE = re.compile(r"\b(?:ignore|override|overrides|supersede|supersedes|set\s+aside|"
                       r"contrary\s+to|despite|regardless\s+of|bypass|"
                       r"no\s+longer\s+(?:follow|applies?))\b[^.!?\n]*\bGOV-\d{4}\b", re.IGNORECASE)


# ---------------------------------------------------------------- parsing

class FormatError(ValueError):
    pass


def _scalar(s: str):
    s = s.strip()
    if s in ("", "null", "~"):
        return None
    if len(s) >= 2 and s[0] == s[-1] and s[0] in "\"'":
        return s[1:-1]
    if s.startswith("[") and s.endswith("]"):
        inner = s[1:-1].strip()
        return [_scalar(x) for x in inner.split(",")] if inner else []
    if re.fullmatch(r"-?\d+", s):
        return int(s)
    if re.fullmatch(r"-?\d+\.\d*", s):
        return float(s)
    return s


def parse_yaml(text: str) -> dict:
    """The YAML subset frontmatter uses: `key: scalar`, `key: [a, b]`, `key:` followed by
    `- item` lines, and one level of nested mapping (`applies_to:` with `roles:` etc.).
    Comments and blank lines are skipped. Anything else is a FormatError."""
    out: dict = {}
    stack: list[tuple[int, object]] = [(-1, out)]   # (indent, container)
    pending: list[tuple[int, dict, str]] = []        # a `key:` awaiting its block
    for n, raw in enumerate(text.splitlines(), 1):
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        line = raw.strip()
        if pending:
            p_indent, p_parent, p_key = pending.pop()
            if indent > p_indent:
                p_parent[p_key] = [] if line.startswith("- ") or line == "-" else {}
                stack.append((p_indent, p_parent[p_key]))   # children sit deeper than the key
            else:
                p_parent[p_key] = None
        while len(stack) > 1 and indent <= stack[-1][0]:
            stack.pop()
        container = stack[-1][1]
        if line.startswith("- ") or line == "-":
            if not isinstance(container, list):
                raise FormatError(f"line {n}: a list item where a key was expected")
            container.append(_scalar(line[2:]))
            continue
        m = re.fullmatch(r"([A-Za-z_][\w-]*):(?:\s+(.*))?", line)
        if not m or not isinstance(container, dict):
            raise FormatError(f"line {n}: can't read {line!r}")
        key, value = m.group(1), m.group(2)
        if key in container:
            raise FormatError(f"line {n}: {key} appears twice")
        if value is None or value.strip() == "":
            container[key] = None
            pending.append((indent, container, key))
        else:
            container[key] = _scalar(value)
    return out


def split_file(text: str) -> tuple[dict, str]:
    """(frontmatter, body) of a Markdown file that starts with a `---` block."""
    lines = text.split("\n")
    if not lines or lines[0].strip() != "---":
        raise FormatError("no frontmatter: the file must start with ---")
    try:
        end = next(i for i in range(1, len(lines)) if lines[i].strip() == "---")
    except StopIteration:
        raise FormatError("the frontmatter has no closing ---") from None
    return parse_yaml("\n".join(lines[1:end])), "\n".join(lines[end + 1:]).strip()


@dataclass
class Lesson:
    path: Path
    meta: dict
    body: str
    errors: list[str] = field(default_factory=list)

    @property
    def id(self) -> str:
        return str(self.meta.get("id") or self.path.name[:6])

    @property
    def status(self) -> str:
        return str(self.meta.get("status") or "")

    @property
    def scope(self) -> str:
        return str(self.meta.get("scope") or "")

    def applies(self, key: str) -> list[str]:
        a = self.meta.get("applies_to")
        v = a.get(key) if isinstance(a, dict) else None
        return [str(x) for x in v] if isinstance(v, list) else []


def load(path: Path) -> Lesson:
    try:
        meta, body = split_file(path.read_text())
    except (OSError, UnicodeDecodeError, FormatError) as e:
        return Lesson(path, {}, "", [f"{path.name}: {e}"])
    return Lesson(path, meta, body)


def load_all(lessons_dir: Path | None = None) -> list[Lesson]:
    lessons_dir = lessons_dir or LESSONS
    if not lessons_dir.is_dir():
        return []
    return [load(p) for p in sorted(lessons_dir.glob("*.md")) if p.name.lower() != "readme.md"]


# ---------------------------------------------------------------- episodes

def norm_login(login: str | None) -> str:
    """One spelling of a GitHub login: no `@`, `app/x` as `x[bot]`, lower case."""
    s = (login or "").strip().lstrip("@").lower()
    if s.startswith("app/"):
        s = s[4:] + "[bot]"
    return s


def load_episodes(dirs: list[Path] | None = None) -> dict[str, dict]:
    """Every episode by id, read by episodes.load() from `dirs` (default memory/episodes/;
    `swarm memory` adds the engine's outbox)."""
    import episodes
    return {e["id"]: e for e in episodes.load(dirs if dirs is not None else [EPISODES])
            if isinstance(e.get("id"), str)}


def author(e: dict, owner: str) -> str | None:
    """The login whose content the episode carries, or ENGINE for a run; None if unknown."""
    if e.get("by"):
        return str(e["by"])
    t = e.get("type")
    if t in OWNER_TYPES:
        return owner
    if t == "run":
        return ENGINE
    if t == "note" and isinstance(e.get("role"), str) and re.fullmatch(r"[a-z]+", e["role"]):
        return f"productswarm-{e['role']}[bot]"
    return None


def independence_key(e: dict) -> str:
    """Two sources are independent when their keys differ: a note's session, a run's session,
    another signal's source link. Two quotes of one comment share a link, so they count once
    (GOV-0055)."""
    t = e.get("type")
    if t in ("note", "run"):
        return f"{t}:" + str(e.get("session_id") or e["id"])
    return "link:" + str(e.get("source") or e["id"])


def engine_recorded(e: dict) -> bool:
    return e.get("type") in ENGINE_TYPES


# ---------------------------------------------------------------- validation

MAINTAINERS_RE = re.compile(r"^([ \t]+)maintainers:[ \t]*\n((?:\1[ \t]+\S.*\n?)+)", re.MULTILINE)


def trusted_logins(path: Path = ROOT / "governance" / "jurisdictions.yml") -> set[str]:
    """Whose content may feed a lesson (GOV-0055): the owner, identities.agents, and the
    repo's listed maintainers. jurisdictions.yml lists no maintainers today, so an
    `identities.maintainers` block is read only if the owner adds one."""
    import swarm
    out = {swarm.owner_login(path), *swarm.agent_logins(path)}
    m = MAINTAINERS_RE.search(path.read_text())
    if m:
        out |= set(re.findall(r'"@?([^"]+)"', m.group(2)))
    return {norm_login(x) for x in out}


def in_force_rulings(index: Path | None = None) -> dict[str, str]:
    """GOV-NNNN -> status, from governance/INDEX.md's rows."""
    out, index = {}, index or GOV_INDEX
    try:
        text = index.read_text()
    except OSError:
        return out
    for line in text.splitlines():
        m = GOV_ROW_RE.match(line.strip())
        if m:
            out[m.group(1)] = m.group(2)
    return out


def today() -> dt.date:
    return dt.date.today()


def _date(v) -> dt.date | None:
    if isinstance(v, dt.date):
        return v
    try:
        return dt.date.fromisoformat(str(v))
    except (TypeError, ValueError):
        return None


def path_exists(pattern: str, root: Path = ROOT) -> bool:
    if not pattern or pattern.startswith("/") or ".." in Path(pattern).parts:
        return False
    try:
        return any(True for _ in root.glob(pattern))
    except (ValueError, NotImplementedError):
        return False


def power_sentences(text: str) -> list[str]:
    """Sentences that ask to change permissions, credentials, tools or governance."""
    return [m.group(0).strip() for m in POWER_RE.finditer(text)]


@dataclass
class Context:
    """What validation reads beyond the lesson: trusted authors (the owner, identities.agents
    and listed maintainers, normalised), episodes by id, rulings by status, this repo's slug,
    the repo root for paths, and today."""
    trusted: set[str]
    episodes: dict[str, dict]
    rulings: dict[str, str]
    repo: str
    root: Path | None = None    # None: ROOT
    today: dt.date | None = None  # None: today()
    owner: str | None = None    # None: humans.owner in jurisdictions.yml

    def __post_init__(self):
        self.root = self.root or ROOT
        self.today = self.today or today()
        if self.owner is None:
            import swarm
            self.owner = swarm.owner_login()


def validate(lesson: Lesson, ctx: Context) -> list[str]:
    """Every reason this lesson isn't valid; [] if it is."""
    if lesson.errors:
        return list(lesson.errors)
    m, name, errs = lesson.meta, lesson.path.name, []

    def err(s: str):
        errs.append(f"{name}: {s}")

    for k in REQUIRED:
        if k not in m:
            err(f"missing {k}")
    fm = FILE_RE.match(name)
    if not fm:
        err("file name must be L-NNNN-<slug>.md (lower-case slug)")
    lid = m.get("id")
    if not (isinstance(lid, str) and ID_RE.match(lid)):
        err(f"id {lid!r} isn't L-NNNN")
    elif fm and fm.group(1) != lid:
        err(f"id {lid} doesn't match the file name")
    if not (isinstance(m.get("title"), str) and m["title"].strip()):
        err("title must be the lesson as one sentence")
    status = m.get("status")
    if status not in STATUSES:
        err(f"status {status!r} isn't one of {', '.join(STATUSES)}")
    scope = m.get("scope")
    if not (isinstance(scope, str) and SCOPE_RE.match(scope)):
        err(f"scope {scope!r} isn't fleet or repo:<owner/name>")

    a = m.get("applies_to")
    if "applies_to" in m:
        if not isinstance(a, dict) or set(a) - {"roles", "paths", "situations"}:
            err("applies_to must hold only roles, paths and situations")
        else:
            for k in ("roles", "paths", "situations"):
                if a.get(k) is not None and not isinstance(a.get(k), list):
                    err(f"applies_to.{k} must be a list")
            # Paths are checked here only for lessons that apply to this repo.
            here = scope == "fleet" or (isinstance(scope, str)
                                        and scope.lower() == f"repo:{ctx.repo}".lower())
            for p in a.get("paths") or [] if isinstance(a.get("paths"), list) else []:
                if here and not path_exists(str(p), ctx.root):
                    err(f"path {p} matches nothing in this repo")

    conf = m.get("confidence")
    if isinstance(conf, bool) or not isinstance(conf, (int, float)) or not 0 <= conf <= 1:
        err(f"confidence {conf!r} must be a number from 0 to 1")
    uses = m.get("uses")
    if isinstance(uses, bool) or not isinstance(uses, int) or uses < 0:
        err(f"uses {uses!r} must be a whole number, 0 or more")
    if m.get("last_used") is not None and _date(m.get("last_used")) is None:
        err(f"last_used {m.get('last_used')!r} must be a date or empty")
    created, review_by = _date(m.get("created")), _date(m.get("review_by"))
    if created is None:
        err(f"created {m.get('created')!r} must be a date")
    if review_by is None:
        err(f"review_by {m.get('review_by')!r} must be a date")
    elif created and review_by < created:
        err("review_by is before created")

    eval_case = m.get("eval_case")
    if status == "active" and not (isinstance(eval_case, str) and eval_case.strip()):
        err("an active lesson needs an eval_case")
    for k, pat in (("supersedes", ID_RE), ("related_rulings", GOV_RE)):
        v = m.get(k)
        if v is not None and not isinstance(v, list):
            err(f"{k} must be a list")
            continue
        for x in v or []:
            if not pat.match(str(x)):
                err(f"{k} names {x!r}; " + ("a lesson supersedes only lessons (L-NNNN)"
                                            if k == "supersedes" else "rulings are GOV-NNNN"))
    for g in m.get("related_rulings") or [] if isinstance(m.get("related_rulings"), list) else []:
        st = ctx.rulings.get(str(g))
        if st is None:
            err(f"names {g}, which isn't in governance/INDEX.md")
        elif st != "in-force":
            err(f"names {g}, which is {st}, not in force")

    errs += [f"{name}: {e}" for e in source_errors(m, ctx)]

    body = lesson.body
    if not body:
        err("the body is empty: say the lesson, why, and an example")
    else:
        for h in ("Why", "Example"):
            if not re.search(rf"^##\s+{h}\b", body, re.M | re.I):
                err(f"the body has no `## {h}` section")
    text = f"{m.get('title') or ''}\n{body}"
    for s in power_sentences(text):
        err(f"asks to change permissions, credentials, tools or governance (GOV-0055): {s!r}")
    for c in CONTRA_RE.finditer(text):
        err(f"sets aside a ruling; a lesson is guidance under the rulings: {c.group(0)!r}")
    return errs


def source_errors(m: dict, ctx: Context) -> list[str]:
    """GOV-0055 (option 1 of #1151) on a lesson's sources."""
    sources = m.get("sources")
    if not isinstance(sources, list) or not all(isinstance(s, str) and s for s in sources):
        return ["sources must be a list of episode ids"]
    if len(set(sources)) < 2:
        return [f"needs at least two sources; has {len(set(sources))} (GOV-0055)"]
    found = [ctx.episodes[s] for s in dict.fromkeys(sources) if s in ctx.episodes]
    missing = [s for s in dict.fromkeys(sources) if s not in ctx.episodes]
    errs = []
    # Every source must resolve, whatever the lesson's age: GOV-0055 makes no exception (#1206).
    if missing:
        errs.append(f"source {', '.join(missing)} isn't an episode")
    trusted = {norm_login(t) for t in ctx.trusted} | {ENGINE}
    for e in found:
        who = author(e, ctx.owner)
        if norm_login(who) not in trusted:
            errs.append(f"source {e['id']} is by {who or 'an unknown author'}, not the "
                        f"owner, a swarm App or a listed maintainer (GOV-0055)")
    if len({independence_key(e) for e in found}) < 2:
        errs.append("needs two independent sources: different sessions or signals (GOV-0055)")
    if not any(engine_recorded(e) for e in found):
        errs.append("needs an engine-recorded signal among its sources (an owner act, a review "
                    "outcome, a revert, a failed run), not only session notes (GOV-0055)")
    return errs


def validate_all(lessons: list[Lesson], ctx: Context) -> list[str]:
    errs: list[str] = []
    seen: dict[str, str] = {}
    for les in lessons:
        errs += validate(les, ctx)
        if les.id in seen:
            errs.append(f"{les.path.name}: id {les.id} is also {seen[les.id]}")
        seen.setdefault(les.id, les.path.name)
    ids = set(seen)
    for les in lessons:
        for s in les.meta.get("supersedes") or [] if isinstance(les.meta.get("supersedes"), list) else []:
            if str(s) not in ids:
                errs.append(f"{les.path.name}: supersedes {s}, which isn't a lesson")
    return errs


# ---------------------------------------------------------------- listing

def glob_match(pattern: str, path: str) -> bool:
    """Whether `path` matches the glob: `**` crosses directories, `*` and `?` don't, and
    `dir/**` also matches `dir` itself."""
    rx, i = "", 0
    while i < len(pattern):
        if pattern.startswith("**/", i):
            rx, i = rx + "(?:.*/)?", i + 3
        elif pattern.startswith("**", i):
            rx, i = rx + ".*", i + 2
        else:
            c = pattern[i]
            rx += "[^/]*" if c == "*" else "[^/]" if c == "?" else re.escape(c)
            i += 1
    path = path.removeprefix("./").rstrip("/")
    return bool(re.fullmatch(rx, path)) or (pattern.endswith("/**") and path == pattern[:-3])


def visible_in(lesson: Lesson, repo: str) -> bool:
    """A fleet lesson shows in every repo; a repo:<x> lesson only in x (FEAT-15)."""
    if lesson.scope == "fleet":
        return True
    return lesson.scope.lower() == f"repo:{repo}".lower()


def select(lessons: list[Lesson], repo: str, role: str | None = None, path: str | None = None,
           status: str | None = None) -> list[Lesson]:
    out = []
    for les in lessons:
        if les.errors or not visible_in(les, repo):
            continue
        if status and les.status != status:
            continue
        roles = les.applies("roles")
        if role and roles and role not in roles:
            continue
        paths = les.applies("paths")
        if path and paths and not any(glob_match(p, path) for p in paths):
            continue
        out.append(les)
    return out


def summary(les: Lesson) -> dict:
    m = les.meta
    return {"id": les.id, "title": m.get("title"), "status": les.status, "scope": les.scope,
            "roles": les.applies("roles"), "paths": les.applies("paths"),
            "situations": les.applies("situations"), "confidence": m.get("confidence"),
            "uses": m.get("uses"), "last_used": _iso(m.get("last_used")),
            "review_by": _iso(m.get("review_by")), "eval_case": m.get("eval_case") or None,
            "file": f"memory/lessons/{les.path.name}"}


def _iso(v) -> str | None:
    d = _date(v)
    return d.isoformat() if d else (str(v) if v else None)


def list_text(lessons: list[Lesson]) -> str:
    if not lessons:
        return "No lessons match."
    rows = []
    for les in lessons:
        roles = ",".join(les.applies("roles")) or "all roles"
        rows.append(f"{les.id}  {les.status:<8}  {les.scope:<24}  {roles:<16}  {les.meta.get('title')}")
    return "\n".join(rows)


def resolve_sources(les: Lesson, episodes: dict[str, dict], owner: str) -> list[dict]:
    out = []
    for s in les.meta.get("sources") or [] if isinstance(les.meta.get("sources"), list) else []:
        e = episodes.get(str(s))
        if e is None:
            out.append({"id": str(s), "found": False})
        else:
            out.append({"id": str(s), "found": True, "type": e.get("type"),
                        "engine_recorded": engine_recorded(e), "author": author(e, owner),
                        "session_id": e.get("session_id"), "source": e.get("source"),
                        "at": e.get("at")})
    return out


def eval_result(les: Lesson) -> dict:
    """The lesson's eval case. Replays (#1189) don't record results yet, so there is none."""
    case = les.meta.get("eval_case") or None
    return {"case": case, "result": None,
            "note": "no eval case yet" if not case else "not run yet: replays come with #1189"}


def show_text(les: Lesson, sources: list[dict], ev: dict, errors: list[str]) -> str:
    out = [les.path.read_text().rstrip(), "", "Sources:"]
    for s in sources:
        if not s["found"]:
            out.append(f"  {s['id']}: missing (not in memory/episodes/ or the engine's outbox)")
        else:
            kind = "engine signal" if s["engine_recorded"] else "session note"
            where = s.get("source") or (f"session {s['session_id']}" if s.get("session_id") else "")
            out.append(f"  {s['id']}: {s.get('type')} ({kind}) by {s.get('author')}, "
                       f"{s.get('at') or 'undated'}{', ' + where if where else ''}")
    out += ["", f"Eval: {ev['case'] or '-'}: {ev['note']}"]
    if errors:
        out += ["", "Invalid:"] + [f"  {e}" for e in errors]
    return "\n".join(out)


# ---------------------------------------------------------------- INDEX.md

INDEX_HEAD = """# Lessons index

Generated by `launcher/swarm memory index` from `memory/lessons/`; don't edit it by hand. One row per active or dormant lesson. Lessons are cited as `per L-NNNN`; the format is in `launcher/README.md` (#1185).

| ID | Lesson | Scope | Roles | Status | Confidence | Review by |
|----|--------|-------|-------|--------|------------|-----------|
"""


def _cell(s) -> str:
    return str(s if s is not None else "").replace("|", "\\|").replace("\n", " ")


def index_text(lessons: list[Lesson]) -> str:
    rows = []
    for les in sorted(lessons, key=lambda x: x.id):
        if les.errors or les.status not in ("active", "dormant"):
            continue
        m = les.meta
        rows.append(f"| [{les.id}](lessons/{les.path.name}) | {_cell(m.get('title'))} | "
                    f"{_cell(les.scope)} | {_cell(', '.join(les.applies('roles')) or 'all')} | "
                    f"{les.status} | {_cell(m.get('confidence'))} | {_cell(_iso(m.get('review_by')))} |")
    return INDEX_HEAD + "".join(r + "\n" for r in rows)
