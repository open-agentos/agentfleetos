# classify/: the classifier engine and its eval harness

A label set says what the labels mean and what bar a classifier must clear. A labelled set is
items with gold labels. `swarm classify eval` scores a classifier on the labelled set and writes
a Markdown report (#1010, FEAT-1 of Goal #987).

Everything here is public (GOV-0044). The label set's pass mark and the labelled set are
committed before the first live run, and every report carries both files' sha256, so the bar
can't move after a result is known. Model calls run on the owner's Mac through the Claude Code
login (`claude -p`), capped per run (GOV-0045). **No cost figures** go in any file here
(`evals/README.md`, GOV-0033).

| Path | What |
|---|---|
| `labelsets/<name>.yml` | a label set |
| `data/<name>.jsonl` | its labelled set |
| `recordings/<name>/<model>.jsonl` | every reply a live run got, for replay |
| `reports/<name>-<split>-<classifier>.md` | eval reports |
| `reports/<name>.md` | majority, paths and the model side by side (#1012) |
| `cache/effort.json` | each merged PR's label, which the Desk reads (#1012, GOV-0046) |
| `effort_data.py` | builds the effort labelled set, drafts its labels and takes the owner's review (#1011) |
| `effortrun.py` | `swarm classify run effort` and `swarm classify compare` (#1012) |
| `review/<name>.md` | the file the owner edits to label a labelled set |
| `testdata/` | the fixture label set, labelled set, recordings and expected report the tests use |

Standard library only.

## Label set format

```yaml
description: What the labels sort.        # optional; goes in the model's instructions
threshold: 0.6      # majority agreement below this answers "needs human"
runs: 3             # samples per item (optional, default 3)
max_calls: 300      # the most model calls one live run may make
labels:             # two or more
  - name: bug
    definition: The change fixes behaviour that was wrong.
    boundary:       # optional rules for the edges
      - A fix to documentation is docs, not bug.
    examples:       # 2 or 3
      - "Fix the crash when the list is empty"
      - "Stop double-counting merges"
flags:              # optional yes/no questions asked alongside the label
  - name: urgent
    definition: The text says the change is urgent.
pass_mark:
  accuracy: 0.8     # required
  coverage: 0.7     # optional
  min_recall:       # optional, per label: lopsided bars
    bug: 0.6
```

The file is read with a strict YAML subset: mappings, block lists, `[a, b]` lists, plain or
quoted scalars, numbers, `true`/`false`, comments. Block scalars (`|`, `>`), inline mappings
and anchors are refused. Quote a list item that has `word: ` in it. "needs human" can't be a
label name.

## Labelled set format

One JSON object per line:

```json
{"id": "pr-812", "text": "…", "label": "bug", "flags": {"urgent": false}, "split": "dev", "labelled_by": "owner", "week": "2026-W45"}
```

`id`, `text`, `label`, `split` (`dev` or `test`) and `labelled_by` are required. `flags` and
`week` are optional. Share error is reported only for items that carry a week.

`hard` (the name of the boundary rule a hard case tests) and `fixes` (the PR number a `fix`
flag points at) are optional too. An item `labelled_by: draft` carries a model's guess, not a
gold label: an eval neither scores it nor lets a baseline see it, and the report says how many
it left out.

## The report

All on the chosen split:

- **Accuracy**: correct ÷ all items. An item answered "needs human" counts as wrong.
- **Coverage**: answered ÷ all items. "Needs human" isn't an answer.
- **Accuracy on covered items**: correct ÷ answered.
- **Per label**: precision is correct ÷ answered items predicted as the label. Recall is correct
  ÷ items whose gold label it is, and "needs human" counts as a miss.
- **Confusion matrix**: gold labels down, predicted labels (and "needs human") across.
- **Flags**: per flag, precision and recall of `true` over answered items.
- **Share error by week**: a label's share of the week's answered items against its share of
  the week's gold labels, and the difference in points.
- **Pass mark**: every bar must hold. A label under its `min_recall` fails a run whose accuracy
  passes. A label with no gold items has no recall, so it fails its bar.
- **Items**: each item's gold and predicted label, confidence and evidence.

## Classifiers

**The model classifier** asks the model `runs` times per item. Each reply is one JSON object
with the label, the flags and an evidence line quoted from the text. It returns the majority
label, with confidence = the share of samples that agree with it, a flag's majority among
those samples, and the first agreeing sample's evidence. A reply that names no known label is a
sample with no vote. A tie, or confidence below `threshold`, answers "needs human".

Each call is `claude -p --model <model> --tools "" --strict-mcp-config
--no-session-persistence --system-prompt <the label set> --max-budget-usd <what is left>`,
with the item on stdin, run in an empty temporary directory (GOV-0045).

**Baselines** are plain functions registered by name in `classifier.py`:

```python
@baseline("paths")
def paths(labelset, dev_items, item) -> Prediction: ...
```

`majority` is built in: the dev split's most common gold label, with ties going to the label
listed first. `paths` is built in too (#1012): it reads an item's `Paths touched` line, and the
first rule that matches wins: `governance/` or `roles/` is governance; `research/`, or only
Markdown, is knowledge; `dashboard/` is capability; anything else is upkeep. Its fix flag is a
`Fixes #N` or `follow-up to #N` in the text.

## Running an eval

```sh
launcher/swarm classify eval <labelset> [--split dev|test] [--baseline NAME]
                             [--replay | --live] [--runs N] [--model M]
```

- `--replay` (the default) uses only `recordings/` and makes no model calls. A missing
  recording stops the run and says which one. A recording is keyed by item, sample and a hash of
  the prompt, so editing a label or an item's text needs a new live run.
- `--live` calls the model and records every reply. It refuses to start unless the label set
  and labelled set are committed as they are on disk (GOV-0044), and unless `swarm.toml` has
  `[classify] eval_budget_usd`. It stops at the label set's `max_calls` or when the budget is
  spent, whichever comes first, says which, and writes no report. Replies recorded before the
  stop are kept.
- `--baseline NAME` scores a baseline instead of the model, with no model calls.
- The model is `--model`, else `[classify] model` in `swarm.toml`, else `claude-haiku-5-5`.
- `--dir` points at another classify directory (the tests use `testdata/`), and `--out`
  writes the report somewhere else.

It exits 0 when the run passes its pass mark, 1 when it fails it, and 2 when it can't run.

Recordings hold the item id, the sample number, the prompt hash and the model's reply, and
nothing else: no prompt text, keys or session data (GOV-0044).

## The effort label set (#1011)

`labelsets/effort.yml` sorts merged PRs into capability, upkeep, governance and knowledge, with
a `fix` flag (FEAT-2 of Goal #987). Each boundary rule starts with its name, and a hard case
names its rule in `hard`. `data/effort.jsonl` holds every PR merged up to the cut-off
(2026-11-13 UTC), with title, linked issue, paths touched and body in `text`, and its merge
week.

```sh
python3 classify/effort_data.py build --live   # add new PRs, drafted by the model (GOV-0045)
python3 classify/effort_data.py review         # write review/effort.md
python3 classify/effort_data.py apply          # take the owner's edits from it
python3 classify/effort_data.py check          # how far from #1011's criteria
```

`build` drafts each new PR with one model sample, capped at $0.25 per PR (GOV-0045), and
records the reply in `recordings/effort-draft/`. Without `--live` it replays them. New items are
split 70/30, dev/test, stratified by draft label and merge month. In `review/effort.md` the
owner sets each PR's `label`, `fix` and `hard`, and `reviewed: yes` makes the label gold
(`labelled_by: owner`). A PR tagged `hard` moves to test, and a draft test PR with the same label
moves to dev in its place. Every test item needs the owner's label before the set is done.

## Comparing and running the effort classifier (#1012)

```sh
launcher/swarm classify compare effort            # writes reports/effort.md, no model calls
launcher/swarm classify run effort --since 2026-11-14
```

`compare` scores majority, paths and the model (from its recordings only) on the test split and
writes them side by side, each with its pass mark, per-label precision and recall, confusion
matrix and share error by week. With no recordings it reports the model as not run. It says
which classifier the cache uses: the model if its recorded replies pass the label set's pass
mark on the test split, else paths. So the model is used only after a `swarm classify eval
effort --split test --live` that passes.

`run` labels the PRs merged on or after `--since` (UTC) into `cache/effort.json`, schema 1 as
`dashboard/README.md#effort` documents it. Each entry's `hash` covers what the classifier reads
(the label set's prompt and the PR's text); a PR already in the cache at the same hash, by the
same classifier, is skipped, so a re-run with no new merges makes no model calls. `goal` is the
open Goal or Area above the PR's closing issue when the entry is written, as `owner/repo#N` or
null; it is stored and never re-resolved, and a changed goal never relabels (GOV-0046). A model
run reuses recorded replies (`recordings/effort/`) and calls `claude -p` only for the rest,
capped at $0.25 per PR (GOV-0045).

A `kind:<label>` label on a PR is the owner's correction. The next run sets that entry's
`label` and `labeller: owner`, with no model call for a PR already in the cache, and leaves `fix`
and `goal` alone. A corrected PR not yet in `data/effort.jsonl` is appended there as a dev item,
`labelled_by: owner`. Items already in the labelled set are left alone, so the test split the
pass mark was set on doesn't move (GOV-0044).

It exits 0 when every PR is labelled, 1 when a cap or model error stopped it (what it labelled is
kept), and 2 when it can't run. The lead runs it by hand until it has run twice (#526 §5).
