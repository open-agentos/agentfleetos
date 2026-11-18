---
id: GOV-0060
title: Heartbeat events do not record the lessons a session was given
status: in-force
kind: ruling
question: "#1243"
domain: security
shape: authoritative
classification:
  reversibility: two-way
  blast_radius: org
  nature: preference
  knowledge: shared
decided_by: humans.owner
ratified_by: humans.owner
date: 2026-11-18
review_by: 2027-02-28
supersedes: []
applies_to:
  paths:
    - heartbeat/**
  roles: []
  situations:
    - recording which lessons a session was given (Recall, FEAT-17, #1187)
    - adding a field to the heartbeat event or its schema
---

## Ruling

Do not add a `lessons` field, or any lesson id, to heartbeat events. GOV-0002's field list is unchanged. Record the lessons a session was given as a `given` episode in the engine's episodes outbox, and in the launcher's local `sessions.json`.

## Applies when / does not apply when

- Applies when: a change would put the lessons given to a session into a heartbeat event, `heartbeat/SCHEMA.md` or `event.schema.json`.
- Does not apply when: the owner later rules that the Desk needs a session's lessons from its event stream. That is a new question, and the Desk can read the `given` episodes meanwhile.

## Context

#1187 (FEAT-17, Recall) says the heartbeat records which lessons each session was given. GOV-0002 lists the fields a heartbeat event may capture and says nothing else may be captured. Lesson ids aren't on that list, and heartbeat events go to public tracking issues (GOV-0003, GOV-0004). The builder asked in #1243. The lessons and their ids are public in `memory/lessons/` (GOV-0052), so nothing secret was at stake.

## Options considered

1. **Keep it out of the heartbeat.** The `given` episode is the record. GOV-0002 stays as it is. The dashboard can't show a session's lessons from its event stream.
2. **Add an optional `lessons` field (ids only) to `session_started`.** GOV-0002 gains a field; `heartbeat/SCHEMA.md` and `event.schema.json` change.
3. **Do nothing.** The spec line stays unbuilt and unrecorded.

## Deliberation

n/a (authoritative). The owner confirmed option 1 in a comment on #1243 and asked for a record.

## Consequences

- GOV-0002's field list stays closed, and GOV-0004 still holds.
- The dream reads `given` episodes for the given-not-used count.
- The Desk can't show a session's lessons from heartbeat events. If it needs to, it reads the episodes, or the owner rules on option 2 in a new question; adding the field later is a small change.
