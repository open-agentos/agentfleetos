---
id: GOV-0058
title: The context pack is capped by a setting, ranks below rulings and respects repo scope
status: in-force
kind: ruling
question: "#1203"
domain: architecture
shape: authoritative
classification:
  reversibility: two-way
  blast_radius: org
  nature: preference
  knowledge: shared
decided_by: humans.owner
ratified_by: humans.owner
date: 2026-11-17
review_by: 2027-02-28
supersedes: []
applies_to:
  paths: []
  roles: []
  situations:
    - building or changing the context pack of lessons that the launcher or `swarm watch` gives a session (Recall, FEAT-17)
    - choosing how many lessons a session gets
    - deciding whether a lesson may be given to a session in another repo
---

## Ruling

The context pack of lessons that the launcher and `swarm watch` give each session follows three terms:

- **Cap:** at most N lessons per session, ranked by match strength times confidence. N is a `swarm.toml` setting (`[memory] pack_cap`), 10 by default.
- **Standing:** every pack says its lessons are guidance under the rulings, never above them. Where a lesson and an in-force ruling disagree, the ruling wins.
- **Scope:** a lesson with `scope: repo:<owner/name>` is never put in a session in another repo. This limits who is given a lesson, not who can read it (lessons are public, GOV-0052).

## Applies when / does not apply when

- Applies when: building or changing the pack for Recall (#1187), or its cap, standing line or scoping.
- Does not apply when: deciding which roles see the owner model (GOV-0056), what may become a lesson (GOV-0055) or where memory lives (GOV-0052).

## Context

#1187 (FEAT-17, Recall) has sessions started with a pack of lessons, supplied the way GOV-0039 supplies `CLAUDE.md` and the role prompt. GOV-0052 put memory public in this repo but left the pack's recall terms unruled. The builder raised them in #1203. The owner answered "Option 1 confirmed. Record: yes" in a comment on #1203.

## Options considered

1. **Rule all three terms** (chosen): cap in `swarm.toml`, the guidance-under-rulings line in every pack, repo-scoped lessons only for sessions in that repo.
2. **Rule standing and scope, fix the cap in code at 10:** one fewer knob, but changing it needs a PR.
3. **No cap:** simplest, but a session handed every matching lesson learns nothing.
4. **Do nothing:** each later change would revisit the terms.

## Deliberation

n/a. This is an authoritative decision by the owner, who confirmed option 1, the question's recommendation.

## Consequences

- #1187 may be built to these terms once the lessons store (#1185) exists. The cap is tuned in `swarm.toml` without a code PR, as GOV-0053 does for its limits.
- Lessons rank below rulings, so a conflicting lesson is a signal for the librarian to raise a question (GOV-0056), not a pack override.
- Revisit if a pack crowds out a relevant lesson at the default cap, or when `review_by` passes.
