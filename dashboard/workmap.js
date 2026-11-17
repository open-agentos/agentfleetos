// The Work map (#1082, FEAT-9): a squarified treemap of map.json's rows, drawn in the browser.
// workmap_page.py inlines this file and names its hash in the page's CSP. It reads the data
// from the page's JSON block, builds DOM nodes with createElement and text nodes only (no
// innerHTML, no eval), and never fetches. It shows each issue's own figures and each group's
// share as a percentage: no amount is ever summed across issues for display (GOV-0033).
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

  var st = Object.assign({}, DEFAULTS, { zoom: null, selected: null });
  try {
    var saved = JSON.parse(window.localStorage.getItem(KEY) || "{}");
    Object.keys(CHOICES).forEach(function (k) {
      if (saved && CHOICES[k].indexOf(saved[k]) >= 0) st[k] = saved[k];
    });
  } catch (e) { /* no storage: the defaults stand */ }

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

  function draw() {
    clear(mapEl); clear(legendEl); clear(crumbEl); hideTip();
    syncButtons();
    var all = rowsNow();
    if (!data || data.error) { note("The Work map's data wasn't read in this build" + (data && data.error ? ": " + data.error : ".")); crumb([]); return; }
    if (!all) {
      note(st.window === "month"
        ? "Month isn't in the Desk's data: the build reads 14 days of heartbeats, too few for a month. `swarm map --window month` prints it."
        : "This window isn't in the build's data.");
      crumb([]); return;
    }
    var shown = all.filter(function (r) { return sizeOf(r) > 0; });
    var left = all.length - shown.length;
    var groups = new Map();
    shown.forEach(function (r) {
      var g = groupOf(r);
      if (!groups.has(g)) groups.set(g, { name: g, rows: [], value: 0 });
      var e = groups.get(g); e.rows.push(r); e.value += sizeOf(r);
    });
    var whole = 0;
    groups.forEach(function (g) { whole += g.value; });
    if (st.zoom !== null && !groups.has(st.zoom)) st.zoom = null;
    crumb(st.zoom === null ? [] : [st.zoom]);
    var list = Array.from(groups.values()).filter(function (g) { return st.zoom === null || g.name === st.zoom; });
    list.sort(function (a, b) { return b.value - a.value || (a.name < b.name ? -1 : 1); });
    var inView = [];
    list.forEach(function (g) { inView = inView.concat(g.rows); });
    var sh = shades(inView);
    var W = mapEl.clientWidth, H = mapEl.clientHeight;
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
      if (st.zoom === null) head.addEventListener("click", function () { st.zoom = g.name; draw(); });
      else head.disabled = true;
      box.appendChild(head);
      mapEl.appendChild(box);
      var items = g.rows.map(function (r) { return { value: sizeOf(r), row: r }; })
        .sort(function (a, b) { return b.value - a.value; });
      squarify(items, gp.x, gp.y + HEAD, dim.w, Math.max(0, dim.h - HEAD)).forEach(function (p) {
        mapEl.appendChild(issueBox(p, sh.of.get(p.item.row)));
      });
    });
    legend(sh.ends, left);
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
    if (dim.w >= 44 && dim.h >= 18) b.appendChild(el("span", "wm-t", r.title || r.ref));
    if (dim.w >= 44 && dim.h >= 34) b.appendChild(el("span", "wm-m", sizeText(r) + " · " + shade.text));
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
    var boxes = mapEl.querySelectorAll(".wm-box");
    for (var i = 0; i < boxes.length; i++) {
      var on = boxes[i].getAttribute("data-ref") === st.selected;
      boxes[i].classList.toggle("wm-sel", on);
      boxes[i].setAttribute("aria-pressed", on ? "true" : "false");
    }
  }

  function crumb(path) {
    var root = ROOT[st.group];
    if (!path.length) { crumbEl.appendChild(el("span", "", root)); return; }
    var back = el("button", "wm-back", root);
    back.type = "button";
    back.addEventListener("click", function () { st.zoom = null; draw(); });
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
    [["wm-k-fold", "no outcome"], ["wm-k-needs", "needs you"], ["wm-k-blocked", "blocked"], ["wm-k-sel", "selected"]]
      .forEach(function (k) {
        var s = el("span", "wm-key"); s.appendChild(el("span", "wm-sw " + k[0])); s.appendChild(document.createTextNode(k[1]));
        legendEl.appendChild(s);
      });
    if (left) legendEl.appendChild(el("span", "wm-left muted", left + (left === 1 ? " issue" : " issues") +
      " with no " + (st.size === "lines" ? "lines changed" : st.size) + " in this window left off"));
  }

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
  }

  var bs = document.querySelectorAll(".wm-seg button[data-k]");
  for (var i = 0; i < bs.length; i++) {
    bs[i].disabled = false;
    bs[i].addEventListener("click", function (ev) {
      var k = ev.currentTarget.getAttribute("data-k"), v = ev.currentTarget.getAttribute("data-v");
      if (k === "group" && st.group !== v) st.zoom = null;
      st[k] = v; save(); draw();
    });
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
