"""Escalation (#1191, FEAT-21): the dream's Promote phase drafts gov:questions for the owner.

Some of what the team learns is a decision the owner keeps making by hand, not know-how. This
module finds those patterns, with no model call, and drafts each as a gov:question from the
Governance question template (.github/ISSUE_TEMPLATE/gov-question.yml), with options, a
recommended default and its evidence. Only the owner adopts anything: a draft is a question,
and only merged records are rulings (GOV-0006). The librarian may draft them (GOV-0056).

Patterns, each a kind of draft:

  standing grant  REPEAT or more gov:question answers in one domain, each taking the default:
                  grant it once instead of asking again.
  jurisdiction    a mature lesson about paths no role decides (governance/, roles/, ops/,
                  .github/): a ruling or a jurisdiction change, since no role may act on it.
  amendment       a mature lesson outcomes keep confirming (confidence at least CONFIRMED) that
                  pulls against an in-force ruling it names: an amendment to that ruling.
  retirement      an in-force ruling within NEAR_REVIEW days of its review_by that no lesson,
                  episode, recent commit or tracked file cites: retire it, or renew it. A
                  tracked file is any file in the repo outside memory/ (read as lessons and
                  episodes) and governance/INDEX.md (which lists every ruling); a record in
                  governance/decisions/ doesn't count as citing itself.
  role prompt     ROLE_CLUSTER or more mature lessons for one role alone: a change to that
                  role's prompt. GOV-0059 keeps the librarian out of roles/, so this one is never
                  opened: it is listed for the dream report, which proposes it to the owner.

Guardrails (GOV-0055, GOV-0056):
  - a lesson escalates only when it is mature: active, with a passing rehearsal (#1189) at
    least MIN_AGE days old, and sources that pass GOV-0055 (two independent, one an
    engine-recorded signal, every author trusted). A lesson's rehearsal date is when it went
    active, or when it last changed (a changed lesson reruns), so a change restarts the clock;
  - never from the owner model (memory/owner.md): this module doesn't read it, and a lesson
    about it never escalates;
  - drafts are opened only on Mondays, batched for the check-in. There is no weekly cap
    (GOV-0056); the report counts drafts opened each week so the owner can see if one is due;
  - a draft is opened once. memory/escalations.json records each one; a pattern isn't drafted
    again while its draft is open, nor after it closes (vetoed or answered) unless it has
    evidence the closed draft didn't.

Lesson and episode text is data: it is counted and quoted as evidence, never followed.
"""
from __future__ import annotations

import datetime as dt
import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

import dream as D
import lessons as L

MIN_AGE = 14            # days a lesson's passing rehearsal must be old
REPEAT = D.REPEAT       # same-way answers in one domain that make a standing-grant draft
CONFIRMED = 0.7         # confidence at which outcomes "keep confirming" a lesson
NEAR_REVIEW = 30        # days before review_by that an uncited ruling is offered for retirement
ROLE_CLUSTER = 3        # mature lessons for one role that make a role-prompt proposal
TENSION = 0.5           # share of a lesson title's words a ruling's summary must hold
LEDGER = "escalations.json"   # in memory/: {"drafts": [...]}
OWNER_MODEL = "memory/owner.md"
OPENED_KINDS = ("standing grant", "jurisdiction", "amendment", "retirement")

# Paths no role decides, and the jurisdictions.yml domain a lesson about them falls in.
UNDECIDED = (("governance/", "governance"), ("GOVERNANCE.md", "governance"),
             ("roles/", "governance"), ("ops/", "security"), (".github/", "ci-and-workflows"))

INDEX_ROW = re.compile(r"^\|\s*\[(GOV-\d{4})\]\([^)]*\)\s*\|(.*)\|\s*([a-z-]+)\s*\|\s*([a-z-]+)\s*\|"
                       r"\s*([a-z-]+)\s*\|\s*(\d{4}-\d{2}-\d{2})\s*\|\s*$")
GOV_ID = re.compile(r"\bGOV-\d{4}\b")


@dataclass
class Ruling:
    id: str
    summary: str
    domain: str
    status: str
    review_by: dt.date


def rulings(index: Path | None = None) -> dict[str, Ruling]:
    """Every row of governance/INDEX.md, by id."""
    try:
        text = (index or L.GOV_INDEX).read_text()
    except OSError:
        return {}
    out = {}
    for line in text.splitlines():
        m = INDEX_ROW.match(line.strip())
        if m:
            out[m.group(1)] = Ruling(m.group(1), m.group(2).strip(), m.group(3), m.group(5),
                                     dt.date.fromisoformat(m.group(6)))
    return out


