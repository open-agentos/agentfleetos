"""The authority map: who may decide what, from governance/jurisdictions.yml (#410, part 11
of #397).

Governance's #authority section (#1113; authority.html until then). It's reference, not live
data, but state.json carries build()'s plain fields as `authority` so Governance's script can
draw it (#1140). One row per domain: who decides (agents blue, owner amber), owner, ratify, vote-eligible and default
shape, with the domain's in-force records from governance/INDEX.md (the rows the governance
section already parses), counted and linked to the decision log (#rulings) on the same page.

Stdlib only, so there is no YAML library: read() understands only the shape this one file
has (nested mappings of scalars and `[a, b]` lists, comments, quoted strings). Anything else
raises ValueError, and the page says it can't read the file rather than guess.
"""
from __future__ import annotations

import re
from pathlib import Path

JURISDICTIONS = Path(__file__).resolve().parent.parent / "governance" / "jurisdictions.yml"
JURISDICTIONS_PATH = "governance/jurisdictions.yml"   # for links to GitHub
LIST_KEYS = ("decide", "ratify", "vote_eligible")
KEY_RE = re.compile(r"([A-Za-z0-9_-]+):(?:\s+(.*))?$")


# ---------------------------------------------------------------- reading the file

def strip_comment(line: str) -> str:
    """The line without a `#` comment (one at the start, or after a space, outside quotes)."""
    quote = None
    for i, c in enumerate(line):
        if quote:
            if c == quote:
                quote = None
        elif c in "\"'":
            quote = c
        elif c == "#" and (i == 0 or line[i - 1] in " \t"):
            return line[:i].rstrip()
    return line.rstrip()


def scalar(s: str):
    """A plain or quoted string, a number, a boolean or a `[a, b]` list of plain strings."""
    s = s.strip()
    if s.startswith("["):
        if not s.endswith("]"):
            raise ValueError(f"unclosed list: {s}")
        inner = s[1:-1].strip()
        items = [scalar(x) for x in inner.split(",")] if inner else []
        if any(not isinstance(x, str) or not x for x in items):
            raise ValueError(f"unexpected list: {s}")
        return items
    if len(s) >= 2 and s[0] == s[-1] and s[0] in "\"'":
        return s[1:-1]
    if s[:1] in "\"'{|>&*!-":
        raise ValueError(f"unsupported value: {s}")
    if s in ("true", "false"):
        return s == "true"
    try:
        return float(s) if "." in s else int(s)
    except ValueError:
        return s


def read(text: str) -> dict:
    """The file as nested dicts. Raises ValueError on anything outside its known shape."""
    root: dict = {}
    stack = [(0, root)]    # (indent, mapping)
    pending = None         # (indent, parent, key) of a key whose value is a nested mapping
    for n, raw in enumerate(text.splitlines(), 1):
        if "\t" in raw[:len(raw) - len(raw.lstrip())]:
            raise ValueError(f"line {n}: tab indent")
        line = strip_comment(raw)
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip())
        m = KEY_RE.fullmatch(line.strip())
        if not m:
            raise ValueError(f"line {n}: not a `key: value` line")
        if pending:
            p_indent, parent, key = pending
            pending = None
            if indent > p_indent:
                parent[key] = {}
                stack.append((indent, parent[key]))
            else:
                parent[key] = None   # an empty value
        while indent < stack[-1][0]:
            stack.pop()
        if indent != stack[-1][0]:
            raise ValueError(f"line {n}: unexpected indent")
        mapping = stack[-1][1]
        key, value = m.group(1), m.group(2)
        if key in mapping:
            raise ValueError(f"line {n}: duplicate key {key}")
        if value is None or not value.strip():
            pending = (indent, mapping, key)
            mapping[key] = None
        else:
            mapping[key] = scalar(value)
    return root


def domains(doc: dict) -> list[dict]:
    """The domains, in file order, each with its fields checked. Raises ValueError if the
    file doesn't have the shape the page draws."""
    ds = doc.get("domains")
    if not isinstance(ds, dict) or not ds:
        raise ValueError("no domains")
    out = []
    for name, d in ds.items():
        if not isinstance(d, dict):
            raise ValueError(f"domain {name} is not a mapping")
        for k in LIST_KEYS:
            if not isinstance(d.get(k, []), list):
                raise ValueError(f"domain {name}: {k} is not a list")
        if not isinstance(d.get("owner"), str) or not isinstance(d.get("default_shape"), str):
            raise ValueError(f"domain {name}: missing owner or default_shape")
        out.append({"name": name, "description": d.get("description"),
                    "owner": d["owner"], "default_shape": d["default_shape"],
                    "always_one_way": d.get("always_one_way") is True, "note": d.get("note"),
                    **{k: d.get(k) or [] for k in LIST_KEYS}})
    return out


def identity(ref: str, ids: dict) -> dict:
    """`agents.builder` or `humans.owner` as who it names: kind (agent, owner, or other for a
    reference the file doesn't list), short name and login."""
    group, _, name = ref.partition(".")
    login = (ids.get(group) or {}).get(name) if isinstance(ids.get(group), dict) else None
    if group == "agents" and login:
        return {"kind": "agent", "name": name, "login": login}
    if group == "humans" and login:
        return {"kind": "owner", "name": name, "login": login}
    return {"kind": "other", "name": ref, "login": None}


# ---------------------------------------------------------------- model

def build(text: str | None, records: list[dict]) -> dict:
    """The page's model. `records` are governance.build()'s all_records (each with its review
    flag). `error` is set, and nothing else, when the file is missing or unreadable."""
    if text is None:
        return {"error": f"can't read {JURISDICTIONS_PATH}: not found"}
    try:
        doc = read(text)
        ds = domains(doc)
    except ValueError as e:
        return {"error": f"can't read {JURISDICTIONS_PATH}: {e}"}
    ids = doc.get("identities") if isinstance(doc.get("identities"), dict) else {}
    in_force = [r for r in records if r.get("status") == "in-force"]
    rows = []
    for d in ds:
        recs = sorted((r for r in in_force if r.get("domain") == d["name"]), key=lambda r: r["num"])
        rows.append({**d,
                     "owner": identity(d["owner"], ids),
                     **{k: [identity(x, ids) for x in d[k]] for k in LIST_KEYS},
                     "records": [r["id"] for r in recs],
                     "passed": [r["id"] for r in recs if r.get("flag") == "passed"]})
    known = {d["name"] for d in ds}
    elsewhere = sorted({r["domain"] for r in in_force if r.get("domain") not in known})
    return {"error": None, "domains": rows, "quorum": doc.get("quorum"),
            "consent_window": doc.get("consent_window"), "elsewhere": elsewhere}
