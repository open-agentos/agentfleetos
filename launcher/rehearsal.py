"""Rehearsal: the replay gate for lessons (#1189, FEAT-19).

A proposed lesson goes active only after its eval case is replayed twice, once without the
lesson and once with it, and the gate passes:

  - the run with it passes the case's check and the run without it doesn't; or
  - both pass and the run with it cost no more than the run without it.

Otherwise the lesson stays proposed, with the result in its frontmatter, and the dream may
retire it. Changing an active lesson (its title, body or case) makes it due again; if the
rerun fails the gate it goes back to proposed. One replay each way is a sanity check, not a
benchmark.

**Eval cases** live in `evals/lessons/<L-NNNN>.toml` (format in evals/lessons/README.md): a
past task from the lesson's source episodes (the issue and the repo at that commit), the
behaviour the lesson should change, and a declarative check on the replay's reply and diff.
The librarian drafts them. A check never runs code from the case.

**Caps (GOV-0053)**, from swarm.toml's `[memory]`: each replay runs on `replay_model` (a
Haiku-tier model) with `--max-budget-usd replay_cap_usd` ($0.50), and at most
`replays_per_night` (10) replays run in a UTC day; a lesson needs two, so the rest wait for
the next night. Each replay's cost goes into the lesson's frontmatter and a ledger,
`<PRODUCTSWARM_HOME>/memory/replays.jsonl`, which the nightly count is read from.

**Credential (GOV-0053).** Replays run on the engine's Console key: `claude --bare` reads only
ANTHROPIC_API_KEY (never the owner's login or keychain), and rehearse refuses to start
without it.

**A replay never pushes, comments or labels.** It runs in a throwaway local clone with its
remote removed, under `claude -p --bare --restricted` with only the file tools (no shell, so
no git or gh; no hooks, MCP servers, settings files or CLAUDE.md), with GitHub and git
credentials taken out of its environment. The clone is deleted after the run. Lesson and case
text are data: they reach the model only as the replayed task and the lesson under test.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import lessons as L

ROOT = L.ROOT
CASES = ROOT / "evals" / "lessons"
LEDGER = Path("memory") / "replays.jsonl"     # under the launcher's home

DEFAULTS = {"replay_model": "claude-haiku-5-5", "replay_cap_usd": 0.5, "replays_per_night": 10}
TOOLS = "Read,Edit,Write,Glob,Grep"           # file tools only: no Bash, no web
# Taken out of a replay's environment, with any GH_* and GITHUB_* variable: nothing in the
# replay may reach GitHub or the owner's login.
STRIPPED_ENV = ("CLAUDE_CODE_OAUTH_TOKEN", "GIT_ASKPASS", "SSH_ASKPASS", "SSH_AUTH_SOCK",
                "GIT_SSH", "GIT_SSH_COMMAND", "GIT_CONFIG_GLOBAL")
CHECK_KEYS = ("reply_matches", "reply_lacks", "diff_matches", "diff_lacks", "changed", "unchanged")
SHA_RE = re.compile(r"^[0-9a-f]{40}$")

PROMOTED, CONFIRMED, KEPT, DEMOTED, INCONCLUSIVE = (
    "promoted", "confirmed", "kept", "demoted", "inconclusive")
PASSING = (PROMOTED, CONFIRMED)

SYSTEM = """You are replaying a past task in a throwaway copy of a repository, as one of the \
AgentFleetOS agent team would have done it. Work only in the current directory with the file \
tools you have. Nothing you do leaves this copy. Do the task, then end with a short summary of \
what you changed."""

PACK_HEAD = """Lessons the team has learned. They are guidance under the governance rulings; \
where a ruling disagrees, the ruling wins (GOV-0058)."""


class RehearsalError(RuntimeError):
    pass


# ---------------------------------------------------------------- settings

def settings(manifest_path: Path | None = None) -> dict:
    """swarm.toml's [memory] replay settings, defaults filled in. Raises RehearsalError on a
    bad value: a cap or a count is a `spend` setting, so a typo shouldn't run unbounded."""
    path = manifest_path or ROOT / "swarm.toml"
    try:
        table = tomllib.loads(path.read_text()).get("memory") or {}
    except (OSError, tomllib.TOMLDecodeError) as e:
        raise RehearsalError(f"can't read {path.name}: {e}") from None
    if not isinstance(table, dict):
        raise RehearsalError("swarm.toml: [memory] must be a table")
    out = {**DEFAULTS, **{k: table[k] for k in DEFAULTS if k in table}}
    if not (isinstance(out["replay_model"], str) and out["replay_model"].strip()):
        raise RehearsalError("[memory] replay_model must be a model id")
    cap = out["replay_cap_usd"]
    if isinstance(cap, bool) or not isinstance(cap, (int, float)) or not 0 < cap <= 5:
        raise RehearsalError(f"[memory] replay_cap_usd must be more than 0 and at most 5, got {cap!r}")
    n = out["replays_per_night"]
    if isinstance(n, bool) or not isinstance(n, int) or n < 0:
        raise RehearsalError(f"[memory] replays_per_night must be a whole number, got {n!r}")
    return out


