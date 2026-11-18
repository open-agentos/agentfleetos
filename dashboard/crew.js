// Crew, drawn client-side (#1139, stage 2 of #1135; option 3 of #1102). crewpage.py fills in
// the settings at build time and generate.py serves it as js/crew.js; the page's CSP allows
// only this script, by hash. It draws every section from plain fields (the page's JSON block
// first, then each newer same-origin state.json) with createElement, setAttribute and text
// nodes. It never parses HTML, sets markup or runs strings as code, so text from the repo
// stays text. It doesn't read state.json's `desk`.
(function () {
  "use strict";
  var EVERY = /*EVERY*/0, STALE = /*STALE*/0;
  var SVG = "http://www.w3.org/2000/svg";
  // Links only to https URLs, a page beside this one (with a query or fragment) or a fragment.
  var SAFE_URL = /^(https:\/\/|[A-Za-z0-9_-]+\.html(\?[A-Za-z0-9=&_-]*)?(#[A-Za-z0-9_-]*)?$|#[A-Za-z0-9_-]*$)/;
  var MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  var DAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
  var SECTIONS = ["roles", "floor", "sessions", "reviewer", "grants", "effort"];
  var builtAt = null, page = {};

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

  function safe(url) { return typeof url === "string" && SAFE_URL.test(url); }
  // A link when the URL is safe, else the content alone.
  function link(text, url, attrs) {
    if (!safe(url)) { return text; }
    // class first, then href, then the rest: the attribute order the Python renderers wrote.
    var a = attrs && attrs["class"] ? {"class": attrs["class"]} : {}, k;
    a.href = url;
    for (k in attrs || {}) { if (Object.prototype.hasOwnProperty.call(attrs, k) && k !== "class") { a[k] = attrs[k]; } }
    return h("a", a, text);
  }
  function muted(text) { return h("span", {"class": "muted"}, text); }
  function plural(n, word) { return n + " " + word + (n === 1 ? "" : "s"); }
  function join(items, sep) {
    var out = [], i;
    for (i = 0; i < items.length; i++) { if (i) { out.push(sep); } out.push(items[i]); }
    return out;
  }
  function gh(repo, kind, n) { return "https://github.com/" + repo + "/" + kind + "/" + n; }

  // ------------------------------------------------------------ times (UTC, RFC 3339 in)

  function stamp(t) { return t ? t.slice(0, 10) + " " + t.slice(11, 16) + " UTC" : ""; }
  function hm(t) { return t ? t.slice(11, 16) : ""; }
  function ago(t, now) {
    if (!t) { return "never"; }
    var sec = Math.max(0, Math.floor((Date.parse(now) - Date.parse(t)) / 1000));
    var units = [["d", 86400], ["h", 3600], ["m", 60]], i;
    for (i = 0; i < units.length; i++) {
      if (sec >= units[i][1]) { return Math.floor(sec / units[i][1]) + units[i][0] + " ago"; }
    }
    return "just now";
  }
  // "Tue 17 Nov, 20:28 UTC"
  function longStamp(t) {
    var d = new Date(Date.parse(t));
    return DAYS[d.getUTCDay()] + " " + t.slice(8, 10) + " " + MONTHS[d.getUTCMonth()] + ", " + hm(t) + " UTC";
  }
  // 40 min, 2 h, 2 h 5 min, 3 d (floor.py's span).
  function span(minutes) {
    if (minutes === null || minutes === undefined) { return "no events"; }
    if (minutes < 60) { return minutes + " min"; }
    if (minutes < 24 * 60) {
      var hr = Math.floor(minutes / 60), mi = minutes % 60;
      return mi ? hr + " h " + mi + " min" : hr + " h";
    }
    return Math.floor(minutes / (24 * 60)) + " d";
  }

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
        h("time", {"class": "stamp", datetime: t, title: stamp(t)}, hm(t) + " UTC")),
      owner];
  }

  // ------------------------------------------------------------ #roles (#932, #1113)

  function roleRow(r) {
    var cls = r.lead ? " lead" : r.group === "idle" ? " idle" : "";
    return link([h("span", {"class": "br-av" + cls, "aria-hidden": "true"}, r.badge),
      h("span", {"class": "cm-name"}, h("span", {"class": "br-title"}, r.role.charAt(0).toUpperCase() + r.role.slice(1)),
        h("span", {"class": "muted"}, r.does), h("span", {"class": "muted"}, r.line)),
      h("span", {"class": "mono ag-n"}, r.count)], r.href, {"class": "cm-row"});
  }

  function roles(d) {
    var rows = d.crew_roles || [];
    var working = rows.filter(function (r) { return r.group === "working"; }).length;
    var out = [h("div", {"class": "br-titlebar"}, h("h1", null, "Crew"),
        h("span", {"class": "mono muted"}, working + " working · " + (rows.length - working) + " idle · " +
          longStamp(d.built_at))),
      h("p", {"class": "muted"}, "The team that runs the plan for you. Pick one to see its record, what it's " +
        "working on, the authority it used and how to ask it something.")];
    [["working", "Working"], ["idle", "Idle"]].forEach(function (g) {
      var rs = rows.filter(function (r) { return r.group === g[0]; });
      if (rs.length) { out.push(h("p", {"class": "cm-grp"}, g[1].toUpperCase() + " · " + rs.length), rs.map(roleRow)); }
    });
    return out;
  }

  // ------------------------------------------------------------ #floor (#403, #459)

  // "#392" and "PR #394" in a card's plain words, as links.
  function refs(text, repo) {
    var out = [], re = /(PR )?#(\d+)/g, at = 0, m;
    while ((m = re.exec(text)) !== null) {
      out.push(text.slice(at, m.index));
      if (m[1]) { out.push("PR "); }
      out.push(link("#" + m[2], gh(repo, m[1] ? "pull" : "issues", m[2])));
      at = re.lastIndex;
    }
    out.push(text.slice(at));
    return out;
  }

  function sparkline(counts) {
    var w = 10, gap = 3, ht = 22, top = Math.max.apply(null, counts.concat([0])) || 1;
    var width = counts.length * (w + gap) - gap;
    return s("svg", {"class": "spark", role: "img", "aria-label": "events per 5 minutes, last 30 minutes, oldest first: " +
        counts.join(", "), width: width, height: ht, viewBox: "0 0 " + width + " " + ht},
      counts.map(function (n, i) {
        var bh = n ? Math.max(1, Math.round(ht * n / top)) : 1;
        return s("rect", {"class": n ? "bar" : "bar zero", x: i * (w + gap), y: ht - bh, width: w, height: bh});
      }));
  }

  function card(c, repo) {
    var used = Object.keys(c.slots_used || {}).map(function (k) {
      return k + " in " + c.slots_used[k] + " of " + c.events_per_slot.length;
    }).join(" · ");
    return h("div", {"class": "card s-" + c.status},
      h("div", {"class": "who"}, h("span", {"class": "role"}, c.role), " ", h("span", {"class": "mono muted"}, c.model)),
      h("div", {"class": "what"}, refs(c.activity || "", repo)),
      h("div", {"class": "muted"}, c.run_minutes !== null && c.run_minutes !== undefined ? "running " + span(c.run_minutes) : ""),
      sparkline(c.events_per_slot || []),
      h("div", {"class": "muted used"}, "last 30 min, 5-min slots: " + used));
  }

  var WATCHER_NOTES = {
    missing: "No [watch] issue: swarm watch's state isn't published (launcher/README.md).",
    not_owner: "The [watch] issue wasn't opened by the owner, so the floor doesn't show it (GOV-0025).",
    several: "The owner has more than one open [watch] issue; close all but one.",
    malformed: "Can't read swarm watch's state from the [watch] issue."
  };
  var ENDING = {at_cap: "at its cap", error: "error", limited: "usage limit", no_result: "no result"};

  function watcher(w, repo) {
    w = w || {status: "missing"};
    var out = [h("h3", null, "The watcher")], lines = [], when;
    if (w.status !== "ok") {
      out.push(h("p", {"class": "muted"}, WATCHER_NOTES[w.status] || WATCHER_NOTES.malformed));
      return h("div", {"class": "watcher"}, out);
    }
    function ref(r) {
      var n = r.slice(r.lastIndexOf("#") + 1), pr = r.indexOf("PR ") === 0;
      return [pr ? "PR " : "", link("#" + n, gh(repo, pr ? "pull" : "issues", n))];
    }
    when = span(w.age_minutes) + " ago, at " + hm(w.checked) + " UTC";
    // The watcher publishes only when its state changes (#458), so an old time can mean a
    // quiet loop or a stopped one: the lists are shown as of then, not as current.
    out.push(w.stale
      ? h("p", {"class": "stale"}, "watcher last published " + when + ": these lists are as of then, and it may " +
        "have stopped (it publishes only when they change)")
      : h("p", {"class": "muted"}, "as of " + when));
    (w.running || []).forEach(function (r) { lines.push([r.role + " on ", ref(r.ref), " since " + hm(r.started)]); });
    ["held", "skipped"].forEach(function (name) {
      (w[name] || []).forEach(function (x) {
        var cut = x.reason ? x.reason.indexOf(": ") : -1;
        var why = !x.reason ? x.code : cut < 0 ? x.reason : x.reason.slice(cut + 2);
        lines.push(why !== name ? [name + ": ", ref(x.ref), ", " + why] : [name + ": ", ref(x.ref)]);
      });
    });
    (w.failed || []).forEach(function (f) {
      lines.push(["failed: ", ref(f.ref), " " + f.kind + ", " + ENDING[f.ending] + ", " + hm(f.ended)]);
    });
    out.push(lines.length ? h("ul", null, lines.map(function (l) { return h("li", null, l); }))
      : h("p", {"class": "muted"}, "Nothing running, held, skipped or failed."));
    return h("div", {"class": "watcher"}, out);
  }

  function floor(d) {
    var f = d.floor || {cards: [], idle: []};
    var out = [h("h2", null, "On the floor")];
    out.push(f.cards.length ? h("div", {"class": "floor"}, f.cards.map(function (c) { return card(c, d.repo); }))
      : h("p", {"class": "muted"}, "No session is working."));
    if (f.idle.length) {
      out.push(h("p", {"class": "muted idle"}, "idle: " + f.idle.map(function (i) {
        return i.role + " " + span(i.idle_minutes);
      }).join(", ")));
    }
    out.push(watcher(d.watcher, d.repo));
    return out;
  }

  // ------------------------------------------------------------ #sessions

  function issueLink(repo, n, title) {
    if (!n) { return muted("—"); }
    return link("#" + n + (title ? " " + title : ""), gh(repo, "issues", n), {title: title || ""});
  }

  // spend.usd's text for a session's own estimate: "—" unpriced, "<$0.01" below a cent.
  function usd(x) {
    if (typeof x !== "number") { return "—"; }
    if (x !== 0 && !(x >= 0.01)) { return "<$0.01"; }
    // toFixed rounds an exact half cent up, Python's format to even (0.125 is "$0.12").
    var c = x * 8 % 2 === 1 ? Math.round(x * 100) : null;
    var p = (c !== null && c % 2 ? (c - 1) / 100 : x).toFixed(2).split(".");
    return "$" + p[0].replace(/\B(?=(\d{3})+$)/g, ",") + "." + p[1];
  }

  function sessionRows(d, list) {
    var repo = d.repo, now = d.built_at;
    var head = h("tr", null, h("th", null, "Status"), h("th", null, "Role"), h("th", null, "Current issue"),
      h("th", null, "Last activity"), h("th", null, "Session"), h("th", {"class": "num"}, "Spend (est.)"));
    return h("div", {"class": "scroll"}, h("table", null, head, list.map(function (x) {
      return h("tr", null,
        h("td", null, h("span", {"class": "pill s-" + x.status}, x.status),
          x.gov_question ? [" on ", issueLink(repo, x.gov_question, null)] : null),
        h("td", null, h("b", null, x.role), h("br"), muted(x.model || "")),
        h("td", null, issueLink(repo, x.issue, x.issue_title),
          x.pr ? [" · PR ", link("#" + x.pr, gh(repo, "pull", x.pr))] : null),
        h("td", {title: stamp(x.last_ts)}, ago(x.last_ts, now), h("br"), muted(x.last_event || "")),
        h("td", null, link(h("code", null, x.session_id.slice(0, 8)), gh(repo, "issues", x.tracking_issue)),
          h("br"), muted("started " + ago(x.started_ts, now))),
        h("td", {"class": "num"}, usd(x.cost), x.over_cap ? [h("br"), h("span", {"class": "pill s-blocked"}, "over cap " + usd(x.cap))] : null));
    })));
  }

  function sessions(d) {
    // A session that never acted (#454: no event, tracking issue older than the idle threshold)
    // isn't a row: it would read "started never". A line counts them instead (#1262).
    var all = (d.sessions || []).filter(function (x) { return !x.never_acted; });
    var ghosts = (d.sessions || []).length - all.length;
    var live = all.filter(function (x) { return x.status !== "stopped"; });
    var stopped = all.filter(function (x) { return x.status === "stopped"; });
    var out = [h("h2", null, "Sessions"), h("p", {"class": "muted"}, "idle after " + d.idle_minutes + " min without an event"),
      live.length ? sessionRows(d, live) : h("p", {"class": "muted"}, "No live sessions.")];
    if (ghosts) {
      out.push(h("p", {"class": "muted"}, ghosts + (ghosts === 1 ? " session" : " sessions") + " never reported; hidden"));
    }
    if (stopped.length) {
      out.push(h("details", null, h("summary", null, stopped.length + " stopped"), sessionRows(d, stopped)));
    }
    out.push(h("p", {"class": "muted method"}, "Spend (est.) is each session's own: " + (page.spend_method || "")));
    return out;
  }

  // ------------------------------------------------------------ #reviewer (#356)

  function duration(seconds) {
    var x = Math.floor(seconds), d = Math.floor(x / 86400), hr = Math.floor(x % 86400 / 3600), mi = Math.floor(x % 3600 / 60);
    if (d) { return d + "d " + hr + "h"; }
    if (hr) { return hr + "h " + mi + "m"; }
    return mi ? mi + "m" : x + "s";
  }

  function reviewer(d) {
    var r = d.reviewer_runs || {}, repo = d.repo, unrev = r.unreviewed || [], days = r.window_days, out, line, times, rate;
    function prLink(n, head) {
      return link(["#" + n, head ? [" ", h("code", null, head.slice(0, 7))] : null], gh(repo, "pull", n));
    }
    out = [h("h2", null, "Actions reviewer")];
    line = [unrev.length + " builder PR" + (unrev.length !== 1 ? "s" : "") + " with no reviewer review at " +
      (unrev.length !== 1 ? "their" : "its") + " head",
      unrev.length ? [": ", join(unrev.map(function (n) { return prLink(n); }), ", ")] : null, " (also in Needs you)."];
    if (r.error) {
      out.push(h("p", {"class": "muted"}, r.error), h("p", null, line));
      return out;
    }
    rate = [r.jobs_ok + " of " + r.jobs_done + " review jobs succeeded in the last " + days + " days"];
    if ((r.failed || []).length) {
      rate.push(". Failed: ", join(r.failed.map(function (j) {
        return [link(["#" + j.pr + " ", h("code", null, (j.head || "").slice(0, 7))], j.url), " (" + j.outcome + ")"];
      }), ", "));
    }
    if (r.times_error) {
      times = muted("Commit to review: " + r.times_error);
    } else if ((r.times || []).length) {
      times = ["Commit to review: median " + duration(r.median) + ", longest " + duration(r.longest.seconds) + " (",
        prLink(r.longest.pr, r.longest.head), "), over " + r.times.length + " reviewed heads."];
    } else {
      times = muted("Commit to review: no reviewer reviews in the window.");
    }
    out.push(h("p", null, rate, ".", h("br"), times, h("br"), line));
    if (!(r.sweeps || []).length) {
      out.push(h("p", {"class": "muted"}, "No reviewer sweeps in the last " + days + " days."));
    } else {
      out.push(h("details", null, h("summary", null, r.sweeps.length + " sweeps in the last " + days + " days (newest " +
          r.max_runs + " at most)"),
        h("div", {"class": "scroll"}, h("table", null,
          h("tr", null, h("th", null, "Started"), h("th", null, "How"), h("th", null, "Sweep"), h("th", null, "Reviewed")),
          r.sweeps.map(function (sw) {
            var what = sw.reviewed.length ? join(sw.reviewed.map(function (j) {
              return [prLink(j.pr, j.head), " ", j.url ? link(j.outcome, j.url) : j.outcome];
            }), h("br")) : muted(sw.outcome === "success" ? "nothing to review" : "no review jobs");
            return h("tr", null, h("td", {title: stamp(sw.ts)}, ago(sw.ts, d.built_at)), h("td", null, sw.started_by),
              h("td", null, link(sw.outcome, sw.url)), h("td", null, what));
          })))));
    }
    out.push(h("p", {"class": "muted method"}, "Commit to review runs from the reviewed commit's committer date " +
      "(GitHub doesn't give push time) to the reviewer App's first review of that commit. No cost is shown, and no " +
      "job logs are read."));
    return out;
  }

  // ------------------------------------------------------------ #grants (#713)

  var GROUPS = [["merged", "Merged"], ["enqueued", "Enqueued"], ["would", "Would merge (shadow)"], ["left", "Left for you"]];

  function callLine(x) {
    if (x.group === "merged") { return "merged under " + x.reason + (x.queued ? " via the queue" : ""); }
    if (x.group === "enqueued") { return "enqueued under " + x.reason; }
    if (x.group === "would") { return "would merge (" + x.reason + ")"; }
    return "left for you: " + x.reason;
  }

  function grants(d) {
    var g = d.grants, out;
    if (!g) { return []; }
    out = [h("h2", null, "Grants in use"), h("p", {"class": "grants-mode"}, g.mode_text)];
    if (!g.read) {
      out.push(h("p", {"class": "muted"}, "Couldn't read the merger's calls."));
    } else if (!g.calls.length) {
      out.push(h("p", {"class": "muted"}, "No merger calls in the last 24 hours."));
    }
    GROUPS.forEach(function (grp) {
      var rows = g.calls.filter(function (x) { return x.group === grp[0]; });
      if (!rows.length) { return; }
      out.push(h("h3", {"class": grp[0]}, grp[1]), h("ol", {"class": "grants " + grp[0]}, rows.map(function (x) {
        return h("li", null, link("#" + x.number, gh(d.repo, "pull", x.number)), x.title ? " " + x.title : null, ": ",
          link([callLine(x) + ", ", h("time", {datetime: x.time}, hm(x.time))], x.link));
      })));
    });
    out.push(h("p", {"class": "muted method"}, "The merger's comments on PRs in the last 24 hours, each PR's latest, " +
      "newest first; times in UTC. Other uses of delegated authority are in the daily report."));
    return out;
  }

  // ------------------------------------------------------------ #effort (#1013)

  var LABELS = ["capability", "upkeep", "governance", "knowledge"];
  var WINDOWS = [["this", "last 7 days"], ["last", "7 days before"]];

  function anchor(ref, w, lb) {
    return "e-" + ref.replace(/[^A-Za-z0-9]+/g, "-").replace(/^-+|-+$/g, "") + "-" + w + "-" + lb;
  }
  function pct(n, of) { return Math.round(10000 * n / of) / 100 + "%"; }
  function share(x) { return Math.round(100 * x.capability / x.total) + "%"; }
  function dayText(d) { return parseInt(d.slice(8, 10), 10) + " " + MONTHS[parseInt(d.slice(5, 7), 10) - 1]; }

  function bar(row, w, word, scale) {
    var c = row[w], segs = LABELS.filter(function (lb) { return c.by[lb]; }).map(function (lb) {
      var n = c.by[lb], fixes = c.fix_by[lb], tip = n + " " + lb + (fixes ? ", " + fixes + " fixing recent work" : "");
      return link(fixes ? h("span", {"class": "ef-fix", style: "width:" + pct(fixes, n)}) : null,
        "effort.html#" + anchor(row.ref, w, lb),
        {"class": "ef-seg ef-" + lb, style: "width:" + pct(n, scale), title: tip, "aria-label": tip});
    });
    return h("div", {"class": "ef-row"}, h("span", {"class": "ef-when muted"}, word),
      h("span", {"class": "ef-bar"}, segs.length ? segs : h("span", {"class": "ef-none"})),
      h("span", {"class": "ef-n mono"}, String(c.total)));
  }

  function trend(t) {
    var w = 240, ht = 48, pad = 4, step = (w - 2 * pad) / Math.max(t.length - 1, 1), pts = [], label, now, prev, said, i;
    for (i = 0; i < t.length; i++) {
      if (t[i].total) { pts.push([pad + i * step, pad + (ht - 2 * pad) * (1 - t[i].capability / t[i].total)]); }
    }
    now = t[t.length - 1];
    said = now.total ? "This week " + share(now) + " of " + now.total + " merged PRs were capability"
      : "No PRs merged this week yet";
    for (i = t.length - 2; i >= 0; i--) { if (t[i].total) { prev = t[i]; break; } }
    if (prev) { said += "; the week of " + dayText(prev.week) + ", " + share(prev) + " of " + prev.total; }
    label = "Capability share by week, the last " + t.length + " weeks";
    return h("div", {"class": "ef-trend"}, h("h3", null, "Capability share by week"),
      s("svg", {"class": "ef-line", role: "img", "aria-label": label, width: w, height: ht, viewBox: "0 0 " + w + " " + ht},
        s("title", {}, label),
        pts.length > 1 ? s("polyline", {points: pts.map(function (p) { return p[0].toFixed(1) + "," + p[1].toFixed(1); }).join(" ")}) : null,
        pts.map(function (p) { return s("circle", {cx: p[0].toFixed(1), cy: p[1].toFixed(1), r: "2.5"}); })),
      h("p", {"class": "muted"}, said + ". All merged PRs in the cache, by week from Monday (UTC), from the week of " +
        dayText(t[0].week) + "."));
  }

  function effort(d) {
    var e = d.effort, head = h("h2", null, "Effort"), scale = 1, by, note;
    if (!e || e.status === "missing") {
      return h("section", {"class": "effort"}, head, h("p", {"class": "muted"}, "No effort labels yet: ",
        h("code", null, "classify/cache/effort.json"), " isn't there. ", h("code", null, "swarm classify run effort"),
        " writes it (#1012)."));
    }
    if (e.status === "error") {
      return h("section", {"class": "effort"}, head, h("p", {"class": "muted"}, "Effort labels couldn't be read: " + e.error));
    }
    e.goals.forEach(function (r) { WINDOWS.forEach(function (w) { scale = Math.max(scale, r[w[0]].total); }); });
    by = e.classifier === "model" ? "the model classifier" : e.classifier === "paths" ? "the paths baseline" : "the classifier";
    note = "Merged PRs per open Goal, by kind of work, from " + by +
      (e.updated_at ? ", labels updated " + e.updated_at.slice(0, 10) + " " + hm(e.updated_at) + " UTC" : "") +
      (e.unreadable ? "; " + e.unreadable + " cache entries left out as unreadable" : "") + ". A segment opens its PRs.";
    return h("section", {"class": "effort"}, head, h("p", {"class": "muted"}, note),
      h("div", {"class": "ef-legend muted"}, LABELS.map(function (lb) {
        return h("span", null, h("span", {"class": "ef-key ef-" + lb}), lb);
      }), h("span", null, h("span", {"class": "ef-key ef-capability"}, h("span", {"class": "ef-fix", style: "width:100%"})),
        "fixes recent work")),
      e.goals.length ? e.goals.map(function (r) {
        return h("div", {"class": "ef-goal"}, h("div", {"class": "ef-name"},
          r.lead ? [h("span", {"class": "mono"}, r.lead), " "] : null, link(r.title, r.url)),
          WINDOWS.map(function (w) { return bar(r, w[0], w[1], scale); }));
      }) : h("p", {"class": "muted"}, "No open Goal."),
      e.trend && e.trend.length ? trend(e.trend) : null);
  }

  // ------------------------------------------------------------ drawing and refreshing

  var DRAW = {roles: roles, floor: floor, sessions: sessions, reviewer: reviewer, grants: grants, effort: effort};

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
    if (!st || st.schema !== 1 || typeof st.built_at !== "string" || !Array.isArray(st.sessions)) { return; }
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

  var block = document.getElementById("crew-data");
  try { page = JSON.parse(block.textContent); draw(page); } catch (e) { /* the noscript note's words stand */ }
  fresh();
  setInterval(poll, EVERY);
}());
