"""The owner model (#1188, FEAT-18): what the team knows about how the owner likes to work.

**Where (GOV-0052).** One public file, memory/owner.md, with short entries: preferences (style,
format, what to leave out), standing patterns (what the owner reliably approves or rejects),
vocabulary and don'ts. Because it is public, an entry holds working preferences only: never
the owner's health, family, finances, contacts or whereabouts. validate() rejects an entry that
carries contact details or names one of those topics.

**Who changes it (GOV-0056).** Every change needs the owner's approval as an approved ask:
merger.py lists memory/owner.md as a protected path, so the merger never merges a PR that
touches it and only the owner does. The librarian never writes it (GOV-0059): its dream
proposes additions in the dream report (proposals()), and nothing reaches a session until the
owner has put it in the file. The owner can also edit the file directly.

**Format.**

    ## Entries

    ### O-0001: Plain words in reports
    - kind: preference
    - roles: builder, docs
    - sources: #1150, act:12345
    - date: 2026-11-18

    One or two sentences saying the preference.

    ## Vetoed

    - O-0002, 2026-11-18: the vetoed entry's title and text

kind is one of KINDS. roles are the roles besides the planner the entry is for; the planner gets
the whole file and every other role only the entries that name it (GOV-0056), so an entry with
no roles reaches the planner alone. sources cite the episodes it came from (episode ids) or the
issue, PR or comment where the owner said it (#N, owner/name#N or a github.com link). date is
when it was added.

**Vetoes.** `swarm memory owner veto O-NNNN` moves an entry from Entries to Vetoed with today's
date, so it stops reaching sessions; with --text it records a veto of a dream proposal that was
never added. For VETO_DAYS after a veto, the dream doesn't propose an entry like it again.

**Not a rule.** An entry says what the owner prefers; it never binds the roles the way a ruling
does unless the owner asks for that through governance. Every pack says so (STANDING), and
validate() rejects an entry that asks to change permissions, credentials, tools or governance,
or to set a ruling aside, as lessons.validate() does for lessons (GOV-0055).

Entry text is data: it is quoted to sessions, never followed here.
"""
from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass, field
from pathlib import Path

import lessons as L

FILE = "owner.md"           # in memory/
KINDS = ("preference", "pattern", "vocabulary", "dont")
LEAD = "planner"            # gets the whole file (GOV-0056)
VETO_DAYS = 30              # a vetoed entry isn't proposed again for this long
STANDING = ("These are the owner's working preferences, kept by the team and approved by the owner. "
            "They describe how the owner likes things done; they are not rules and never outrank a "
            "ruling (GOV-0056).")

ID_RE = re.compile(r"^O-\d{4}$")
HEAD_RE = re.compile(r"^### (O-\d{4}):\s*(.+?)\s*$")
META_RE = re.compile(r"^- (kind|roles|sources|date):\s*(.*?)\s*$")
VETO_RE = re.compile(r"^- (O-\d{4}), (\d{4}-\d{2}-\d{2}): (.+?)\s*$")
SOURCE_RE = re.compile(r"^(?:#\d+|[\w.-]+/[\w.-]+#\d+|https://github\.com/\S+|"
                       r"(?:note|act|retag|review|revert|closed-unmerged|run|answer):\S+)$")

# ---------------------------------------------------------------- personal data

EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
PHONE_RE = re.compile(r"\+?\(?\d[\d\s().-]{7,}\d")
DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
HANDLE_RE = re.compile(r"(?<![\w`/])@[A-Za-z0-9][\w-]*")
URL_RE = re.compile(r"\bhttps?://(?!github\.com/)\S+", re.I)
ADDRESS_RE = re.compile(r"\b\d+\s+(?:[A-Z][a-z]+\s+){1,3}(?:Street|St|Avenue|Ave|Road|Rd|Lane|Ln|"
                        r"Drive|Dr|Boulevard|Blvd|Way|Court|Ct|Place|Pl|Terrace|Close)\b")
