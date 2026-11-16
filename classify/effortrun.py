"""`swarm classify run effort`: label merged PRs and write classify/cache/effort.json (#1012).

    launcher/swarm classify run effort --since <YYYY-MM-DD> [--model M] [--repo owner/name]

fetches the PRs merged on or after --since (UTC) and labels the ones the cache doesn't already
hold at the same content hash. The classifier is the model when its recorded replies pass the
label set's pass mark on the test split (evalrun.model_choice), else the paths baseline. A
model run reuses any recorded reply and calls `claude -p` only for the rest, capped at
PER_PR_USD per PR (GOV-0045), recording every reply in recordings/effort/<model>.jsonl.

The cache is schema 1, as dashboard/README.md#effort documents it (GOV-0046):

    {"schema": 1, "labelset": "effort", "classifier": "model" | "paths", "updated_at": ...,
     "prs": {"<n>": {"repo", "title", "merged_at", "label", "fix", "fixes", "goal", "hash",
                     "labeller": "model" | "paths" | "owner"}}}

- `hash` is the hash of what the classifier reads (the label set's prompt and the PR's text).
  Only a changed hash, or a change of classifier, relabels a PR.
- `goal` is the open Goal or Area above the PR's closing issue when it was classified, as
  `owner/repo#N`, or null. It is resolved when an entry is written and stored; a changed goal
  never relabels (GOV-0046).
- A `kind:<label>` label on the PR is the owner's correction: it overrides `label` (and
  `labeller: owner`) on the next run and leaves `fix` and `goal` alone: no model call for a PR
  already in the cache at the same hash. A new PR is still classified, for its fix flag.
  A corrected PR that isn't in data/effort.jsonl yet is appended there as a dev item,
  `labelled_by: owner`. Items already in the labelled set are left as they are, so the test
  split the pass mark was set on doesn't move (GOV-0044).

Exits 0 when every PR in the window is labelled, 1 when the run stopped early (a cap or a
model error; what was labelled is kept), 2 when it can't run.
"""
from __future__ import annotations

import datetime as dt
import json
import subprocess
import sys
from pathlib import Path
from typing import Callable, Optional

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import classifier  # noqa: E402
import effort_data  # noqa: E402
import evalrun  # noqa: E402
import labelset as lsmod  # noqa: E402

NAME = "effort"
SCHEMA = 1
PER_PR_USD = effort_data.PER_PR_USD
OWNER = "owner"
KIND = "kind:"

QUERY = """query($q: String!, $endCursor: String) {
  search(query: $q, type: ISSUE, first: 50, after: $endCursor) {
    pageInfo { hasNextPage endCursor }
    nodes { ... on PullRequest {
      number title body mergedAt
      labels(first: 30) { nodes { name } }
      files(first: 100) { totalCount nodes { path } }
      closingIssuesReferences(first: 5) {
        nodes { number title repository { nameWithOwner } } } } }
  }
}"""


class CantRun(RuntimeError):
    """The run can't start; the message says why."""


# ---------------------------------------------------------------- GitHub