# ---------------------------------------------------------------- eval cases

@dataclass
class Case:
    path: Path
    lesson: str
    repo: str
    commit: str
    task: str
    behaviour: str
    check: dict
    issue: int | None = None
    episodes: list[str] = field(default_factory=list)


def case_path(les: L.Lesson, root: Path | None = None) -> Path | None:
    """The lesson's eval_case as a path in the repo, or None if it names none."""
    root = root or ROOT
    ec = les.meta.get("eval_case")
    if not (isinstance(ec, str) and ec.strip()):
        return None
    p = Path(ec.strip())
    if p.is_absolute() or ".." in p.parts:
        raise RehearsalError(f"{les.id}: eval_case {ec!r} must be a path in the repo")
    return root / p


def load_case(path: Path) -> Case:
    try:
        d = tomllib.loads(path.read_text())
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as e:
        raise RehearsalError(f"{path.name}: {e}") from None
    errs = []
    for k in ("lesson", "repo", "commit", "task", "behaviour"):
        if not (isinstance(d.get(k), str) and d[k].strip()):
            errs.append(f"{k} must be a non-empty string")
    if isinstance(d.get("lesson"), str) and not L.ID_RE.match(d["lesson"]):
        errs.append(f"lesson {d['lesson']!r} isn't L-NNNN")
    if isinstance(d.get("commit"), str) and not SHA_RE.match(d["commit"]):
        errs.append("commit must be a full commit sha (40 hex characters)")
    if isinstance(d.get("repo"), str) and not re.fullmatch(r"[A-Za-z0-9-]+/[A-Za-z0-9._-]+", d["repo"]):
        errs.append("repo must be owner/name")
    issue = d.get("issue")
    if issue is not None and (isinstance(issue, bool) or not isinstance(issue, int)):
        errs.append("issue must be an issue number")
    eps = d.get("episodes", [])
    if not (isinstance(eps, list) and all(isinstance(e, str) for e in eps)):
        errs.append("episodes must be a list of episode ids")
    check = d.get("check")
    if not isinstance(check, dict) or not check:
        errs.append("[check] must hold at least one of " + ", ".join(CHECK_KEYS))
    else:
        for k in sorted(set(check) - set(CHECK_KEYS)):
            errs.append(f"check.{k} isn't one of {', '.join(CHECK_KEYS)}")
        for k in CHECK_KEYS:
            v = check.get(k)
            if v is None:
                continue
            if not (isinstance(v, list) and v and all(isinstance(x, str) and x for x in v)):
                errs.append(f"check.{k} must be a non-empty list of strings")
            elif k.startswith(("reply", "diff")):
                for x in v:
                    try:
                        re.compile(x)
                    except re.error as e:
                        errs.append(f"check.{k}: {x!r} isn't a regular expression: {e}")
    for k in sorted(set(d) - {"lesson", "repo", "commit", "task", "behaviour", "issue",
                              "episodes", "check"}):
        errs.append(f"unknown key {k}")
    if errs:
        raise RehearsalError(f"{path.name}: " + "; ".join(errs))
    return Case(path, d["lesson"], d["repo"], d["commit"], d["task"], d["behaviour"], check,
                issue, list(eps))


@dataclass
class Outcome:
    """What one replay left: its final reply, the diff of the throwaway clone, the paths it
    changed, its cost and how it ended (done, at cap, error)."""
    reply: str
    diff: str
    changed: list[str]
    cost: float
    ending: str


