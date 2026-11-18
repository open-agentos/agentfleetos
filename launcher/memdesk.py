"""Memory on the Desk (#1192, FEAT-22): what the Desk shows of the team's memory, as one JSON.

`swarm memory desk --json` prints it and the Desk's build (dashboard/generate.py) reads the same
build(), so every number and list the Desk shows of memory comes from a `swarm memory` command
(command first). It reads only files: memory/ in the checkout and the engine's episodes outbox.

    lessons    each lesson this repo can see (fleet, or repo:<this repo>; lessons.visible_in), by
               id, as `swarm memory show --json` prints it: summary, body, sources (resolved
               against the episodes), eval and rehearsal result, and validation errors. A
               repo:<other> lesson is never here, so the Desk can't show one (GOV-0058's scoping)
    used       the given and cite episodes (#1187) for this repo, oldest first: which lessons a
               session on an issue or PR was given, and which a swarm App cited as `per L-NNNN`.
               Lesson ids not in `lessons` are dropped, so an episode can't carry another
               repo's lesson onto the Desk. The Desk works out per issue, Goal and role from these
    counts     active and dormant lessons, and each role's active lessons against the dream's
               per-role budget (dream.BUDGET): counts only, no spend (GOV-0033)
    dream      the last applied dream's three lines, learned, forgot and proposing, from
               memory/dream.json (dream.lines), less any lesson this repo can't see, or None
               before the first
    owner      the owner model's valid entries with their sources, as `swarm memory owner
               --json` prints them (public in the repo, GOV-0052)
    drafts     Escalation's draft gov:questions still open, as `swarm escalate --list --json`
               prints them from memory/escalations.json

Lesson, episode and owner-model text is data: the Desk shows it as text, never as markup.
"""
from __future__ import annotations

import re
from pathlib import Path

import dream as D
import episodes as EP
import escalation as E
import lessons as L
import owner as O

SCHEMA = 1
BOT_RE = re.compile(r"(?:app/)?productswarm-([a-z0-9-]+?)(?:\[bot\])?")
USED_FIELDS = ("role", "issue", "pr", "number", "closes", "source")


def role_of(login: str | None) -> str | None:
    m = BOT_RE.fullmatch(login or "")
    return m.group(1) if m else None


def lesson_view(les: L.Lesson, ctx: L.Context) -> dict:
    """One lesson as `swarm memory show --json` prints it."""
    return {**L.summary(les), "body": les.body, "sources": L.resolve_sources(les, ctx.episodes, ctx.owner),
            "eval": L.eval_result(les), "errors": L.validate(les, ctx)}


def used(eps: list[dict], repo: str, known: set[str]) -> list[dict]:
    """The given and cite episodes for `repo`, each with only the lessons in `known`."""
    out = []
    for e in eps:
        if e.get("type") not in ("given", "cite") or str(e.get("repo") or "").lower() != repo.lower():
            continue
        ids = [str(x) for x in e.get("lessons") or [] if str(x) in known]
        if not ids and e.get("type") == "cite":
            continue
        row = {"type": e["type"], "at": e.get("at"), "lessons": ids,
               **{k: e.get(k) for k in USED_FIELDS}}
        if e["type"] == "cite":
            row["role"] = role_of(e.get("by"))
            row["closes"] = [n for n in e.get("closes") or [] if isinstance(n, int)]
        out.append(row)
    return sorted(out, key=lambda r: str(r.get("at") or ""))


def dream_lines(lines: dict | None, hidden: set[str]) -> dict | None:
    """The dream's lines without the lessons in `hidden`: those in the store this repo can't
    see. An id the store doesn't hold yet (a proposed lesson the librarian hasn't written)
    stays: it has no scope yet."""
    if not lines:
        return None
    def keep(xs):
        return [x for x in xs or [] if str(x) not in hidden]
    ln, fg = lines.get("learned") or {}, lines.get("forgot") or {}
    return {**lines, "learned": {**ln, "proposed": keep(ln.get("proposed")), "reconfirmed": keep(ln.get("reconfirmed"))},
            "forgot": {**fg, "dormant": keep(fg.get("dormant")), "retired": keep(fg.get("retired"))}}


def counts(lessons: list[L.Lesson], roles: set[str]) -> dict:
    active = [x for x in lessons if x.status == "active"]
    per = {r: sum(1 for x in active if not x.applies("roles") or r in x.applies("roles")) for r in sorted(roles)}
    return {"active": len(active), "dormant": sum(1 for x in lessons if x.status == "dormant"),
            "budget": D.BUDGET, "roles": per}


def build(root: Path, repo: str, home: Path | None = None, memory: Path | None = None) -> dict:
    """The Desk's memory, for `repo`, from root's memory/ (or `memory`) and, when `home` is given,
    the engine's episodes outbox under it. Raises OSError, RuntimeError or ValueError when the
    episodes or the trust list can't be read."""
    memory = memory or root / "memory"
    dirs = [memory / "episodes"] + ([EP.outbox(home)] if home else [])
    eps = EP.load(dirs)
    ctx = L.Context(L.trusted_logins(), {e["id"]: e for e in eps}, L.in_force_rulings(), repo)
    mine = [x for x in L.load_all(memory / "lessons") if not x.errors and L.visible_in(x, repo)]
    views = {x.id: lesson_view(x, ctx) for x in mine}
    hidden = {x.id for x in L.load_all(memory / "lessons")} - set(views)
    roles = O.known_roles(root / "roles")
    om = O.load(memory / O.FILE)
    return {"schema": SCHEMA, "repo": repo, "lessons": views, "used": used(eps, repo, set(views)),
            "counts": counts(mine, roles), "dream": dream_lines(D.last_lines(memory), hidden),
            "owner": O.as_json(O.valid_entries(om, roles), None)["entries"],
            "drafts": [d for d in E.load_ledger(memory) if d.get("state") != "closed"]}


def text(d: dict) -> str:
    """`swarm memory desk` without --json: the same, in a few lines."""
    c = d["counts"]
    fullest = max(c["roles"].items(), key=lambda kv: (kv[1], kv[0]), default=None)
    out = [f"Memory for {d['repo']}: {len(d['lessons'])} lessons, {c['active']} active, {c['dormant']} dormant"
           + (f"; fullest role {fullest[0]} at {fullest[1]} of {c['budget']}" if fullest else "")]
    dr = d["dream"]
    if dr:
        out.append(f"Last dream {dr['last_run']}: learned {len(dr['learned']['proposed'])} proposed, "
                   f"{len(dr['learned']['reconfirmed'])} reconfirmed; forgot {len(dr['forgot']['dormant'])} "
                   f"to dormant, {len(dr['forgot']['retired'])} retired; proposing "
                   f"{len(dr['proposing']['patterns'])} pattern(s), {len(dr['proposing']['owner'])} owner entr(ies)")
    else:
        out.append("No dream applied yet.")
    out.append(f"{len(d['used'])} given or cite episode(s); {len(d['owner'])} owner-model entr(ies); "
               f"{len(d['drafts'])} open draft gov:question(s)")
    return "\n".join(out)
