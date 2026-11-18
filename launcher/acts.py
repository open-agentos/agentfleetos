"""The owner's acts per working day (#771), counted and reported for M4 (#686).

Owner acts are counted and reported, never a gate (per GOV-0040): there is no limit a day and
no run of working days to pass. Each day gives its count and each act's kind, including how
many weren't C-team work ('other'). GitHub's events API keeps 300 events, so one busy day pushes earlier
ones out (dashboard/activity.py). This keeps its own record in swarm.db instead, in two steps:

1. **Leads, from webhooks.** For each delivery that could be an owner act, the receiver
   (webhooks.py) stores a pointer in `act_leads`: delivery id, event, action, repo, number,
   the object to read back (a comment or review id, or a label's name) and the sender's login.
   Nothing else from the payload, and no comment or issue body (GOV-0002, GOV-0004).
2. **Acts, read back from GitHub.** `sync()` reads each unread lead whose sender is the owner
   back from GitHub, the way the watcher reads everything else (a payload is never trusted
   for who did what), and stores the act in `acts`: when, act, kind, a short label, repo,
   number and a link. A body read to classify an act is never stored. The receiver holds only
   WEBHOOK_SECRET, so it can't read GitHub itself: `swarm acts` runs sync() before it prints.

Each role App delivers the same event, so one act has several leads; an act's key is its
GitHub object (a comment id, review id, issue event id, or a merge or open of repo#n), so it
is stored once.

What counts:
    label    the owner added or removed a label on an issue or PR (issue events, by id)
    comment  an issue or PR conversation comment
    review   a PR review, including an approval that is an approved ask (GOV-0027); an
             inline comment or reply makes a review too, so they aren't counted again
    merge    the owner merged a PR, including a protected-path merge
    open     the owner opened an issue other than a Goal or Area
    edit     the owner edited an agent's issue, PR or comment (#1184)
    close    the owner closed an agent's issue, or its PR unmerged: a veto (#1184)
What doesn't: opening or editing a Goal or Area (labels on one are edits to it), closing their
own issue or one a merge closes, closing a gov:question (routine once it is answered,
GOVERNANCE.md §6), reading the report or the Desk.

Kind: `plan` (on a Mission, Goal or Area, or a `hold` veto, GOV-0031), `report`
(on the report issue: replies, asks and `Ask:` one-on-ones), `ask` (on a `gov:question`, or
approving a protected-path PR at head, GOV-0027), `protected-merge` (merging a PR that touches
a protected path) and `other`, work that isn't the C-team's: a `ready` on a Task, a dispatching
comment, a merge of an ordinary PR.

**A day is counted only once it is backfilled (#844).** Leads only exist where the receiver
runs (the engine host), and a receiver that was down leaves none, so a day with no stored acts
may simply have no data. `backfill()` reads each finished day's acts from GitHub instead, as
leads with the same keys, so an act seen both ways is stored once: the owner's label and merge
events from each org repo's issue events, their comments from each repo's comment list, and
their reviews and opened issues from search. Once every one of them is read back, the day's
window goes in `act_backfills`, and only then does the day count, even at 0 acts. Any other
day is `not counted` (never 0), and today is `in progress` until it ends. A day is backfilled
SETTLE after it ends (search lags), and only within BACKFILL_DAYS (its comment list is long).

**Reads run WORKERS at a time, within a deadline (#858).** Each read is a `gh` call of about a
second, so a backfill read one at a time took minutes: a day is about 30 calls to find the
leads and one or two per lead to read them back, and the first backfill of 15 days was 75
and about 800. Repos, searches and leads are read in parallel. A caller with a deadline
(`swarm trouble`) starts no read after it: leads found but not read back stay unread, so the
next run carries on from them, and a search that runs out of time stores nothing, so the
next run starts it again. `swarm acts` has no deadline and always finishes.

**Tags (#1184, FEAT-14).** Each act also gets a tag for the learning loop, by rule (rule_tag),
with no model call:
    approval       a `ready` label, an approving review (an approval at the PR's head when it
                   was given), or a merge
    correction     an edit to an agent's issue, PR or comment; a `kind:*` label; a veto (a
                   `hold` label, taking `ready` off, or closing an agent's issue, other than a
                   gov:question, or its PR unmerged);
                   merging a revert
    repeat answer  an answer on a gov:question whose domain is that of an earlier answered
                   question and whose title says much the same (title_overlap)
    genuine call   everything else
The owner retags an act with a comment line `Retag <act key or link>: <tag>` anywhere; the
retag wins over the rule, and the comment itself has no tag. `swarm acts` shows each act's
key. Edits and closes are acts from #1184 on; edits come from webhooks only (a backfill can't
find them) and are read back through GraphQL, which says who edited last.

Limits: an object deleted before it is read back is lost; Discussion comments aren't read; an
org repo the owner's token can't list isn't searched. Back-room repairs leave no record at all
(the checklist has the owner self-report them).
"""
from __future__ import annotations

