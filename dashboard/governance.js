// Governance, drawn client-side (#1140, stage 3 of #1135; option 3 of #1102). govpage.py fills
// in the settings at build time and generate.py serves it as js/governance.js; the page's CSP
// allows only this script, by hash. It draws every section from plain fields (the page's JSON
// block first, then each newer same-origin state.json) with createElement, setAttribute and
// text nodes. It never parses HTML, sets markup or runs strings as code, so text from the
// repo stays text. It doesn't read state.json's `desk`.
(function () {
  "use strict";
  var EVERY = /*EVERY*/0, STALE = /*STALE*/0;
  var SVG = "http://www.w3.org/2000/svg";
  // Links only to https URLs or a fragment on this page.
  var SAFE_URL = /^(https:\/\/|#[A-Za-z0-9_-]*$)/;
  var MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  var SECTIONS = ["rulings", "questions", "committees", "authority", "precedent", "trends"];
  var builtAt = null;

  // ------------------------------------------------------------ building nodes

  function add(el, kids) {
    var i, k;
    for (i = 0; i < kids.length; i++) {
      k = kids[i];
      if (k === null || k === undefined || k === false || k === "") { continue; }
      if (Array.isArray(k)) { add(el, k); continue; }
      el.appendChild(typeof k === "object" ? k : document.createTextNode(String(k)));
    }
    return el;
  }

  // h("td", {class: "num"}, child, ...): an element; strings become text nodes.
  function h(tag, attrs) {
    var el = document.createElement(tag), k;
    for (k in attrs || {}) {
      if (Object.prototype.hasOwnProperty.call(attrs, k) && attrs[k] !== null && attrs[k] !== undefined) {
        el.setAttribute(k, String(attrs[k]));
      }
    }
    return add(el, Array.prototype.slice.call(arguments, 2));
  }

  function s(tag, attrs) {
    var el = document.createElementNS(SVG, tag), k;
    for (k in attrs) { if (Object.prototype.hasOwnProperty.call(attrs, k)) { el.setAttribute(k, String(attrs[k])); } }
    return add(el, Array.prototype.slice.call(arguments, 2));
  }

  // A link when the URL is safe, else the text alone.
  function link(text, url) {
    return typeof url === "string" && SAFE_URL.test(url) ? h("a", {href: url}, text) : text;
  }

  function muted(text) { return h("span", {"class": "muted"}, text); }
  function dash() { return muted("—"); }
  function table(cls, head, rows) {
    return h("div", {"class": "scroll"}, h("table", cls ? {"class": cls} : null,
      h("tr", null, head.map(function (x) { return typeof x === "string" ? h("th", null, x) : x; })), rows));
  }
  function plural(n, word) { return n + " " + word + (n === 1 ? "" : "s"); }
  function join(items, sep) {
    var out = [], i;
    for (i = 0; i < items.length; i++) { if (i) { out.push(sep); } out.push(items[i]); }
    return out;
  }
  // `code` spans in a ruling stay code; the rest is text.
  function codeSpans(text) {
    return String(text).split("`").map(function (p, i) { return i % 2 ? h("code", null, p) : p; });
  }

  // ------------------------------------------------------------ times (UTC, RFC 3339 in)

  function stamp(t) { return t ? t.slice(0, 10) + " " + t.slice(11, 16) + " UTC" : ""; }
  function ago(t, now) {
    if (!t) { return "never"; }
    var sec = Math.max(0, Math.floor((Date.parse(now) - Date.parse(t)) / 1000));
    var units = [["d", 86400], ["h", 3600], ["m", 60]], i;
    for (i = 0; i < units.length; i++) {
      if (sec >= units[i][1]) { return Math.floor(sec / units[i][1]) + units[i][0] + " ago"; }
    }
    return "just now";
  }
  function dayText(d) { return parseInt(d.slice(8, 10), 10) + " " + MONTHS[parseInt(d.slice(5, 7), 10) - 1]; }

  // ------------------------------------------------------------ the masthead (#402)

  function mast(d) {
    var t = d.built_at, o = d.owner_last_acted || {status: "unknown"}, owner, what;
    if (o.status === "acted") {
      what = [o.verb];
      if (o.ref) { what.push(" ", link(o.ref, o.link)); }
      if (o.extra) {
        what.push(" ", o.ref ? h("code", null, o.extra) : link(h("code", null, o.extra), o.link));
      } else if (!o.ref) {
        what = [link(o.verb, o.link)];
      }
      owner = h("span", {"class": "owner"}, "Owner last acted ",
        h("span", {title: stamp(o.time)}, ago(o.time, t)), ": ", what);
    } else if (o.status === "none") {
      owner = h("span", {"class": "owner"}, "Owner: no activity in the last " + plural(o.days, "day"));
    } else {
      owner = h("span", {"class": "owner"}, "Owner: unknown");
    }
    return [h("span", {"class": "live"}, "LIVE"),
      h("span", {"class": "muted"}, "built ",
        h("time", {"class": "stamp", datetime: t, title: stamp(t)}, t.slice(11, 16) + " UTC")),
      owner];
  }

  // ------------------------------------------------------------ #rulings (#401)

  function rulings(d) {
    var g = d.governance, repo = d.repo, recs = g.all_records || [];
    var base = "https://github.com/" + repo + "/blob/main/governance";
    var out = [h("h2", null, "Rulings"), h("h3", null, "Decision log (" + recs.length + ")")];
    if (!recs.length) {
      out.push(h("p", {"class": "muted"}, g.index_found ? "none" : "governance/INDEX.md not found"));
      return out;
    }
    out.push(table(null, ["Record", "Ruling", "Domain", "Shape", "Status", "Review by"], recs.map(function (r) {
      var flag = r.flag === "passed"
        ? [" ", h("span", {"class": "pill s-blocked"}, "review date passed"), h("br"),
           muted("not precedent until re-affirmed")]
        : r.flag === "soon" ? [" ", h("span", {"class": "pill s-idle"}, "review due soon")] : null;
      return h("tr", null, h("td", null, h("a", {"class": "id", href: base + "/" + r.file}, r.id)),
        h("td", null, codeSpans(r.ruling)), h("td", null, r.domain), h("td", null, r.shape),
        h("td", null, r.status), h("td", null, r.review_by_text, flag));
    })));
    out.push(h("p", {"class": "muted"}, h("a", {href: "https://github.com/" + repo + "/blob/main/governance/INDEX.md"},
      "Full index")));
    return out;
  }

  // ------------------------------------------------------------ #questions (#355)

  function ttl(q) {
    if (q.ttl === null || q.ttl === undefined) { return muted("none given"); }
    if (!q.ttl_date) { return [q.ttl, h("br"), muted("no date")]; }
    if (q.past_ttl) {
      return [q.ttl_date, h("br"), h("span", {"class": "pill s-blocked"}, "past TTL"), " ",
        muted(-q.days_left + "d ago")];
    }
    return [q.ttl_date, h("br"), muted(q.days_left + "d left")];
  }

  function questions(d) {
    var g = d.governance, qs = d.gov_questions || [], roles = {};
    (d.sessions || []).forEach(function (x) { roles[x.session_id] = x.role; });
    function line(name, pairs) {
      return name + ": " + pairs.map(function (p) { return p[0] + " " + p[1]; }).join(", ");
    }
    var out = [h("h2", null, "Questions"), h("h3", null, "Open gov questions (" + qs.length + ")")];
    if (!qs.length) {
      out.push(h("p", {"class": "muted"}, "None."));
    } else {
      out.push(h("p", {"class": "muted"}, line("By shape", g.by_shape) + " · " + line("by domain", g.by_domain)));
      out.push(table(null, ["Question", "Domain", "Shape", "Blocking", "Opened", "Time to live", "Sessions waiting"],
        qs.map(function (q) {
          var labels = (q.labels || []).filter(function (l) { return l.indexOf("gov:shape/") !== 0 && l !== "gov:blocking"; });
          var shape = q.shape_suggested ? [q.shape, h("br"), muted("suggested")] : q.shape ? q.shape : dash();
          var waiting = (q.waiting || []).map(function (id) {
            return [roles[id] || "session", " ", h("code", null, String(id).slice(0, 8))];
          });
          return h("tr", null,
            h("td", null, link("#" + q.number, q.url), " ", q.title, labels.length ? [h("br"), muted(labels.join(", "))] : null),
            h("td", null, q.domain ? q.domain : dash()), h("td", null, shape),
            h("td", null, q.blocking === true ? "yes" : q.blocking === false ? "no" : dash()),
            h("td", {title: stamp(q.created_ts)}, ago(q.created_ts, d.built_at)),
            h("td", null, ttl(q)), h("td", null, waiting.length ? join(waiting, ", ") : muted("none")));
        })));
    }
    out.push(h("h3", null, "Lapsed questions"));
    if (!(g.lapsed || []).length) {
      out.push(h("p", {"class": "muted"}, "None open or closed in the last " + g.days + " days."));
    } else {
      out.push(h("ul", null, g.lapsed.map(function (q) {
        var state = q.state === "open" ? "open" : "closed";
        var t = q.ttl ? ", time to live " + q.ttl : ", no time to live given";
        return h("li", null, link("#" + q.number, q.url), " ", q.title, " ", muted("(" + state + t + ")"));
      })));
      out.push(h("p", {"class": "muted"}, "A lapsed default stands but is not precedent: the next agent " +
        "to hit the same situation asks again (GOVERNANCE.md §8)."));
    }
    return out;
  }

  // ------------------------------------------------------------ #committees (#354, #404, #409)

  function qText(c) { return "#" + c.question + (c.question_title ? " " + c.question_title : ""); }
  function postTime(t) { return t ? t.slice(5, 10) + " " + t.slice(11, 16) + " UTC" : "posted"; }

  function seatCard(x, waiting) {
    var said;
    if (x.url || x.posted) {
      said = [x.summary ? h("blockquote", null, "“" + x.summary + "”") : h("p", {"class": "muted"}, "no Position section"),
        h("div", {"class": "when"}, link("round " + x.round + " · " + postTime(x.posted), x.url))];
    } else {
      said = h("div", {"class": "when muted"}, waiting ? "up next" : "not posted yet");
    }
    return h("div", {"class": "seat" + (waiting ? " up" : "")},
      h("div", {"class": "who"}, x.seat, " ", muted([x.role + " · ", h("code", null, x.model)])),
      x.recommendation ? h("div", {"class": "reco"}, x.recommendation)
        : h("div", {"class": "reco none"}, "no recommendation yet"),
      x.swing === "moved" ? h("div", {"class": "swing"}, "moved from " + (x.moved_from || "no recommendation"))
        : x.swing === "held" ? h("div", {"class": "swing"}, "held") : null,
      said);
  }

  function desk(c) {
    var k = c.consensus, marks = [], i;
    for (i = 0; i < k.seats; i++) { marks.push(h("span", {"class": i < k.agree ? "on" : ""})); }
    return h("section", {"class": "desk"},
      h("div", {"class": "band"}, h("span", {"class": "live"}, "LIVE"), h("span", {"class": "tag"}, "Committee"),
        h("span", {"class": "q"}, link(qText(c), c.question_url)),
        h("span", null, "Round " + c.round + " of " + c.max_rounds),
        h("span", null, c.waiting_on ? "waiting on " + c.waiting_on : "rounds over"),
        h("span", {"class": "disc"}, link("Discussion #" + c.discussion, c.url))),
      h("div", {"class": "seats"}, c.seats.map(function (x) { return seatCard(x, x.seat === c.waiting_on); })),
      h("div", {"class": "bar" + (k.consensus ? " done" : "")}, h("span", {"class": "marks"}, marks), h("b", null, k.text)));
  }

  function timeline(steps) {
    return join(steps.map(function (x) {
      if (!x.reached) { return muted(x.label); }
      var text = [link(x.label, x.url), x.when ? [" ", muted(x.when)] : null];
      return x.current ? h("b", {"class": "now", title: "current step"}, text) : text;
    }), " → ");
  }

  function cell(x) {
    if (x.kind === "post") {
      return [link(x.time, x.url), x.recommendation ? [h("br"), x.recommendation] : null,
        x.signed ? [h("br"), muted("signed " + x.signed)] : null];
    }
    return {waiting: null, stopped: muted("stopped early"), missed: muted("missed")}[x.kind] || null;
  }

  function convergence(o) {
    var n = o.round;
    return {"none": muted("no recommendations yet"), "agree": "all agree after round " + n,
      "no majority": "no majority after round " + n, "dissent": "dissent: " + o.dissent.join(", "),
      "no dissent": "after round " + n + ": no dissent so far"}[o.kind];
  }

  function one(c) {
    var head = ["Member"], i, dv = c.diversity;
    for (i = 1; i <= c.grid.rounds; i++) { head.push("Round " + i); }
    var posts = c.over_limit.length
      ? [h("span", {"class": "pill s-blocked"}, "over " + c.daily_posts + " posts a day"), " ",
         c.over_limit.map(function (o) { return o.seat + " " + o.count + " on " + o.day; }).join(", ")]
      : "nobody over " + c.daily_posts + " posts a day";
    return [h("h3", null, link(qText(c), c.question_url)),
      h("p", null, "Discussion ", link("#" + c.discussion, c.url), " · ", timeline(c.timeline)),
      table(null, ["Seat", "Role", "Model", "Evidence"], c.members.map(function (m) {
        return h("tr", null, h("td", null, m.seat), h("td", null, m.role), h("td", null, h("code", null, m.model)),
          h("td", null, m.evidence));
      })),
      h("p", null, "§7.2 diversity " + (dv.met ? "met" : "not met") + ": " + plural(dv.models, "model") + ", " +
        plural(dv.evidence, "evidence base")),
      table("grid", head, c.grid.rows.map(function (r) {
        return h("tr", null, h("th", null, r.seat), r.cells.map(function (x) {
          return h("td", null, x.kind === "waiting" ? h("b", null, "waiting on " + r.seat) : cell(x));
        }));
      })),
      h("p", null, convergence(c.outcome), " · rounds used: " + c.rounds_used + " of " + c.max_rounds + " · ", posts)];
  }

  function pastCard(p) {
    var rec = p.record, k = p.consensus;
    return h("div", {"class": "past"},
      h("div", {"class": "rec"}, rec ? link(rec.id, rec.url) : muted("no record yet")),
      h("div", {"class": "q"}, link(qText(p), p.question_url), " · ", link("Discussion #" + p.discussion, p.url)),
      p.summary ? h("blockquote", null, "“", codeSpans(p.summary), "”")
        : h("p", {"class": "muted"}, rec ? "not in governance/INDEX.md yet" : "no ruling recorded"),
      h("div", {"class": "call" + (k.dissent && k.dissent.length ? " split" : "")}, k.text),
      h("ul", null,
        h("li", null, p.rounds_used + " of " + p.max_rounds + " rounds" + (p.stopped_early ? " · stopped early" : "")),
        h("li", null, join(p.models.map(function (m) { return h("code", null, m); }), ", "),
          " · §7.2 " + (p.diversity_met ? "met" : "not met")),
        h("li", null, p.minutes !== null && p.minutes !== undefined ? plural(p.minutes, "minute") + " first to last post"
          : "one post or none"),
        h("li", null, "swing: " + p.swing + " of " + plural(p.seats, "seat") + " changed")));
  }

  function committees(d) {
    var v = d.committee_views || {open: [], ended: [], unparsed: [], notes: []};
    var past = d.past_committees || [];
    var out = [h("h2", null, "Committees"), (d.committee_desk || []).map(desk)];
    out.push(v.open.length ? v.open.map(one) : h("p", {"class": "muted"}, "No open committees."));
    if (v.unparsed.length) {
      out.push(h("p", {"class": "muted"}, "Unparsed: ", join(v.unparsed.map(function (c) {
        return link("#" + c.discussion + (c.title ? " " + c.title : ""), c.url);
      }), ", ")));
    }
    if (v.notes.length) { out.push(h("p", {"class": "muted"}, v.notes.join("; "))); }
    if (past.length) { out.push(h("h2", null, "Past committees"), h("div", {"class": "pasts"}, past.map(pastCard))); }
    if (v.ended.length) {
      out.push(h("details", null, h("summary", null, "Round grids of the " + plural(v.ended.length, "ended committee")),
        v.ended.map(one)));
    }
    return out;
  }

  // ------------------------------------------------------------ #authority (#410)

  function who(i) { return h("span", {"class": "w-" + i.kind, title: i.login || null}, i.name); }
  function whos(items, empty) { return items.length ? join(items.map(who), ", ") : muted(empty); }

  function authority(d) {
    var a = d.authority || {error: "can't read governance/jurisdictions.yml: not found"}, repo = d.repo;
    var out = [h("h2", null, "Authority map")];
    if (a.error) { out.push(h("p", {"class": "muted"}, a.error)); return out; }
    out.push(h("p", {"class": "muted"}, "Who may decide what, from ",
      h("a", {href: "https://github.com/" + repo + "/blob/main/governance/jurisdictions.yml"}, "governance/jurisdictions.yml"),
      ". ", h("span", {"class": "w-agent"}, "Agents"), " in blue, the ", h("span", {"class": "w-owner"}, "owner"),
      " in amber. Agents decide only two-way choices in their domains (GOVERNANCE.md §3); everything else is a ",
      h("code", null, "gov:question"), ". Votes need a quorum of " + a.quorum + " of those eligible; the consent window is " +
      a.consent_window + "."));
    out.push(table("authority", ["Domain", "Decides", "Owner", "Ratify", "Vote-eligible", "Default shape", "Records"],
      a.domains.map(function (x) {
        var recs = x.records.length
          ? [h("a", {href: "#rulings"}, x.records.length + " in force"), h("br"), muted(x.records.join(", ")),
             x.passed.length ? [h("br"), muted("review date passed: " + x.passed.join(", "))] : null]
          : muted("none");
        return h("tr", {id: x.name},
          h("td", null, h("b", null, x.name),
            x.always_one_way ? [" ", h("span", {"class": "pill s-stopped"}, "always one-way")] : null,
            [x.description, x.note].filter(Boolean).map(function (t) { return [h("br"), muted(t)]; })),
          h("td", null, whos(x.decide, "nobody: ask")), h("td", null, who(x.owner)),
          h("td", null, whos(x.ratify, "nobody")), h("td", null, whos(x.vote_eligible, "—")),
          h("td", null, x.default_shape), h("td", null, recs));
      })));
    if (a.elsewhere.length) {
      out.push(h("p", {"class": "muted"}, "In-force records in domains the file doesn't list: " + a.elsewhere.join(", ") + "."));
    }
    out.push(h("p", {"class": "muted"}, "Records count as precedent only while in force and before their review-by " +
      "date (GOVERNANCE.md §6). The full log is under ", h("a", {href: "#rulings"}, "Rulings"), "."));
    return out;
  }

  // ------------------------------------------------------------ #precedent (#408)

  function precedent(d) {
    var p = d.precedent, repo = d.repo, WHO = ["n", "agents", "owner", "reviewer"], top = 0;
    if (!p) { return []; }
    Object.keys(p.counts).forEach(function (r) {
      Object.keys(p.counts[r]).forEach(function (day) { top = Math.max(top, p.counts[r][day].n || 0); });
    });
    var head = ["Record"].concat(p.days.map(function (day) { return h("th", {"class": "num", title: day}, day.slice(5)); }),
      ["Total", "Agents", "Owner", "By reviewer"].map(function (t) { return h("th", {"class": "num"}, t); }));
    var recs = p.records.slice().sort(function (a, b) { return a.id < b.id ? 1 : a.id > b.id ? -1 : 0; });
    var rows = recs.map(function (r) {
      var mine = p.counts[r.id] || {}, t = p.totals[r.id] || {n: 0, agents: 0, owner: 0, reviewer: 0};
      var url = "https://github.com/" + repo + "/blob/main/governance/decisions/" + (r.file || "");
      return h("tr", null, h("td", {"class": "id" + (r.status !== "in-force" ? " muted" : "")}, h("a", {href: url}, r.id)),
        p.days.map(function (day) {
          var n = (mine[day] || {}).n || 0, before = day < r.date;
          return h("td", {"class": "num" + (before || !n ? " muted" : ""),
            style: n && top ? "background:rgba(31,79,184," + (0.08 + 0.32 * n / top).toFixed(2) + ")" : null},
            before ? "" : n || "·");
        }),
        WHO.map(function (k) { return h("td", {"class": "num"}, String(t[k])); }));
    });
    return [h("h2", null, "Precedent in use"),
      h("ul", {"class": "findings"}, p.findings.map(function (f) { return h("li", null, f); })),
      table("precedent", head, rows),
      h("p", {"class": "muted method"}, "A citation is a GOV-NNNN mention in an issue or PR body, comment or review, " +
        "once per text, on or after the record's date. Signature lines, tracking issues, the digest issue and review " +
        "comments on governance/ files don't count. Days are UTC; a blank cell is before the record was made.")];
  }

  // ------------------------------------------------------------ #trends (#406, #407)

  function spark(t) {
    var W = 120, H = 24, PAD = 2, pts = t.series, runs = [], run = [];
    var vals = pts.filter(function (p) { return p.value !== null; }).map(function (p) { return p.value; });
    var top = Math.max.apply(null, [0].concat(vals)) || 1, step = (W - 2 * PAD) / Math.max(pts.length - 1, 1);
    pts.forEach(function (p, i) {
      if (p.value === null) { if (run.length) { runs.push(run); } run = []; return; }
      run.push([(PAD + i * step).toFixed(1), (H - PAD - (p.value / top) * (H - 2 * PAD)).toFixed(1)]);
    });
    if (run.length) { runs.push(run); }
    var alt = pts.length ? t.label + " by day, " + dayText(pts[0].date) + " to " + dayText(pts[pts.length - 1].date) + ": " +
      pts.map(function (p) { return p.value === null ? "none" : String(p.value); }).join(", ") : "";
    return s("svg", {"class": "spark", role: "img", "aria-label": alt, width: W, height: H, viewBox: "0 0 " + W + " " + H},
      s("title", {}, alt),
      runs.map(function (r) {
        return r.length > 1 ? s("polyline", {points: r.map(function (xy) { return xy.join(","); }).join(" ")})
          : s("circle", {cx: r[0][0], cy: r[0][1], r: "1.5"});
      }));
  }

  function trends(tr) {
    if (!tr) { return []; }
    return [h("h2", null, "What the numbers say"),
      h("ul", {"class": "trends"}, tr.trends.map(function (t) {
        return h("li", {"class": t.too_few ? "few" : ""}, spark(t), h("span", null, t.sentence));
      })),
      h("p", {"class": "muted method"}, "The last " + tr.days + " days in UTC; \"this week\" is the last 7. Under " +
        tr.min_count + " merged PRs, decided questions or records a trend says \"too few to tell\": one or two values " +
        "can't show a direction. A question is decided when the owner first adds gov:ruled or ready, or else when it closes.")];
  }

  function went(w) {
    if (!w) { return []; }
    var n = w.total, rows = [["asked", "Asked by", "asked_by"], ["decided", "Decided by", "decided_by"], ["became", "Became", "became"]];
    return [h("h2", null, "How the questions went"),
      h("p", null, n + " question" + (n !== 1 ? "s" : "") + " asked in the last " + w.days + " days (from " + dayText(w.first_day) + ")."),
      h("ul", {"class": "went"}, rows.map(function (row) {
        var counts = w[row[2]], cats = w.cats[row[2]];
        var parts = cats.filter(function (c) { return counts[c[0]] || c[0] !== "other"; })
          .map(function (c) { return c[1] + " " + counts[c[0]]; });
        return h("li", {"class": row[0]},
          h("span", {"class": "went-bar", "aria-hidden": "true"}, n ? cats.filter(function (c) { return counts[c[0]]; })
            .map(function (c) { return h("span", {"class": c[0], style: "flex:" + counts[c[0]]}); }) : null),
          h("span", null, row[1] + ": " + parts.join(", ") + "."));
      })),
      h("p", {"class": "muted method"}, "Asked by the owner: the owner opened it, or its \"Raised by\" starts with \"owner\". " +
        "Decided by a committee: a committee Discussion serves it or its record's shape is committee; by the owner: the " +
        "owner added gov:ruled or ready, it has a record, or it was closed without gov:lapsed. Became a record: a file in " +
        "governance/decisions/ answers it; direction only: ruled or ready with no record, which is not precedent (GOV-0006).")];
  }

  // ------------------------------------------------------------ drawing and refreshing

  var DRAW = {
    rulings: rulings, questions: questions, committees: committees, authority: authority, precedent: precedent,
    trends: function (d) { return [trends(d.trends), went(d.questions_went)]; }
  };

  // Build each section whole first, so one that fails keeps what it showed.
  function fill(el, nodes) {
    var frag = add(document.createDocumentFragment(), [nodes]);
    while (el.firstChild) { el.removeChild(el.firstChild); }
    el.appendChild(frag);
  }

  function draw(d) {
    var i, el, box = document.querySelector("header.mast [data-panel=\"mast\"]");
    for (i = 0; i < SECTIONS.length; i++) {
      el = document.getElementById(SECTIONS[i]);
      if (!el) { continue; }
      try { fill(el, DRAW[SECTIONS[i]](d)); } catch (e) { /* keep the section as it was */ }
    }
    if (box) { try { fill(box, mast(d)); } catch (e) { /* keep the masthead */ } }
    builtAt = d.built_at;
  }

  // Grey the LIVE mark (#402) once the data on screen is older than STALE.
  function fresh() {
    var old = !(Date.now() - Date.parse(builtAt) <= STALE);
    var marks = document.querySelectorAll("header.mast .live"), i;
    for (i = 0; i < marks.length; i++) { marks[i].classList.toggle("stale", old); }
  }

  function apply(st) {
    if (!st || st.schema !== 1 || typeof st.built_at !== "string" || !st.governance) { return; }
    // Pages' cache can serve a state.json older than the page; only ever move forward.
    if (!(Date.parse(st.built_at) > Date.parse(builtAt))) { return; }
    draw(st);
  }

  function poll() {
    if (document.hidden) { fresh(); return; }
    fetch("state.json?t=" + Date.now(), {cache: "no-store", credentials: "same-origin"})
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(apply)
      .catch(function () {})
      .then(fresh);
  }

  var block = document.getElementById("gov-data");
  try { draw(JSON.parse(block.textContent)); } catch (e) { /* the noscript note's words stand */ }
  fresh();
  setInterval(poll, EVERY);
}());