TOPICS = {
    "health": r"medical|doctors?|hospitals?|illness|sick|diagnos\w*|therapy|therapist|medication|"
              r"pregnan\w*|surgery|disabilit\w*|mental health|physical health|health (?:condition|issue)s?",
    # Not "parent", "child" or "debt": the repo says parent issue, child issue and tech debt.
    "family": r"wife|husband|spouse|girlfriend|boyfriend|kids?|sons?|daughters?|"
              r"mother|father|mom|mum|dad|(?<!font )(?<!font-)family|baby|wedding|divorce",
    "finances": r"salary|income|bank(?: account)?|mortgage|loans?|net worth|"
                r"credit cards?|tax return|personal finances?",
    "whereabouts": r"lives (?:in|at)|living in|home address|whereabouts|vacation|holiday in|"
                   r"travell?ing to|flight to|staying at|hotel",
    "contacts": r"phone number|mobile number|telephone|email address|contact details|whatsapp|signal number",
}
TOPIC_RE = {k: re.compile(rf"\b(?:{v})\b", re.I) for k, v in TOPICS.items()}


def personal_data(text: str) -> list[str]:
    """What in the text is personal data outside working preferences, as short reasons."""
    out = []
    if EMAIL_RE.search(text):
        out.append("an email address")
    for m in PHONE_RE.finditer(text):
        s = m.group(0)
        if sum(c.isdigit() for c in s) >= 9 and not DATE_RE.fullmatch(s.strip()):
            out.append("a phone number")
            break
    if HANDLE_RE.search(text):
        out.append("a handle (contact details)")
    if URL_RE.search(text):
        out.append("a link outside github.com")
    if ADDRESS_RE.search(text):
        out.append("a street address")
    for topic, rx in TOPIC_RE.items():
        m = rx.search(text)
        if m:
            out.append(f"{topic} ('{m.group(0)}')")
    return out


# ---------------------------------------------------------------- the file

@dataclass
class Entry:
    id: str
    title: str
    kind: str = ""
    roles: list[str] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)
    date: str = ""
    body: str = ""
    errors: list[str] = field(default_factory=list)    # what parse() couldn't read

    def text(self) -> str:
        return f"{self.title}\n{self.body}"


@dataclass
class Veto:
    id: str
    date: str
    text: str


@dataclass
class Model:
    entries: list[Entry] = field(default_factory=list)
    vetoed: list[Veto] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)    # lines outside any entry it can't place


def _list(v: str) -> list[str]:
    return [x.strip() for x in v.split(",") if x.strip()]


def parse(text: str) -> Model:
    """The entries and vetoes in owner.md's text. Anything under another `##` section, and
    the preamble, is left out."""
    m = Model()
    section, cur, meta_done = None, None, False
    body: list[str] = []

    def close():
        if cur is not None:
            cur.body = "\n".join(body).strip()
            m.entries.append(cur)

    for n, line in enumerate(text.splitlines(), 1):
        if line.startswith("## "):
            close()
            cur, body = None, []
            section = line[3:].strip().lower()
            continue
        if section == "entries":
            h = HEAD_RE.match(line)
            if h:
                close()
                cur, body, meta_done = Entry(h.group(1), h.group(2)), [], False
                continue
            if line.startswith("### "):
                close()
                cur, body, meta_done = Entry(f"line {n}", line[4:].strip()), [], False
                cur.errors.append("an entry's heading is `### O-NNNN: <title>`")
                continue
            if cur is None:
                if line.strip():
                    m.errors.append(f"line {n}: text under Entries outside any entry")
                continue
            mm = META_RE.match(line)
            if mm and not meta_done:
                k, v = mm.groups()
                if k in ("roles", "sources"):
                    setattr(cur, k, _list(v))
                else:
                    setattr(cur, k, v)
                continue
            if line.strip():
                meta_done = True
            if meta_done:
                body.append(line)
        elif section == "vetoed" and line.strip():
            v = VETO_RE.match(line)
            if v:
                m.vetoed.append(Veto(*v.groups()))
            else:
                m.errors.append(f"line {n}: a veto is `- O-NNNN, YYYY-MM-DD: <text>`")
    close()
    return m


def load(path: Path) -> Model:
    """The model in the file; an empty one if there is no file yet."""
    try:
        return parse(path.read_text())
    except FileNotFoundError:
        return Model()


def known_roles(roles_dir: Path) -> set[str]:
    return {p.stem for p in roles_dir.glob("*.md")} if roles_dir.is_dir() else set()