@dataclass
class Draft:
    kind: str
    key: str                 # the pattern's subject: one draft per key while it is open
    title: str
    domain: str
    evidence: list[str]      # lesson ids, episode ids, question numbers, ruling ids
    context: str
    options: list[str]
    recommendation: str
    default: str
    reversibility: str = "two-way"
    blast: str = "repo"
    precedent: str = ""
    links: list[str] = field(default_factory=list)   # the evidence's source links


# ---------------------------------------------------------------- guardrails

def active_since(les: L.Lesson) -> dt.date | None:
    """When the lesson's passing rehearsal ran: it went active then, or last changed."""
    r = les.meta.get("rehearsal")
    if not isinstance(r, dict) or r.get("result") not in ("promoted", "confirmed"):
        return None
    return L._date(r.get("at"))


def maturity_errors(les: L.Lesson, ctx: L.Context) -> list[str]:
    """Why this lesson may not escalate; [] if it may (GOV-0056's maturity rules)."""
    if les.errors:
        return list(les.errors)
    errs = []
    if les.status != "active":
        errs.append(f"is {les.status or 'without a status'}, not active")
    since = active_since(les)
    if since is None:
        errs.append("has no passing rehearsal")
    elif (ctx.today - since).days < MIN_AGE:
        errs.append(f"has been active {(ctx.today - since).days} days, under {MIN_AGE}")
    errs += L.source_errors(les.meta, ctx)
    if any(p.lstrip("/") == OWNER_MODEL for p in les.applies("paths")):
        errs.append("is about the owner model, which never escalates unless the owner asks")
    return errs


# ---------------------------------------------------------------- the patterns

def _words(text: str) -> set[str]:
    return D.words(text) - D.NEG_WORDS


def _negated(text: str) -> bool:
    return bool(D.NEGATION.search(text or ""))


def cited_rulings(lessons: list[L.Lesson], episodes: list[dict], texts: list[str] = ()) -> set[str]:
    """Ruling ids any lesson, episode or other text (e.g. recent commit messages) names."""
    out: set[str] = set()
    for x in lessons:
        rr = x.meta.get("related_rulings")
        out |= {str(g) for g in rr} if isinstance(rr, list) else set()
        out |= set(GOV_ID.findall(f"{x.meta.get('title') or ''} {x.body}"))
    for e in episodes:
        out |= set(GOV_ID.findall(json.dumps(e)))
    for t in texts:
        out |= set(GOV_ID.findall(t or ""))
    return out


def cited_in_files(root: Path, files: list[str]) -> set[str]:
    """Ruling ids the repo's tracked files name (paths relative to root), such as role prompts,
    launcher code, PRODUCT.md and other rulings' records. memory/ is left out: its lessons and
    episodes are counted on their own terms, and its escalation ledger names the very rulings
    it drafted. governance/INDEX.md names every ruling, and a record doesn't cite itself."""
    out: set[str] = set()
    for rel in files:
        if rel.startswith("memory/") or rel == "governance/INDEX.md":
            continue
        try:
            text = (root / rel).read_text(encoding="utf-8", errors="replace")
        except (OSError, ValueError):
            continue
        ids = set(GOV_ID.findall(text))
        if rel.startswith("governance/decisions/"):
            ids -= set(GOV_ID.findall(Path(rel).name))
        out |= ids
    return out


def _lesson_links(les: L.Lesson, ctx: L.Context) -> list[str]:
    return [str(e.get("source")) for s in les.meta.get("sources") or []
            if (e := ctx.episodes.get(str(s))) and e.get("source")]


def _lesson_ev(les: L.Lesson) -> list[str]:
    return [les.id, *[str(s) for s in les.meta.get("sources") or []]]


