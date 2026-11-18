---
id: GOV-0059
title: Add a librarian role with its own App, a model different from the planner's, and a lane limited to `memory/`
status: in-force
kind: ruling
question: "#1148"
domain: governance
shape: authoritative
classification:
  reversibility: costly
  blast_radius: repo
  nature: preference
  knowledge: shared
decided_by: humans.owner
ratified_by: humans.owner
date: 2026-11-17
review_by: 2027-02-28
supersedes: []
applies_to:
  paths: ["roles/librarian.md", "memory/**"]
  roles: [librarian]
  situations:
    - adding or changing the librarian role, its App, model or jurisdiction
    - deciding which role distils lessons into `memory/`
---

## Ruling

Add a **librarian** role (GOV-0032). It writes only under `memory/` (the public part, per #1147) and opens one PR a night. It never edits `governance/`, `roles/`, `jurisdictions.yml` or the owner model; it proposes changes to those in its dream report. It runs on a different model family or tier from the planner (for example Sonnet, while the planner runs on Opus) and acts as its own App, `productswarm-librarian`.

## Applies when / does not apply when

- Applies when: the librarian role, its App, model or lane is being set up or changed.
- Does not apply when: the choice is how the nightly run works inside `memory/` (FEAT-16).

## Context

GOV-0032 adds "a new librarian role on a different model from the lead", and FEAT-16 specifies it. No record set its App, model or jurisdiction. The owner answered on #1148: "Option 1 confirmed", `Record: yes`. See #1148 for the full options and the steps the owner takes.

## Options considered

1. **A new librarian role** with its own App, limited to `memory/`: chosen. One narrow lane that is easy to review and stop; model diversity; every memory change traceable to it.
2. **The analyst does it**: no new App, but the analyst distils its own research, and "different model from the lead" holds only while `swarm.toml` keeps the analyst and planner on different models.
3. **The planner does it**: the lead would grade its own team's work and lessons, which GOV-0032 avoided on purpose.
4. **Do nothing**: no learning loop.

## Deliberation

n/a (authoritative; the owner decided on #1148).

## Consequences

- The owner takes these steps; agents do not: create the `productswarm-librarian` App; add `librarian` to `identities.agents` in `jurisdictions.yml` (which per GOV-0024 also makes it a trusted author for the Actions reviewer); give the lane either a `memory` domain where the librarian alone holds `decide` or no `decide` and a limit in `roles/librarian.md`; merge `roles/librarian.md` and its `swarm.toml` `[[session]]` with a `spend_cap_usd` (GOV-0010).
- Until then, FEAT-16's by-hand runs use the analyst role under its existing App, writing only to `memory/`, with the planner starting each run (the default action on #1148).
- GOV-0012 and GOV-0013 run limits apply to it as to any role.
- Revisit if the librarian's PRs show it needs to write outside `memory/`.
