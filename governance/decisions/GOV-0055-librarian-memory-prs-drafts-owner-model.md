---
id: GOV-0055
title: Memory-only PRs merge under the standing grant; the librarian drafts gov:questions without a weekly cap; the owner model goes in full to the planner only
status: in-force
kind: ruling
question: "#1150"
domain: governance
shape: authoritative
classification:
  reversibility: two-way
  blast_radius: repo
  nature: values
  knowledge: shared
decided_by: humans.owner
ratified_by: humans.owner
date: 2026-11-17
review_by: 2027-02-28
supersedes: []
applies_to:
  paths: ["memory/**"]
  roles: [librarian, planner, merger]
  situations:
    - the librarian opens a PR that touches only `memory/`
    - the librarian sees a pattern in its dream and wonders whether to open a gov:question
    - a role other than the planner needs to read the owner model
    - someone proposes a change to the owner model
---

## Ruling

1. **Memory PRs.** A PR from the librarian that touches only `memory/` falls under the standing grant like any other go PR: the merger may merge it under GOV-0027 and GOV-0034 once the reviewer approved it at head, `tests` pass, there is no overstep and no protected path, and it is under the size limit. This widens GOV-0022's author condition (`productswarm-builder[bot]`) to the librarian for PRs that touch only `memory/`. Lesson files stay off the protected paths.
2. **Drafting questions.** The librarian may open draft `gov:question`s when its dream sees a pattern (FEAT-21): the same answer three times, a confirmed lesson outside a role's jurisdiction, a lesson that conflicts with a ruling, or an uncited ruling near its `review_by`. There is **no weekly cap**. They are batched for the Monday check-in. Each carries options, a default and evidence, and only a lesson that is active, rehearsed, two-source and at least 14 days old may escalate.
3. **The owner model.** It goes in full to the planner. Every other role gets only the entries tagged for it. Every change to it needs the owner's approval, as an approved ask.

## Applies when / does not apply when

- Applies when: the PR's changed files are all under `memory/`, and its author is the librarian.
- Does not apply when: a PR touches anything outside `memory/`. It goes the usual way: builder authors under GOV-0022, any other author waits for the owner.
- Does not apply when: a question would be raised from a lesson that doesn't meet the maturity rules in 2. Those stay in the dream report.
- Does not apply to adopting anything a draft proposes. Only merged records are rulings (GOV-0006).

## Context

The Learning loop specs (FEAT-14 to FEAT-22) have the librarian merge one memory PR a night, draft questions when it sees a pattern, and keep an owner model. Today the merger merges only builder-authored PRs (GOV-0022, kept by GOV-0027 and GOV-0034), and a role opens a `gov:question` only for a choice in its own task. The planner asked in #1150. The owner answered there: "Option 1 with no specific cap on draft gov:questions a week", with `Record: yes`.

## Options considered

1. **Narrow grants** (chosen, without the cap): memory PRs merge under the standing grant, the librarian drafts questions under maturity rules, and the owner model is split by role.
2. **Every memory PR waits for the owner:** safest, but adds an owner act a night.
3. **No escalation drafts:** patterns stay in the dream report for the planner to raise; fewer questions, but the evidence is lost in the hand-off.
4. **Wider:** no weekly cap and the owner model in full to every role.

## Deliberation

n/a. This is an authoritative decision by the owner on #1150.

## Consequences

- `launcher/merger.py` needs a rule that accepts the librarian as author when every changed file is under `memory/`. That is a separate issue, and until it lands the merger still skips librarian PRs.
- With no cap, draft questions can pile up. The maturity rules and the Monday batching are the limits; if the owner finds the volume too high, a cap needs a new question.
- The owner model's tags and the approved-ask step need building in the learning-loop work.
- Revisit if a memory PR merges something that should have waited, or when `review_by` passes.
