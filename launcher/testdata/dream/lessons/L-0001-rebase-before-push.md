---
id: L-0001
title: Rebase the branch on origin main before pushing when the merge queue shows a conflict.
status: active
scope: fleet
applies_to:
  roles: [builder]
  paths: []
  situations: []
sources:
  - note:s-1
  - review:1
confidence: 0.6
uses: 0
last_used: 2026-11-12
created: 2026-11-01
review_by: 2027-02-01
eval_case: evals/lessons/x.json
rehearsal:
  result: promoted
supersedes: []
related_rulings: []
---

Rebase on origin main first.

## Why

Sessions kept tripping on it.

## Example

One session did, and the reviewer asked for it.