def find(lessons: list[L.Lesson], episodes: list[dict], ctx: L.Context, rules: dict[str, Ruling],
         cited: set[str]) -> tuple[list[Draft], list[dict]]:
    """(drafts, held): every pattern that may escalate now, and each lesson held back from
    escalating with why. Nothing here reads the owner model."""
    today = ctx.today
    drafts: list[Draft] = []
    held: list[dict] = []
    mature: list[L.Lesson] = []
    for x in lessons:
        if x.errors or x.status in ("retired", "dormant", "proposed"):
            continue
        errs = maturity_errors(x, ctx)
        if errs:
            held.append({"id": x.id, "why": errs})
        else:
            mature.append(x)

    # standing grant: the owner took the default REPEAT times in one domain
    same: dict[str, list[dict]] = {}
    for e in episodes:
        if e.get("type") == "answer" and e.get("took_default") is True and e.get("domain"):
            same.setdefault(str(e["domain"]), []).append(e)
    for dom, eps in sorted(same.items()):
        if len(eps) < REPEAT:
            continue
        qs = sorted({e["number"] for e in eps if isinstance(e.get("number"), int)})
        refs = ", ".join(f"#{n}" for n in qs)
        drafts.append(Draft(
            kind="standing grant", key=f"standing grant:{dom}", domain=dom,
            title=f"GOV-Q (draft): A standing grant for {dom} questions the owner answers with the default?",
            evidence=[e["id"] for e in eps] + [f"#{n}" for n in qs],
            links=[str(e["source"]) for e in eps if e.get("source")],
            context=(f"The owner answered {len(eps)} `{dom}` questions ({refs}) by taking the asker's "
                     f"default each time. A standing grant would let a role act on its stated default "
                     f"for questions like these, and report it, instead of asking."),
            options=[f"**Standing grant.** In `{dom}`, for a two-way question like {refs}, the asking "
                     f"role proceeds on its stated default and lists it under delegated authority in "
                     f"the next daily report. One-way and blocking questions still ask.",
                     "**Keep asking.** Every such question still waits for the owner's answer.",
                     f"**Narrower grant.** As option 1, but only for the questions' shared subject, "
                     f"which the owner names in the answer."],
            recommendation=("Option 1. The owner made the same call each time, so asking again costs "
                            "the owner's time without changing the outcome. Every use is reported, "
                            "and the grant can be withdrawn."),
            default="Option 2: nothing changes, and these questions keep waiting for the owner.",
            precedent="GOV-0056 lets the librarian draft this. No ruling grants standing authority in "
                      f"`{dom}` for questions like these."))

    # jurisdiction: a mature lesson about paths no role decides
    for x in mature:
        hit = [(p, dom) for p in x.applies("paths") for pre, dom in UNDECIDED if p.startswith(pre)]
        if not hit:
            continue
        dom = hit[0][1]
        paths = ", ".join(f"`{p}`" for p, _ in hit)
        drafts.append(Draft(
            kind="jurisdiction", key=f"jurisdiction:{x.id}", domain=dom,
            title=f"GOV-Q (draft): Should {x.id} become a ruling? It applies to {', '.join(p for p, _ in hit)}",
            evidence=_lesson_ev(x), links=_lesson_links(x, ctx),
            context=(f"Lesson {x.id} (\"{x.meta.get('title')}\") applies to {paths}, which no role "
                     f"decides under `jurisdictions.yml`. It is active, rehearsed and backed by "
                     f"independent sources, but no role may act on it."),
            options=[f"**A ruling.** Record {x.id}'s guidance as a decision in `{dom}`.",
                     f"**A jurisdiction change.** Let a named role decide this in `{dom}`; the owner "
                     f"edits `jurisdictions.yml`.",
                     f"**Leave it.** {x.id} stays a lesson: guidance only, under the rulings."],
            recommendation=f"Option 1. The lesson keeps holding, and only a ruling can bind here.",
            default=f"Option 3: {x.id} stays a lesson.",
            blast="repo",
            precedent=f"GOV-0056 lets the librarian draft this; GOV-0059 keeps it out of these paths."))

    # amendment: a confirmed lesson that pulls against an in-force ruling it names
    for x in mature:
        if D._num(x.meta.get("confidence")) < CONFIRMED:
            continue
        title = str(x.meta.get("title") or "")
        tw = _words(title)
        rr = x.meta.get("related_rulings") if isinstance(x.meta.get("related_rulings"), list) else []
        for g in rr:
            r = rules.get(str(g))
            if r is None or r.status != "in-force" or not tw:
                continue
            if _negated(title) == _negated(r.summary) or len(tw & _words(r.summary)) / len(tw) < TENSION:
                continue
            drafts.append(Draft(
                kind="amendment", key=f"amendment:{x.id}:{r.id}", domain=r.domain,
                title=f"GOV-Q (draft): Amend {r.id}? Lesson {x.id} keeps pulling against it",
                evidence=[*_lesson_ev(x), r.id], links=_lesson_links(x, ctx),
                context=(f"Lesson {x.id} (\"{title}\", confidence {D._num(x.meta.get('confidence')):g}) "
                         f"names {r.id} and seems to pull against it: {r.summary} Outcomes keep "
                         f"confirming the lesson. The ruling wins until the owner says otherwise."),
                options=[f"**Amend {r.id}** to take in what {x.id} says.",
                         f"**Keep {r.id}.** The librarian retires or rewrites {x.id}.",
                         f"**Both stand.** The owner explains on this question why they don't conflict."],
                recommendation=f"Option 1, if the evidence holds on reading: outcomes keep confirming {x.id}.",
                default=f"Option 2 in effect: {r.id} stands, and sessions follow it over {x.id}.",
                precedent=f"{r.id} is the ruling in question; GOV-0056 lets the librarian draft this."))

    # retirement: an in-force ruling near its review_by that nobody cites
    for r in sorted(rules.values(), key=lambda r: r.id):
        if r.status != "in-force" or r.id in cited or not 0 <= (r.review_by - today).days <= NEAR_REVIEW:
            continue
        drafts.append(Draft(
            kind="retirement", key=f"retirement:{r.id}", domain=r.domain,
            title=f"GOV-Q (draft): Retire {r.id}? Nothing in the repo or memory cites it, and its review is due {r.review_by.isoformat()}",
            evidence=[r.id, f"review_by {r.review_by.isoformat()}"],
            context=(f"{r.id} ({r.summary}) is due for review on {r.review_by.isoformat()}. No lesson, "
                     f"no episode in memory, no commit from the last 90 days and no tracked file "
                     f"in the repo (outside its own record and governance/INDEX.md) cites it. "
                     f"Something may still rely on it without naming it."),
            options=[f"**Retire {r.id}.** It lapses at its review date.",
                     f"**Renew {r.id}** with a new review_by.",
                     f"**Replace {r.id}** with a narrower ruling the owner describes."],
            recommendation=(f"Option 1, unless the owner still relies on it: nothing in the repo or "
                            f"memory names it."),
            default=f"Option 2 in effect: {r.id} stays in force until the owner reviews it.",
            precedent=f"{r.id} itself; GOV-0056 lets the librarian draft this."))

    # role prompt: a cluster of mature lessons for one role alone (never opened, GOV-0059)
    by_role: dict[str, list[str]] = {}
    for x in mature:
        roles = x.applies("roles")
        if len(roles) == 1:
            by_role.setdefault(roles[0], []).append(x.id)
    for role, ids in sorted(by_role.items()):
        if len(ids) >= ROLE_CLUSTER:
            drafts.append(Draft(
                kind="role prompt", key=f"role prompt:{role}", domain="governance",
                title=f"Fold {', '.join(ids)} into roles/{role}.md",
                evidence=ids, context=f"{len(ids)} mature lessons apply to the {role} alone.",
                options=[], recommendation="", default=""))
    return drafts, held


