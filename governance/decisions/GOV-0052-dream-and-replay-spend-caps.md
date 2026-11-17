---
id: GOV-0052
title: The nightly dream and lesson replays run on the engine's key under per-run caps only
status: in-force
kind: ruling
question: "#1149"
domain: spend
shape: authoritative
classification:
  reversibility: two-way
  blast_radius: repo
  nature: preference
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
    - setting caps for the nightly dream (librarian run, FEAT-16, FEAT-20)
    - setting caps or counts for lesson replays (rehearsal, FEAT-19)
    - choosing which credential memory runs use
---

## Ruling

The nightly dream and the lesson replays run on the engine's dedicated Console workspace key (GOV-0032) under per-run caps only, with no spend totals (GOV-0033):

- the dream is one librarian run a night, only when there are new episodes, capped by the librarian's `spend_cap_usd` of $3 and by `[watch] max_turns` (GOV-0012);
- each replay costs at most $0.50, on a Haiku-tier model, and never pushes;
- at most 10 replays run a night; the rest wait for the next night.

The caps are `swarm.toml` settings, so tuning them stays two-way.

## Applies when / does not apply when

- Applies when: setting or building the caps, the replay count or the model for the dream and replays.
- Does not apply when: adding a monthly memory budget or any spend total, or running replays on the owner's subscription. Each would be a new `spend` question.

## Context

The Learning loop initiative (FEAT-14 to FEAT-22) has a librarian dream each night and replays a past task twice for each new or changed lesson, with and without it. GOV-0033 gives the engine no spend totals. Its limits are per-run caps (GOV-0012), the concurrency ceiling (GOV-0010) and the $1,000-a-month Console workspace limit (GOV-0032). `swarm.toml`'s `[[session]]` accepts only `role`, `count`, `model` and `spend_cap_usd`, so a per-replay cap and a replay count need a new setting, as `[classify]` added for GOV-0045. #1149 asked what these runs may spend and on which credential. The owner answered "Option 1 confirmed. Record: yes" in a comment on #1149.

## Options considered

1. **Per-run caps only, on the engine's key** (chosen): fits GOV-0033; the Console limit stays the backstop; the 10-replay ceiling caps a bad night.
2. **Option 1 plus a monthly memory budget on the Desk:** conflicts with GOV-0033 and would need it amended.
3. **Replays on the owner's subscription, on the Mac, as GOV-0045 does for the classifier:** cheaper, but only works while the Mac is on, and mixes credentials.
4. **No replays:** lessons go active on the librarian's judgement alone; drops GOV-0032's "Every lesson ships with an eval case."

## Deliberation

n/a. This is an authoritative decision by the owner, who confirmed option 1, the question's recommendation.

## Consequences

- The by-hand FEAT-16 runs and any replays may go ahead within these caps once the settings exist.
- The new settings (replay cap, replay count, replay model) are added to `swarm.toml` by the builder issue that ships rehearsal. This record does not name them.
- The team accepts up to about $3 for a dream plus up to about $5 for replays on a night, per run caps and not a total, with the Console limit as the backstop.
- Expires on 2026-12-01 (the question's time to live) unless re-affirmed.