def validate(m: Model, roles: set[str], today: dt.date | None = None) -> list[str]:
    """Every reason the model isn't valid; [] if it is. `roles`: the roles it may tag (empty:
    any lower-case name)."""
    today = today or L.today()
    errs = list(m.errors)
    seen: set[str] = set()
    for e in m.entries:
        p = f"{e.id}: "
        errs += [p + x for x in e.errors]
        if e.errors:
            continue
        if e.id in seen:
            errs.append(p + "id used twice")
        seen.add(e.id)
        if e.kind not in KINDS:
            errs.append(p + f"kind must be one of {', '.join(KINDS)}, not {e.kind!r}")
        for r in e.roles:
            if not re.fullmatch(r"[a-z]+", r) or (roles and r not in roles):
                errs.append(p + f"no role {r!r}")
        if not e.sources:
            errs.append(p + "needs at least one source: the episodes it came from, or where the owner said it")
        for s in e.sources:
            if not SOURCE_RE.match(s):
                errs.append(p + f"source {s!r} isn't an episode id, #N, owner/name#N or a github.com link")
        d = L._date(e.date)
        if d is None:
            errs.append(p + "date must be YYYY-MM-DD")
        elif d > today:
            errs.append(p + f"date {e.date} is in the future")
        if not e.body:
            errs.append(p + "says nothing: write the preference under its list")
        bad = personal_data(e.text())
        if bad:
            errs.append(p + "personal data outside working preferences: " + ", ".join(bad)
                        + " (the file is public; #1188)")
        if L.power_sentences(e.text()) or L.CONTRA_RE.search(e.text()):
            errs.append(p + "asks to change permissions, credentials, tools or governance, or to set "
                            "a ruling aside: an owner preference can't (GOV-0055, GOV-0056)")
    for v in m.vetoed:
        if v.id in seen:
            errs.append(f"{v.id}: both an entry and vetoed; take it out of Entries")
        if L._date(v.date) is None:
            errs.append(f"{v.id}: veto date must be YYYY-MM-DD")
    return errs


def valid_entries(m: Model, roles: set[str], today: dt.date | None = None) -> list[Entry]:
    """The entries that pass validate(): an entry that fails never reaches a session, as recall
    re-checks lessons rather than trust the store."""
    vetoed = {v.id for v in m.vetoed}
    bad = {x.split(":", 1)[0] for x in validate(m, roles, today)}
    return [e for e in m.entries if e.id not in bad and e.id not in vetoed]


def for_role(entries: list[Entry], role: str) -> list[Entry]:
    """The part of the model a role is given (GOV-0056): all of it for the planner, otherwise
    only the entries tagged for that role. An untagged entry reaches the planner alone."""
    return list(entries) if role == LEAD else [e for e in entries if role in e.roles]


def render(entries: list[Entry], role: str) -> str:
    """The role's part as it goes into a session's pack; "" when there is none."""
    if not entries:
        return ""
    which = "the whole model" if role == LEAD else f"the entries tagged for {role}"
    out = ["# The owner's working preferences (memory/owner.md)", "",
           f"{which.capitalize()}: {len(entries)} entr{'y' if len(entries) == 1 else 'ies'}. {STANDING}"]
    for e in entries:
        out += ["", f"## {e.id}: {e.title} ({e.kind})", "", e.body]
    return "\n".join(out) + "\n"


def text(entries: list[Entry], role: str | None) -> str:
    """`swarm memory owner`'s output."""
    if role is None:
        if not entries:
            return "The owner model is empty: memory/owner.md has no entries."
        out = []
        for e in entries:
            tags = ", ".join(e.roles) or f"{LEAD} only"
            out += [f"{e.id}: {e.title} ({e.kind}; for {tags}; {e.date}; from {', '.join(e.sources)})",
                    *[f"  {ln}" for ln in e.body.splitlines()], ""]
        return "\n".join(out).rstrip()
    return render(for_role(entries, role), role) or f"No owner-model entries are tagged for {role}."


def as_json(entries: list[Entry], role: str | None) -> dict:
    mine = entries if role is None else for_role(entries, role)
    return {"role": role, "entries": [{"id": e.id, "title": e.title, "kind": e.kind, "roles": e.roles,
                                       "sources": e.sources, "date": e.date, "body": e.body} for e in mine],
            "text": render(mine, role) if role else None}


# ---------------------------------------------------------------- vetoes

