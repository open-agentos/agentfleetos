---
id: L-9001
title: Open every PR body with one line that starts `Why:` and says why the change is needed.
status: proposed
scope: fleet
applies_to:
  roles: [builder]
  paths: []
  situations:
    - writing a PR body
sources:
  - ep-drill-correction
  - ep-drill-note
confidence: 0.6
uses: 0
last_used:
created: 2026-11-18
review_by: 2027-02-18
eval_case: evals/lessons/drill/L-9001.toml
supersedes: []
related_rulings: []
---

The first line of a PR body is `Why: ` and one sentence on the problem the change solves, before any heading or summary.

## Why

The planted correction: in this drill the owner corrected a builder whose PR body said what changed but not why. Nothing else in the repo asks for this line, so a replay without the lesson has no reason to write it.

## Example

A PR that adds the replay gate opens with `Why: a lesson drawn from two bad days could make every later session worse, and nobody would see it.`
