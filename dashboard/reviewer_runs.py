"""The dashboard's Actions reviewer section (#356, part 4 of #348).

Shows the reviewer workflow's recent sweeps and how each started (schedule, nudge or a
manual dispatch), the review jobs each ran, the review-job success rate, the time from a
head's commit to its first reviewer-App review, and how many builder PRs have no reviewer
review at their head (generate.unreviewed(), #344; not a second rule).

Reads only run, job, review and commit metadata. It never fetches job logs: GOV-0016 puts
`total_cost_usd` in them, and #348 keeps cost off the page. Without `actions: read` the
section says so in one line and the rest of the page still builds.

generate.py fetches the data and calls build(); state.json carries it and crew.js draws it
(#1139). Stdlib only.
"""
from __future__ import annotations

import datetime as dt
import json
import statistics
import subprocess
import sys
from pathlib import Path

import ghql

LAUNCHER = Path(__file__).resolve().parent.parent / "launcher"

WINDOW_DAYS = 7
MAX_RUNS = 15               # the newest runs in the window, at most: one jobs call each (#392)
NUDGE_ACTOR = "github-actions[bot]"   # reviewer-nudge.yml's dispatches show this actor
REVIEWER = "productswarm-reviewer[bot]"
NO_ACTIONS = "can't read Actions runs: the token needs `actions: read`"




def _actions_review():
    """launcher/actions_review.py, imported on first use: it imports swarm, which imports
    generate, so importing it while generate loads would be circular."""
    if str(LAUNCHER) not in sys.path:
        sys.path.insert(0, str(LAUNCHER))
    import actions_review
    return actions_review


def parse_review_job(name: object) -> tuple[int, str] | None:
    """(pr, head) from a `review #<pr> <sha>` job name (REVIEW_JOB), else None."""
    return _actions_review().parse_review_job(name)


# ---------------------------------------------------------------- reading GitHub

def _gh(path: str, jq: str, paginate: bool) -> list[dict]:
    if "/logs" in path:   # never: GOV-0016 puts run cost in the logs (#348)
        raise ValueError(f"refusing to read logs: {path}")
    argv = ["gh", "api", *(["--paginate"] if paginate else []), path, "--jq", jq]
    r = subprocess.run(argv, capture_output=True, text=True, timeout=120)
    if r.returncode != 0:
        raise RuntimeError(f"gh api {path.split('?')[0]} failed: {r.stderr.strip()[:300]}")
    return [json.loads(line) for line in r.stdout.splitlines() if line.strip()]


PR_BATCH = 20   # PRs per GraphQL query: about one rate-limit point each
PR_FIELD = ("p%d: pullRequest(number: %d) { "
            "reviews(first: 100) { totalCount nodes { author { login __typename } commit { oid } "
            "submittedAt state } } "
            "commits(first: 100) { totalCount nodes { commit { oid committedDate } } } }")


def pr_reviews_and_commits(repo: str, numbers: list[int]) -> dict[int, tuple[list[dict], list[dict]]]:
    """Each PR's reviews and commits in REST's shape (only the fields this section reads),
    oldest first, from one GraphQL query per PR_BATCH PRs (#392). A PR with more than 100 of
    either, or one the query didn't return, falls back to REST."""
    out = {}
    for n, pr in ghql.batched(repo, numbers, PR_FIELD, PR_BATCH).items():
        rv, cm = ghql.complete((pr or {}).get("reviews")), ghql.complete((pr or {}).get("commits"))
        reviews = (_gh(f"repos/{repo}/pulls/{n}/reviews?per_page=100", ".[]", True) if rv is None else
                   [{"user": {"login": ghql.login(x.get("author"))},
                     "commit_id": (x.get("commit") or {}).get("oid"),
                     "submitted_at": x.get("submittedAt"), "state": x.get("state")} for x in rv])
        commits = (_gh(f"repos/{repo}/pulls/{n}/commits?per_page=100", ".[]", True) if cm is None else
                   [{"sha": (x.get("commit") or {}).get("oid"),
                     "commit": {"committer": {"date": (x.get("commit") or {}).get("committedDate")}}}
                    for x in cm])
        out[n] = (reviews, commits)
    return out