import datetime as dt
import re
import sqlite3
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Callable

import statedb

SCOPE_TYPES = ("Mission", "Goal", "Area")
EXEMPT_TYPES = ("Goal", "Area")  # opening or editing one is plan approval, not an act
KINDS = ("plan", "report", "ask", "protected-merge", "other")
APPROVAL, CORRECTION, REPEAT, GENUINE = "approval", "correction", "repeat answer", "genuine call"
TAGS = (APPROVAL, CORRECTION, REPEAT, GENUINE)
READY = "ready"
RETAG_RE = re.compile(r"^\s*retag\s+(\S+?)\s*:?\s+(approval|correction|repeat answer|genuine call)\s*\.?\s*$",
                      re.I | re.M)
REPEAT_OVERLAP = 0.5            # title_overlap at or above this, in the same domain, is a repeat
HOLD = "hold"                   # the owner's veto (GOV-0031)
GOV_QUESTION = "gov:question"
SETTLE = dt.timedelta(hours=1)  # a day is backfilled this long after it ends (search lags)
BACKFILL_DAYS = 31              # older days aren't backfilled: not counted
COUNTED, NOT_COUNTED, IN_PROGRESS = "counted", "not counted", "in progress"
WORKERS = 8                     # gh calls in flight at once (#858)
OUT_OF_TIME = "out of time"


def late(deadline: float | None) -> bool:
    """Past the deadline, a time.monotonic() value; never with None."""
    return deadline is not None and time.monotonic() >= deadline


def each(fn: Callable, items: list) -> list:
    """fn over items, WORKERS at a time, in order: each result, or the exception it raised."""
    def safe(x):
        try:
            return fn(x)
        except Exception as e:   # noqa: BLE001 - handed back to the caller, which sorts them
            return e
    if len(items) < 2:
        return [safe(x) for x in items]
    with ThreadPoolExecutor(min(WORKERS, len(items))) as pool:
        return list(pool.map(safe, items))

SCHEMA = """
CREATE TABLE IF NOT EXISTS act_leads (
    delivery TEXT PRIMARY KEY, event TEXT NOT NULL, action TEXT, repo TEXT NOT NULL,
    number INTEGER NOT NULL, ref TEXT, sender TEXT, received_at TEXT NOT NULL, read_at TEXT
);
CREATE TABLE IF NOT EXISTS acts (
    key TEXT PRIMARY KEY, at TEXT NOT NULL, act TEXT NOT NULL, kind TEXT NOT NULL,
    what TEXT, repo TEXT NOT NULL, number INTEGER NOT NULL, url TEXT
);
CREATE INDEX IF NOT EXISTS acts_at ON acts (at);
CREATE TABLE IF NOT EXISTS act_backfills (start TEXT NOT NULL, end TEXT NOT NULL, at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS act_retags (
    target TEXT PRIMARY KEY, tag TEXT NOT NULL, at TEXT NOT NULL, url TEXT
);
"""


# ---------------------------------------------------------------- tags (#1184)

def rule_tag(act: str, *, label: str | None = None, added: bool = True, state: str | None = None,
             revert: bool = False, repeat: bool | None = None) -> str:
    """An act's tag by rule: approval, correction, repeat answer or genuine call (see above).
    `repeat` is None unless the act is an answer on a gov:question."""
    if act == "label":
        if label == READY:
            return APPROVAL if added else CORRECTION
        if label == HOLD or (label or "").startswith("kind:"):
            return CORRECTION
        return GENUINE
    if act == "merge":
        return CORRECTION if revert else APPROVAL
    if act == "review":
        return APPROVAL if state == "APPROVED" else GENUINE
    if act in ("edit", "close"):
        return CORRECTION
    if act == "comment" and repeat:
        return REPEAT
    return GENUINE


_STOP = {"a", "an", "the", "of", "to", "in", "on", "for", "and", "or", "is", "it", "its", "be", "by",
         "may", "should", "we", "do", "does", "how", "what", "which", "who", "when", "where", "with",
         "gov", "q"}


