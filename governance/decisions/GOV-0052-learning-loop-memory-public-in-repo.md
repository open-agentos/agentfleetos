---
id: GOV-0052
title: The learning loop's memory lives in this repo, all public, under memory/
status: in-force
kind: ruling
question: "#1147"
domain: architecture
shape: authoritative
classification:
  reversibility: costly
  blast_radius: org
  nature: preference
  knowledge: shared
decided_by: humans.owner
ratified_by: humans.owner
date: 2026-11-17
review_by: 2026-12-01
supersedes: []
applies_to:
  paths:
    - memory/**
  roles: []
  situations:
    - building or changing where the learning loop's episodes, lessons or owner model are stored (FEAT-14, FEAT-15, FEAT-18)
    - deciding whether a piece of team memory goes in git, on the engine host or in another repo
---

## Ruling

The learning loop's memory lives in this repo, all public: raw session notes in `memory/episodes/`, distilled lessons in `memory/lessons/`, and the owner model in `memory/owner.md`. Rulings are unchanged (`governance/decisions/`).

## Applies when / does not apply when

- Applies when: building or changing where episodes, lessons or the owner model are stored or read from.
- Does not apply when: the choice is about what a lesson says or when it is distilled (GOV-0032), or about the classifier's data (GOV-0044).

## Context

GOV-0032 rules in a learning loop and a librarian role, but not where the memory lives. The Learning loop initiative specifies episodes (about 30 days, FEAT-14), lessons (one fact per file, in the ruling format, FEAT-15), the owner model (FEAT-18) and rulings. The repo is public. Episodes may quote issue text and owner corrections, and the owner model is personal. #1147 asked; the planner recommended option 2 (split by sensitivity). The owner answered "Option 1 confirmed. Record: yes" in a comment on #1147.

## Options considered

1. **All public in the repo** (chosen): `memory/episodes/`, `memory/lessons/`, `memory/owner.md`. Simplest and fully reviewable, but it publishes the owner model and raw notes.
2. **Split by sensitivity:** episodes on the engine host, `scope: fleet` lessons in `memory/`, and the owner model and `scope: repo:<x>` lessons in a private repo. The question's recommendation.
3. **All private:** one private memory repo. Safe, but fleet lessons aren't visible beside the code and the public Desk can't show them.
4. **Do nothing:** no team memory; lessons stay in individual sessions' memory.

## Deliberation

n/a. This is an authoritative decision by the owner, who chose option 1, not the question's recommendation (option 2).

## Consequences

- FEAT-14, FEAT-15 and FEAT-18 are built to the in-repo layout: no engine-host episode store and no private memory repo.
- The team accepts that the owner model and raw episode notes are public in git history, and that git retention can't enforce the 30-day episode window by deletion alone.
- The question's extra terms (a capped context pack set in `swarm.toml`, lessons as guidance under the rulings, never putting a `repo:<x>` lesson into a session in another repo) were part of the recommendation, not option 1. They are not ruled here; the builder raises them in a new question if needed.
- Episodes sit in tension with GOV-0002 and GOV-0004 (prompt text local-only and redacted; everything posted to GitHub is public). This record doesn't amend them; a build that writes prompt text to episodes needs its own ruling.
- Consultants' client memory is not covered; this record says nothing about memory for other repos or clients.
- Expires on 2026-12-01 (the question's time to live) unless re-affirmed.
