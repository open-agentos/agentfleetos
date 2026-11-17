"""Episodes (#1184, FEAT-14): what each session tried, what surprised it and what blocked it,
and the signals the engine sees, kept as raw experience for the learning loop.

**Store (GOV-0052).** One JSONL file per UTC day, `YYYY-MM-DD.jsonl`, one episode per line,
schema 1. GOV-0052 puts them in `memory/episodes/` in this repo. How the engine commits them is
#1199, not ruled yet: until it is, the engine writes them to an outbox on its own host,
`~/.productswarm/memory/episodes/`, the default #1199 states, and nothing is committed or
pushed. `swarm memory episodes` reads the outbox and `memory/episodes/` together. Episodes are
appended, never edited; one with an id already in its day's file isn't written again. The
dream (FEAT-15, not this) deletes files after 30 days.

**Nothing secret, no prompt text (GOV-0002, GOV-0004, GOV-0055).** Every string in an episode
goes through scrub() before it is written: tokens and keys, `NAME=value` secrets, the values of
this process's environment, email addresses and paths under home directories. A session's
note is also checked against the session's prompt, and a field that quotes it is cut
(cut_prompt). No episode carries prompt text or a transcript excerpt. Episode text is data:
nothing reads it as instructions (R-LL5).

Episode types, each with `schema`, `id`, `type`, `at` (UTC) and `source` (a link, or None):

    note             a session's note, written by the stop hook (stophook.py) as the session
                     ends: session_id, role, model, repo, issue, pr, paths (the files its PR
                     touched) and note {tried, surprised, blocked}, or note None with
                     no_note true when the session ended without one
    act              an owner act from `swarm acts` (acts.py), with its tag: approval,
                     correction, repeat answer or genuine call (acts.rule_tag)
    retag            the owner retagged an act with a comment; the retag wins
    review           a changes-requested review and what it asked for (an excerpt)
    revert           a merged PR that reverts another
    closed-unmerged  a PR closed without merging
    run              a run that failed or hit its cap (the runs ledger, ledger.py)
    answer           the owner's answer on a gov:question, with took_default: whether it
                     chose the question's recommendation (None when it can't tell)

The engine records the signals with no model call: `swarm watch` sweeps once an hour
(sweep()), and `swarm memory record` sweeps by hand.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import urllib.parse
from pathlib import Path
from typing import Callable, Iterable

SCHEMA = 1
TYPES = ("note", "act", "retag", "review", "revert", "closed-unmerged", "run", "answer")
NOTE_FIELDS = ("tried", "surprised", "blocked")
NOTE_FILE = ".session-note.json"     # in the session's worktree; .gitignore'd
FIELD_MAX = 400                      # characters kept of a note field
EXCERPT_MAX = 300                    # characters kept of what a review asked for
QUOTE_WORDS = 8                      # this many words in a row from the prompt is a quote
CUT = "[cut: quotes the session's prompt]"
FAILED_ENDINGS = {"error": "failed", "ended at cap": "at cap"}   # watch.ERROR, watch.AT_CAP
REVERT_RE = re.compile(r'^Revert "')


def outbox(home: Path) -> Path:
    """Where the engine writes episodes until #1199 rules how they're committed."""
    return home / "memory" / "episodes"


def in_repo(root: Path) -> Path:
    return root / "memory" / "episodes"


# ---------------------------------------------------------------- scrubbing

REDACTED = "[redacted]"
_SECRETS = [
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?(?:-----END [A-Z ]*PRIVATE KEY-----|$)", re.S),
    re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{16,}"),                  # Anthropic and OpenAI keys
    re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}"),           # Slack
    re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),            # AWS access key ids
    re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b"),                # Google API keys
    re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{4,}"),   # JWTs
    re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{12,}"),
    re.compile(r"(?i)\b(?:https?://)[^\s/:@]+:[^\s/@]+@"),   # credentials in a URL
]
_ASSIGN = re.compile(r"(?i)\b([A-Z0-9_]*(?:TOKEN|SECRET|PASSWORD|PASSWD|API_?KEY|PRIVATE_KEY|"
                     r"CREDENTIALS?|AUTH)[A-Z0-9_]*)(\s*[=:]\s*)(\"[^\"]*\"|'[^']*'|\S+)")
_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}")
_HOME = re.compile(r"(?:/Users|/home|/root(?=/|\b)|[A-Za-z]:\\Users)(?:[/\\][^\s'\"`<>()\[\]]*)?"
                   r"|~[A-Za-z0-9._-]*(?:/[^\s'\"`<>()\[\]]*)?")
ENV_MIN = 8                          # shorter environment values are too common to strip


def env_values(env: dict[str, str] | None = None) -> list[str]:
    """Values of the environment worth stripping, longest first."""
    env = os.environ if env is None else env
    vals = {v for v in env.values() if isinstance(v, str) and len(v.strip()) >= ENV_MIN}
    return sorted(vals, key=len, reverse=True)