# ---------------------------------------------------------------- the ledger and the batch

def load_ledger(memory: Path) -> list[dict]:
    try:
        v = json.loads((memory / LEDGER).read_text()).get("drafts")
    except (OSError, ValueError, AttributeError):
        return []
    return [d for d in v if isinstance(d, dict)] if isinstance(v, list) else []


def save_ledger(memory: Path, ledger: list[dict]) -> None:
    (memory / LEDGER).write_text(json.dumps({"drafts": ledger}, indent=2) + "\n")


def blocked_by(d: Draft, ledger: list[dict]) -> dict | None:
    """The earlier draft that stops this one: one for the same pattern still open, or one
    closed (vetoed or answered) whose evidence covers all of this one's."""
    for e in ledger:
        if e.get("key") != d.key:
            continue
        if e.get("state") != "closed" or set(d.evidence) <= set(e.get("evidence") or []):
            return e
    return None


def monday(day: dt.date) -> dt.date:
    return day - dt.timedelta(days=day.weekday())


@dataclass
class Batch:
    today: dt.date
    open_now: list[Draft]           # opened today: it's Monday
    waiting: list[Draft]            # found midweek: they wait for Monday
    blocked: list[tuple[Draft, dict]]
    proposals: list[Draft]          # role prompt: for the dream report only (GOV-0059)
    held: list[dict]
    weeks: list[tuple[str, int]]    # (Monday, drafts opened that week), newest first
    warnings: list[str] = field(default_factory=list)   # e.g. a shallow history, unread files

    def as_json(self) -> dict:
        return {"today": self.today.isoformat(),
                "open_now": [asdict(d) for d in self.open_now],
                "waiting": [asdict(d) for d in self.waiting],
                "blocked": [{"key": d.key, "by": e.get("issue")} for d, e in self.blocked],
                "proposals": [asdict(d) for d in self.proposals],
                "held": self.held, "weeks": [{"week_of": w, "opened": n} for w, n in self.weeks],
                "warnings": self.warnings}