def title_words(title: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", (title or "").lower()) if w not in _STOP}


def title_overlap(a: str, b: str) -> float:
    """Jaccard overlap of two titles' content words."""
    x, y = title_words(a), title_words(b)
    return len(x & y) / len(x | y) if x and y else 0.0


def domain_of(body: str | None) -> str | None:
    m = re.search(r"^###\s*Domain\s*$\s*(\S+)", body or "", re.M | re.I)
    return m.group(1).strip().lower() if m else None


def retags_in(body: str | None) -> list[tuple[str, str]]:
    """(target, tag) for each `Retag <key or link>: <tag>` line in a comment."""
    return [(t, tag.lower()) for t, tag in RETAG_RE.findall(body or "")]


def migrate(db: sqlite3.Connection) -> None:
    """Add acts.tag to a swarm.db made before #1184."""
    if "tag" not in {r[1] for r in db.execute("PRAGMA table_info(acts)")}:
        db.execute("ALTER TABLE acts ADD COLUMN tag TEXT")


# ---------------------------------------------------------------- leads (from the receiver)

def lead(event: str, payload: object) -> tuple[str, str, int, str | None, str | None] | None:
    """(action, repo, number, ref, sender) for a delivery that could be an owner act, else None.
    Read from the payload only to know what to read back; never acted on."""
    if not isinstance(payload, dict):
        return None
    action = payload.get("action")
    repo = (payload.get("repository") or {}).get("full_name") if isinstance(
        payload.get("repository"), dict) else None
    sender = (payload.get("sender") or {}).get("login") if isinstance(payload.get("sender"), dict) else None
    if not isinstance(action, str) or not isinstance(repo, str):
        return None
    obj = payload.get("pull_request" if event in ("pull_request", "pull_request_review") else "issue")
    number = obj.get("number") if isinstance(obj, dict) else None
    if not isinstance(number, int):
        return None

    def field(key: str, name: str) -> str | None:
        v = payload.get(key)
        v = v.get(name) if isinstance(v, dict) else None
        return str(v)[:100] if isinstance(v, (str, int)) and not isinstance(v, bool) else None

    ref: str | None = None
    if event in ("issues", "pull_request") and action in ("labeled", "unlabeled"):
        ref = field("label", "name")
        if ref is None:
            return None
    elif event == "issues" and action == "opened":
        pass
    elif event == "pull_request" and action == "closed" and obj.get("merged") is True:
        action = "merged"
    elif event == "issue_comment" and action == "created":
        ref = field("comment", "id")
    elif event == "issue_comment" and action == "edited":
        ref = field("comment", "id")
    elif event in ("issues", "pull_request") and action == "edited":
        pass
    elif event in ("issues", "pull_request") and action == "closed":
        pass                       # an unmerged close (a merge is caught above)
    elif event == "pull_request_review" and action == "submitted":
        ref = field("review", "id")
    else:
        return None
    if event in ("issue_comment", "pull_request_review") and ref is None:
        return None
    return action, repo[:140], number, ref, sender[:64] if isinstance(sender, str) else None


def record_lead(db: sqlite3.Connection, delivery: str, event: str, found: tuple,
                now: dt.datetime) -> None:
    """Store one lead; the caller holds the transaction (the receiver's delivery insert)."""
    db.execute("INSERT OR IGNORE INTO act_leads (delivery, event, action, repo, number, ref, sender, "
               "received_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
               (delivery, event, *found, now.isoformat(timespec="seconds")))


# ---------------------------------------------------------------- reading back

def connect(state_dir: Path) -> sqlite3.Connection:
    db = statedb.connect(state_dir / statedb.DB_FILE)
    db.executescript(SCHEMA)
    migrate(db)
    return db


def not_found(e: Exception) -> bool:
    return "Not Found" in str(e) or "404" in str(e)


def login(o: object) -> str | None:
    return (o or {}).get("login") if isinstance(o, dict) else None


class Reader:
    """Reads acts back from GitHub, caching each issue and PR's files for one sync."""

    def __init__(self, owner: str, report: tuple[str, int] | None, gh_json: Callable,
                 gh_items: Callable, protected: Callable[[str], bool]):
        self.owner, self.report = owner, report
        self.gh_json, self.gh_items, self.protected = gh_json, gh_items, protected
        self._issues: dict[tuple[str, int], dict] = {}
        self._files: dict[tuple[str, int], bool] = {}
        self._questions: dict[str, list[dict]] = {}

    def issue(self, repo: str, n: int) -> dict:
        if (repo, n) not in self._issues:
            self._issues[(repo, n)] = self.gh_json("api", f"repos/{repo}/issues/{n}") or {}
        return self._issues[(repo, n)]

    def touches_protected(self, repo: str, n: int) -> bool:
        if (repo, n) not in self._files:
            files = self.gh_items(f"repos/{repo}/pulls/{n}/files?per_page=100")
            self._files[(repo, n)] = any(self.protected(f.get("filename") or "") for f in files)
        return self._files[(repo, n)]

    def where(self, repo: str, n: int) -> str | None:
        """The kind any act on this issue has: plan, report or ask; None if it depends on the act."""
        if self.report == (repo, n):
            return "report"
        it = self.issue(repo, n)
        if ((it.get("type") or {}).get("name")) in SCOPE_TYPES:
            return "plan"
        if GOV_QUESTION in {(l or {}).get("name") for l in it.get("labels") or []}:
            return "ask"
        return None

    def exempt(self, repo: str, n: int) -> bool:
        return ((self.issue(repo, n).get("type") or {}).get("name")) in EXEMPT_TYPES

    @staticmethod
    def is_question(it: dict) -> bool:
        """Whether an issue is a gov:question. Closing an answered one is routine (GOVERNANCE.md
        §6, "the owner closes the question"), not a veto, so it isn't an act."""
        return GOV_QUESTION in {(l or {}).get("name") for l in it.get("labels") or []}

    def agent_made(self, x: dict) -> bool:
        """Whether an issue, PR or comment was written by an agent (a bot), not the owner."""
        who = login(x.get("user")) or ""
        return who.endswith("[bot]")

    def questions(self, repo: str) -> list[dict]:
        """Every gov:question in repo, read once per sync."""
        if repo not in self._questions:
            self._questions[repo] = [q for q in self.gh_items(
                f"repos/{repo}/issues?labels={GOV_QUESTION}&state=all&per_page=100")
                if "pull_request" not in q]
        return self._questions[repo]

    def repeat(self, repo: str, n: int) -> bool:
        """Whether gov:question #n matches an earlier answered one: same domain, much the same
        title (REPEAT_OVERLAP). Answered: closed, or labelled gov:ruled."""
        q = self.issue(repo, n)
        domain = domain_of(q.get("body"))
        if not domain:
            return False
        for other in self.questions(repo):
            names = {(l or {}).get("name") for l in other.get("labels") or []}
            if (other.get("number") != n and (other.get("created_at") or "") < (q.get("created_at") or "")
                    and (other.get("state") == "closed" or "gov:ruled" in names)
                    and domain_of(other.get("body")) == domain
                    and title_overlap(other.get("title") or "", q.get("title") or "") >= REPEAT_OVERLAP):
                return True
        return False

    def last_edit(self, node: str, gql: str) -> dict:
        """{author, editor, at} for one node, from GraphQL (REST doesn't say who edited)."""
        q = ("query($id: ID!) { node(id: $id) { ... on %s { author { login } "
             "editor { login } lastEditedAt } } }" % gql)
        d = self.gh_json("api", "graphql", "-f", f"query={q}", "-f", f"id={node}") or {}
        x = ((d.get("data") or {}).get("node") or {})
        return {"author": login(x.get("author")), "editor": login(x.get("editor")), "at": x.get("lastEditedAt")}

    def read(self, event: str, action: str, repo: str, n: int, ref: str | None) -> list[dict]:
        """The owner's acts this lead points at, read from GitHub ([] if none), each with its
        tag. A comment's act may carry `retags`, the (target, tag) pairs it sets."""
        page = f"https://github.com/{repo}/issues/{n}"
        act = {"repo": repo, "number": n}
        if action in ("labeled", "unlabeled", "closed"):
            if self.exempt(repo, n):
                return []
            it = self.issue(repo, n) if action == "closed" else {}
            out = []
            for e in self.gh_items(f"repos/{repo}/issues/{n}/events?per_page=100"):
                if (login(e.get("actor")) != self.owner or e.get("id") is None
                        or not e.get("created_at")):
                    continue
                key = f"{repo}:event:{e['id']}"
                name = (e.get("label") or {}).get("name")
                if e.get("event") in ("labeled", "unlabeled") and name:
                    verb = "labelled" if e["event"] == "labeled" else "unlabelled"
                    kind = self.where(repo, n) or ("plan" if name == HOLD else "other")
                    out.append({**act, "key": key, "at": e["created_at"], "act": "label", "kind": kind,
                                "what": f"{verb} {name}", "url": page,
                                "tag": rule_tag("label", label=name, added=e["event"] == "labeled")})
                elif (e.get("event") == "closed" and action == "closed" and not e.get("commit_id")
                      and self.agent_made(it) and not self.is_question(it)):
                    if "pull_request" in it:
                        pr = self.gh_json("api", f"repos/{repo}/pulls/{n}") or {}
                        if pr.get("merged_at"):
                            continue
                    out.append({**act, "key": key, "at": e["created_at"], "act": "close",
                                "kind": self.where(repo, n) or "plan", "what": "closed unmerged"
                                if "pull_request" in it else "closed", "url": page,
                                "tag": rule_tag("close")})
            return out
        if action == "opened":
            it = self.issue(repo, n)
            if login(it.get("user")) != self.owner or self.exempt(repo, n) or not it.get("created_at"):
                return []
            kind = self.where(repo, n) or "other"
            what = f"opened {(it.get('type') or {}).get('name') or 'issue'}"
            return [{**act, "key": f"{repo}#{n}:open", "at": it["created_at"], "act": "open",
                     "kind": kind, "what": what, "url": it.get("html_url") or page, "tag": rule_tag("open")}]
        if action == "merged":
            pr = self.gh_json("api", f"repos/{repo}/pulls/{n}") or {}
            if login(pr.get("merged_by")) != self.owner or not pr.get("merged_at"):
                return []
            kind = "protected-merge" if self.touches_protected(repo, n) else "other"
            revert = (pr.get("title") or "").startswith('Revert "')
            return [{**act, "key": f"{repo}#{n}:merge", "at": pr["merged_at"], "act": "merge",
                     "kind": kind, "what": "merged a revert" if revert else "merged",
                     "url": pr.get("html_url") or page, "tag": rule_tag("merge", revert=revert)}]
        if action == "edited":
            if event == "issue_comment":
                c = self.gh_json("api", f"repos/{repo}/issues/comments/{ref}") or {}
                node, gql, key = c.get("node_id"), "IssueComment", f"{repo}:comment:{ref}"
                url, what = c.get("html_url") or page, "edited an agent's comment"
            else:
                c = self.issue(repo, n)
                pr = "pull_request" in c
                node, gql, key = c.get("node_id"), "PullRequest" if pr else "Issue", f"{repo}#{n}"
                url, what = c.get("html_url") or page, f"edited an agent's {'PR' if pr else 'issue'}"
            if not node or not self.agent_made(c) or (event != "issue_comment" and self.exempt(repo, n)):
                return []
            ed = self.last_edit(node, gql)
            if ed["editor"] != self.owner or not ed["at"]:
                return []
            return [{**act, "key": f"{key}:edit:{ed['at']}", "at": ed["at"], "act": "edit",
                     "kind": self.where(repo, n) or "other", "what": what, "url": url,
                     "tag": rule_tag("edit")}]
        if event == "issue_comment":
            c = self.gh_json("api", f"repos/{repo}/issues/comments/{ref}") or {}
            if login(c.get("user")) != self.owner or not c.get("created_at"):
                return []
            kind = self.where(repo, n) or "other"
            retags = retags_in(c.get("body"))      # read to tag, never stored
            if retags:
                tag = None                         # a retag isn't itself a call
            elif GOV_QUESTION in {(l or {}).get("name") for l in self.issue(repo, n).get("labels") or []}:
                tag = rule_tag("comment", repeat=self.repeat(repo, n))
            else:
                tag = rule_tag("comment")
            out = {**act, "key": f"{repo}:comment:{ref}", "at": c["created_at"], "act": "comment",
                   "kind": kind, "what": "retagged" if retags else "commented",
                   "url": c.get("html_url") or page, "tag": tag}
            if retags:
                out["retags"] = retags
            return [out]
        if event == "pull_request_review":
            r = self.gh_json("api", f"repos/{repo}/pulls/{n}/reviews/{ref}") or {}
            state = r.get("state") or ""
            if login(r.get("user")) != self.owner or not r.get("submitted_at") or state == "PENDING":
                return []
            kind = ("ask" if state == "APPROVED" and self.touches_protected(repo, n)
                    else self.where(repo, n) or "other")
            return [{**act, "key": f"{repo}:review:{ref}", "at": r["submitted_at"], "act": "review",
                     "kind": kind, "what": f"reviewed: {state.lower().replace('_', ' ')}",
                     "url": r.get("html_url") or page, "tag": rule_tag("review", state=state)}]
        return []


def sync(state_dir: Path, owner: str, report: tuple[str, int] | None, gh_json: Callable,
         gh_items: Callable, protected: Callable[[str], bool],
         now: dt.datetime | None = None, deadline: float | None = None) -> list[str]:
    """Read every unread lead the owner sent back from GitHub and store its acts, WORKERS at a
    time, starting none after `deadline`. Leads from anyone else are marked read without a call.
    Returns the errors; a lead that failed or wasn't reached stays unread for the next sync, and
    one whose object is gone (404) is marked read."""
    now = now or dt.datetime.now(dt.timezone.utc)
    stamp = now.isoformat(timespec="seconds")
    reader = Reader(owner, report, gh_json, gh_items, protected)
    errors: list[str] = []
    db = connect(state_dir)
    try:
        db.execute("UPDATE act_leads SET read_at = ? WHERE read_at IS NULL "
                   "AND (sender IS NULL OR sender != ?)", (stamp, owner))
        groups = db.execute(
            "SELECT event, action, repo, number, ref FROM act_leads WHERE read_at IS NULL "
            "GROUP BY event, action, repo, number, ref ORDER BY MIN(received_at)").fetchall()
        for i in range(0, len(groups), WORKERS):
            if late(deadline):
                errors.append(f"{len(groups) - i} lead(s) not read back yet ({OUT_OF_TIME}); "
                              f"the next run reads them")
                break
            chunk = groups[i:i + WORKERS]
            for (event, action, repo, n, ref), found in zip(chunk, each(lambda g: reader.read(*g), chunk)):
                if isinstance(found, Exception):
                    if not (isinstance(found, RuntimeError) and not_found(found)):
                        errors.append(f"{event} {action} {repo}#{n}: {found}")
                        continue
                    found = []
                db.execute("BEGIN IMMEDIATE")      # the reads ran in threads; writes stay here
                for a in found:
                    for target, tag in a.pop("retags", []):    # a later retag of the same act wins
                        db.execute("INSERT INTO act_retags (target, tag, at, url) VALUES (?, ?, ?, ?) "
                                   "ON CONFLICT(target) DO UPDATE SET tag = excluded.tag, at = excluded.at, "
                                   "url = excluded.url WHERE excluded.at >= act_retags.at",
                                   (target, tag, a["at"], a["url"]))
                db.executemany("INSERT OR IGNORE INTO acts (key, at, act, kind, what, repo, number, url, tag) "
                               "VALUES (:key, :at, :act, :kind, :what, :repo, :number, :url, :tag)",
                               [{"tag": None, **a} for a in found])
                db.execute("UPDATE act_leads SET read_at = ? WHERE read_at IS NULL AND event = ? AND "
                           "action IS ? AND repo = ? AND number = ? AND ref IS ?",
                           (stamp, event, action, repo, n, ref))
                db.execute("COMMIT")
    finally:
        db.close()
    return errors


# ---------------------------------------------------------------- backfill (#844)

def utc(t: dt.datetime) -> str:
    return t.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def bounds(d: dt.date, tz: dt.tzinfo | None = None) -> tuple[dt.datetime, dt.datetime]:
    """A local day's start and end (tz, or this machine's)."""
    def at(x: dt.date) -> dt.datetime:
        t = dt.datetime.combine(x, dt.time())
        return t.replace(tzinfo=tz) if tz else t.astimezone()
    return at(d), at(d + dt.timedelta(days=1))


def windows(db: sqlite3.Connection) -> list[tuple[dt.datetime, dt.datetime]]:
    """Every backfilled window, as (start, end)."""
    return [(dt.datetime.fromisoformat(a.replace("Z", "+00:00")),
             dt.datetime.fromisoformat(b.replace("Z", "+00:00")))
            for a, b in db.execute("SELECT start, end FROM act_backfills")]


def day_state(d: dt.date, now: dt.datetime, backfills: list, tz: dt.tzinfo | None = None
              ) -> tuple[str, str | None, bool]:
    """(status, why it isn't counted, whether to backfill it now) for one day."""
    start, end = bounds(d, tz)
    if now < start:
        return NOT_COUNTED, "the day hasn't started", False
    if now < end:
        return IN_PROGRESS, "the day isn't over", False
    if any(a <= start and b >= end for a, b in backfills):
        return COUNTED, None, False
    if now < end + SETTLE:
        return NOT_COUNTED, f"read back from GitHub {SETTLE.seconds // 3600}h after the day ends", False
    if now - end > dt.timedelta(days=BACKFILL_DAYS):
        return NOT_COUNTED, f"older than {BACKFILL_DAYS} days, never read back from GitHub", False
    return NOT_COUNTED, "not read back from GitHub yet", True


def scope_repos(repo: str, gh_items: Callable) -> tuple[str, list[str]]:
    """(search qualifier, repos) for repo's org, or for repo alone if its owner isn't an org."""
    org = repo.split("/")[0]
    try:
        names = {r.get("full_name") for r in gh_items(f"orgs/{org}/repos?per_page=100")}
    except RuntimeError as e:
        if not not_found(e):
            raise
        return f"repo:{repo}", [repo]
    return f"org:{org}", sorted({n for n in names if isinstance(n, str)} | {repo})


def recent_events(repo: str, since: str, gh_json: Callable, deadline: float | None = None) -> list[dict]:
    """repo's issue events created at or after `since`, a page at a time from the newest, so a
    busy repo's whole history isn't read. Raises RuntimeError if they aren't newest first, or
    when a page is due after `deadline`."""
    out, page = [], 1
    while True:
        if late(deadline):
            raise RuntimeError(f"{repo}'s issue events: {OUT_OF_TIME}")
        batch = gh_json("api", f"repos/{repo}/issues/events?per_page=100&page={page}") or []
        times = [e.get("created_at") or "" for e in batch]
        if times != sorted(times, reverse=True):
            raise RuntimeError(f"{repo}'s issue events aren't newest first")
        out += [e for e in batch if (e.get("created_at") or "") >= since]
        if len(batch) < 100 or times[-1] < since:
            return out
        page += 1


def discover(owner: str, repo: str, since: str, gh_json: Callable, gh_items: Callable,
             deadline: float | None = None) -> list[tuple]:
    """(key, event, action, repo, number, ref) per lead for the owner's possible acts since
    `since` in repo's org, found on GitHub rather than from webhooks. Each repo and search is
    read in parallel (each). Raises RuntimeError, also when a read is due after `deadline`."""
    def search(q: str) -> list[tuple[str, int]]:
        items = gh_items(f"search/issues?q={urllib.parse.quote(q)}&per_page=100", ".items[]")
        return [(it["repository_url"].split("/repos/", 1)[1], it["number"]) for it in items
                if isinstance(it.get("number"), int) and "/repos/" in (it.get("repository_url") or "")]

    def ok(results: list) -> list:
        for x in results:
            if isinstance(x, Exception):
                raise x if isinstance(x, RuntimeError) else RuntimeError(str(x))
        return results

    def in_repo(r: str) -> list[tuple]:
        found: list[tuple] = []
        for e in recent_events(r, since, gh_json, deadline):
            n = (e.get("issue") or {}).get("number")
            if login(e.get("actor")) != owner or not isinstance(n, int) or e.get("id") is None:
                continue
            if e.get("event") in ("labeled", "unlabeled"):     # one read finds every label act
                found.append((f"backfill:{r}:event:{e['id']}", "issues", "labeled", r, n, None))
            elif e.get("event") == "merged":
                found.append((f"backfill:{r}#{n}:merge", "pull_request", "merged", r, n, None))
            elif e.get("event") == "closed" and not e.get("commit_id"):    # a veto, if unmerged (#1184)
                found.append((f"backfill:{r}:event:{e['id']}", "issues", "closed", r, n, None))
        if late(deadline):
            raise RuntimeError(f"{r}'s comments: {OUT_OF_TIME}")
        for c in gh_items(f"repos/{r}/issues/comments?since={since}&per_page=100"):
            num = (c.get("issue_url") or "").rsplit("/", 1)[-1]
            if (login(c.get("user")) == owner and (c.get("created_at") or "") >= since
                    and c.get("id") is not None and num.isdigit()):
                found.append((f"backfill:{r}:comment:{c['id']}", "issue_comment", "created", r,
                              int(num), str(c["id"])))
        return found

    def reviews(pr: tuple[str, int]) -> list[tuple]:
        r, n = pr
        if late(deadline):
            raise RuntimeError(f"reviews on {r}#{n}: {OUT_OF_TIME}")
        return [(f"backfill:{r}:review:{rv['id']}", "pull_request_review", "submitted", r, n, str(rv["id"]))
                for rv in gh_items(f"repos/{r}/pulls/{n}/reviews?per_page=100")
                if login(rv.get("user")) == owner and (rv.get("submitted_at") or "") >= since
                and rv.get("id") is not None]

    qual, repos = scope_repos(repo, gh_items)
    queries = [f"{qual} is:issue author:{owner} created:>={since}",
               f"{qual} is:pr reviewed-by:{owner} updated:>={since}"]
    *per_repo, opened, reviewed = ok(each(lambda job: job[0](job[1]),
                                          [(in_repo, r) for r in repos] + [(search, q) for q in queries]))
    found = [x for leads in per_repo for x in leads]
    found += [(f"backfill:{r}#{n}:open", "issues", "opened", r, n, None) for r, n in opened]
    found += [x for leads in ok(each(reviews, reviewed)) for x in leads]
    return found


def backfill(state_dir: Path, owner: str, report: tuple[str, int] | None, repo: str,
             gh_json: Callable, gh_items: Callable, protected: Callable[[str], bool],
             days: list[dt.date], now: dt.datetime | None = None,
             tz: dt.tzinfo | None = None, deadline: float | None = None) -> list[str]:
    """Read the owner's acts on each of `days` that is due (day_state) back from GitHub as leads,
    then sync() every unread lead, starting no read after `deadline`. The window counts only once
    no backfilled lead is left unread. Returns the errors, sync()'s included."""
    now = now or dt.datetime.now(dt.timezone.utc)
    db = connect(state_dir)
    try:
        have = windows(db)
        due = [bounds(d, tz) for d in days if day_state(d, now, have, tz)[2]]
        errors: list[str] = []
        if due:
            start, end = min(a for a, _ in due), max(b for _, b in due)
            try:
                found = discover(owner, repo, utc(start), gh_json, gh_items, deadline)
            except RuntimeError as e:
                errors.append(f"backfill from {utc(start)}: {e}")
                due = []
            else:
                db.execute("BEGIN IMMEDIATE")
                for key, event, action, r, n, ref in found:
                    record_lead(db, key, event, (action, r, n, ref, owner), now)
                db.execute("COMMIT")
    finally:
        db.close()
    errors += sync(state_dir, owner, report, gh_json, gh_items, protected, now, deadline)
    if due:
        db = connect(state_dir)
        try:
            unread = db.execute("SELECT COUNT(*) FROM act_leads WHERE read_at IS NULL "
                                "AND delivery LIKE 'backfill:%'").fetchone()[0]
            if not unread:
                with db:
                    db.execute("INSERT INTO act_backfills VALUES (?, ?, ?)",
                               (utc(start), utc(end), now.isoformat(timespec="seconds")))
        finally:
            db.close()
    return errors


def backfilled(state_dir: Path) -> list[tuple[dt.datetime, dt.datetime]]:
    if not (state_dir / statedb.DB_FILE).exists():
        return []
    db = connect(state_dir)
    try:
        return windows(db)
    finally:
        db.close()


def refresh(state_dir: Path, owner: str, report: tuple[str, int] | None, repo: str,
            gh_json: Callable, gh_items: Callable, protected: Callable[[str], bool],
            days: list[dt.date], now: dt.datetime | None = None,
            tz: dt.tzinfo | None = None, deadline: float | None = None) -> tuple[list[dict], list[str]]:
    """backfill(), then per_day() for `days`: what `swarm acts` and `swarm trouble` read.
    `swarm trouble` passes a deadline (#858); `swarm acts` doesn't."""
    now = now or dt.datetime.now(dt.timezone.utc)
    errors = backfill(state_dir, owner, report, repo, gh_json, gh_items, protected, days, now, tz,
                      deadline)
    return per_day(stored(state_dir), days, tz, now, backfilled(state_dir)), errors


# ---------------------------------------------------------------- per day

def stored(state_dir: Path) -> list[dict]:
    """Every act in swarm.db, oldest first, each with its tag: the owner's latest retag of it
    (by key or link) if any (retagged true), else the rule's (#1184)."""
    if not (state_dir / statedb.DB_FILE).exists():
        return []
    db = connect(state_dir)
    try:
        db.row_factory = sqlite3.Row
        rows = [dict(r) for r in db.execute("SELECT * FROM acts ORDER BY at, key")]
        retag = {t: tag for t, tag in db.execute("SELECT target, tag FROM act_retags")}
    finally:
        db.close()
    for r in rows:
        mine = retag.get(r["key"]) or (retag.get(r["url"]) if r["act"] in ("comment", "review") else None)
        r["retagged"] = mine is not None
        r["tag"] = mine or r["tag"]
    return rows


def retags(state_dir: Path) -> list[dict]:
    """Every retag the owner made: {target, tag, at, url}."""
    if not (state_dir / statedb.DB_FILE).exists():
        return []
    db = connect(state_dir)
    try:
        db.row_factory = sqlite3.Row
        return [dict(r) for r in db.execute("SELECT * FROM act_retags ORDER BY at, target")]
    finally:
        db.close()


def by_tag(rows: list[dict]) -> dict[str, int]:
    """How many of the acts in per_day()'s rows have each tag, over the whole window."""
    out = {t: 0 for t in TAGS}
    for r in rows:
        for a in r["acts"]:
            if a.get("tag") in out:
                out[a["tag"]] += 1
    return out


def per_day(acts: list[dict], days: list[dt.date], tz: dt.tzinfo | None = None,
            now: dt.datetime | None = None, backfills: list | None = None) -> list[dict]:
    """One entry per day, in the order given: {day, status, why, count, other, c_team, acts},
    each act with its local time. Days are local (tz, or this machine's). Only a `counted` day
    (backfilled, day_state) has a count, its 'other' acts and c_team (none 'other'); a `not
    counted` one has None for all three, never 0; an `in progress` one counts so far. There is
    no limit to check a count against (per GOV-0040)."""
    now = now or dt.datetime.now(dt.timezone.utc)
    by: dict[dt.date, list[dict]] = {d: [] for d in days}
    for a in acts:
        at = dt.datetime.fromisoformat(a["at"].replace("Z", "+00:00"))
        at = at.astimezone(tz) if tz else at.astimezone()
        if at.date() in by:
            by[at.date()].append({"at": at.isoformat(timespec="seconds"), "act": a["act"],
                                  "kind": a["kind"], "what": a["what"], "repo": a["repo"],
                                  "number": a["number"], "url": a["url"], "key": a.get("key"),
                                  "tag": a.get("tag"), "retagged": bool(a.get("retagged"))})
    out = []
    for d in days:
        items = sorted(by[d], key=lambda a: a["at"])
        status, why, _ = day_state(d, now, backfills or [], tz)
        other = sum(a["kind"] == "other" for a in items)
        row = {"day": d.isoformat(), "status": status, "why": why, "count": None, "other": None,
               "c_team": None, "acts": items}
        if status == COUNTED:
            row.update(count=len(items), other=other, c_team=other == 0)
        elif status == IN_PROGRESS:
            row.update(count=len(items), other=other)
        out.append(row)
    return out


def text(rows: list[dict], owner: str, repo: str | None = None) -> str:
    """`swarm acts`'s output: each day newest first, its count (or why it isn't counted) and each act."""
    out = [f"Owner acts by @{owner} (local time; counted, with no limit, per GOV-0040):"]
    for r in rows:
        d = dt.date.fromisoformat(r["day"])
        n = r["count"]
        if r["status"] == NOT_COUNTED:
            head = f"not counted ({r['why']})"
        else:
            head = f"{n} act{'' if n == 1 else 's'}"
            if r["status"] == IN_PROGRESS:
                head += " so far (the day isn't over)"
            if r["other"]:
                head += f"  ({r['other']} not C-team)"
        out.append(f"  {d:%a %Y-%m-%d}  {head}")
        for a in r["acts"]:
            ref = f"#{a['number']}" if a["repo"] == repo else f"{a['repo']}#{a['number']}"
            tag = (a.get("tag") or "-") + (" (retagged)" if a.get("retagged") else "")
            out.append(f"    {a['at'][11:16]}  {a['kind']:<15}  {tag:<26}  {a['what']} on {ref}  {a['url']}"
                       + (f"  [{a['key']}]" if a.get("key") else ""))
    tags = by_tag(rows)
    out.append("By kind over these days: " + ", ".join(f"{t} {n}" for t, n in tags.items())
               + "  (retag one with a comment line `Retag <key>: <kind>`)")
    return "\n".join(out)
