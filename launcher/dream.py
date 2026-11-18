"""The dream (#1186, FEAT-16): one librarian run over the episodes since the last run.

`swarm dream` works out each phase here, with no model call, as a plan:

  1. Replay       the episodes since the last run (memory/dream.json), or since --since.
  2. Consolidate  cluster similar episodes; a cluster with a new episode that passes GOV-0055's
                  source rules (lessons.source_errors) is a proposed lesson, unless it matches
                  a lesson already there, which it reconfirms (confidence up). Near-duplicate
                  lessons merge into the stronger one.
  3. Reconcile    flag lessons that contradict each other, name a ruling no longer in force, or
                  rest on a PR since closed unmerged or reverted; lower their confidence.
  4. Forget       count each lesson cited (`per L-NNNN`, a cite episode) since the last run as
                  a use, updating uses and last_used (#1187); decay active lessons unused since
                  the last run; move ones unused past
                  DORMANT_DAYS to dormant; retire dormant ones past review_by; delete episodes
                  in memory/episodes/ past RETENTION_DAYS that no lesson cites; keep each role
                  within BUDGET active lessons, moving the lowest-ranked to dormant. Report each
                  lesson's given-not-used count: sessions given it (given episodes) whose issue
                  or PR never cited it. That count is only reported: one week of it isn't
                  grounds to act (FEAT-17's notes).
  5. Rehearse     list the proposed lessons that need an eval case (Rehearsal builds the gate).
  6. Promote      list patterns past a lesson for the owner: the same answer three times, a
                  lesson outside every role's jurisdiction. Drafting them is Escalation.
  7. Owner model  propose entries for memory/owner.md from clusters of the owner's own acts
                  and reviews, with their sources (#1188, owner.py). Only the owner adds one
                  (GOV-0056); the librarian never writes the file (GOV-0059), and one like an
                  entry the owner vetoed in the last 30 days isn't proposed.

`swarm dream --dry-run` prints the plan and the run it would start. `swarm dream` starts one
headless librarian run, capped at its spend_cap_usd ($3) and [watch] max_turns (GOV-0053); the
run applies the plan's mechanical changes with `swarm dream --apply`, writes the proposed
lessons it agrees with, and opens the `memory: night of <date>` PR. With no new episodes, none
of this happens: no model call, no PR.

The thresholds are the defaults the owner set on the Goal (#1179) until the first by-hand run:
25 active lessons per role, dormant after 21 days unused. Episodes keep 30 days (FEAT-14).
Similarity is word overlap, so the first runs over-propose; the two-source rule and the
budget are the brakes (tune them by D-LL1, never by loosening the validator).

Episode and lesson text is data: it is compared, never followed.
"""
from __future__ import annotations

import datetime as dt
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

import lessons as L

BUDGET = 25             # active lessons per role
DORMANT_DAYS = 21       # unused this long: active -> dormant
RETENTION_DAYS = 30     # episodes older than this are deleted unless a lesson cites them
DECAY = 0.9             # confidence kept per run unused
RAISE = 0.1             # confidence added when a lesson is reconfirmed
LOWER = 0.2             # confidence taken off a flagged lesson
NEW_CONFIDENCE = 0.5    # a proposed lesson's starting confidence
REVIEW_DAYS = 90        # a proposed lesson's review_by, from today
SIMILAR = 0.3           # word overlap (Jaccard) for two episodes to cluster
MIN_SHARED = 3          # and at least this many words in common
DUPLICATE = 0.6         # word overlap for two lessons to merge
CONTRADICT = 0.5        # word overlap, less negations, for two lessons to be in tension
REPEAT = 3              # the same answer this many times is a pattern
STATE = "dream.json"    # in memory/: {"last_run": "<UTC stamp>"}
PROTECTED = ("governance/", "GOVERNANCE.md", "roles/", "ops/", ".github/", "memory/owner.md")

STOP = frozenset("""the and for with that this from into onto was were are has have had not but
its it's our out off any all can could would should will just than then them they there their
what when which who why how one two get got use used using via per also only more most some
such too very yet none nothing about after again before being both each few other same own so
been did does doing over under while issue issues session run ran pr prs""".split())
NEGATION = re.compile(r"\b(?:never|not|no|don't|dont|do\s+not|avoid|stop|without)\b", re.I)
NEG_WORDS = frozenset({"never", "not", "no", "don't", "dont", "avoid", "stop", "without"})
PR_RE = re.compile(r"/pull/(\d+)")