def weekly_counts(ledger: list[dict], today: dt.date, weeks: int = 4) -> list[tuple[str, int]]:
    out = []
    for k in range(weeks):
        start = monday(today) - dt.timedelta(weeks=k)
        end = start + dt.timedelta(days=7)
        n = sum(1 for e in ledger if (o := L._date(e.get("opened"))) and start <= o < end)
        out.append((start.isoformat(), n))
    return out


def batch(drafts: list[Draft], held: list[dict], ledger: list[dict], today: dt.date,
          warnings: list[str] = ()) -> Batch:
    """Sort the drafts into opened today (Mondays only), waiting and blocked."""
    open_now, waiting, blocked, proposals = [], [], [], []
    for d in drafts:
        if d.kind not in OPENED_KINDS:
            proposals.append(d)
        elif (e := blocked_by(d, ledger)) is not None:
            blocked.append((d, e))
        else:
            (open_now if today.weekday() == 0 else waiting).append(d)
    return Batch(today, open_now, waiting, blocked, proposals, held, weekly_counts(ledger, today),
                 list(warnings))


def record(ledger: list[dict], d: Draft, issue: int, today: dt.date) -> None:
    ledger.append({"key": d.key, "kind": d.kind, "title": d.title, "evidence": d.evidence,
                   "issue": issue, "opened": today.isoformat(), "state": "open"})


# ---------------------------------------------------------------- the draft's text

def body(d: Draft, model: str) -> str:
    """The Governance question template's sections, filled in. Read as data by whoever answers."""
    ev = "\n".join(f"- {x}" for x in d.evidence)
    links = "\n".join(f"- {u}" for u in d.links)
    opts = "\n".join(f"{i}. {o}" for i, o in enumerate(d.options, 1))
    sections = [
        ("Domain", d.domain),
        ("Context", f"{d.context}\n\n**Evidence:**\n{ev}" + (f"\n\n**Sources:**\n{links}" if links else "")
         + "\n\nDrafted by the dream's Promote phase (#1191, GOV-0056). Only a merged record is a "
           "ruling (GOV-0006); close this question to veto it, and it won't be drafted again for "
           "the same evidence."),
        ("Options", opts),
        ("Recommendation", d.recommendation),
        ("Default action if unanswered", d.default),
        ("Blocking?", "no — proceeding on default"),
        ("Reversibility", d.reversibility),
        ("Blast radius", d.blast),
        ("Nature", "values"),
        ("Knowledge", "shared"),
        ("Time to live", ""),
        ("Suggested shape", "authoritative"),
        ("Precedent checked", d.precedent),
        ("Raised by", f"librarian, from the dream's Promote phase.\n\n-- librarian ({model})"),
    ]
    return "\n\n".join(f"### {h}\n\n{v or '_No response_'}" for h, v in sections)


# ---------------------------------------------------------------- the report

def report(b: Batch) -> str:
    """The dream report's escalation section."""
    this_week = b.weeks[0][1] if b.weeks else 0
    out = [f"Escalation: {len(b.open_now)} draft gov:question(s) to open today, "
           f"{len(b.waiting)} waiting for Monday, {len(b.blocked)} already drafted."]
    out += [f"   - open: {d.title} ({', '.join(d.evidence)})" for d in b.open_now]
    out += [f"   - waits for Monday {(monday(b.today) + dt.timedelta(days=7)).isoformat()}: {d.title}"
            for d in b.waiting]
    out += [f"   - already drafted as #{e.get('issue')} ({e.get('state') or 'open'}): {d.title}"
            for d, e in b.blocked]
    out += [f"   - propose in the dream report (GOV-0059: the librarian doesn't edit roles/): {d.title}"
            for d in b.proposals]
    out += [f"   - held: {h['id']} {'; '.join(h['why'])}" for h in b.held]
    out += [f"   - warning: {w}" for w in b.warnings]
    out.append("   Drafts opened per week: " + ", ".join(f"week of {w}: {n}" for w, n in b.weeks)
               + f" (this week {this_week}; no weekly cap, GOV-0056).")
    return "\n".join(out)