def veto(path: Path, eid: str, today: dt.date, note: str | None = None) -> str:
    """Veto entry `eid`: move it from Entries to Vetoed with today's date. With `note` and no
    such entry, record a veto of a dream proposal of that id. Returns what it did. Raises
    ValueError if there's nothing to veto."""
    eid = eid.upper()
    if not ID_RE.match(eid):
        raise ValueError(f"{eid} isn't an owner-model id (O-NNNN)")
    src = path.read_text() if path.exists() else ""
    m = parse(src)
    if any(v.id == eid for v in m.vetoed):
        raise ValueError(f"{eid} is already vetoed")
    e = next((x for x in m.entries if x.id == eid), None)
    if e is None and not note:
        raise ValueError(f"no entry {eid} in {path.name}; to veto a dream proposal, pass --text with its words")
    lines = src.splitlines()
    if e is not None:
        start = next(i for i, ln in enumerate(lines) if HEAD_RE.match(ln) and HEAD_RE.match(ln).group(1) == eid)
        end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith(("### ", "## "))), len(lines))
        del lines[start:end]
        what = " ".join(f"{e.title}. {e.body}".split())
    else:
        what = " ".join(note.split())
    row = f"- {eid}, {today.isoformat()}: {what}"
    at = next((i for i, ln in enumerate(lines) if ln.strip().lower() == "## vetoed"), None)
    if at is None:
        while lines and not lines[-1].strip():
            lines.pop()
        lines += ["", "## Vetoed", "", row]
    else:
        j = at + 1
        while j < len(lines) and not lines[j].startswith("## "):
            j += 1
        while j > at + 1 and not lines[j - 1].strip():
            j -= 1
        lines[j:j] = ([""] if j == at + 1 else []) + [row]
    path.write_text("\n".join(lines) + "\n")
    return f"vetoed {eid}" + ("" if e is not None else " (a proposal)") + f" on {today.isoformat()}"


def held_by_veto(words: set[str], m: Model, today: dt.date, similar: float) -> Veto | None:
    """A veto in the last VETO_DAYS whose text is like these words, if any."""
    import dream as D
    for v in m.vetoed:
        d = L._date(v.date)
        if d and (today - d).days < VETO_DAYS and D.jaccard(words, D.words(v.text)) >= similar:
            return v
    return None


# ---------------------------------------------------------------- the dream's proposals

def is_owner_episode(e: dict, owner: str | None) -> bool:
    """An episode that carries what the owner did or asked: an owner act with its words, or a
    review the owner wrote."""
    if e.get("type") == "act":
        return bool(e.get("what"))
    if e.get("type") == "review":
        return bool(owner) and L.norm_login(e.get("by")) == L.norm_login(owner)
    return False


def next_ids(m: Model, n: int) -> list[str]:
    ids = [int(x.id[2:]) for x in m.entries if ID_RE.match(x.id)] + [int(v.id[2:]) for v in m.vetoed]
    top = max(ids, default=0)
    return [f"O-{top + i:04d}" for i in range(1, n + 1)]


def proposals(m: Model, episodes: list[dict], new_ids: set[str], owner: str | None,
              today: dt.date) -> tuple[list[dict], list[dict]]:
    """The dream's owner-model proposals: each a cluster of two or more independent owner
    episodes, one of them new, that no entry already says. Returns (proposed, held), held being
    those a veto in the last VETO_DAYS keeps back. Nothing here writes the file: the owner
    adds a proposal (GOV-0056)."""
    import dream as D
    mine = [e for e in episodes if is_owner_episode(e, owner)]
    proposed, held = [], []
    for group in D.cluster(mine):
        if not any(e["id"] in new_ids for e in group):
            continue
        if len({L.independence_key(e) for e in group}) < 2:
            continue
        agreed = D.agreed_words(group)
        if any(D.jaccard(agreed, D.words(e.text())) >= D.SIMILAR for e in m.entries):
            continue
        v = held_by_veto(agreed, m, today, D.SIMILAR)
        srcs = [e["id"] for e in group]
        if v is not None:
            until = L._date(v.date) + dt.timedelta(days=VETO_DAYS)
            held.append({"sources": srcs, "veto": v.id, "until": until.isoformat()})
            continue
        proposed.append({"sources": srcs, "links": [e.get("source") for e in group if e.get("source")],
                         "words": sorted(agreed)[:12]})
    for c, oid in zip(proposed, next_ids(m, len(proposed))):
        c["id"] = oid
    return [{"id": c.pop("id"), **c} for c in proposed], held