def run_check(check: dict, o: Outcome) -> tuple[bool, list[str]]:
    """(passed, the reasons it didn't). Patterns are multi-line regular expressions; globs use
    lessons.glob_match."""
    why = []
    for k, text in (("reply", o.reply), ("diff", o.diff)):
        for p in check.get(f"{k}_matches") or []:
            if not re.search(p, text, re.M):
                why.append(f"{k} doesn't match {p!r}")
        for p in check.get(f"{k}_lacks") or []:
            if re.search(p, text, re.M):
                why.append(f"{k} matches {p!r}")
    for g in check.get("changed") or []:
        if not any(L.glob_match(g, c) for c in o.changed):
            why.append(f"changed nothing matching {g}")
    for g in check.get("unchanged") or []:
        hit = [c for c in o.changed if L.glob_match(g, c)]
        if hit:
            why.append(f"changed {', '.join(hit)} ({g} must stay unchanged)")
    return not why, why


# ---------------------------------------------------------------- one replay

def pack_text(les: L.Lesson) -> str:
    """The lesson under test, as a context pack (FEAT-17) would carry it."""
    return f"{PACK_HEAD}\n\n{les.id}: {les.meta.get('title')}\n\n{les.body}"


def replay_command(model: str, cap: float, lesson: L.Lesson | None) -> list[str]:
    """The `claude -p` argv for one replay. --bare: no hooks, CLAUDE.md, plugins or OAuth
    (ANTHROPIC_API_KEY only); --restricted: no shell or web, settings files ignored, file
    tools confined to the clone; --tools names only the file tools."""
    argv = ["claude", "-p", "--bare", "--restricted", "--model", model,
            "--tools", TOOLS, "--permission-mode", "acceptEdits",
            "--strict-mcp-config", "--no-session-persistence",
            "--system-prompt", SYSTEM, "--max-budget-usd", f"{cap:g}",
            "--output-format", "json"]
    if lesson is not None:
        argv += ["--append-system-prompt", pack_text(lesson)]
    return argv


def replay_env(base: dict | None = None, home: Path | None = None) -> dict:
    """The environment for a replay: ANTHROPIC_API_KEY kept, every GitHub and git credential
    out, git never prompting, gh pointed at an empty config."""
    env = {k: v for k, v in (os.environ if base is None else base).items()
           if not k.startswith(("GH_", "GITHUB_")) and k not in STRIPPED_ENV}
    env["GIT_TERMINAL_PROMPT"] = "0"
    if home is not None:
        env["GH_CONFIG_DIR"] = str(home / "gh")      # empty: gh has no login
    return env


def git(args: list[str], cwd: Path | None = None) -> str:
    r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RehearsalError(f"git {args[0]} failed: {(r.stderr or r.stdout).strip()[:300]}")
    return r.stdout


def checkout(source: Path, commit: str, dest: Path) -> None:
    """A throwaway repo at `commit`, fetched from the local clone `source` by sha: it never
    has a remote, so there is nothing to push to."""
    git(["init", "--quiet", str(dest)])
    git(["fetch", "--quiet", "--depth=1", "--no-tags", str(source), commit], dest)
    git(["-c", "advice.detachedHead=false", "checkout", "--quiet", "--detach", "FETCH_HEAD"], dest)
    if git(["remote"], dest).strip():
        raise RehearsalError("the throwaway repo has a remote")


def collect(clone: Path) -> tuple[str, list[str]]:
    git(["add", "-A"], clone)
    changed = [x for x in git(["diff", "--cached", "--name-only"], clone).splitlines() if x]
    return git(["diff", "--cached"], clone), changed


Runner = Callable[[list[str], Path, dict, str], dict]


def claude_runner(argv: list[str], cwd: Path, env: dict, stdin: str) -> dict:
    """Run `claude -p` and return its JSON result ({} if there is none)."""
    try:
        r = subprocess.run(argv, input=stdin, cwd=cwd, env=env, capture_output=True,
                           text=True, timeout=900)
    except (OSError, subprocess.TimeoutExpired) as e:
        return {"subtype": "error", "is_error": True, "result": f"claude didn't run: {e}"}
    try:
        out = json.loads(r.stdout)
    except json.JSONDecodeError:
        return {"subtype": "error", "is_error": True,
                "result": f"claude exited {r.returncode} without a JSON result"}
    return out if isinstance(out, dict) else {"subtype": "error", "is_error": True}


def ending(result: dict) -> str:
    st = result.get("subtype")
    if st == "error_max_budget_usd":
        return "at cap"
    if st == "success" and not result.get("is_error"):
        return "done"
    return "error"


