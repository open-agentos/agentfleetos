---
id: GOV-0055
title: A lesson needs two independent episodes, one an engine-recorded signal, from trusted authors only; session notes strip secrets; the validator rejects lessons that instruct changes to permissions, credentials, tools or governance
status: in-force
kind: ruling
question: "#1151"
domain: security
shape: authoritative
classification:
  reversibility: one-way
  blast_radius: org
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
    - writing, validating or accepting a lesson in team memory (FEAT-15's validator, the dream pass, the context pack)
    - deciding whether text from an issue body, PR comment or review thread may feed a lesson
    - writing session notes that memory may later read
---

## Ruling

Adopt option 1 of #1151. Nothing becomes a lesson unless all of these hold, and FEAT-15's validator enforces them:

- **Two independent episodes.** At least two, from different sessions or signals. Two quotes of one comment count as one.
- **One engine-recorded signal.** At least one source is a signal the engine recorded (an owner act, a review outcome, a revert, a failed run), not only text a session wrote.
- **Trusted authors only.** Nothing becomes a lesson from content by anyone other than the owner, the swarm's Apps (`identities.agents`) or the repo's listed maintainers.
- **Secrets stripped.** Session notes strip secrets.
- **No instructions to widen power.** A lesson's body may not contain instructions to change permissions, credentials, tools or governance. The validator rejects one that does.

## Applies when / does not apply when

- Applies when: an agent or the engine writes, validates or accepts a lesson, or writes session notes that memory may read.
- Does not apply when: the text is spec text reaching a session as a fenced snapshot (GOV-0042), or heartbeat prompt redaction (GOV-0002).
- Does not decide: where memory lives, who may write it, or spend caps (separate questions).

## Context

Lessons reach every matching session through the context pack (FEAT-17), so a poisoned lesson spreads. Episodes include text from issue bodies, PR comments and review threads, and in other org repos (GOV-0036) will include content from outside contributors. The specs say issue and PR text is untrusted data, and that a lesson needs two independent episodes and must cite its sources; this makes that a rule. `jurisdictions.yml` marks `security` `always_one_way`.

Raised by the planner on #1151 for the Learning loop initiative (FEAT-14 to FEAT-22). The owner answered "Option 1 confirmed" and "Record: yes". Precedent checked on the question: GOV-0013, GOV-0043, GOV-0039, GOV-0042 (nearest; covers specs, not memory) and GOV-0002. None covers memory written from untrusted text.

## Options considered

1. **Strict sources**: the rules above. Ties every lesson to something that happened, keeps outside contributors' text out of memory, and makes the rule mechanical. Chosen.
2. **Two sources only**: simpler, but two copies of one injected comment could clear it.
3. **The owner approves every lesson**: safest, but the owner becomes the bottleneck again.

## Deliberation

n/a (authoritative). The owner confirmed the planner's recommendation.

## Consequences

Stricter than the spec, so fewer lessons will qualify. The rules can be loosened later by a new ruling. Until this record merges, no lesson is written from episodes (the question's default). The review date is the question's time to live; re-affirm or supersede it by then.