def fetch(repo: str, now: dt.datetime, reviews: dict[int, list[dict]]) -> dict:
    """The section's raw data. `reviews` is generate.fetch()'s reviews on open PRs, reused
    so those aren't read twice. Never raises: a failure is kept as an error line."""
    since = (now - dt.timedelta(days=WINDOW_DAYS)).strftime("%Y-%m-%d")
    try:
        runs = _gh(f"repos/{repo}/actions/workflows/{_actions_review().WORKFLOW}/runs"
                   f"?per_page={MAX_RUNS}&created=%3E%3D{since}", ".workflow_runs[]", False)
        jobs = {r["id"]: _gh(f"repos/{repo}/actions/runs/{r['id']}/jobs?per_page=100",
                             ".jobs[]", True) for r in runs if isinstance(r.get("id"), int)}
    except (RuntimeError, OSError, subprocess.SubprocessError, ValueError) as e:
        msg = str(e)
        no_access = "403" in msg or "not accessible" in msg.lower()
        return {"error": NO_ACTIONS if no_access else f"can't read Actions runs: {msg[:200]}"}
    data = {"runs": runs, "jobs": jobs, "reviews": {}, "commits": {}}
    # Reviews and head dates for every PR a sweep reviewed in the window, plus open PRs.
    prs = {parsed[0] for js in jobs.values() for j in js if (parsed := parse_review_job(j.get("name")))}

    def reviewed(rv: list[dict]) -> bool:
        return any((r.get("user") or {}).get("login") == REVIEWER for r in rv)

    try:
        # Open PRs' reviews are reused; one GraphQL query per PR_BATCH PRs reads the rest (#392).
        wanted = sorted((prs - set(reviews)) | {n for n, rv in reviews.items() if reviewed(rv)})
        read = pr_reviews_and_commits(repo, wanted)
        for n in sorted(prs | set(reviews)):
            rv = reviews[n] if n in reviews else read[n][0]
            data["reviews"][n] = rv
            if reviewed(rv):
                data["commits"][n] = read[n][1]
    except (RuntimeError, OSError, subprocess.SubprocessError, ValueError, KeyError) as e:
        data["times_error"] = f"can't read reviews: {str(e)[:200]}"
    return data


# ---------------------------------------------------------------- deriving state

def parse_ts(s: object) -> dt.datetime | None:
    try:
        t = dt.datetime.fromisoformat(s.replace("Z", "+00:00"))  # type: ignore[union-attr]
    except (AttributeError, ValueError):
        return None
    return t if t.tzinfo else None


def started_by(run: dict) -> str:
    """How a sweep started: "schedule", "nudge", "manual (<login>)", or the event name."""
    event = run.get("event")
    if event == "schedule":
        return "schedule"
    if event == "workflow_dispatch":
        actor = (run.get("triggering_actor") or run.get("actor") or {}).get("login", "")
        return "nudge" if actor == NUDGE_ACTOR else f"manual ({actor or 'unknown'})"
    return str(event or "unknown")


def outcome(x: dict) -> str:
    """A run's or job's conclusion, or its status while it hasn't finished."""
    return x.get("conclusion") or x.get("status") or "unknown"


def commit_to_review(reviews: dict[int, list[dict]], commits: dict[int, list[dict]],
                     since: dt.datetime) -> list[dict]:
    """Each head's first reviewer-App review submitted at or after `since`, timed from the
    reviewed commit's committer date (not push time, which the API doesn't give). A review
    counts for the commit it was made on, so one on an older head says nothing about the
    PR's current head."""
    out = []
    for n, rv in sorted(reviews.items()):
        dates = {c.get("sha"): parse_ts(((c.get("commit") or {}).get("committer") or {}).get("date"))
                 for c in commits.get(n, [])}
        seen = set()
        for r in rv:   # REST order: oldest first
            sha, at = r.get("commit_id"), parse_ts(r.get("submitted_at"))
            if (r.get("user") or {}).get("login") != REVIEWER or not at or sha in seen:
                continue
            seen.add(sha)
            if at >= since and dates.get(sha):
                out.append({"pr": n, "head": sha, "seconds": max(0, (at - dates[sha]).total_seconds())})
    return out


def build(data: dict | None, unreviewed_prs: list[dict], now: dt.datetime) -> dict:
    """The section's model. `unreviewed_prs` is generate.build()'s non-draft PRs that
    generate.unreviewed() flags."""
    m = {"window_days": WINDOW_DAYS, "unreviewed": unreviewed_prs}
    data = data or {"error": "Actions runs weren't read"}
    if data.get("error"):
        return {**m, "error": data["error"]}
    sweeps, review_jobs = [], []
    for run in sorted(data["runs"], key=lambda r: r.get("created_at") or "", reverse=True):
        reviewed = []
        for j in data["jobs"].get(run.get("id"), []):
            parsed = parse_review_job(j.get("name"))
            if parsed:
                reviewed.append({"pr": parsed[0], "head": parsed[1], "outcome": outcome(j),
                                 "done": j.get("status") == "completed", "url": j.get("html_url")})
        review_jobs += reviewed
        sweeps.append({"ts": parse_ts(run.get("created_at")), "started_by": started_by(run),
                       "outcome": outcome(run), "done": run.get("status") == "completed",
                       "url": run.get("html_url"), "reviewed": reviewed})
    done = [j for j in review_jobs if j["done"]]
    times = commit_to_review(data["reviews"], data["commits"], now - dt.timedelta(days=WINDOW_DAYS))
    secs = [t["seconds"] for t in times]
    return {**m, "sweeps": sweeps, "jobs_done": len(done),
            "jobs_ok": sum(j["outcome"] == "success" for j in done),
            "failed": [j for j in done if j["outcome"] != "success"],
            "times": times, "times_error": data.get("times_error"),
            "median": statistics.median(secs) if secs else None,
            "longest": max(times, key=lambda t: t["seconds"]) if times else None}