def replay(case: Case, source: Path, model: str, cap: float, lesson: L.Lesson | None,
           runner: Runner = claude_runner, env: dict | None = None) -> Outcome:
    """Replay the case once, with the lesson or without it (lesson=None)."""
    with tempfile.TemporaryDirectory(prefix="rehearse-") as tmp:
        clone = Path(tmp) / "repo"
        checkout(source, case.commit, clone)
        result = runner(replay_command(model, cap, lesson), clone,
                        replay_env(env, Path(tmp)), case.task)
        diff, changed = collect(clone)
    return Outcome(str(result.get("result") or ""), diff, changed,
                   float(result.get("total_cost_usd") or 0), ending(result))


# ---------------------------------------------------------------- the gate

def lesson_hash(les: L.Lesson, case_file: Path) -> str:
    """What a rehearsal result is good for: the lesson's title and body and its case. Any
    change to them makes the lesson due again."""
    h = hashlib.sha256()
    for part in (str(les.meta.get("title") or ""), les.body, case_file.read_text()):
        h.update(part.encode() + b"\0")
    return h.hexdigest()[:12]


def decide(status: str, without: tuple[bool, Outcome], with_: tuple[bool, Outcome]) -> tuple[str, str]:
    """(result, the lesson's new status)."""
    (p0, o0), (p1, o1) = without, with_
    if o0.ending != "done" or o1.ending != "done":
        return INCONCLUSIVE, status
    ok = p1 and (not p0 or o1.cost <= o0.cost)
    if status == "active":
        return (CONFIRMED, "active") if ok else (DEMOTED, "proposed")
    return (PROMOTED, "active") if ok else (KEPT, "proposed")


def rehearsal_of(les: L.Lesson) -> dict:
    r = les.meta.get("rehearsal")
    return r if isinstance(r, dict) else {}


def due(lessons: list[L.Lesson], repo: str, root: Path | None = None) -> list[L.Lesson]:
    """Lessons for this repo to rehearse, in id order: proposed or active, with an eval case,
    not yet rehearsed at their current hash, or last inconclusive."""
    out = []
    for les in sorted(lessons, key=lambda x: x.id):
        if les.errors or les.status not in ("proposed", "active") or not L.visible_in(les, repo):
            continue
        try:
            cp = case_path(les, root)
        except RehearsalError:
            continue
        if cp is None or not cp.is_file():
            continue
        r = rehearsal_of(les)
        if r.get("hash") != lesson_hash(les, cp) or r.get("result") == INCONCLUSIVE:
            out.append(les)
    return out


# ---------------------------------------------------------------- the ledger

def ledger_path(home: Path) -> Path:
    return home / LEDGER


def replays_on(home: Path, day: dt.date) -> int:
    """Replays recorded in the ledger on this UTC day."""
    try:
        lines = ledger_path(home).read_text().splitlines()
    except OSError:
        return 0
    n = 0
    for line in lines:
        try:
            if str(json.loads(line).get("at", ""))[:10] == day.isoformat():
                n += 1
        except (json.JSONDecodeError, AttributeError):
            continue
    return n


def record(home: Path, row: dict) -> None:
    p = ledger_path(home)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")


# ---------------------------------------------------------------- writing the result

def write_result(les: L.Lesson, status: str, block: dict) -> None:
    """Set the lesson's status and replace its `rehearsal:` block, leaving every other line of
    the file as it was."""
    lines = les.path.read_text().split("\n")
    end = next(i for i in range(1, len(lines)) if lines[i].strip() == "---")
    head, rest = lines[1:end], lines[end:]
    out, skipping = [], False
    for line in head:
        if skipping and (line.startswith((" ", "\t")) or not line.strip()):
            continue
        skipping = False
        if re.match(r"^status:", line):
            out.append(f"status: {status}")
        elif re.match(r"^rehearsal:", line):
            skipping = True
        else:
            out.append(line)
    out.append("rehearsal:")
    for k, v in block.items():
        out.append(f"  {k}: {_yaml(v)}")
    les.path.write_text("\n".join([lines[0], *out, *rest]))


def _yaml(v) -> str:
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return f"{v:g}" if isinstance(v, float) else str(v)
    s = str(v).replace("\n", " ")
    plain = not re.search(r"[:#\[\],'\"]|^\s|\s$|^$", s) and s not in ("null", "~") \
        and not re.fullmatch(r"-?\d+(?:\.\d*)?", s)
    return s if plain else json.dumps(s)


# ---------------------------------------------------------------- rehearse

