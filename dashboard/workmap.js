// The Work map (#1082, FEAT-9): a squarified treemap of map.json's rows, drawn in the browser.
// generate.py serves this file as js/workmap.js and the page's CSP names its hash. It reads the
// data from the page's JSON block and builds DOM nodes with createElement and text nodes only (it
// never parses markup or runs strings as code). It shows each issue's own figures and each group's
// share as a percentage: no amount is ever summed across issues for display (GOV-0033).
// Since #1138 an open map also fetches same-origin map.json while the tab is visible, and redraws
// in place when it carries a newer build, keeping the view and selection (see "live refresh").
// Since #1135 it fetches same-origin state.json too, for what map.json doesn't carry: the strip,
// Briefing, tape, masthead, and the Goals, roles and decisions waiting. The page never reloads.
// The Selected panel (#1083) shows one issue: its 14-day cost is that issue's own sum, a
// per-issue figure, not a sum across issues. The lists (#1084) under the Briefing show issues
// one per row; a heading's count is a number of issues, not an amount.
// Since #1115 (FEAT-13) the panel also shows a Goal, Area or role (the "i" in a group header, or
// any element with data-wm-sel), each issue's links (what it waits on and holds up), and the URL
// keeps the view: ?group=&size=&colour=&w=&zoom= and #issue-N, #goal-N, #role-NAME. The URL
// wins over localStorage, and Back and Forward step through selections. A Goal's view shows
// each issue's share of it, never a summed amount.
(function () {
  "use strict";
  var KEY = "agentfleetos.workmap";
  var DEFAULTS = { group: "effort", size: "cost", colour: "yield", window: "day" };
  var CHOICES = { group: ["effort", "goal", "role", "stage"], size: ["cost", "tokens", "lines"],
                  colour: ["yield", "velocity", "change"], window: ["hour", "day", "week", "month"] };
  var HOURS = { hour: 1, day: 24, week: 168, month: 720 };
  var RAMP = ["#F3EFE7", "#E2D8C7", "#CBBBA2", "#AE987A", "#8A7458", "#64523E"];
  var ROOT = { effort: "All effort types", goal: "All goals", role: "All roles", stage: "All stages" };
  var UNIT = { cost: "per $100", tokens: "per M tokens", lines: "per 1k lines" };
  var HEAD = 20;   // a group header's height, px

  var dataEl = document.getElementById("wm-data");
  var mapEl = document.getElementById("wm-map");
  if (!dataEl || !mapEl) return;
  var data;
  try { data = JSON.parse(dataEl.textContent); } catch (e) { return; }
  var crumbEl = document.getElementById("wm-crumb");
  var legendEl = document.getElementById("wm-legend");
  var tipEl = document.getElementById("wm-tip");

  // mark: the strip's pick (#1114), "flagged" or "decisions", outlining the matching boxes.
  var st = Object.assign({}, DEFAULTS, { zoom: null, selected: null, mark: null });
  var STRIP = (data && data.strip) || { flagged: [], decisions: [] };
  try {
    var saved = JSON.parse(window.localStorage.getItem(KEY) || "{}");
    Object.keys(CHOICES).forEach(function (k) {
      if (saved && CHOICES[k].indexOf(saved[k]) >= 0) st[k] = saved[k];
    });
  } catch (e) { /* no storage: the defaults stand */ }

  // ------------------------------------------------------------ the URL (#1115)

  var PARAM = { group: "group", size: "size", colour: "colour", window: "w" };
  function refToHash(ref) {
    if (!ref) return "";
    return ref.charAt(0) === "#" ? "#issue-" + ref.slice(1) : "#" + ref;
  }
  function hashToRef(h) {
    h = (h || "").replace(/^#/, "");
    var m = /^issue-(\d+)$/.exec(h);
    if (m) return "#" + m[1];
    if (/^(goal-\d+|role-[a-z]+|unattributed)$/.test(h)) return h;
    return null;
  }
  function readUrl() {
    var q;
    try { q = new URLSearchParams(window.location.search); } catch (e) { return; }
    Object.keys(PARAM).forEach(function (k) {
      var v = q.get(PARAM[k]);
      if (v !== null && CHOICES[k].indexOf(v) >= 0) st[k] = v;
    });
    st.zoom = q.get("zoom");
    st.selected = hashToRef(window.location.hash);
  }
  function url() {
    var q = new URLSearchParams();
    Object.keys(PARAM).forEach(function (k) { q.set(PARAM[k], st[k]); });
    if (st.zoom !== null && st.zoom !== undefined) q.set("zoom", st.zoom);
    return window.location.pathname + "?" + q.toString() + refToHash(st.selected);
  }
  // A new selection is a history entry; a control, zoom or a dropped selection replaces it.
  function writeUrl(push) {
    try {
      var u = url();
      if (u === window.location.pathname + window.location.search + window.location.hash) return;
      if (push) window.history.pushState(null, "", u); else window.history.replaceState(null, "", u);
    } catch (e) { /* a page opened from a file may refuse it: the view still works */ }
  }
  readUrl();

  function save() {
    try {
      window.localStorage.setItem(KEY, JSON.stringify(
        { group: st.group, size: st.size, colour: st.colour, window: st.window }));
    } catch (e) { /* the page works without it */ }
  }

  // ------------------------------------------------------------ helpers

  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text !== undefined && text !== null) e.appendChild(document.createTextNode(String(text)));
    return e;
  }
  function clear(e) { while (e.firstChild) e.removeChild(e.firstChild); }
  function cap(s) { return s ? s.charAt(0).toUpperCase() + s.slice(1) : s; }
  function num(x, d) {
    return x.toLocaleString("en-US", { maximumFractionDigits: d, minimumFractionDigits: 0 });
  }
  function short(n) {
    if (n >= 1e6) return num(n / 1e6, n >= 1e7 ? 0 : 1) + "M";
    if (n >= 1e3) return num(n / 1e3, n >= 1e4 ? 0 : 1) + "k";
    return num(n, n < 10 ? 1 : 0);
  }
  function usd(x) {
    if (x === null || x === undefined) return "unpriced";
    if (x > 0 && x < 0.01) return "<$0.01";
    return "$" + x.toFixed(2);
  }

  function sizeOf(r) {
    var v = st.size === "cost" ? r.cost : st.size === "tokens" ? r.tokens : r.lines;
    return typeof v === "number" && v > 0 ? v : 0;
  }
  function sizeText(r) {
    if (st.size === "cost") return usd(r.cost);
    if (st.size === "tokens") return short(r.tokens) + " tokens";
    return num(r.lines, 0) + " lines";
  }
  function groupOf(r) {
    if (st.group === "effort") return r.effort ? cap(r.effort) : "Unattributed";
    if (st.group === "goal") return r.goal ? (r.goal.lead || ("#" + r.goal.number)) : "No Goal";
    if (st.group === "role") return r.role ? cap(r.role) : "No role";
    return r.stage ? cap(r.stage) : (r.state === "closed" ? "Closed" : "No stage");
  }
  // The Goal or role a group stands for, as a selection, or null (#1115).
  function groupSel(r) {
    if (st.group === "goal") return r.goal ? "goal-" + r.goal.number : null;
    if (st.group === "role") return r.role ? "role-" + r.role : null;
    return null;
  }
  function goalText(r) {
    if (!r.goal) return "no Goal";
    return (r.goal.lead ? r.goal.lead + ": " : "#" + r.goal.number + " ") + (r.goal.title || "");
  }

  // ------------------------------------------------------------ shade

  function median(xs) {
    if (!xs.length) return 0;
    var s = xs.slice().sort(function (a, b) { return a - b; });
    var m = Math.floor(s.length / 2);
    return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
  }
  function step(t) { return Math.max(0, Math.min(RAMP.length - 1, Math.floor(t * RAMP.length))); }

  // Each shown row's shade: {i: ramp index or null (hatched), text}. And the legend's ends.
  function shades(rows) {
    var out = new Map(), ends;
    if (st.colour === "yield") {
      var per = st.size === "cost" ? 100 : st.size === "tokens" ? 1e6 : 1e3;
      var ys = rows.map(function (r) { return r.outcomes / sizeOf(r) * per; });
      var med = median(ys);
      rows.forEach(function (r, k) {
        var t = med > 0 ? ys[k] / (2 * med) : (ys[k] > 0 ? 1 : 0);
        out.set(r, { i: Math.min(step(t), RAMP.length - 1), text: num(ys[k], ys[k] < 10 ? 1 : 0) + " " + UNIT[st.size] });
      });
      ends = ["none", med > 0 ? "2× the median (" + num(med, med < 10 ? 1 : 0) + ") or more" : "any outcome (the median is 0)"];
    } else if (st.colour === "velocity") {
      var hrs = HOURS[st.window];
      var vs = rows.map(function (r) { return r.tokens / hrs; });
      var top = Math.max.apply(null, vs.concat([0]));
      rows.forEach(function (r, k) {
        out.set(r, { i: top > 0 ? step(Math.sqrt(vs[k]) / Math.sqrt(top)) : 0, text: short(vs[k]) + " tokens/h" });
      });
      ends = ["0 tokens/h", short(top) + " tokens/h (the most shown)"];
    } else {
      rows.forEach(function (r) {
        var b = r.baseline, c = r.cost;
        if (c === null || c === undefined) { out.set(r, { i: null, text: "unpriced" }); return; }
        if (b === null || b === undefined) { out.set(r, { i: null, text: "no baseline" }); return; }
        if (b === 0 && c === 0) { out.set(r, { i: null, text: "no spend before or now" }); return; }
        if (b === 0) { out.set(r, { i: RAMP.length - 1, text: "new: none usually" }); return; }
        var x = c === 0 ? -Infinity : Math.log2(c / b);
        var t = (Math.max(-2, Math.min(2, x)) + 2) / 4;
        out.set(r, { i: step(t), text: c === 0 ? "none (usual " + usd(b) + ")" : "×" + num(c / b, 1) + " usual" });
      });
      ends = ["¼ of usual or less", "4× usual or more"];
    }
    return { of: out, ends: ends };
  }

  // ------------------------------------------------------------ squarify

  // Lay out items ({value}) in a rectangle, largest first: [{item, x, y, w, h}].
  function squarify(items, x, y, w, h) {
    var out = [], total = 0;
    items.forEach(function (it) { total += it.value; });
    if (!(total > 0) || w <= 0 || h <= 0) return out;
    var scale = w * h / total, rest = items.slice();
    while (rest.length) {
      var side = Math.min(w, h), row = [], sum = 0, lo = Infinity, hi = 0, best = Infinity;
      while (rest.length) {
        var a = rest[0].value * scale, s = sum + a;
        var l = Math.min(lo, a), u = Math.max(hi, a);
        var worst = Math.max(side * side * u / (s * s), (s * s) / (side * side * l));
        if (row.length && worst > best) break;
        row.push(rest.shift()); sum = s; lo = l; hi = u; best = worst;
      }
      var thick = sum / side, at;
      if (w >= h) {
        at = y;
        row.forEach(function (it) { var hh = it.value * scale / thick; out.push({ item: it, x: x, y: at, w: thick, h: hh }); at += hh; });
        x += thick; w -= thick;
      } else {
        at = x;
        row.forEach(function (it) { var ww = it.value * scale / thick; out.push({ item: it, x: at, y: y, w: ww, h: thick }); at += ww; });
        y += thick; h -= thick;
      }
    }
    return out;
  }

  function place(node, r) {
    var x0 = Math.round(r.x), y0 = Math.round(r.y);
    node.style.left = x0 + "px"; node.style.top = y0 + "px";
    node.style.width = Math.max(0, Math.round(r.x + r.w) - x0) + "px";
    node.style.height = Math.max(0, Math.round(r.y + r.h) - y0) + "px";
    return { w: Math.round(r.x + r.w) - x0, h: Math.round(r.y + r.h) - y0 };
  }

  // ------------------------------------------------------------ drawing

  function rowsNow() {
    var w = data && data.windows ? data.windows[st.window] : null;
    return Array.isArray(w) ? w : null;
  }

  function note(text) {
    var p = el("p", "wm-empty muted", text);
    mapEl.appendChild(p);
  }

  function draw() { drawMap(); drawLists(); }

  function drawMap() {
    clear(mapEl); clear(legendEl); clear(crumbEl); hideTip();
    syncButtons();
    var all = rowsNow();
    if (!data || data.error) { panel(); note("The Work map's data wasn't read in this build" + (data && data.error ? ": " + data.error : ".")); crumb([]); return; }
    if (!all) {
      note(st.window === "month"
        ? "Month isn't in the Desk's data: the build reads 14 days of heartbeats, too few for a month. `swarm map --window month` prints it."
        : "This window isn't in the build's data.");
      crumb([]); panel(); return;
    }
    var shown = all.filter(function (r) { return sizeOf(r) > 0; });
    var left = all.length - shown.length;
    var groups = new Map();
    shown.forEach(function (r) {
      var g = groupOf(r);
      if (!groups.has(g)) groups.set(g, { name: g, rows: [], value: 0, sel: groupSel(r) });
      var e = groups.get(g); e.rows.push(r); e.value += sizeOf(r);
    });
    var whole = 0;
    groups.forEach(function (g) { whole += g.value; });
    if (st.zoom !== null && !groups.has(st.zoom)) { st.zoom = null; writeUrl(false); }
    crumb(st.zoom === null ? [] : [st.zoom]);
    var list = Array.from(groups.values()).filter(function (g) { return st.zoom === null || g.name === st.zoom; });
    list.sort(function (a, b) { return b.value - a.value || (a.name < b.name ? -1 : 1); });
    var inView = [];
    list.forEach(function (g) { inView = inView.concat(g.rows); });
    var sh = shades(inView);
    var W = mapEl.clientWidth, H = mapEl.clientHeight;
    var markG = [];
    if (!list.length) note("Nothing in this window has any " + (st.size === "lines" ? "lines changed" : st.size) + ".");
    squarify(list, 0, 0, W, H).forEach(function (gp) {
      var g = gp.item;
      var box = el("div", "wm-g");
      var dim = place(box, gp);
      var pct = whole > 0 ? g.value / whole * 100 : 0;
      var head = el("button", "wm-gh");
      head.type = "button";
      head.appendChild(el("span", "wm-gn", g.name));
      head.appendChild(el("span", "wm-gp", (pct >= 1 || pct === 0 ? Math.round(pct) : "<1") + "%"));
      head.setAttribute("aria-label", g.name + ", " + Math.round(pct) + "% of what's shown" +
        (st.zoom === null ? ": zoom in" : ""));
      if (st.zoom === null) head.addEventListener("click", function () { st.zoom = g.name; writeUrl(false); draw(); });
      else head.disabled = true;
      box.appendChild(head);
      if (g.sel && dim.w >= 60) {   // the "i": select the Goal or role; the header still zooms
        head.classList.add("wm-gh-i");
        var info = el("button", "wm-gi", "i");
        info.type = "button";
        info.setAttribute("aria-label", "Show " + g.name + " in the Selected panel");
        info.setAttribute("aria-controls", "wm-sel");
        info.setAttribute("aria-pressed", st.selected === g.sel ? "true" : "false");
        info.setAttribute("data-sel", g.sel);
        info.addEventListener("click", function () { select(g.sel); });
        box.appendChild(info);
      }
      mapEl.appendChild(box);
      if (st.mark === "flagged" && st.group === "goal" && g.sel &&
          STRIP.flagged.indexOf(Number(g.sel.slice(5))) >= 0) {
        markG.push(gp);
      }
      var items = g.rows.map(function (r) { return { value: sizeOf(r), row: r }; })
        .sort(function (a, b) { return b.value - a.value; });
      squarify(items, gp.x, gp.y + HEAD, dim.w, Math.max(0, dim.h - HEAD)).forEach(function (p) {
        mapEl.appendChild(issueBox(p, sh.of.get(p.item.row)));
      });
    });
    // The strip's flagged Goals: a solid frame over each one's box, drawn last so the issue
    // boxes don't cover it, and letting clicks through.
    markG.forEach(function (gp) { var o = el("div", "wm-markg"); place(o, gp); mapEl.appendChild(o); });
    legend(sh.ends, left);
    markSelected();
    panel();
  }

  function issueBox(p, shade) {
    var r = p.item.row;
    var b = el("div", "wm-box");
    b.setAttribute("data-ref", r.ref);
    var dim = place(b, p);
    if (dim.w < 20 || dim.h < 14) b.style.padding = "0";   // padding would push it past its place
    if (dim.w < 3 || dim.h < 3) b.style.borderWidth = "0";
    var hatched = shade.i === null;
    if (hatched) b.classList.add("wm-hatch");
    else {
      b.style.background = RAMP[shade.i];
      if (shade.i >= 3) b.classList.add("wm-dark");
    }
    var marks = [];
    if (r.stage === "blocked") { b.classList.add("wm-blocked"); marks.push("blocked"); }
    if (r.needs_you) { b.classList.add("wm-needs"); marks.push("needs you"); }
    if ((r.tokens > 0 || r.cost > 0) && !r.outcomes) {
      b.appendChild(el("span", "wm-fold")); marks.push("no outcome");
    }
    if (r.ref === st.selected) b.classList.add("wm-sel");
    if (st.mark === "decisions" && (r.needs_you || STRIP.decisions.indexOf(r.ref) >= 0)) b.classList.add("wm-mark");
    if (dim.w >= 44 && dim.h >= 18) b.appendChild(el("span", "wm-t", r.title || r.ref));
    if (dim.w >= 44 && dim.h >= 34) b.appendChild(el("span", "wm-m", sizeText(r) + " · " + shade.text));
    b.setAttribute("aria-controls", "wm-sel");
    b.tabIndex = 0;
    b.setAttribute("role", "button");
    b.setAttribute("aria-pressed", r.ref === st.selected ? "true" : "false");
    b.setAttribute("aria-label", (r.ref === "unattributed" ? "" : r.ref + " ") + (r.title || "") +
      ": " + sizeText(r) + ", " + shade.text + (marks.length ? ", " + marks.join(", ") : ""));
    b.addEventListener("click", function () { select(r.ref); });
    b.addEventListener("keydown", function (ev) {
      if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); select(r.ref); }
    });
    b.addEventListener("mouseenter", function () { showTip(r, b); });
    b.addEventListener("mouseleave", hideTip);
    b.addEventListener("focus", function () { showTip(r, b); });
    b.addEventListener("blur", hideTip);
    return b;
  }

  function select(ref) {
    st.selected = st.selected === ref ? null : ref;
    writeUrl(true);
    markSelected();
    panel();
  }

  // The selected box, the boxes the selected issue holds up (a thin dashed outline, #1115),
  // and the pressed "i".
  function markSelected() {
    var found = st.selected && st.selected.charAt(0) === "#" ? findRow(st.selected) : null;
    var holds = (found && found.row.blocks) || [];
    var boxes = mapEl.querySelectorAll(".wm-box");
    for (var i = 0; i < boxes.length; i++) {
      var ref = boxes[i].getAttribute("data-ref");
      var on = ref === st.selected;
      boxes[i].classList.toggle("wm-sel", on);
      boxes[i].classList.toggle("wm-dep", holds.indexOf(Number(ref.slice(1))) >= 0);
      boxes[i].setAttribute("aria-pressed", on ? "true" : "false");
    }
    var items = document.querySelectorAll("#wm-lists [data-wm-ref]");
    for (var k = 0; k < items.length; k++) {
      items[k].setAttribute("aria-pressed", items[k].getAttribute("data-wm-ref") === st.selected ? "true" : "false");
    }
    var is = mapEl.querySelectorAll(".wm-gi");
    for (var j = 0; j < is.length; j++) {
      is[j].setAttribute("aria-pressed", is[j].getAttribute("data-sel") === st.selected ? "true" : "false");
    }
  }

  function crumb(path) {
    var root = ROOT[st.group];
    if (!path.length) { crumbEl.appendChild(el("span", "", root)); return; }
    var back = el("button", "wm-back", root);
    back.type = "button";
    back.addEventListener("click", function () { st.zoom = null; writeUrl(false); draw(); });
    crumbEl.appendChild(back);
    crumbEl.appendChild(document.createTextNode(" › "));
    crumbEl.appendChild(el("span", "", path[0]));
  }

  function legend(ends, left) {
    var ramp = el("span", "wm-ramp");
    ramp.appendChild(el("span", "wm-end", ends[0]));
    RAMP.forEach(function (c) { var s = el("span", "wm-sw"); s.style.background = c; ramp.appendChild(s); });
    ramp.appendChild(el("span", "wm-end", ends[1]));
    legendEl.appendChild(ramp);
    if (st.colour === "change") {
      var h = el("span", "wm-key"); h.appendChild(el("span", "wm-sw wm-hatch")); h.appendChild(document.createTextNode("no baseline or unpriced"));
      legendEl.appendChild(h);
    }
    [["wm-k-fold", "no outcome"], ["wm-k-needs", "needs you"], ["wm-k-blocked", "blocked"], ["wm-k-sel", "selected"],
     ["wm-k-dep", "held up by the selected"]]
      .forEach(function (k) {
        var s = el("span", "wm-key"); s.appendChild(el("span", "wm-sw " + k[0])); s.appendChild(document.createTextNode(k[1]));
        legendEl.appendChild(s);
      });
    if (left) legendEl.appendChild(el("span", "wm-left muted", left + (left === 1 ? " issue" : " issues") +
      " with no " + (st.size === "lines" ? "lines changed" : st.size) + " in this window left off"));
  }

  // ------------------------------------------------------------ the Selected panel (#1083)

  var STAGE_ORDER = ["queued", "building", "review", "merging"];
  var STAGE_NAME = { queued: "Queued", building: "Building", review: "In review", merging: "Merging" };
  var PER = { cost: 100, tokens: 1e6, lines: 1e3 };
  var PLACEHOLDER = [30, 45, 25, 60, 40, 20, 50, 35, 55, 30, 45, 25, 40, 50];   // empty state, %
  function $(id) { return document.getElementById(id); }
  function setText(id, text) { var e = $(id); if (e) { clear(e); e.appendChild(document.createTextNode(text)); } }

  // The selected issue's row: this window's if it's in it, else any window's (for its title,
  // Goal and stage), with `here` false.
  function findRow(ref) {
    var here = rowsNow() || [];
    for (var i = 0; i < here.length; i++) if (here[i].ref === ref) return { row: here[i], here: true };
    var ws = (data && data.windows) || {};
    var names = ["day", "week", "hour"];
    for (var k = 0; k < names.length; k++) {
      var w = ws[names[k]] || [];
      for (var j = 0; j < w.length; j++) if (w[j].ref === ref) return { row: w[j], here: false };
    }
    return null;
  }
  function yieldOf(r) {
    var s = sizeOf(r);
    return s > 0 ? r.outcomes / s * PER[st.size] : null;
  }
  function yieldText(y) { return y === null ? "–" : num(y, y < 10 ? 1 : 0) + " " + UNIT[st.size]; }
  function changeText(r) {
    var b = r.baseline, c = r.cost;
    if (c === null || c === undefined) return "unpriced";
    if (b === null || b === undefined) return "no baseline";
    if (b === 0) return c === 0 ? "none before or now" : "new: none usually";
    return c === 0 ? "none (usual " + usd(b) + ")" : "×" + num(c / b, 1) + " usual (" + usd(b) + ")";
  }

  function panel() {
    var box = $("wm-sel");
    if (!box) return;
    var kind = st.selected ? st.selected.split("-")[0] : null;
    if (kind === "goal" || kind === "role") {
      if ((kind === "goal" ? goalPanel : rolePanel)(box, st.selected.slice(5))) return;
    }
    var found = st.selected === null || kind === "goal" || kind === "role" ? null : findRow(st.selected);
    if (!found) { if (st.selected !== null) { st.selected = null; writeUrl(false); } emptyPanel(box); return; }
    box.classList.remove("wm-sel-other");
    setText("wm-sel-kind", "SELECTED");
    var r = found.row, here = found.here;
    // An idle issue has nothing this window. Its row is another window's, so that row's baseline
    // is a usual for a window of another length: don't show it as this window's usual.
    var w = here ? r : { cost: 0, tokens: 0, lines: 0, outcomes: 0, baseline: null, unpriced_tokens: 0 };
    var idle = !here || (!(w.tokens > 0) && !(w.cost > 0) && !w.outcomes);
    box.classList.remove("wm-sel-empty");
    setText("wm-sel-ref", r.ref === "unattributed" ? "unattributed" : r.ref);

    var t = $("wm-sel-title"); clear(t);
    if (typeof r.url === "string" && r.url.indexOf("https://github.com/") === 0) {
      var a = el("a", "", r.title || r.ref); a.href = r.url; t.appendChild(a);
    } else t.appendChild(document.createTextNode(r.title || r.ref));
    t.title = r.title || r.ref;

    var c = $("wm-sel-ctx"); clear(c);
    c.appendChild(document.createTextNode((r.effort ? cap(r.effort) : "no effort") + " · "));
    c.appendChild(r.role ? pick("role-" + r.role, r.role) : document.createTextNode("no role"));
    c.appendChild(document.createTextNode(" · "));
    c.appendChild(r.goal ? pick("goal-" + r.goal.number, r.goal.lead || "#" + r.goal.number) : document.createTextNode("no Goal"));
    if (r.needs_you) { c.appendChild(document.createTextNode(" · ")); c.appendChild(el("span", "wm-flag", "◆ needs you")); }
    if (idle) { c.appendChild(document.createTextNode(" · ")); c.appendChild(el("span", "", "idle this window")); }
    c.title = goalText(r);

    stagePanel(r);
    depsPanel(r);
    daysPanel(r.ref);
    peersPanel(r, here);
    var y = here ? yieldOf(r) : null;
    var nums = { cost: usd(w.cost) + (w.unpriced_tokens ? "*" : ""), tokens: num(w.tokens || 0, 0),
                 lines: num(w.lines || 0, 0), outcomes: String(w.outcomes || 0), "yield": yieldText(y),
                 change: changeText(w) };
    numbers(nums);
  }

  function stagePanel(r) {
    var segs = $("wm-sel-sgs").children;
    var cur = r.stage === "blocked" ? r.blocked_at || "queued" : r.stage;
    var at = STAGE_ORDER.indexOf(cur), closed = r.state === "closed";
    for (var i = 0; i < segs.length; i++) {
      var cls = "wm-sg";
      if (closed || (at >= 0 && i < at)) cls += " wm-sg-past";
      else if (i === at) cls += r.stage === "blocked" ? " wm-sg-stop" : " wm-sg-now";
      segs[i].className = cls;
    }
    var text = closed ? "closed" : r.stage === "blocked" ? "blocked at " + STAGE_NAME[cur]
      : at >= 0 ? STAGE_NAME[cur] : r.ref === "unattributed" ? "no issue" : "not go yet";
    setText("wm-sel-stage", text);
    $("wm-sel-sgs").setAttribute("aria-label", "Stage: " + text);
  }

  function daysPanel(ref) {
    var days = (data && data.days) || {}, dates = days.dates || [];
    var series = (days.of || {})[ref] || [];
    var bars = $("wm-sel-bars").children, n = bars.length;
    var peak = 0, sum = 0, priced = false, outs = 0;
    for (var i = 0; i < n; i++) {
      var d = series[i] || [null, 0];
      if (typeof d[0] === "number") { priced = true; sum += d[0]; if (d[0] > peak) peak = d[0]; }
      outs += d[1] || 0;
    }
    for (var k = 0; k < n; k++) {
      var b = bars[k], v = (series[k] || [null, 0]);
      clear(b);
      b.className = "wm-bar" + (k === n - 1 ? " wm-today" : "");
      var cost = typeof v[0] === "number" ? v[0] : 0;
      if (peak > 0 && cost > 0) {
        var i2 = el("i"); i2.style.height = Math.max(1, cost / peak * 100) + "%"; b.appendChild(i2);
      }
      if (v[1] > 0) b.appendChild(el("b"));
      b.title = (dates[k] || "") + ": " + (v[0] === null || v[0] === undefined ? (series[k] ? "unpriced" : "no spend") : usd(v[0])) +
        (v[1] ? ", " + v[1] + (v[1] === 1 ? " outcome" : " outcomes") : "");
    }
    setText("wm-sel-dsum", (priced ? usd(sum) : "–") + " · " + outs + (outs === 1 ? " outcome" : " outcomes"));
    setText("wm-sel-peak", peak > 0 ? "peak " + usd(peak) : "no spend");
    $("wm-sel-bars").setAttribute("aria-label", "Cost per day, last 14 days" + (peak > 0 ? ", peak " + usd(peak) : ", none"));
  }

  function peersPanel(r, here) {
    var strip = $("wm-sel-strip"), ax = $("wm-sel-pax");
    while (strip.children.length > 1) strip.removeChild(strip.lastChild);
    var g = groupOf(r);
    var peers = (rowsNow() || []).filter(function (p) { return sizeOf(p) > 0 && groupOf(p) === g; });
    var ys = peers.map(yieldOf), mine = here ? yieldOf(r) : null;
    var top = Math.max.apply(null, ys.concat([mine || 0, 0]));
    var med = median(ys);
    function at(y) { return (top > 0 ? y / top * 100 : 0) + "%"; }
    peers.forEach(function (p, k) {
      if (p === r) return;
      var d = el("span", "wm-pd"); d.style.left = at(ys[k]); strip.appendChild(d);
    });
    if (peers.length) { var m = el("span", "wm-med"); m.style.left = at(med); strip.appendChild(m); }
    if (mine !== null) { var me = el("span", "wm-me"); me.style.left = at(mine); strip.appendChild(me); }
    setText("wm-sel-grp", g + " · " + peers.length + (peers.length === 1 ? " issue" : " issues"));
    var spans = ax.children;
    spans[0].textContent = "0";
    spans[1].textContent = peers.length ? "median " + num(med, med < 10 ? 1 : 0) : "no peers";
    spans[2].textContent = top > 0 ? "max " + num(top, top < 10 ? 1 : 0) : "max 0";
    strip.setAttribute("aria-label", "Yield " + UNIT[st.size] + ": this issue " + (mine === null ? "not on the map" : num(mine, 1)) +
      ", median " + num(med, 1) + ", max " + num(top, 1) + ", of " + peers.length + " in " + g);
  }

  function numbers(vals) {
    var dds = $("wm-sel-nums").querySelectorAll("dd[data-n]");
    for (var i = 0; i < dds.length; i++) {
      var k = dds[i].getAttribute("data-n");
      dds[i].textContent = vals ? vals[k] : "–";
      dds[i].title = vals ? vals[k] : "";
    }
  }

  // A button that selects `sel` (an issue "#N", "goal-N" or "role-NAME").
  function pick(sel, text) {
    var b = el("button", "wm-pick", text);
    b.type = "button";
    b.setAttribute("data-wm-sel", sel);
    b.setAttribute("aria-controls", "wm-sel");
    return b;
  }
  // An issue number as a selector if the map has it, else as a link to it on GitHub.
  function issueRef(n, text) {
    if (findRow("#" + n)) return pick("#" + n, text || "#" + n);
    return link("https://github.com/" + (data.repo || "") + "/issues/" + n, text || "#" + n);
  }
  function link(href, text) {
    if (typeof href !== "string" || href.indexOf("https://github.com/") !== 0) return el("span", "", text);
    var a = el("a", "", text); a.href = href; return a;
  }

  // What the issue waits on and what it holds up (#1115): each one selects that issue.
  function depsPanel(r) {
    [["wm-sel-by", r.blocked_by], ["wm-sel-blocks", r.blocks]].forEach(function (x) {
      var e = $(x[0]); clear(e);
      var ns = x[1] || [];
      if (!ns.length) { e.appendChild(document.createTextNode(r.ref === "unattributed" ? "–" : "nothing")); return; }
      ns.forEach(function (n) { e.appendChild(issueRef(n)); });
      e.title = ns.map(function (n) { return "#" + n; }).join(" ");
    });
  }

  // ------------------------------------------------------------ a Goal, Area or role (#1115)

  var CRIT = { met: "met", progress: "in progress", failing: "failing", counted: "counted",
               unmeasured: "unmeasured: not known to be on track" };

  function other(box, kind, ref, title, href, ctx) {
    box.classList.remove("wm-sel-empty");
    box.classList.add("wm-sel-other");
    setText("wm-sel-kind", kind);
    setText("wm-sel-ref", ref);
    var t = $("wm-sel-title"); clear(t); t.title = title;
    t.appendChild(link(href, title));
    setText("wm-sel-ctx", ctx);
    $("wm-sel-ctx").title = ctx;
    var alt = $("wm-sel-alt"); clear(alt); alt.scrollTop = 0;
    return alt;
  }
  function head(alt, name, right) {
    var h = el("p", "wm-sh");
    h.appendChild(el("span", "", name));
    h.appendChild(el("span", "", right || ""));
    alt.appendChild(h);
  }
  function list(alt, items, none, each) {
    if (!items.length) { alt.appendChild(el("p", "muted", none)); return; }
    var ul = el("ul");
    items.forEach(function (x) { var li = el("li"); each(li, x); ul.appendChild(li); });
    alt.appendChild(ul);
  }
  function why(li, x) {
    li.appendChild(x.ref && /^#\d+$/.test(x.ref) ? issueRef(Number(x.ref.slice(1))) : link(x.url, x.ref || ""));
    li.appendChild(document.createTextNode(" " + (x.reason || "")));
  }
  function since() {
    var end = Date.parse((data && data.built_at) || "") || Date.now();
    return st.window === "month" ? null : end - HOURS[st.window] * 3600 * 1000;
  }
  function windowText() {
    return st.window === "month" ? "last 14 days (the Desk reads 14)" : "last " + st.window;
  }

  // Each issue's share of the Goal in this window: its own size over the Goal's, a percentage.
  function shares(number) {
    var mine = (rowsNow() || []).filter(function (r) { return r.goal && r.goal.number === number && sizeOf(r) > 0; });
    var whole = 0, out = {};
    mine.forEach(function (r) { whole += sizeOf(r); });
    mine.forEach(function (r) { out[r.ref] = whole > 0 ? sizeOf(r) / whole * 100 : 0; });
    return out;
  }
  function pct(x) { return x >= 1 || x === 0 ? Math.round(x) + "%" : "<1%"; }

  // A Goal or Area: false if the map knows nothing of it.
  function goalPanel(box, num) {
    var n = Number(num), g = ((data && data.scopes) || {})[num];
    var any = (rowsNow() || []).filter(function (r) { return r.goal && r.goal.number === n; })[0];
    if (!g && !any) return false;
    var lead = g ? g.lead : any.goal.lead, title = g ? g.title : any.goal.title;
    var type = g ? g.type : (any.goal.kind || "Goal");
    var crit = g ? g.criteria : [];
    var ctx = type + (g ? " · " + (crit.length ? g.met + " of " + crit.length + " criteria met" : "no criteria")
      + (g.date ? " · date " + g.date + (g.date_missed ? " (missed)" : "") : "") : "");
    var alt = other(box, type.toUpperCase(), "#" + n, (lead ? lead + ": " : "") + (title || ""),
                    (g && g.url) || "https://github.com/" + (data.repo || "") + "/issues/" + n, ctx);
    if (!g) { alt.appendChild(el("p", "muted", "This build didn't read its done test or the work under it.")); return true; }
    head(alt, "Done test", crit.length ? g.met + " of " + crit.length + " met" : "");
    list(alt, crit, "No criteria found in its body.", function (li, c) {
      li.appendChild(el("b", c.status === "failing" ? "wm-bad" : "", CRIT[c.status] || c.status || ""));
      li.appendChild(document.createTextNode(" " + c.text + (c.detail ? " (" + c.detail + ")" : "")));
    });
    head(alt, "Stuck, and why nothing will start it", g.stuck.length ? String(g.stuck.length) : "");
    list(alt, g.stuck, "Nothing is stuck.", why);
    head(alt, "Waits on you", g.waiting.length ? String(g.waiting.length) : "");
    list(alt, g.waiting, "Nothing waits on you.", why);
    head(alt, "Authority used under it", "last 24 hours");
    list(alt, g.authority, "None.", why);
    var sh = shares(n);
    head(alt, "Open work under it", "share of " + (st.size === "lines" ? "lines" : st.size) + ", " + windowText());
    list(alt, g.subs, "No open sub-issue.", function (li, x) {
      li.appendChild(x.number ? issueRef(x.number, x.ref || "#" + x.number) : link(x.url, x.ref));
      li.appendChild(document.createTextNode(" " + x.title + " · "));
      li.appendChild(el("span", x.go === "go" ? "" : "muted", x.status || x.go || "–"));
      if (x.pr) { li.appendChild(document.createTextNode(" · ")); li.appendChild(link(x.pr.url, "PR #" + x.pr.number)); }
      var share = sh[x.ref || "#" + x.number];
      if (share !== undefined) li.appendChild(el("span", "mono muted", " · " + pct(share)));
    });
    var p = el("p", "wm-sh"); p.appendChild(link(g.url, "Open it on GitHub")); alt.appendChild(p);
    return true;
  }

  function rolePanel(box, name) {
    var roles = (data && data.roles) || {}, r = (roles.of || {})[name];
    if (!r) return false;
    var state = r.blocked ? "blocked" : r.working ? "working" : "idle";
    var alt = other(box, "ROLE", name, cap(name), null, r.does + " · " + state);
    head(alt, "On now");
    list(alt, r.on, "No live session.", function (li, x) {
      var m = /^#(\d+)$/.exec(x.ref);
      li.appendChild(m ? issueRef(Number(m[1])) : link(x.url, x.ref));
      li.appendChild(document.createTextNode(" " + x.title + (x.status === "blocked" ? " (blocked)" : "")));
    });
    var from = since();
    function inWindow(t) { var v = Date.parse(t || ""); return from === null || (v && v >= from); }
    var merged = r.merged.filter(function (p) { return inWindow(p.merged_at); });
    var runs = r.sessions.filter(inWindow);
    head(alt, "PRs and sessions", windowText());
    var tiles = el("dl", "wm-tiles");
    [["Merged", merged.length], ["Open now", r.open.length], ["Changes requested at head", r.changes.length],
     ["Sessions run", runs.length]].forEach(function (t) {
      var d = el("div", "wm-num"); d.appendChild(el("dt", "", t[0])); d.appendChild(el("dd", "", String(t[1])));
      tiles.appendChild(d);
    });
    alt.appendChild(tiles);
    function pr(li, p) {
      li.appendChild(link(p.url, "#" + p.number));
      li.appendChild(document.createTextNode(" " + p.title));
    }
    head(alt, "Merged", windowText());
    list(alt, merged, "Nothing merged in the window.", pr);
    head(alt, "Open");
    list(alt, r.open, "No open PR.", pr);
    head(alt, "Changes requested at head");
    list(alt, r.changes, "None.", pr);
    head(alt, name === "merger" ? "Its calls" : "The merger's calls on its PRs", "last 24 hours");
    list(alt, r.calls, "None.", function (li, c) {
      li.appendChild(link(c.url, "PR #" + c.number));
      li.appendChild(document.createTextNode(" " + c.group + (c.reason ? ": " + c.reason : "")));
    });
    if (r.ask) {
      head(alt, "Ask it something");
      var a = el("p");
      a.appendChild(document.createTextNode("Comment "));
      a.appendChild(el("code", "", "Ask: " + name + ": …"));
      a.appendChild(document.createTextNode(" on "));
      a.appendChild(roles.report_issue
        ? link("https://github.com/" + (data.repo || "") + "/issues/" + roles.report_issue, "#" + roles.report_issue)
        : document.createTextNode("the report issue"));
      a.appendChild(document.createTextNode(". It starts once and answers there (GOV-0029)."));
      alt.appendChild(a);
    }
    return true;
  }

  function emptyPanel(box) {
    box.classList.add("wm-sel-empty");
    box.classList.remove("wm-sel-other");
    setText("wm-sel-kind", "SELECTED");
    setText("wm-sel-ref", "–");
    setText("wm-sel-by", "–"); setText("wm-sel-blocks", "–");
    clear($("wm-sel-alt"));
    var t = $("wm-sel-title"); clear(t); t.title = "";
    t.appendChild(document.createTextNode("Click a box, or an item in a list below, to see it here."));
    setText("wm-sel-ctx", "–");
    var segs = $("wm-sel-sgs").children;
    for (var i = 0; i < segs.length; i++) segs[i].className = "wm-sg";
    setText("wm-sel-stage", "–");
    var bars = $("wm-sel-bars").children;
    for (var k = 0; k < bars.length; k++) {
      clear(bars[k]); bars[k].className = "wm-bar"; bars[k].title = "";
      var b = el("i"); b.style.height = PLACEHOLDER[k % PLACEHOLDER.length] + "%"; bars[k].appendChild(b);
    }
    setText("wm-sel-dsum", "–"); setText("wm-sel-peak", "–");
    var strip = $("wm-sel-strip");
    while (strip.children.length > 1) strip.removeChild(strip.lastChild);
    setText("wm-sel-grp", "–");
    var spans = $("wm-sel-pax").children;
    spans[0].textContent = "0"; spans[1].textContent = "–"; spans[2].textContent = "–";
    numbers(null);
  }

  // Any element with data-wm-ref (the Work map's lists) selects that issue.
  // Any element with data-wm-sel (an issue "#N", "goal-N" or "role-NAME", #1115) selects it.
  document.addEventListener("click", function (ev) {
    var t = ev.target && ev.target.closest ? ev.target.closest("[data-wm-ref]") : null;
    if (t) { select(t.getAttribute("data-wm-ref")); return; }
    var s2 = ev.target && ev.target.closest ? ev.target.closest("[data-wm-sel]") : null;
    if (s2 && st.selected !== s2.getAttribute("data-wm-sel")) select(s2.getAttribute("data-wm-sel"));
  });

  // ------------------------------------------------------------ the lists (#1084)

  // workmap.py's lists() picked and ordered each window's matches for each size, as
  // [ref, value, figure]. Here: keep those in the zoomed group, show five, count them all.
  var SHOW = 5;
  var LONGER = { hour: "day", day: "week", week: "month" };
  var QUIET_LINE = "Cost under half its usual, or idle now after spend in the next longer window.";

  function figText(x) {
    if (st.size === "cost") return usd(x);
    if (st.size === "tokens") return short(x || 0) + " tokens";
    return num(x || 0, 0) + " lines";
  }
  function stageText(r) { return r.stage ? r.stage : r.state === "closed" ? "closed" : "no stage"; }
  function pct(x) { return Math.round(Math.abs(x) * 100) + "%"; }

  // The value on the right, in mono, and the muted line under the title.
  function listText(key, it, r) {
    var ref = r.ref, role = r.role || "no role";
    if (key === "hot") return ["+" + pct(it[1] - 1), ref + " · usual " + usd(it[2]) + ", now " + usd(r.cost)];
    if (key === "quiet") {
      if (it[1] === null) return ["idle", ref + " · " + figText(it[2]) + " in the " + LONGER[st.window]];
      return ["−" + pct(1 - it[1]), ref + " · usual " + usd(it[2]) + ", now " + usd(r.cost)];
    }
    if (key === "yield") {
      return [num(it[1], it[1] < 10 ? 1 : 0) + " " + UNIT[st.size],
              ref + " · " + r.outcomes + (r.outcomes === 1 ? " outcome" : " outcomes") + " for " + sizeText(r)];
    }
    if (key === "blocked") return [sizeText(r), ref + " · was " + (r.blocked_at || "queued") + " · " + role];
    return [sizeText(r), ref + " · " + stageText(r) + " · " + role];
  }

  function listRow(key, it, r) {
    var li = el("li");
    var b = el("button", "wm-li");
    b.type = "button";
    b.setAttribute("data-wm-ref", r.ref);
    b.setAttribute("aria-controls", "wm-sel");
    b.setAttribute("aria-pressed", r.ref === st.selected ? "true" : "false");
    var t = listText(key, it, r);
    var top = el("span", "wm-lt");
    top.appendChild(el("span", "wm-ln", r.title || r.ref));
    var flags = [];
    if (r.needs_you) { top.appendChild(el("span", "wm-lf wm-lf-you", "You")); flags.push("needs you"); }
    if (r.stage === "blocked") { top.appendChild(el("span", "wm-lf wm-lf-blk", "Blocked")); flags.push("blocked"); }
    b.appendChild(top);
    b.appendChild(el("span", "wm-lv mono", t[0]));
    b.appendChild(el("span", "wm-lx muted", t[1]));
    b.title = (r.title || r.ref) + "\n" + t[1];
    b.setAttribute("aria-label", (r.title || r.ref) + ": " + t[0] + ", " + t[1] + (flags.length ? ", " + flags.join(", ") : ""));
    li.appendChild(b);
    return li;
  }

  function drawLists() {
    var box = $("wm-lists");
    if (!box) return;
    var why = null, sets = null;
    if (!data || data.error) why = "The Work map's data wasn't read in this build.";
    else if (!rowsNow()) why = st.window === "month" ? "Month isn't in the Desk's data." : "This window isn't in the build's data.";
    else sets = ((data.lists || {})[st.window] || {})[st.size] || {};
    var secs = box.querySelectorAll("[data-list]");
    for (var i = 0; i < secs.length; i++) {
      var sec = secs[i], key = sec.getAttribute("data-list");
      var ol = sec.querySelector(".wm-lol"), count = sec.querySelector(".wm-lc");
      clear(ol);
      var shown = [];
      if (sets) {
        (sets[key] || []).forEach(function (it) {
          var f = findRow(it[0]);
          if (f && (st.zoom === null || groupOf(f.row) === st.zoom)) shown.push({ it: it, row: f.row });
        });
      }
      if (key === "quiet") {
        var longer = LONGER[st.window];
        var line = sets && longer && !rowsOf(longer)
          ? "Cost under half its usual. Idle ones need the " + longer + ", which the Desk doesn't read."
          : QUIET_LINE;
        var d = sec.querySelector(".wm-ld"); d.textContent = line; d.title = line;
      }
      // Needs you: then the decisions waiting its rows don't show (#1114), oldest first, and
      // it shows them all, scrolling inside its five rows' height.
      var extra = key === "needs" && sets && st.zoom === null ? needsExtra(shown) : [];
      count.textContent = sets ? String(shown.length + extra.length) : "–";
      if (!shown.length && !extra.length) { ol.appendChild(el("li", "wm-lnone muted", why || sec.getAttribute("data-empty"))); continue; }
      (key === "needs" ? shown : shown.slice(0, SHOW)).forEach(function (x) { ol.appendChild(listRow(key, x.it, x.row)); });
      extra.forEach(function (d) { ol.appendChild(extraRow(d)); });
    }
  }
  function needsExtra(shown) {
    var here = shown.map(function (x) { return x.row.ref; });
    return (data.needs_extra || []).filter(function (d) {
      return !(d.refs || []).some(function (r) { return here.indexOf(r) >= 0; });
    });
  }

  // A decision waiting that isn't a row of the list: it selects its issue when that is on
  // the map, else it links to where it's answered on GitHub.
  function extraRow(d) {
    var li = el("li");
    var onMap = (d.refs || []).filter(function (r) { return findRow(r); })[0];
    var b;
    if (onMap) {
      b = el("button", "wm-li");
      b.type = "button";
      b.setAttribute("data-wm-ref", onMap);
      b.setAttribute("aria-controls", "wm-sel");
      b.setAttribute("aria-pressed", onMap === st.selected ? "true" : "false");
    } else if (d.url) {
      b = el("a", "wm-li"); b.href = d.url;
    } else b = el("span", "wm-li");
    var top = el("span", "wm-lt");
    top.appendChild(el("span", "wm-ln", d.title || d.ref));
    top.appendChild(el("span", "wm-lf wm-lf-you", "You"));
    b.appendChild(top);
    var v = d.age ? "waiting " + d.age : (d.ttl ? "TTL " + d.ttl : "");
    b.appendChild(el("span", "wm-lv mono", v));
    var line = d.ref + " · " + d.scope + (d.why ? " · " + d.why : "");
    b.appendChild(el("span", "wm-lx muted", line));
    b.title = (d.title || d.ref) + "\n" + line;
    b.setAttribute("aria-label", (d.title || d.ref) + ": " + (v ? v + ", " : "") + line + ", needs you");
    li.appendChild(b);
    return li;
  }
  function rowsOf(w) { var r = data && data.windows ? data.windows[w] : null; return Array.isArray(r) ? r : null; }

  // ------------------------------------------------------------ tooltip

  function showTip(r, box) {
    clear(tipEl);
    tipEl.appendChild(el("b", "", r.title || r.ref));
    tipEl.appendChild(el("span", "mono", r.ref === "unattributed" ? "unattributed" : r.ref));
    tipEl.appendChild(el("span", "", goalText(r)));
    tipEl.appendChild(el("span", "", "effort " + (r.effort || "none") + " · role " + (r.role || "none") +
      " · stage " + (r.stage || (r.state === "closed" ? "closed" : "none"))));
    tipEl.appendChild(el("span", "mono", "cost " + usd(r.cost) + " · " + num(r.tokens, 0) + " tokens · " +
      num(r.lines, 0) + " lines · " + r.outcomes + (r.outcomes === 1 ? " outcome" : " outcomes")));
    tipEl.hidden = false;
    var W = mapEl.clientWidth, H = mapEl.clientHeight;
    var bx = box.offsetLeft, by = box.offsetTop, bw = box.offsetWidth, bh = box.offsetHeight;
    var tw = tipEl.offsetWidth, th = tipEl.offsetHeight;
    var x = Math.max(0, Math.min(W - tw, bx + bw / 2 - tw / 2));
    var y = by + bh + 4 + th <= H ? by + bh + 4 : Math.max(0, by - th - 4);
    tipEl.style.left = x + "px"; tipEl.style.top = y + "px";
  }
  function hideTip() { tipEl.hidden = true; }

  // ------------------------------------------------------------ controls

  function syncButtons() {
    var bs = document.querySelectorAll(".wm-seg button[data-k]");
    for (var i = 0; i < bs.length; i++) {
      bs[i].setAttribute("aria-pressed", st[bs[i].getAttribute("data-k")] === bs[i].getAttribute("data-v") ? "true" : "false");
    }
    var ms = document.querySelectorAll(".sp-pick[data-mark]");
    for (var j = 0; j < ms.length; j++) {
      ms[j].setAttribute("aria-pressed", st.mark === ms[j].getAttribute("data-mark") ? "true" : "false");
    }
  }

  var bs = document.querySelectorAll(".wm-seg button[data-k]");
  for (var i = 0; i < bs.length; i++) {
    bs[i].disabled = false;
    bs[i].addEventListener("click", function (ev) {
      var k = ev.currentTarget.getAttribute("data-k"), v = ev.currentTarget.getAttribute("data-v");
      if (k === "group" && st.group !== v) { st.zoom = null; st.mark = null; }
      st[k] = v; save(); writeUrl(false); draw();
    });
  }

  // The strip (#1114): picking "flagged" or "decisions waiting" sets Group by to Goal and
  // outlines the matching boxes; picking it again clears the outline. Nothing is resized.
  // One listener on the page, since the strip is redrawn from each newer state.json (#1135).
  var ms = document.querySelectorAll(".sp-pick[data-mark]");
  for (var mi = 0; mi < ms.length; mi++) ms[mi].disabled = false;
  document.addEventListener("click", function (ev) {
    var b = ev.target && ev.target.closest ? ev.target.closest(".sp-pick[data-mark]") : null;
    if (!b) return;
    var v = b.getAttribute("data-mark");
    if (st.mark === v) { st.mark = null; draw(); return; }
    st.mark = v;
    if (st.group !== "goal") { st.group = "goal"; st.zoom = null; save(); writeUrl(false); }
    draw();
  });

  // Back and Forward: the URL's view and selection, as on opening it.
  window.addEventListener("popstate", function () { readUrl(); draw(); });

  // ------------------------------------------------------------ the strip, Briefing, tape, masthead (#1135)

  // What map.json doesn't carry, drawn from state.json's `workmap` and `owner_last_acted` as
  // workmap_page.py and strip.py draw it at build time. Each part is built whole, then swapped
  // in, so one that fails to draw keeps what it showed.
  function plural(n, word) { return n + " " + word + (n === 1 ? "" : "s"); }

  function stripNode(s) {
    var f = (s.flagged || []).length, sec = el("section", "sp");
    sec.setAttribute("aria-label", "Counts");
    function pickBtn(mark, cls, text) {
      var b = el("button", "sp-i sp-pick" + cls, text);
      b.type = "button";
      b.setAttribute("data-mark", mark);
      b.setAttribute("aria-pressed", st.mark === mark ? "true" : "false");
      return b;
    }
    sec.appendChild(pickBtn("flagged", f ? " sp-red" : "", f + " of " + s.scopes + " Goals and Areas flagged"));
    sec.appendChild(pickBtn("decisions", s.waiting ? " sp-owner" : "",
      plural(s.waiting, "decision") + " waiting" + (s.oldest ? ", oldest " + s.oldest : "")));
    sec.appendChild(el("span", "sp-i", s.working + " agents working of " + s.agents + " live"));
    sec.appendChild(el("span", "sp-i", s.authority + " uses of your authority, last " + s.authority_hours + "h"));
    if (s.error) sec.appendChild(el("span", "sp-i sp-red", "trouble report not read: counts may be low"));
    return sec;
  }

  // A line of report Markdown: `code` and **bold** kept, the rest text (report.inline's rule).
  var INLINE = /`([^`]+)`|\*\*(.+?)\*\*/g;
  function inline(p, text) {
    var i = 0, m;
    text = String(text || "");
    INLINE.lastIndex = 0;
    while ((m = INLINE.exec(text)) !== null) {
      if (m.index > i) p.appendChild(document.createTextNode(text.slice(i, m.index)));
      p.appendChild(m[1] !== undefined ? el("code", "", m[1]) : el("b", "", m[2]));
      i = INLINE.lastIndex;
    }
    if (i < text.length) p.appendChild(document.createTextNode(text.slice(i)));
    return p;
  }

  function colHead(sec, title, line) {
    var h = el("div", "br-colh");
    h.appendChild(el("h2", "br-h", title));
    if (line) h.appendChild(line);
    sec.appendChild(h);
  }

  function briefingNode(br) {
    var sec = el("section", "br-brief wm-brief");
    sec.setAttribute("aria-label", "Briefing");
    if (!br) {
      colHead(sec, "Briefing");
      sec.appendChild(el("p", "muted", "No briefing from the lead in the last few days."));
      return sec;
    }
    var line = el("span", "muted", "from the lead · ");
    line.appendChild(br.url ? link(br.url, br.stamp) : document.createTextNode(br.stamp));
    colHead(sec, "Briefing", line);
    if (br.old) sec.appendChild(el("p", "muted", "None yet today; this is the newest."));
    var body = el("div", "br-briefbody");
    (br.paras || []).forEach(function (x) { body.appendChild(inline(el("p"), x)); });
    sec.appendChild(body);
    return sec;
  }

  function onMap(ref) {
    var ws = (data && data.windows) || {};
    return Object.keys(ws).some(function (w) {
      return (ws[w] || []).some(function (r) { return r.ref === ref && r.issue !== null && r.issue !== undefined; });
    });
  }

  function tapeNode(items) {
    var sec = el("section", "tp");
    sec.setAttribute("aria-label", "Tape");
    colHead(sec, "Tape", el("span", "muted", "reports, merges, your acts and governance, newest first"));
    var box = el("div", "tp-box");
    sec.appendChild(box);
    if (!items.length) { box.appendChild(el("p", "muted tp-none", "Nothing on the tape yet.")); return sec; }
    var ol = el("ol", "tp-ol");
    items.forEach(function (x) {
      var li = el("li", "tp-i"), meta = el("span", "tp-m"), text;
      if (x.time) {
        var t = el("time", "mono muted", x.when);
        t.setAttribute("datetime", x.time.slice(0, 19) + "Z");
        meta.appendChild(t);
      } else meta.appendChild(el("span", "mono muted", "?"));
      meta.appendChild(el("span", "tp-w", x.who));
      meta.appendChild(el("span", "tp-k" + (x.flag ? " sp-red" : ""), x.kind));
      li.appendChild(meta);
      if (x.ref && onMap(x.ref)) {
        text = el("button", "tp-t wm-pick", x.text);
        text.type = "button";
        text.setAttribute("data-wm-sel", x.ref);
        text.setAttribute("aria-controls", "wm-sel");
        text.title = "Show " + x.ref + " in the Selected panel";
      } else text = el("span", "tp-t", x.text);
      li.appendChild(text);
      var l = el("span", "tp-l");
      l.appendChild(x.url ? link(x.url, "on GitHub") : el("span", "muted", "no link"));
      li.appendChild(l);
      ol.appendChild(li);
    });
    box.appendChild(ol);
    return sec;
  }

  // The masthead's changing part (#402), as Crew's and Governance's scripts draw it.
  function utc(t) { return t ? t.slice(0, 10) + " " + t.slice(11, 16) + " UTC" : ""; }
  function ago(t, now) {
    if (!t) return "never";
    var sec = Math.max(0, Math.floor((Date.parse(now) - Date.parse(t)) / 1000));
    var units = [["d", 86400], ["h", 3600], ["m", 60]];
    for (var i = 0; i < units.length; i++) {
      if (sec >= units[i][1]) return Math.floor(sec / units[i][1]) + units[i][0] + " ago";
    }
    return "just now";
  }
  function mastNodes(d) {
    var t = d.built_at, o = d.owner_last_acted || { status: "unknown" }, owner = el("span", "owner");
    if (o.status === "acted") {
      owner.appendChild(document.createTextNode("Owner last acted "));
      var a = el("span", "", ago(o.time, t)); a.title = utc(o.time);
      owner.appendChild(a);
      owner.appendChild(document.createTextNode(": "));
      if (o.ref || o.extra) {
        owner.appendChild(document.createTextNode(o.verb));
        if (o.ref) { owner.appendChild(document.createTextNode(" ")); owner.appendChild(link(o.link, o.ref)); }
        if (o.extra) {
          owner.appendChild(document.createTextNode(" "));
          var code = el("code", "", o.extra);
          if (o.ref || !(typeof o.link === "string" && o.link.indexOf("https://github.com/") === 0)) owner.appendChild(code);
          else { var ca = el("a"); ca.href = o.link; ca.appendChild(code); owner.appendChild(ca); }
        }
      } else owner.appendChild(link(o.link, o.verb));
    } else if (o.status === "none") {
      owner.appendChild(document.createTextNode("Owner: no activity in the last " + plural(o.days, "day")));
    } else owner.appendChild(document.createTextNode("Owner: unknown"));
    var built = el("span", "muted", "built ");
    var tm = el("time", "stamp", t.slice(11, 16) + " UTC");
    tm.setAttribute("datetime", t); tm.title = utc(t);
    built.appendChild(tm);
    return [el("span", "live", "LIVE"), built, owner];
  }

  function swap(sel, make) {
    var old = document.querySelector(sel);
    if (!old) return;
    try { var next = make(); old.parentNode.replaceChild(next, old); } catch (e) { /* keep it */ }
  }

  function drawState(s) {
    var w = s.workmap;
    swap("section.sp", function () { return stripNode(w.strip); });
    swap("section.wm-brief", function () { return briefingNode(w.briefing); });
    swap("section.tp", function () { return tapeNode(w.tape || []); });
    var box = document.querySelector('header.mast [data-panel="mast"]');
    if (box) {
      try {
        var nodes = mastNodes(s);   // built whole first, so a failure keeps the masthead
        clear(box);
        nodes.forEach(function (n) { box.appendChild(n); });
      } catch (e) { /* keep the masthead */ }
    }
  }

  // ------------------------------------------------------------ live refresh (#1138, #1135)

  // Every LIVE.every ms while the tab is visible, fetch same-origin map.json and state.json
  // (GOV-0051). A newer map.json redraws the map, lists and Selected panel; a newer state.json
  // the strip, Briefing, tape, masthead and the Goals, roles and decisions waiting the map and
  // panel use. The controls, zoom and selection stay. As Crew and Governance do, each only moves
  // forward, and the masthead's LIVE mark greys once the older of the two is older than
  // LIVE.stale. No part of the page waits for a reload.
  var LIVE = data && data.live;
  function stampEl() { return document.querySelector("header.mast time.stamp"); }
  var pageAt = (stampEl() && stampEl().getAttribute("datetime")) || "";
  var mapAt = (data && data.built_at) || pageAt;
  var stateAt = pageAt;
  function shownAt() { return Date.parse(mapAt) < Date.parse(stateAt) ? mapAt : stateAt; }

  function fresh() {
    var old = !(Date.now() - Date.parse(shownAt()) <= LIVE.stale);
    var marks = document.querySelectorAll("header.mast .live");
    for (var i = 0; i < marks.length; i++) marks[i].classList.toggle("stale", old);
  }

  // map.json as the page's JSON block carries it (workmap_page.page_data): each row without its
  // `days`, and each issue's 14 days once. null if it isn't a map.json this script can draw.
  function fromMap(m) {
    if (!m || typeof m !== "object" || m.schema !== 1 || typeof m.built_at !== "string" ||
        !m.windows || typeof m.windows !== "object" || !m.lists || typeof m.lists !== "object") return null;
    var windows = {}, dates = [], of = {}, ok = true;
    Object.keys(m.windows).forEach(function (w) {
      if (!Array.isArray(m.windows[w])) { ok = false; return; }
      windows[w] = m.windows[w].map(function (r) {
        if (!r || typeof r !== "object" || typeof r.ref !== "string") { ok = false; return null; }
        var ds = Array.isArray(r.days) ? r.days : [], out = {};
        if (ds.length && !Object.prototype.hasOwnProperty.call(of, r.ref)) {
          if (!dates.length) dates = ds.map(function (d) { return d && d.date; });
          of[r.ref] = ds.map(function (d) { return [d && d.cost !== undefined ? d.cost : null, (d && d.outcomes) || 0]; });
        }
        Object.keys(r).forEach(function (k) { if (k !== "days") out[k] = r[k]; });
        return out;
      });
    });
    if (!ok) return null;
    return { built_at: m.built_at, method: m.method, windows: windows, days: { dates: dates, of: of }, lists: m.lists };
  }

  // The masthead shows the older build of what's on screen.
  function stamp() {
    var e = stampEl(), t = Date.parse(shownAt());
    if (!e || isNaN(t)) return;
    var iso = new Date(t).toISOString();
    e.setAttribute("datetime", iso.slice(0, 19) + "Z");
    e.title = iso.slice(0, 10) + " " + iso.slice(11, 16) + " UTC";
    e.textContent = iso.slice(11, 16) + " UTC";
  }

  // Redraw from data with `next`'s fields in it; if it can't be drawn, put the last ones back.
  function redraw(fields, next) {
    var before = {};
    fields.forEach(function (k) { before[k] = data[k]; data[k] = next[k]; });
    try { draw(); } catch (e) {
      fields.forEach(function (k) { data[k] = before[k]; });
      draw();
      return false;
    }
    return true;
  }

  var MAP_FIELDS = ["built_at", "method", "windows", "days", "lists", "error"];
  function applyMap(m) {
    var next = fromMap(m), t = next ? Date.parse(next.built_at) : NaN;
    // A cache can serve a map.json older than the page; only ever move forward.
    if (isNaN(t) || t <= Date.parse(mapAt)) return;
    if (redraw(MAP_FIELDS, next)) mapAt = next.built_at;
  }

  var STATE_FIELDS = ["strip", "needs_extra", "scopes", "roles"];
  function applyState(s) {
    var w = s && s.workmap;
    if (!s || s.schema !== 1 || typeof s.built_at !== "string" || !w || typeof w !== "object" ||
        !w.strip || !Array.isArray(w.strip.flagged) || !Array.isArray(w.strip.decisions) ||
        !Array.isArray(w.needs_extra) || !w.scopes || !w.roles || !Array.isArray(w.tape)) return;
    if (!(Date.parse(s.built_at) > Date.parse(stateAt))) return;
    var was = STRIP;
    STRIP = w.strip;
    if (!redraw(STATE_FIELDS, w)) { STRIP = was; return; }
    drawState(s);
    stateAt = s.built_at;
  }

  var GET = { cache: "no-store", credentials: "same-origin" };
  function body(req) {
    return req.then(function (r) { return r.ok ? r.json() : null; }).catch(function () { return null; });
  }

  function poll() {
    if (document.hidden) { fresh(); return; }
    Promise.all([body(fetch("map.json?t=" + Date.now(), GET)), body(fetch("state.json?t=" + Date.now(), GET))])
      .then(function (both) { applyMap(both[0]); applyState(both[1]); })
      .catch(function () {})
      .then(function () { stamp(); fresh(); });
  }

  if (LIVE && typeof LIVE.every === "number" && LIVE.every >= 1000 && typeof LIVE.stale === "number" &&
      typeof window.fetch === "function") {
    fresh();
    window.setInterval(poll, LIVE.every);
    document.addEventListener("visibilitychange", function () { if (!document.hidden) poll(); });
  }

  var nojs = document.getElementById("wm-nojs");
  if (nojs) nojs.hidden = true;
  var pending = null;
  window.addEventListener("resize", function () {
    if (pending) window.clearTimeout(pending);
    pending = window.setTimeout(draw, 120);
  });
  draw();
})();
