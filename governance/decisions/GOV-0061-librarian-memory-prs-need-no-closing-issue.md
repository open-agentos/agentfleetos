---
id: GOV-0061
title: A librarian PR that touches only memory/ needs no closing go issue to merge under the standing grant
status: in-force
kind: ruling
question: "#1280"
domain: security
shape: authoritative
classification:
  reversibility: two-way
  blast_radius: repo
  nature: values
  knowledge: shared
decided_by: humans.owner
ratified_by: humans.owner
date: 2026-11-18
review_by: 2027-02-28
supersedes: []
applies_to:
  paths:
    - memory/**
  roles:
    - librarian
  situations:
    - the librarian's nightly memory PR says `Refs #N` and closes no issue
    - the merger checks whether a librarian memory-only PR closes exactly one go issue
---

## Ruling

The merger does not require a librarian PR that touches only `memory/` to close exactly one go issue. Such a PR may merge under the standing grant (GOV-0027, GOV-0034) once the reviewer approved it at head, `tests` pass, there is no overstep, no protected path (`memory/owner.md` stays protected) and it is under the size limit, as GOV-0056 Ruling 1 sets out. Every other PR still needs one closing go issue.

## Applies when / does not apply when

- Applies when: the PR's author is the librarian and every changed file is under `memory/`, whether the PR closes no issue (the nightly `memory: night of <date>` PR, which says `Refs #<report issue>`) or one.
- Does not apply when: the PR touches anything outside `memory/`, or touches `memory/owner.md`, or has any other author. Those keep the closing-issue condition.
- Does not widen GOV-0056 in any other way: the other conditions it lists are unchanged.

## Context

Raised by the builder on #1274 (the merger's rule for GOV-0056 Ruling 1). GOV-0056 lists the conditions for a memory-only librarian PR "like any other go PR" but doesn't say whether the closing-issue condition applies. The nightly PR from `[dream]` (#1190) closes no issue, so with the check kept the merger would never merge it. The builder's default was to keep the check. The owner answered on #1280: "Option 2 confirmed", with `Record: yes`.

## Options considered

1. **Keep the check** (the default): the nightly PR waits for the owner each night.
2. **Drop the closing-issue check for librarian memory-only PRs** (chosen): the scope limit and the reviewer's approval are the guard.
3. **Keep the check and have each night's dream open or reuse a go issue:** uniform rule, but an issue a night and the librarian would need an owner-opened Goal or Area to open it under.

## Deliberation

n/a. This is an authoritative decision by the owner on #1280.

## Consequences

#1281 (for #1274) kept the closing-issue check, so `launcher/merger.py` doesn't yet apply this ruling. #1285 tracks the change that skips the condition for a librarian PR that touches only `memory/`. A memory-only librarian PR needs no go issue at all, so the only guards are the `memory/` scope limit, the protected owner model and the reviewer's approval at head. Revisit if a librarian PR ever merges something the owner would have wanted to see first. Reversal is one condition in the merger.
