"""Test helper (#1140): run governance.js (or crew.js, #1139) in node against a fake DOM and read back what it drew.

Governance's panels are drawn client-side, so their tests give the script the data the page
carries (govpage.data(), the same slice of state.json) and check the markup it builds. The fake
DOM serialises each section as HTML, escaping text and attribute values as html.escape() does,
so a test can look for the same strings the Python renderers used to write.

`draw(data)` returns {section: html} for the six sections, plus "mast" (the masthead's changing
part). `run(data, served=..., clock=..., advance_ms=...)` also lets one poll fire and serve a
state.json, for the refresh tests. Tests skip when node isn't installed (`NODE`).
"""
from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path

import govpage

NODE = shutil.which("node")

HARNESS = r"""
const fs = require("fs");
const [scriptPath, casePath] = process.argv.slice(2);
const js = fs.readFileSync(scriptPath, "utf8");
const c = JSON.parse(fs.readFileSync(casePath, "utf8"));
const VOID = new Set(["br"]);
function esc(s) {
  return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;").replace(/'/g, "&#x27;");
}
function el(tag, ns) {
  const e = { tag, ns: ns || null, attrs: {}, order: [], children: [], classes: new Set(),
    setAttribute(k, v) { if (!(k in this.attrs)) { this.order.push(k); } this.attrs[k] = String(v); },
    getAttribute(k) { return k in this.attrs ? this.attrs[k] : null; },
    appendChild(x) { if (x.frag) { this.children.push(...x.children); x.children = []; } else { this.children.push(x); } return x; },
    removeChild(x) { this.children.splice(this.children.indexOf(x), 1); },
    get firstChild() { return this.children[0] || null; } };
  e.classList = { toggle(k, on) { on ? e.classes.add(k) : e.classes.delete(k); } };
  return e;
}
function html(n) {
  if (n.text !== undefined) { return esc(n.text); }
  const a = n.order.map((k) => ` ${k}="${esc(n.attrs[k])}"`).join("");
  if (VOID.has(n.tag)) { return `<${n.tag}${a}>`; }
  return `<${n.tag}${a}>${n.children.map(html).join("")}</${n.tag}>`;
}
const SECTIONS = c.sections;
const sections = {};
for (const s of SECTIONS) { sections[s] = el("section"); sections[s].children.push({ text: "static" }); }
const block = { textContent: JSON.stringify(c.data) };
const mast = el("span"); mast.children.push({ text: "static" });
let now = Date.parse(c.clock), tick = null, fetched = [];
const RealDate = Date;
global.Date = class extends RealDate { static now() { return now; } };
global.document = {
  hidden: false,
  createElement: (t) => el(t), createElementNS: (ns, t) => el(t, ns),
  createTextNode: (t) => ({ text: t }), createDocumentFragment: () => Object.assign(el("#frag"), { frag: true }),
  getElementById: (id) => id === c.data_id ? block : sections[id] || null,
  querySelector: (q) => q === 'header.mast [data-panel="mast"]' ? mast : null,
  querySelectorAll: (q) => q === "header.mast .live" ? mast.children.filter((x) => x.classes && x.attrs.class === "live") : [],
};
global.fetch = (url, opts) => { fetched.push([url.split("?")[0], opts.cache]);
  return Promise.resolve({ ok: true, json: () => Promise.resolve(c.served) }); };
global.setInterval = (fn, ms) => { tick = fn; };
function dump() {
  const out = { mast: mast.children.map(html).join("") };
  for (const s of SECTIONS) { out[s] = sections[s].children.map(html).join(""); }
  const live = mast.children.find((x) => x.classes && x.attrs.class === "live");
  out.stale = !!(live && live.classes.has("stale"));
  return out;
}
(async () => {
  new Function(js)();
  const first = dump();
  let after = null;
  if (c.served !== null) {
    now += c.advance_ms; tick();
    await new Promise((r) => setTimeout(r, 0)); await new Promise((r) => setTimeout(r, 0));
    after = dump();
  }
  console.log(JSON.stringify({ first, after, fetched }));
})();
"""


def run(data: dict, served: dict | None = None, clock: str | None = None, advance_ms: int = 15000,
        page=govpage) -> dict:
    """What `page`'s script (governance.js, or crewpage's crew.js) drew from `data` (`first`),
    and, when `served` is given, after one poll that fetched it (`after`), with the URLs it
    `fetched`."""
    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "page.js").write_text(page.script(), encoding="utf-8")
        (Path(d) / "harness.js").write_text(HARNESS, encoding="utf-8")
        case = {"data": data, "served": served, "advance_ms": advance_ms,
                "sections": list(page.SECTIONS), "data_id": page.DATA_ID,
                "clock": clock or data.get("built_at") or "2026-11-05T10:00:00Z"}
        (Path(d) / "case.json").write_text(json.dumps(case), encoding="utf-8")
        r = subprocess.run([NODE, str(Path(d) / "harness.js"), str(Path(d) / "page.js"),
                            str(Path(d) / "case.json")], capture_output=True, text=True, timeout=30)
    if r.returncode:
        raise RuntimeError(r.stderr)
    return json.loads(r.stdout)


def draw(data: dict) -> dict:
    """{section: html} as governance.js draws `data`, plus "mast"."""
    out = run(data)["first"]
    out.pop("stale")
    return out


def page_data(m: dict) -> dict:
    """The data a model's Governance page carries, as JSON would hand it to the script."""
    import state
    return json.loads(json.dumps(govpage.data(state.state(m))))


def base(**over) -> dict:
    """A minimal page slice: every key empty, with `over` on top. Each test fills in the part
    of state.json its panel reads."""
    d = {"schema": 1, "built_at": "2026-11-05T10:00:00Z", "repo": "o/r",
         "owner_last_acted": {"status": "unknown"}, "sessions": [],
         "governance": {"all_records": [], "index_found": True, "by_shape": [], "by_domain": [],
                        "lapsed": [], "days": 14},
         "gov_questions": [], "committee_desk": [], "past_committees": [],
         "committee_views": {"open": [], "ended": [], "unparsed": [], "notes": []},
         "authority": {"error": "can't read governance/jurisdictions.yml: not found"},
         "precedent": None, "trends": None, "questions_went": None}
    d.update(over)
    return json.loads(json.dumps(d, default=str))
