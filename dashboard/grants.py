"""Grants in use: the merger's calls in the last 24 hours (#713, per the layout in #711).

The merger (launcher/merger.py, GOV-0027) says what it did on each PR in a comment by
`productswarm-merger[bot]`. This panel lists those comments, one line per PR, its latest
call winning, newest first, in three groups:

  comment starts      | group                  | line
  --------------------|------------------------|-----------------------------------------------
  Merged under        | Merged                 | #701 Title: merged under standing grant, 14:02
  Enqueued under      | Enqueued               | #701 Title: enqueued under standing grant, 14:02
    ... once merged   | Merged                 | #701 Title: merged under standing grant via the queue, 14:02
  Would merge         | Would merge (shadow)   | #701 Title: would merge (standing grant), 14:02
  Left for the owner  | Left for you (amber)   | #653 Title: left for you: <reason>, 09:15

When main requires a merge queue (#663) the merger enqueues instead of merging, and GitHub
merges later (#746): an enqueued PR moves to Merged once GitHub has merged it. The reason is
the merger's own words, without the sha or `-- merger`. Above them, one line
for the merger's mode from `[merger] mode` in swarm.toml on main (merger.load_switch, so a
bad table reads as off, as it does for the merger itself). Times are UTC. crew.js draws the
panel from state()'s plain fields (#1139).

API calls: the repo's issue comments since 24 hours ago, 1 or 2 REST calls (`?since=` filters
on the last update, so a comment's own time is checked again here), and one REST call per PR
that isn't open, for its title and whether it merged; open PRs' titles come from the PR list the build already reads.
Stdlib only.
"""
from __future__ import annotations

import datetime as dt
import re
import subprocess
from typing import Callable

MERGER = "productswarm-merger[bot]"   # merger.MERGER: the only App whose comments count
SIGN = "-- merger"
WINDOW = dt.timedelta(hours=24)
GROUPS = ("merged", "enqueued", "would", "left")  # page order, as crew.js draws them
MODES = {"shadow": "The merger is in shadow: it says what it would merge and merges nothing.",
         "live": "The merger is live.",
         "off": "The merger is off."}
UNKNOWN_MODE = "The merger's mode couldn't be read from swarm.toml."

# The bodies merger.py writes (would_body, merged_body, enqueued_body, left_body), before the signature.
SHA = r"[0-9a-f]{7,40}"
MERGED_RE = re.compile(rf"\AMerged under (.+?) \(GOV-0027\) at {SHA}\.?\s*\Z", re.S)
ENQUEUED_RE = re.compile(rf"\AEnqueued under (.+?) \(GOV-0027\) at {SHA}\.?\s*\Z", re.S)
WOULD_RE = re.compile(rf"\AWould merge \((.+?)\) at {SHA}\.?\s*\Z", re.S)
LEFT_RE = re.compile(rf"\ALeft for the owner at {SHA}: (.+?)\.?\s*\Z", re.S)
PR_RE = re.compile(r"/pull/(\d+)(?:#|$)")


def parse_ts(s) -> dt.datetime | None:
    try:
        return dt.datetime.fromisoformat((s or "").replace("Z", "+00:00"))
    except (TypeError, ValueError, AttributeError):
        return None


def login(c: dict) -> str:
    return ((c.get("user") or {}).get("login") or "").lower()


def stamp(t: dt.datetime) -> str:
    return t.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def mode() -> str | None:
    """`[merger] mode` as the merger itself reads it, or None if swarm.toml can't be read."""
    try:
        import sys
        from pathlib import Path
        launcher = str(Path(__file__).resolve().parent.parent / "launcher")
        if launcher not in sys.path:
            sys.path.insert(0, launcher)
        import manifest
        import merger
        return merger.load_switch(manifest.DEFAULT_PATH).mode
    except Exception:   # ImportError, OSError, a TOML error: the panel says it couldn't tell
        return None


def call(c: dict) -> dict | None:
    """One merger comment as a call: its PR, group, reason, time and link; None if it isn't
    one of the merger's four calls on a PR."""
    if not isinstance(c, dict) or login(c) != MERGER:
        return None
    link = c.get("html_url") or ""
    pr, t = PR_RE.search(link), parse_ts(c.get("created_at"))
    if not pr or t is None:
        return None
    body = (c.get("body") or "").strip()
    body = body.removesuffix(SIGN).rstrip()
    for group, rx in (("merged", MERGED_RE), ("enqueued", ENQUEUED_RE), ("would", WOULD_RE),
                      ("left", LEFT_RE)):
        m = rx.match(body)
        if m:
            return {"number": int(pr[1]), "group": group, "reason": " ".join(m[1].split()),
                    "time": t, "link": link}
    return None


def fetch(repo: str, now: dt.datetime, gh_items: Callable[[str], list[dict]],
          gh_json: Callable[..., object], open_titles: dict[int, str]) -> dict:
    """{"comments": the merger's comments since 24 hours ago, or None if they couldn't be read,
    "titles": each PR's title, "merged": the PRs called that GitHub has merged, "mode": the
    merger's mode}. A PR that can't be read is left out of both; an open one isn't merged."""
    since = stamp(now - WINDOW)
    try:
        comments = [c for c in gh_items(f"repos/{repo}/issues/comments?since={since}&per_page=100")
                    if isinstance(c, dict) and login(c) == MERGER]
    except (RuntimeError, OSError, subprocess.SubprocessError, ValueError):
        return {"comments": None, "titles": {}, "merged": [], "mode": mode()}
    titles, merged = dict(open_titles), []
    for n in sorted({x["number"] for c in comments if (x := call(c))} - set(titles)):
        try:
            it = gh_json("api", f"repos/{repo}/issues/{n}")
        except (RuntimeError, OSError, subprocess.SubprocessError, ValueError):
            continue
        if not isinstance(it, dict):
            continue
        if it.get("title"):
            titles[n] = it["title"]
        if (it.get("pull_request") or {}).get("merged_at"):
            merged.append(n)
    return {"comments": comments, "titles": titles, "merged": merged, "mode": mode()}


def build(raw: dict | None, now: dt.datetime) -> dict:
    """{"mode", "read", "calls"}: each PR's latest call in the last 24 hours, newest first. An
    enqueued PR that GitHub has since merged is in Merged, marked `queued`."""
    comments = (raw or {}).get("comments")
    titles = (raw or {}).get("titles") or {}
    landed = set((raw or {}).get("merged") or [])
    latest: dict[int, dict] = {}
    for c in comments or []:
        x = call(c)
        if x is None or not (now - WINDOW <= x["time"] <= now):
            continue
        if x["number"] not in latest or x["time"] >= latest[x["number"]]["time"]:
            latest[x["number"]] = x
    calls = sorted(latest.values(), key=lambda x: (x["time"], x["number"]), reverse=True)
    for x in calls:
        x["title"] = titles.get(x["number"])
        x["queued"] = x["group"] == "enqueued"
        if x["queued"] and x["number"] in landed:
            x["group"] = "merged"
    merger_mode = (raw or {}).get("mode")
    return {"mode": merger_mode if merger_mode in MODES else None,
            "read": comments is not None, "calls": calls}


def state(g: dict | None) -> dict | None:
    """state.json's `grants`, which crew.js draws (#1139)."""
    if g is None:
        return None
    return {"mode": g["mode"], "mode_text": MODES.get(g["mode"], UNKNOWN_MODE), "read": g["read"],
            "calls": [{k: x.get(k) for k in ("number", "title", "group", "queued", "reason", "time",
                                                "link")}
                      for x in g["calls"]]}