def scrub(text: str, env: Iterable[str] = ()) -> str:
    """text with secrets, environment values, email addresses and home-directory paths removed."""
    for rx in _SECRETS:
        text = rx.sub(REDACTED, text)
    text = _ASSIGN.sub(lambda m: f"{m.group(1)}{m.group(2)}{REDACTED}", text)
    for v in env:
        text = text.replace(v, "[env]")
    text = _EMAIL.sub("[email]", text)
    return _HOME.sub("[path]", text)


TEXT_KEYS = {"note", "asked", "title", "what"}   # free text: environment values stripped too


def clean(x: object, env: Iterable[str] = (), text: bool = False) -> object:
    """x with scrub() applied to every string in it. Environment values are stripped only from
    free text (TEXT_KEYS), so a value that is also, say, the repo's name doesn't break a link."""
    env = list(env)
    if isinstance(x, str):
        return scrub(x, env if text else ())
    if isinstance(x, dict):
        return {k: clean(v, env, text or k in TEXT_KEYS) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [clean(v, env, text) for v in x]
    return x


def _words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+(?:['’][a-z]+)?", text.lower())


def cut_prompt(text: str, prompt: str, n: int = QUOTE_WORDS) -> str:
    """text, or CUT if it quotes `n` or more words in a row from the prompt."""
    p = _words(prompt)
    if len(p) < n:
        return CUT if p and " ".join(p) in " ".join(_words(text)) else text
    grams = {tuple(p[i:i + n]) for i in range(len(p) - n + 1)}
    t = _words(text)
    return CUT if any(tuple(t[i:i + n]) in grams for i in range(len(t) - n + 1)) else text


# ---------------------------------------------------------------- the session note

def read_note(path: Path) -> dict | None:
    """The note a session wrote: {tried, surprised, blocked}, each a string (an empty or
    missing field reads "none"), or None if there is no readable note."""
    try:
        raw = json.loads(path.read_text())
    except (OSError, ValueError, UnicodeDecodeError):
        return None
    if not isinstance(raw, dict) or not any(isinstance(raw.get(k), str) for k in NOTE_FIELDS):
        return None
    out = {}
    for k in NOTE_FIELDS:
        v = raw.get(k)
        v = " ".join(v.split()) if isinstance(v, str) else ""
        out[k] = (v[:FIELD_MAX - 1] + "…" if len(v) > FIELD_MAX else v) or "none"
    return out


def note_episode(*, session_id: str, role: str, model: str, repo: str | None, issue: int | None,
                 pr: int | None, note: dict | None, paths: list[str], prompt: str,
                 at: dt.datetime) -> dict:
    """A note episode; a field of the note that quotes the prompt is cut. Not scrubbed yet:
    write() does that."""
    if note is not None:
        note = {k: cut_prompt(note.get(k) or "none", prompt) for k in NOTE_FIELDS}
    n = pr or issue
    source = (f"https://github.com/{repo}/{'pull' if pr else 'issues'}/{n}" if repo and n else None)
    return {"schema": SCHEMA, "id": f"note:{session_id}", "type": "note", "at": stamp(at),
            "session_id": session_id, "role": role, "model": model, "repo": repo, "issue": issue,
            "pr": pr, "paths": sorted(set(paths)), "note": note, "no_note": note is None,
            "source": source}


# ---------------------------------------------------------------- the store

def stamp(t: dt.datetime) -> str:
    return t.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _ids(path: Path) -> set[str]:
    try:
        lines = path.read_text().splitlines()
    except (OSError, UnicodeDecodeError):
        return set()
    out = set()
    for line in lines:
        try:
            out.add(json.loads(line).get("id"))
        except (ValueError, AttributeError):
            continue
    return out


def write(directory: Path, episodes: list[dict], env: Iterable[str] | None = None) -> int:
    """Append each episode not already there to its day's file in `directory`, scrubbed.
    Returns how many were written."""
    env = env_values() if env is None else list(env)
    by_day: dict[str, list[dict]] = {}
    for ep in episodes:
        by_day.setdefault(ep["at"][:10], []).append(ep)
    n = 0
    for day, eps in sorted(by_day.items()):
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{day}.jsonl"
        have = _ids(path)
        lines = []
        for ep in eps:
            if ep["id"] in have:
                continue
            have.add(ep["id"])
            lines.append(json.dumps(clean(ep, env), sort_keys=True, ensure_ascii=False))
        if lines:
            with open(path, "a") as f:
                f.write("".join(line + "\n" for line in lines))
            n += len(lines)
    return n


def load(directories: list[Path], since: dt.date | None = None, role: str | None = None,
         kind: str | None = None) -> list[dict]:
    """Every episode in `directories`, oldest first, once per id. `kind` matches an episode's
    type or an act's tag; `role` matches a note's role."""
    seen: dict[str, dict] = {}
    for d in directories:
        for path in sorted(d.glob("*.jsonl")) if d.is_dir() else []:
            if since and path.stem < since.isoformat():
                continue
            for line in path.read_text().splitlines():
                try:
                    ep = json.loads(line)
                except ValueError:
                    continue
                if isinstance(ep, dict) and ep.get("schema") == SCHEMA and ep.get("id"):
                    seen.setdefault(ep["id"], ep)
    out = [ep for ep in seen.values()
           if (not since or str(ep.get("at", ""))[:10] >= since.isoformat())
           and (not role or ep.get("role") == role)
           and (not kind or kind in (ep.get("type"), ep.get("tag")))]
    return sorted(out, key=lambda ep: (ep.get("at", ""), ep["id"]))


def text(eps: list[dict]) -> str:
    """`swarm memory episodes`' output: one line per episode."""
    if not eps:
        return "No episodes."
    out = []
    for ep in eps:
        t = ep.get("type")
        if t == "note":
            who = f"{ep.get('role')} ({ep.get('model')})"
            on = f" on #{ep['pr'] or ep['issue']}" if ep.get("pr") or ep.get("issue") else ""
            if ep.get("no_note"):
                what = f"{who}{on}: no note"
            else:
                n = ep.get("note") or {}
                what = (f"{who}{on}: tried: {n.get('tried')} | surprised: {n.get('surprised')} | "
                        f"blocked: {n.get('blocked')}")
        elif t == "act":
            what = f"{ep.get('tag') or '-'}: {ep.get('what')} on {ep.get('repo')}#{ep.get('number')}"
        elif t == "retag":
            what = f"retagged {ep.get('target')} as {ep.get('tag')}"
        elif t == "review":
            what = f"changes requested by {ep.get('by')} on #{ep.get('pr')}: {ep.get('asked')}"
        elif t == "run":
            what = f"{ep.get('outcome')}: {ep.get('name')} ({ep.get('ref')})"
        elif t == "answer":
            took = {True: "took the default", False: "didn't take the default"}.get(ep.get("took_default"),
                                                                                   "default unclear")
            what = f"answered #{ep.get('number')} ({ep.get('domain') or '?'}): {took}"
        else:
            what = f"#{ep.get('number')}: {ep.get('title')}"
        out.append(f"{ep.get('at', '')[:16].replace('T', ' ')}  {t:<15}  {what}"
                   + (f"  {ep['source']}" if ep.get("source") else ""))
    return "\n".join(out)


# ---------------------------------------------------------------- signals (no model call)

def from_acts(rows: list[dict], retags: list[dict]) -> list[dict]:
    """An act episode per owner act (acts.stored()), and a retag episode per retag."""
    out = [{"schema": SCHEMA, "id": f"act:{a['key']}", "type": "act", "at": a["at"], "act": a["act"],
            "kind": a["kind"], "tag": a.get("tag"), "what": a.get("what"), "repo": a["repo"],
            "number": a["number"], "source": a.get("url")} for a in rows]
    out += [{"schema": SCHEMA, "id": f"retag:{r['target']}:{r['tag']}", "type": "retag", "at": r["at"],
             "target": r["target"], "tag": r["tag"], "source": r.get("url")} for r in retags]
    return out


def from_runs(rows: list[dict], repo: str) -> list[dict]:
    """A run episode per ledger row that failed or hit its cap."""
    out = []
    for r in rows:
        outcome = FAILED_ENDINGS.get(r.get("ending") or "")
        if not outcome or not r.get("ended"):
            continue
        n = r.get("pr") or r.get("issue")
        source = f"https://github.com/{repo}/{'pull' if r.get('pr') else 'issues'}/{n}" if n else None
        out.append({"schema": SCHEMA, "id": f"run:{r['session_id']}", "type": "run",
                    "at": stamp(dt.datetime.fromisoformat(r["ended"])), "outcome": outcome,
                    "name": r.get("name"), "kind": r.get("kind"), "ref": r.get("ref"),
                    "issue": r.get("issue"), "pr": r.get("pr"), "cost_usd": r.get("cost_usd"),
                    "session_id": r["session_id"], "source": source})
    return out


def from_pr(pr: dict, reviews: list[dict]) -> list[dict]:
    """A PR's signals: each changes-requested review, and its revert or unmerged close."""
    n, url = pr.get("number"), pr.get("html_url")
    out = []
    for r in reviews:
        if r.get("state") != "CHANGES_REQUESTED" or r.get("id") is None or not r.get("submitted_at"):
            continue
        asked = " ".join((r.get("body") or "").split())
        out.append({"schema": SCHEMA, "id": f"review:{r['id']}", "type": "review", "at": r["submitted_at"],
                    "pr": n, "by": (r.get("user") or {}).get("login"), "commit": r.get("commit_id"),
                    "asked": asked[:EXCERPT_MAX - 1] + "…" if len(asked) > EXCERPT_MAX else asked,
                    "source": r.get("html_url") or url})
    title = pr.get("title") or ""
    if pr.get("merged_at") and REVERT_RE.match(title):
        out.append({"schema": SCHEMA, "id": f"revert:{n}", "type": "revert", "at": pr["merged_at"],
                    "number": n, "title": title[:200], "by": (pr.get("user") or {}).get("login"),
                    "source": url})
    elif pr.get("state") == "closed" and not pr.get("merged_at") and pr.get("closed_at"):
        out.append({"schema": SCHEMA, "id": f"closed:{n}", "type": "closed-unmerged", "at": pr["closed_at"],
                    "number": n, "title": title[:200], "by": (pr.get("user") or {}).get("login"),
                    "source": url})
    return out


def section(body: str, heading: str) -> str:
    """The text under `### heading` in an issue form's body."""
    m = re.search(rf"^###\s*{re.escape(heading)}\s*$(.*?)(?=^###\s|\Z)", body or "", re.M | re.S | re.I)
    return m.group(1).strip() if m else ""


_OPTION = re.compile(r"\boption\s*(\d+)\b", re.I)
_TAKES = re.compile(r"\b(?:default|as recommended|recommendation|go with (?:it|that|your)|agreed?|"
                    r"approved?|lgtm|sounds good|yes)\b", re.I)


def took_default(question_body: str, answer: str) -> bool | None:
    """Whether the owner's answer took the question's recommendation: the options it names,
    against the one the recommendation names; with no option named, a plain yes or "default"
    takes it. None when it can't tell."""
    rec = _OPTION.search(section(question_body, "Recommendation")) or re.match(
        r"\s*(\d+)\b", section(question_body, "Recommendation"))
    named = {int(m) for m in _OPTION.findall(answer)}
    if named and rec:
        return named == {int(rec.group(1))}
    if not named and _TAKES.search(answer):
        return True
    return None


def from_answer(q: dict, comment: dict) -> dict:
    """An answer episode for the owner's comment on a gov:question. Its text is read to tell
    whether the owner took the default, and isn't kept."""
    return {"schema": SCHEMA, "id": f"answer:{comment['id']}", "type": "answer", "at": comment["created_at"],
            "number": q.get("number"), "domain": section(q.get("body") or "", "Domain") or None,
            "took_default": took_default(q.get("body") or "", comment.get("body") or ""),
            "source": comment.get("html_url")}


def from_github(repo: str, owner: str, since: dt.datetime, gh_json: Callable,
                gh_items: Callable) -> list[dict]:
    """Review, revert, unmerged-close and answer episodes in repo since `since`, read from
    GitHub: PRs updated since, and gov:questions updated since."""
    day = since.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    out: list[dict] = []
    q = urllib.parse.quote(f"repo:{repo} is:pr updated:>={day}")
    for it in gh_items(f"search/issues?q={q}&per_page=100", ".items[]"):
        n = it.get("number")
        if not isinstance(n, int):
            continue
        # The search item has what from_pr needs; only the reviews take another read.
        pr = {**it, "merged_at": (it.get("pull_request") or {}).get("merged_at")}
        out += [ep for ep in from_pr(pr, gh_items(f"repos/{repo}/pulls/{n}/reviews?per_page=100"))
                if ep["at"] >= day]
    for it in gh_items(f"repos/{repo}/issues?labels=gov:question&state=all&since={day}&per_page=100"):
        if "pull_request" in it:
            continue
        for c in gh_items(f"repos/{repo}/issues/{it['number']}/comments?since={day}&per_page=100"):
            if (c.get("user") or {}).get("login") == owner and c.get("id") is not None \
                    and (c.get("created_at") or "") >= day:
                out.append(from_answer(it, c))
    return out


def sweep(out_dir: Path, state_dir: Path, repo: str, owner: str, since: dt.datetime,
          gh_json: Callable, gh_items: Callable) -> int:
    """Record every signal since `since` as episodes in out_dir: owner acts already in
    swarm.db, failed and capped runs from the runs ledger, and what from_github() reads.
    Returns how many episodes were new. Raises RuntimeError if GitHub can't be read."""
    import acts
    import ledger
    day = stamp(since)
    eps = [ep for ep in from_acts(acts.stored(state_dir), acts.retags(state_dir)) if ep["at"] >= day]
    eps += [ep for ep in from_runs(ledger.rows(state_dir), repo) if ep["at"] >= day]
    eps += from_github(repo, owner, since, gh_json, gh_items)
    return write(out_dir, eps)