def fetch_merged(repo: str, since: str) -> list[dict]:
    """Every PR of repo merged on or after since (YYYY-MM-DD, UTC)."""
    r = subprocess.run(["gh", "api", "graphql", "--paginate",
                        "-f", f"q=repo:{repo} is:pr is:merged merged:>={since}",
                        "-f", f"query={QUERY}", "--jq", ".data.search.nodes[]"],
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise CantRun(f"gh api graphql failed: {r.stderr.strip()[:300]}")
    return [json.loads(line) for line in r.stdout.splitlines() if line.strip()]


def gh_goals(repo: str) -> Callable[[dict], dict]:
    """{pr number: goal} for {pr number: [closing issue numbers]}: the first closing issue's
    nearest open Goal or Area the owner opened, as trouble.py's pr_goal finds it."""
    def resolve(closes: dict) -> dict:
        sys.path.insert(0, str(HERE.parent / "launcher"))
        import swarm
        owner = swarm.owner_login()
        numbers = sorted({n for ns in closes.values() for n in ns})
        scopes = swarm.gh_scopes(repo, numbers) if numbers else {}

        def goal_of(n: int) -> Optional[str]:
            g = swarm.scope_goal(scopes.get(n), owner)
            return f"{g['repo'] or repo}#{g['number']}" if g else None
        return {pr: next((g for g in map(goal_of, ns) if g), None) for pr, ns in closes.items()}
    return resolve


def closing(pr: dict, repo: str) -> list[int]:
    """The numbers of the issues in repo that pr closes."""
    nodes = (pr.get("closingIssuesReferences") or {}).get("nodes") or []
    return [i["number"] for i in nodes
            if ((i.get("repository") or {}).get("nameWithOwner") or repo) == repo]


def kind_label(pr: dict, ls: lsmod.LabelSet) -> Optional[str]:
    """The owner's `kind:<label>` correction on pr, if it carries exactly one known one."""
    kinds = {lb["name"][len(KIND):] for lb in (pr.get("labels") or {}).get("nodes") or []
             if lb.get("name", "").startswith(KIND)}
    kinds &= set(ls.label_names)
    return kinds.pop() if len(kinds) == 1 else None


# ---------------------------------------------------------------- the cache

def load_cache(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise CantRun(f"can't read {path}: {e}") from None
    if not isinstance(data, dict) or not isinstance(data.get("prs"), dict):
        raise CantRun(f"{path} has no \"prs\" object")
    if data.get("schema") != SCHEMA:
        raise CantRun(f"{path} is schema {data.get('schema')}, not {SCHEMA}")
    return data["prs"]


def write_cache(path: Path, use: str, prs: dict, now: dt.datetime) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {"schema": SCHEMA, "labelset": NAME, "classifier": use,
            "updated_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "prs": {k: prs[k] for k in sorted(prs, key=int)}}
    path.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")


def append_corrections(root: Path, ls: lsmod.LabelSet, rows: list[dict], say: Callable) -> None:
    """Add owner-corrected PRs that aren't in data/effort.jsonl to it as dev items."""
    path = root / "data" / f"{NAME}.jsonl"
    have = effort_data.read_rows(path)
    new = [r for r in rows if r["id"] not in have]
    if not new:
        return
    for r in new:
        have[r["id"]] = r
    effort_data.write_rows(path, have)
    lsmod.load_items(path, ls)   # the result must still load
    say(f"swarm classify run: added {len(new)} owner-labelled PRs to {path.name} as dev items")


# ---------------------------------------------------------------- the run

def run(root: Path, since: str, repo: str = effort_data.REPO, model: Optional[str] = None,
        manifest: Path = evalrun.MANIFEST, fetch: Callable = fetch_merged,
        goals: Optional[Callable] = None, runner: Callable = classifier.claude_runner,
        use: Optional[str] = None, now: Optional[dt.datetime] = None,
        say: Callable = print) -> int:
    """Label the PRs merged since `since` into cache/effort.json. use forces "model" or
    "paths" (tests); by default evalrun.model_choice decides."""
    try:
        dt.date.fromisoformat(since)
    except ValueError:
        raise CantRun(f"--since must be a date, YYYY-MM-DD, not '{since}'") from None
    try:
        ls = lsmod.load_labelset(root / "labelsets" / f"{NAME}.yml")
    except lsmod.FormatError as e:
        raise CantRun(str(e)) from None
    cfg = evalrun.config(manifest)
    model = model or cfg.get("model") or evalrun.DEFAULT_MODEL
    if use is None:
        use, why = evalrun.model_choice(NAME, root, model, manifest)
        say(f"swarm classify run: using {use}: {why}")
    goals = goals or gh_goals(repo)
    now = now or dt.datetime.now(dt.timezone.utc)
    cache_path = root / "cache" / f"{NAME}.json"
    cache = load_cache(cache_path)
    prs = sorted(fetch(repo, since), key=lambda p: p["number"])
    prs = [p for p in prs if p.get("mergedAt") and p["mergedAt"][:10] >= since]
    known = {int(k): {"number": int(k), "mergedAt": v.get("merged_at")}
             for k, v in cache.items() if v.get("merged_at")}
    known.update({p["number"]: p for p in prs})
    system = classifier.system_prompt(ls)

    todo, corrected = [], []
    for p in prs:
        key = str(p["number"])
        item = lsmod.Item(f"pr-{p['number']}", effort_data.item_text(p), "", "dev", "run", {},
                          effort_data.iso_week(p["mergedAt"]))
        h = classifier.prompt_hash(system, classifier.user_prompt(item))
        kind, was = kind_label(p, ls), cache.get(key)
        fresh = was is not None and was.get("hash") == h
        if kind and fresh:
            if (was.get("label"), was.get("labeller")) != (kind, OWNER):
                was.update(label=kind, labeller=OWNER)
                corrected.append((p, item, was))
            continue
        if fresh and was.get("labeller") == use:
            continue
        todo.append((p, item, h, kind))

    if use == "model":
        cap = classifier.Cap(ls.runs * len(todo), PER_PR_USD * len(todo))
        rec = classifier.Recordings(root / "recordings", NAME, model)
        classify = classifier.ModelClassifier(ls, model, rec, ls.runs, live=True, cap=cap,
                                              runner=runner, reuse=True)
    else:
        classify = lambda it: classifier.BASELINES["paths"](ls, [], it)  # noqa: E731

    resolved = goals({p["number"]: closing(p, repo) for p, *_ in todo}) if todo else {}
    done, stopped = 0, None
    for p, item, h, kind in todo:
        try:
            pred = classify(item)
        except (classifier.CapReached, classifier.ModelError) as e:
            stopped = str(e)
            break
        if pred.label is None and not kind:   # "needs human": no label to store
            say(f"swarm classify run: PR #{p['number']} needs a human: the samples didn't "
                f"agree; a kind:<label> on it settles it")
            continue
        fix = bool(pred.flags.get("fix"))
        entry = {"repo": repo, "title": p["title"].strip(), "merged_at": p["mergedAt"],
                 "label": kind or pred.label, "fix": fix,
                 "fixes": effort_data.fixed_pr(p, known) if fix else None,
                 "goal": resolved.get(p["number"]), "hash": h,
                 "labeller": OWNER if kind else use}
        cache[str(p["number"])] = entry
        done += 1
        if kind:
            corrected.append((p, item, entry))

    write_cache(cache_path, use, cache, now)
    if corrected:
        append_corrections(root, ls, [
            {"id": item.id, "label": e["label"], "flags": {"fix": e["fix"]},
             **({"fixes": e["fixes"]} if e.get("fixes") else {}),
             "labelled_by": OWNER, "split": "dev", "week": item.week, "text": item.text}
            for _, item, e in corrected], say)
    say(f"swarm classify run: {len(prs)} PRs merged since {since}; {done} labelled, "
        f"{len(corrected)} owner corrections, {len(prs) - len(todo)} already in the cache; "
        f"wrote {cache_path}")
    if stopped:
        say(f"swarm classify run: stopped early: {stopped}; run it again to label the rest")
        return 1
    return 0


def add_run_args(p) -> None:
    p.add_argument("labelset", choices=[NAME], help="the label set: only effort has a cache")
    p.add_argument("--since", required=True, metavar="YYYY-MM-DD",
                   help="label PRs merged on or after this UTC day")
    p.add_argument("--model", help="default: swarm.toml [classify] model")
    p.add_argument("--repo", default=effort_data.REPO, help=f"default: {effort_data.REPO}")
    p.add_argument("--dir", default=str(HERE), help="the classify directory (default: classify/)")
    p.add_argument("--manifest", default=str(evalrun.MANIFEST), help="default: swarm.toml")


def run_main(args, say: Callable = print) -> int:
    try:
        return run(Path(args.dir), args.since, args.repo, args.model, Path(args.manifest),
                   say=say)
    except (CantRun, evalrun.CantRun) as e:
        say(f"swarm classify run: {e}")
        return 2


def add_compare_args(p) -> None:
    p.add_argument("labelset", help="the label set's name: classify/labelsets/<name>.yml")
    p.add_argument("--split", choices=lsmod.SPLITS, default="test", help="default: test")
    p.add_argument("--model", help="default: swarm.toml [classify] model")
    p.add_argument("--dir", default=str(HERE), help="the classify directory (default: classify/)")
    p.add_argument("--out", help="the report's path (default: <dir>/reports/<name>.md)")
    p.add_argument("--manifest", default=str(evalrun.MANIFEST), help="default: swarm.toml")


def compare_main(args, say: Callable = print) -> int:
    try:
        evalrun.compare(args.labelset, Path(args.dir), args.split, args.model,
                        Path(args.manifest), Path(args.out) if args.out else None, say)
    except evalrun.CantRun as e:
        say(f"swarm classify compare: {e}")
        return 2
    return 0