@dataclass
class Result:
    lesson: str
    result: str               # promoted, confirmed, kept, demoted, inconclusive, waits, error
    status: str | None = None
    note: str = ""
    without: dict | None = None
    with_: dict | None = None


def rehearse(les: L.Lesson, *, home: Path, cfg: dict, source_for: Callable[[str], Path],
             runner: Runner = claude_runner, env: dict | None = None,
             now: Callable[[], dt.datetime] | None = None, root: Path | None = None,
             write: bool = True) -> Result:
    """Replay one lesson's case without it and with it, apply the gate, record both replays'
    cost in the ledger and the result in the lesson's frontmatter."""
    now = now or (lambda: dt.datetime.now(dt.timezone.utc))
    root = root or ROOT
    left = cfg["replays_per_night"] - replays_on(home, now().date())
    if left < 2:
        return Result(les.id, "waits", note=f"{cfg['replays_per_night']} replays a night "
                      f"(swarm.toml [memory] replays_per_night) are used; it waits for the next night")
    try:
        cp = case_path(les, root)
        if cp is None:
            raise RehearsalError(f"{les.id} has no eval_case")
        case = load_case(cp)
        if case.lesson != les.id:
            raise RehearsalError(f"{cp.name} is the case for {case.lesson}, not {les.id}")
        source = source_for(case.repo)
    except RehearsalError as e:
        return Result(les.id, "error", note=str(e))

    arms = {}
    for arm, lesson in (("without", None), ("with", les)):
        try:
            o = replay(case, source, cfg["replay_model"], cfg["replay_cap_usd"], lesson, runner, env)
        except RehearsalError as e:
            return Result(les.id, "error", note=f"replay {arm} the lesson: {e}")
        passed, why = run_check(case.check, o)
        record(home, {"at": now().isoformat(timespec="seconds"), "lesson": les.id,
                      "case": cp.relative_to(root).as_posix(), "arm": arm,
                      "model": cfg["replay_model"], "cost_usd": round(o.cost, 4),
                      "ending": o.ending, "passed": passed})
        arms[arm] = (passed, o, why)
        if o.ending != "done":
            break    # inconclusive whatever the other replay does: don't pay for it

    skipped = (False, Outcome("", "", [], 0.0, "skipped"), ["not run"])
    p0, o0, why0 = arms["without"]
    p1, o1, why1 = arms.get("with", skipped)
    result, status = decide(les.status, (p0, o0), (p1, o1))
    block = {"at": now().date().isoformat(), "result": result,
             "hash": lesson_hash(les, cp), "model": cfg["replay_model"],
             "without": _arm(p0, o0), "with": _arm(p1, o1),
             "cost_without_usd": round(o0.cost, 4), "cost_with_usd": round(o1.cost, 4)}
    if write:
        write_result(les, status, block)
    note = "; ".join(why1) if result in (KEPT, DEMOTED) and why1 else ""
    if result == INCONCLUSIVE:
        note = "a replay didn't finish (" + ", ".join(
            f"{a}: {o.ending}" for a, (_, o, _) in arms.items() if o.ending != "done") + ")"
    return Result(les.id, result, status, note,
                  {"passed": p0, "ending": o0.ending, "cost_usd": round(o0.cost, 4), "why": why0},
                  {"passed": p1, "ending": o1.ending, "cost_usd": round(o1.cost, 4), "why": why1})


def _arm(passed: bool, o: Outcome) -> str:
    return o.ending if o.ending != "done" else ("pass" if passed else "fail")


# ---------------------------------------------------------------- the dream report

def report_text(results: list[Result], day: dt.date) -> str:
    """The rehearsal section of the dream report: one line per lesson."""
    head = f"## Rehearsals, {day.isoformat()}\n\n"
    if not results:
        return head + "No lessons were due.\n"
    lines = []
    for r in results:
        if r.result in ("waits", "error"):
            lines.append(f"- {r.lesson}: {r.result}: {r.note}")
            continue
        w0, w1 = r.without, r.with_
        lines.append(f"- {r.lesson}: {r.result} (now {r.status}). Without it: "
                     f"{_said(w0)}, ${w0['cost_usd']:.2f}; with it: {_said(w1)}, "
                     f"${w1['cost_usd']:.2f}." + (f" {r.note}." if r.note else ""))
    return head + "\n".join(lines) + "\n"


def _said(arm: dict) -> str:
    return arm["ending"] if arm["ending"] != "done" else ("pass" if arm["passed"] else "fail")