def words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z][a-z0-9_'-]{2,}", (text or "").lower()) if w not in STOP}


def jaccard(a: set, b: set) -> float:
    return len(a & b) / len(a | b) if a and b else 0.0


def episode_text(e: dict) -> str:
    """The words an episode carries that say what happened. Answers and retags carry none."""
    t = e.get("type")
    if t == "note":
        n = e.get("note") or {}
        return " ".join(v for k in ("tried", "surprised", "blocked")
                        if (v := str(n.get(k) or "")) and v != "none")
    if t == "review":
        return str(e.get("asked") or "")
    if t == "act":
        return str(e.get("what") or "")
    if t in ("revert", "closed-unmerged"):
        return str(e.get("title") or "")
    if t == "run":
        return " ".join(str(e.get(k) or "") for k in ("kind", "outcome"))
    return ""


def lesson_words(les: L.Lesson) -> set[str]:
    return words(f"{les.meta.get('title') or ''} {les.body}")


def stamp(t: dt.datetime) -> str:
    return t.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def last_run(memory: Path) -> str | None:
    try:
        v = json.loads((memory / STATE).read_text()).get("last_run")
    except (OSError, ValueError, AttributeError):
        return None
    return v if isinstance(v, str) else None


def _num(v, default: float = 0.0) -> float:
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else default


def _round(x: float) -> float:
    return round(min(1.0, max(0.0, x)), 2)


# ---------------------------------------------------------------- the plan

@dataclass
class Plan:
    since: str | None                 # episodes at or after this stamp are new; None: all
    today: dt.date
    new: list[str] = field(default_factory=list)                  # Replay: new episode ids
    by_type: dict[str, int] = field(default_factory=dict)
    proposed: list[dict] = field(default_factory=list)            # Consolidate
    reconfirmed: list[dict] = field(default_factory=list)
    merges: list[dict] = field(default_factory=list)
    unsourced: int = 0                                            # clusters short of GOV-0055
    flags: list[dict] = field(default_factory=list)               # Reconcile
    decays: list[dict] = field(default_factory=list)              # Forget
    dormant: list[dict] = field(default_factory=list)
    retired: list[dict] = field(default_factory=list)
    expired: list[str] = field(default_factory=list)              # episode ids to delete
    kept_cited: list[str] = field(default_factory=list)           # past retention, but cited
    rehearse: list[dict] = field(default_factory=list)            # Rehearse
    promote: list[dict] = field(default_factory=list)             # Promote
    owner: list[dict] = field(default_factory=list)               # Owner model: proposals
    owner_held: list[dict] = field(default_factory=list)          # kept back by a veto
    uses: dict[str, dict] = field(default_factory=dict)           # id -> {uses, last_used, by}
    given: dict[str, dict] = field(default_factory=dict)          # id -> {given, cited, not_used}
    confidence: dict[str, float] = field(default_factory=dict)    # lesson id -> new value
    status: dict[str, str] = field(default_factory=dict)          # lesson id -> new status

    def as_json(self) -> dict:
        d = {k: v for k, v in self.__dict__.items() if k not in ("today",)}
        d["today"] = self.today.isoformat()
        return d


def cluster(eps: list[dict]) -> list[list[dict]]:
    """Groups of episodes linked by word overlap (single linkage), each of two or more."""
    ws = [words(episode_text(e)) for e in eps]
    parent = list(range(len(eps)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i in range(len(eps)):
        for j in range(i + 1, len(eps)):
            if len(ws[i] & ws[j]) >= MIN_SHARED and jaccard(ws[i], ws[j]) >= SIMILAR:
                parent[find(i)] = find(j)
    groups: dict[int, list[int]] = {}
    for i in range(len(eps)):
        groups.setdefault(find(i), []).append(i)
    return [[eps[i] for i in g] for g in groups.values() if len(g) > 1]


def agreed_words(group: list[dict]) -> set[str]:
    """Words at least two episodes of the group share: what they agree on."""
    seen: dict[str, int] = {}
    for e in group:
        for w in words(episode_text(e)):
            seen[w] = seen.get(w, 0) + 1
    return {w for w, n in seen.items() if n >= 2}


def next_ids(lessons: list[L.Lesson], n: int) -> list[str]:
    top = max((int(x.id[2:]) for x in lessons if L.ID_RE.match(x.id)), default=0)
    return [f"L-{top + i:04d}" for i in range(1, n + 1)]


def _pr_numbers(e: dict) -> set[int]:
    out = {int(m) for m in PR_RE.findall(str(e.get("source") or ""))}
    if isinstance(e.get("pr"), int):
        out.add(e["pr"])
    return out


def plan(lessons: list[L.Lesson], episodes: list[dict], ctx: L.Context, *, since: str | None,
         in_repo_ids: set[str] | None = None, owner_model=None) -> Plan:
    """Every phase's outcome, with no model call. `episodes` are all those the store holds,
    oldest first; those at or after `since` are new. `in_repo_ids` are the ones in
    memory/episodes/ (the only ones retention deletes); None: all of them. `owner_model`:
    memory/owner.md as owner.load() reads it, for its proposals; None: an empty one."""
    today = ctx.today or L.today()
    p = Plan(since=since, today=today)
    by_id = {e["id"]: e for e in episodes}
    # A session being given lessons is not, alone, something to dream over: it is read below
    # for given-not-used, but doesn't make a run start.
    new = [e for e in episodes if (since is None or str(e.get("at") or "") >= since)
           and e.get("type") != "given"]
    p.new = [e["id"] for e in new]
    for e in new:
        p.by_type[str(e.get("type"))] = p.by_type.get(str(e.get("type")), 0) + 1
    if not new:
        return p
    live = [x for x in lessons if not x.errors and x.status != "retired"]
    conf = {x.id: _num(x.meta.get("confidence")) for x in live}
    touched: set[str] = set()

    # 2. Consolidate
    new_ids = set(p.new)
    candidates = []
    for group in cluster(episodes):
        ids = [e["id"] for e in group]
        fresh = [i for i in ids if i in new_ids]
        if not fresh:
            continue
        agreed = agreed_words(group)
        match = next((x for x in live if set(ids) & set(x.meta.get("sources") or [])
                      or jaccard(agreed, lesson_words(x)) >= SIMILAR), None)
        if match is not None:
            added = [i for i in fresh if i not in (match.meta.get("sources") or [])]
            if added and match.id not in touched:
                conf[match.id] = _round(conf[match.id] + RAISE)
                touched.add(match.id)
                p.reconfirmed.append({"id": match.id, "by": added, "confidence": conf[match.id]})
            continue
        if L.source_errors({"sources": ids}, ctx):
            p.unsourced += 1
            continue
        candidates.append((group, agreed))
    for (group, agreed), lid in zip(candidates, next_ids(lessons, len(candidates))):
        roles = sorted({str(e["role"]) for e in group if e.get("type") == "note" and e.get("role")})
        paths = sorted(set.intersection(*[set(e.get("paths") or []) for e in group
                                          if e.get("type") == "note"] or [set()]))
        p.proposed.append({"id": lid, "sources": [e["id"] for e in group], "roles": roles,
                           "paths": paths, "words": sorted(agreed)[:12],
                           "confidence": NEW_CONFIDENCE,
                           "review_by": (today + dt.timedelta(days=REVIEW_DAYS)).isoformat()})

    # 3. Reconcile (before merging, so lessons in tension aren't merged as duplicates)
    tense: set[frozenset] = set()

    def flag(x: L.Lesson, why: str) -> None:
        conf[x.id] = _round(conf[x.id] - LOWER)
        touched.add(x.id)
        p.flags.append({"id": x.id, "why": why, "confidence": conf[x.id]})

    for i, a in enumerate(live):
        for b in live[i + 1:]:
            if a.scope != b.scope or (a.applies("roles") and b.applies("roles")
                                      and not set(a.applies("roles")) & set(b.applies("roles"))):
                continue
            na = bool(NEGATION.search(str(a.meta.get("title") or "")))
            nb = bool(NEGATION.search(str(b.meta.get("title") or "")))
            if na != nb and jaccard(lesson_words(a) - NEG_WORDS, lesson_words(b) - NEG_WORDS) >= CONTRADICT:
                tense.add(frozenset((a.id, b.id)))
                flag(a, f"contradicts {b.id}")
                flag(b, f"contradicts {a.id}")
    for x in live:
        for g in x.meta.get("related_rulings") or [] if isinstance(x.meta.get("related_rulings"), list) else []:
            st = ctx.rulings.get(str(g))
            if st != "in-force":
                flag(x, f"names {g}, which is {st or 'not in governance/INDEX.md'}")
    undone: dict[int, str] = {}
    for e in new:
        if e.get("type") == "closed-unmerged" and isinstance(e.get("number"), int):
            undone[e["number"]] = f"closed unmerged ({e['id']})"
        elif e.get("type") == "revert":
            for n in re.findall(r"#(\d+)", str(e.get("title") or "")):
                undone[int(n)] = f"reverted ({e['id']})"
    for x in live:
        hit = sorted({n for s in x.meta.get("sources") or [] if (e := by_id.get(str(s)))
                      for n in _pr_numbers(e) if n in undone})
        if hit:
            flag(x, "rests on " + ", ".join(f"PR #{n}, {undone[n]}" for n in hit))

    # Consolidate, continued: merge near-duplicates into the stronger lesson
    gone: set[str] = set()
    for i, a in enumerate(live):
        for b in live[i + 1:]:
            if a.id in gone or b.id in gone or a.scope != b.scope or frozenset((a.id, b.id)) in tense:
                continue
            if jaccard(lesson_words(a), lesson_words(b)) >= DUPLICATE:
                keep, drop = (a, b) if conf[a.id] >= conf[b.id] else (b, a)
                gone.add(drop.id)
                conf[keep.id] = max(conf[keep.id], conf[drop.id])
                touched.add(keep.id)
                srcs = list(dict.fromkeys([*(keep.meta.get("sources") or []), *(drop.meta.get("sources") or [])]))
                p.merges.append({"keep": keep.id, "drop": drop.id, "sources": srcs,
                                 "supersedes": list(dict.fromkeys([*(keep.meta.get("supersedes") or []), drop.id])),
                                 "confidence": conf[keep.id]})
                p.status[drop.id] = "retired"

    # 4. Forget: first, the uses cited since the last run (#1187)
    lives = {x.id: x for x in live if x.id not in gone}
    for e in new:
        if e.get("type") != "cite":
            continue
        day = L._date(str(e.get("at") or "")[:10])
        for lid in dict.fromkeys(str(i) for i in e.get("lessons") or []):
            x = lives.get(lid)
            if x is None or day is None:
                continue
            u = p.uses.setdefault(lid, {"uses": int(_num(x.meta.get("uses"))), "last_used": None, "by": []})
            u["uses"] += 1
            u["by"].append(e["id"])
            prev = L._date(u["last_used"] or x.meta.get("last_used"))
            u["last_used"] = max(day, prev).isoformat() if prev else day.isoformat()
    for lid in p.uses:
        touched.add(lid)
    p.given = given_not_used(episodes, {x.id for x in live})
    ref_run = L._date((since or "")[:10]) if since else None
    for x in live:
        if x.id in gone:
            continue
        used = L._date(p.uses[x.id]["last_used"]) if x.id in p.uses else L._date(x.meta.get("last_used"))
        if x.status == "active":
            idle_from = used or L._date(x.meta.get("created")) or today
            if (today - idle_from).days > DORMANT_DAYS:
                p.status[x.id] = "dormant"
                p.dormant.append({"id": x.id, "why": f"unused since {idle_from.isoformat()}"})
            elif x.id not in touched and (used is None or (ref_run and used < ref_run)):
                conf[x.id] = _round(conf[x.id] * DECAY)
                p.decays.append({"id": x.id, "confidence": conf[x.id]})
        elif x.status == "dormant":
            rb = L._date(x.meta.get("review_by"))
            if rb and rb < today:
                p.status[x.id] = "retired"
                p.retired.append({"id": x.id, "why": f"dormant past review_by {rb.isoformat()}"})
    active = [x for x in live if p.status.get(x.id, x.status) == "active"]
    # A lesson for all roles counts against every role's budget.
    for role in sorted({r for x in active for r in x.applies("roles")}) or (["all"] if active else []):
        mine = [x for x in active if p.status.get(x.id, x.status) == "active"
                and (role == "all" or not x.applies("roles") or role in x.applies("roles"))]
        over = len(mine) - BUDGET
        if over > 0:
            rank = sorted(mine, key=lambda x: (conf[x.id], _num(x.meta.get("uses")),
                                               str(x.meta.get("last_used") or ""), x.id))
            for x in rank[:over]:
                p.status[x.id] = "dormant"
                p.dormant.append({"id": x.id, "why": f"{role} is over its budget of {BUDGET}"})
    cited = {str(s) for x in lessons for s in (x.meta.get("sources") or [])
             if isinstance(x.meta.get("sources"), list)}
    cited |= {s for c in p.proposed for s in c["sources"]}
    # 7. Owner model (#1188), worked out here so the episodes its entries and proposals cite
    # are kept past retention, as a lesson's are.
    import owner as O
    om = owner_model or O.Model()
    p.owner, p.owner_held = O.proposals(om, episodes, new_ids, ctx.owner, today)
    cited |= {s for e in om.entries for s in e.sources} | {s for c in p.owner for s in c["sources"]}
    cutoff = (today - dt.timedelta(days=RETENTION_DAYS)).isoformat()
    for e in episodes:
        if str(e.get("at") or "")[:10] >= cutoff or (in_repo_ids is not None and e["id"] not in in_repo_ids):
            continue
        (p.kept_cited if e["id"] in cited else p.expired).append(e["id"])

    # 5. Rehearse
    p.rehearse = [{"id": x.id, "title": x.meta.get("title")} for x in live
                  if p.status.get(x.id, x.status) == "proposed" and not x.meta.get("eval_case")]
    p.rehearse += [{"id": c["id"], "title": None} for c in p.proposed]

    # 6. Promote
    same: dict[str, list[dict]] = {}
    for e in episodes:
        if e.get("type") == "answer" and e.get("took_default") is True:
            same.setdefault(str(e.get("domain") or "?"), []).append(e)
    for dom, eps in sorted(same.items()):
        if len(eps) >= REPEAT and any(e["id"] in new_ids for e in eps):
            p.promote.append({"pattern": "same answer", "domain": dom,
                              "why": f"the owner took the default {len(eps)} times in {dom}",
                              "episodes": [e["id"] for e in eps]})
    repeats = [e for e in episodes if e.get("type") == "act" and e.get("tag") == "repeat answer"]
    if len(repeats) >= REPEAT and any(e["id"] in new_ids for e in repeats):
        p.promote.append({"pattern": "repeat answer", "why": f"{len(repeats)} owner acts tagged repeat answer",
                          "episodes": [e["id"] for e in repeats]})
    for x in live:
        out = [q for q in x.applies("paths") if q.startswith(PROTECTED)]
        if out:
            p.promote.append({"pattern": "outside jurisdiction", "lesson": x.id,
                              "why": f"{x.id} applies to {', '.join(out)}, which no role edits"})

    for x in live:
        if abs(conf[x.id] - _num(x.meta.get("confidence"))) > 1e-9:
            p.confidence[x.id] = conf[x.id]
    return p


def _refs(e: dict) -> set[tuple[str, int]]:
    """The (repo, number) pairs a given or cite episode is about: its issue, PR and, for a
    merged PR's citation, the issues it closes."""
    repo = str(e.get("repo") or "").lower()
    nums = [e.get(k) for k in ("issue", "pr", "number")] + list(e.get("closes") or [])
    return {(repo, n) for n in nums if isinstance(n, int) and not isinstance(n, bool)}


def given_not_used(episodes: list[dict], ids: set[str]) -> dict[str, dict]:
    """For each lesson in `ids` that a session was given: how many sessions were given it,
    how many of those cited it on their issue or PR (at or after being given), and the rest,
    given-not-used (#1187). Reads every given episode the store holds, which is up to
    RETENTION_DAYS of them."""
    cites = [e for e in episodes if e.get("type") == "cite"]
    out: dict[str, dict] = {}
    for g in episodes:
        if g.get("type") != "given":
            continue
        refs, at = _refs(g), str(g.get("at") or "")
        for lid in dict.fromkeys(str(i) for i in g.get("lessons") or []):
            if lid not in ids:
                continue
            c = out.setdefault(lid, {"given": 0, "cited": 0, "not_used": 0})
            c["given"] += 1
            if refs and any(lid in (e.get("lessons") or []) and str(e.get("at") or "") >= at
                            and _refs(e) & refs for e in cites):
                c["cited"] += 1
            else:
                c["not_used"] += 1
    return dict(sorted(out.items()))


# ---------------------------------------------------------------- the three lines (#1192)

def lines(p: Plan) -> dict:
    """The run's three lines for the Desk's Briefing (FEAT-22), ids and counts only:
    learned (lessons proposed and reconfirmed), forgot (lessons to dormant and retired, and
    episodes deleted) and proposing (patterns for the owner, and owner-model entries).
    `swarm dream --apply` keeps them in memory/dream.json beside last_run."""
    return {"learned": {"proposed": [c["id"] for c in p.proposed],
                        "reconfirmed": [r["id"] for r in p.reconfirmed]},
            "forgot": {"dormant": [d["id"] for d in p.dormant], "retired": [r["id"] for r in p.retired],
                       "episodes": len(p.expired)},
            "proposing": {"patterns": [q["why"] for q in p.promote], "owner": [c["id"] for c in p.owner]}}


def last_lines(memory: Path) -> dict | None:
    """The last applied run's three lines and when it ran, or None before the first."""
    try:
        v = json.loads((memory / STATE).read_text())
    except (OSError, ValueError):
        return None
    if not isinstance(v, dict) or not isinstance(v.get("last_run"), str) or not isinstance(v.get("lines"), dict):
        return None
    return {"last_run": v["last_run"], **v["lines"]}


# ---------------------------------------------------------------- applying it

def set_fields(text: str, values: dict[str, str]) -> str:
    """text with each top-level frontmatter key set to its value, written inline. A block list
    under the key is replaced; a key that isn't there is added before the closing ---."""
    lines = text.split("\n")
    end = next(i for i in range(1, len(lines)) if lines[i].strip() == "---")
    head, rest = lines[1:end], lines[end:]
    for k, v in values.items():
        i = next((n for n, ln in enumerate(head) if re.match(rf"{re.escape(k)}:(\s|$)", ln)), None)
        if i is None:
            head.append(f"{k}: {v}")
            continue
        j = i + 1
        while j < len(head) and (head[j].startswith((" ", "\t", "-")) or not head[j].strip()):
            j += 1
        head[i:j] = [f"{k}: {v}"]
    return "\n".join([lines[0], *head, *rest])


def inline(xs: list[str]) -> str:
    return "[" + ", ".join(xs) + "]"


def apply(p: Plan, lessons: list[L.Lesson], memory: Path, now: dt.datetime) -> list[str]:
    """Write the plan's mechanical changes into memory/: confidence, status, merges and
    expired episodes, then memory/dream.json and memory/INDEX.md. Proposed lessons aren't
    written: the librarian drafts them from p.proposed. Returns what it changed."""
    done: list[str] = []
    by_id = {x.id: x for x in lessons}
    updates: dict[str, dict[str, str]] = {}
    for lid, c in p.confidence.items():
        updates.setdefault(lid, {})["confidence"] = f"{c:g}"
    for lid, u in p.uses.items():
        updates.setdefault(lid, {}).update(uses=str(u["uses"]), last_used=u["last_used"])
    for lid, st in p.status.items():
        updates.setdefault(lid, {})["status"] = st
    for m in p.merges:
        updates.setdefault(m["keep"], {}).update(sources=inline(m["sources"]), supersedes=inline(m["supersedes"]))
    for lid, vals in sorted(updates.items()):
        x = by_id.get(lid)
        if x is None:
            continue
        x.path.write_text(set_fields(x.path.read_text(), vals))
        done.append(f"{x.path.name}: " + ", ".join(f"{k} {v}" for k, v in vals.items()))
    gone = set(p.expired)
    d = memory / "episodes"
    for f in sorted(d.glob("*.jsonl")) if gone and d.is_dir() else []:
        keep, dropped = [], 0
        for line in f.read_text().splitlines():
            try:
                eid = json.loads(line).get("id")
            except (ValueError, AttributeError):
                eid = None
            if eid in gone:
                dropped += 1
            else:
                keep.append(line)
        if dropped:
            if keep:
                f.write_text("".join(ln + "\n" for ln in keep))
            else:
                f.unlink()
            done.append(f"episodes/{f.name}: deleted {dropped} past {RETENTION_DAYS} days")
    (memory / STATE).write_text(json.dumps({"last_run": stamp(now), "lines": lines(p)}, indent=2) + "\n")
    (memory / "INDEX.md").write_text(L.index_text(L.load_all(memory / "lessons")))
    return done


# ---------------------------------------------------------------- the report

def report(p: Plan) -> str:
    since = p.since or "the start"
    if not p.new:
        return f"swarm dream: no new episodes since {since}: nothing to dream, no model call, no PR."
    kinds = ", ".join(f"{n} {t}" for t, n in sorted(p.by_type.items()))
    out = [f"Dream plan, {p.today.isoformat()} (episodes since {since})", "",
           f"1. Replay: {len(p.new)} new episodes ({kinds})."]

    def lst(items: list[str], none: str) -> list[str]:
        return [f"   - {i}" for i in items] or [f"   - {none}"]

    out.append(f"2. Consolidate: {len(p.proposed)} proposed, {len(p.reconfirmed)} reconfirmed, "
               f"{len(p.merges)} merged; {p.unsourced} cluster(s) short of GOV-0055's sources.")
    out += lst([f"propose {c['id']} from {', '.join(c['sources'])}"
                + (f" (roles {', '.join(c['roles'])})" if c["roles"] else "")
                + (f"; shared words: {' '.join(c['words'])}" if c["words"] else "") for c in p.proposed]
               + [f"reconfirm {r['id']} by {', '.join(r['by'])}: confidence {r['confidence']:g}"
                  for r in p.reconfirmed]
               + [f"merge {m['drop']} into {m['keep']}: confidence {m['confidence']:g}" for m in p.merges],
               "nothing")
    out.append(f"3. Reconcile: {len(p.flags)} flagged.")
    out += lst([f"{f['id']} {f['why']}: confidence {f['confidence']:g}" for f in p.flags], "nothing")
    out.append(f"4. Forget: {len(p.uses)} used, {len(p.decays)} decayed, {len(p.dormant)} to dormant, "
               f"{len(p.retired)} retired, {len(p.expired)} episodes deleted"
               + (f" ({len(p.kept_cited)} past retention kept: a lesson cites them)" if p.kept_cited else "") + ".")
    out += lst([f"used {lid}: {u['uses']} uses, last {u['last_used']} ({', '.join(u['by'])})"
                for lid, u in p.uses.items()]
               + [f"decay {d['id']}: confidence {d['confidence']:g}" for d in p.decays]
               + [f"dormant {d['id']}: {d['why']}" for d in p.dormant]
               + [f"retire {r['id']}: {r['why']}" for r in p.retired], "nothing")
    if p.given:
        out.append("   Given, not used (report only; don't act on one week of it):")
        out += [f"   - {lid}: given {c['given']}, cited {c['cited']}, not used {c['not_used']}"
                for lid, c in p.given.items()]
    out.append(f"5. Rehearse: {len(p.rehearse)} proposed lesson(s) need an eval case.")
    out += lst([r["id"] for r in p.rehearse], "none")
    out.append(f"6. Promote: {len(p.promote)} pattern(s) for the owner.")
    out += lst([q["why"] for q in p.promote], "none")
    out.append(f"7. Owner model: {len(p.owner)} proposed entr{'y' if len(p.owner) == 1 else 'ies'} for "
               f"memory/owner.md. None reaches a session until the owner adds it (GOV-0056).")
    out += lst([f"propose {c['id']} from {', '.join(c['sources'])}"
                + (f" ({', '.join(c['links'])})" if c["links"] else "")
                + (f"; shared words: {' '.join(c['words'])}" if c["words"] else "") for c in p.owner]
               + [f"held back: {', '.join(h['sources'])} is like {h['veto']}, vetoed; not proposed "
                  f"before {h['until']}" for h in p.owner_held], "none")
    return "\n".join(out)
