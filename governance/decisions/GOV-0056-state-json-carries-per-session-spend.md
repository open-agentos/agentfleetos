---
id: GOV-0056
title: state.json may carry each session's own spend estimate, its cap and an over-cap flag, never a total
status: in-force
kind: ruling
question: "#1153"
domain: security
shape: authoritative
classification:
  reversibility: one-way
  blast_radius: external
  nature: values
  knowledge: shared
decided_by: humans.owner
ratified_by: humans.owner
date: 2026-11-17
review_by: 2026-12-01
supersedes: []
applies_to:
  paths: []
  roles: []
  situations:
    - changing which fields the Desk's public `state.json` carries for sessions
    - drawing Crew's sessions table (Spend column) client-side
    - deciding whether a public Desk file may carry per-session cost
---

## Ruling

`state.json` may carry each session's own list-price spend estimate, its cap and an over-cap flag, so Crew's sessions table refreshes in place. It carries one figure per session and never sums them into a total (GOV-0033).

## Applies when / does not apply when

- Applies when: adding or changing per-session `cost`, cap or over-cap fields in `state.json`, and drawing them in `crew.html`.
- Does not apply when: publishing any spend total, daily spend or per-day figure, or putting session cost on another Desk page or file. Each is a new `security` question. Per-issue cost on the Work map stays under GOV-0049.

## Context

#1139 moves Crew to client-side drawing from `state.json` (GOV-0051). Crew's sessions table has a Spend (est.) column with an "over cap" pill, shown publicly since #1113. `state.json` carries no cost: #397 set that, and `test_state.py` fails on any key named cost, usd or spend. GOV-0051 excludes changes to which fields `state.json` publishes (GOV-0002, GOV-0004), and GOV-0049 covers per-issue cost in `map.json` only. #1153 asked whether `state.json` may carry per-session spend. The owner answered "Option 2 confirmed. Record: yes" in a comment on #1153.

## Options considered

1. **Keep `state.json` cost-free:** spend updates only on reload, and a new session shows "—" until then.
2. **Publish each session's spend estimate, cap and over-cap flag in `state.json`** (chosen): the whole table refreshes in place; a new machine-readable cost field; ends #397's no-cost rule for `state.json`.
3. **Drop the Spend column from Crew:** everything refreshes, but the owner loses a figure kept in #1113.

## Deliberation

n/a. This is an authoritative decision by the owner, who confirmed option 2, the question's recommendation.

## Consequences

- `state.json` may carry per-session cost, cap and an over-cap flag. The same figures are already public in `crew.html`, so this adds a format, not new exposure.
- `test_state.py`'s ban on keys named cost, usd or spend, and the README's "no cost in `state.json`" line (`dashboard/README.md`), must change to allow these per-session fields and still fail on any total. Those edits belong to the PR that ships the fields (#1139), not this record.
- Sums stay barred (GOV-0033), so the test should keep rejecting totals.
- The team accepts publishing a new cost field in ready-made form. Dropping the fields again is a code change, but figures already published can't be recalled.
- Expires on 2026-12-01 (the question's time to live) unless re-affirmed.
