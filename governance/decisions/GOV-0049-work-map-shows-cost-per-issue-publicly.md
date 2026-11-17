---
id: GOV-0049
title: The Desk's Work map may show cost per issue on both public Desks, sized by Cost by default
status: in-force
kind: ruling
question: "#1075"
domain: security
shape: authoritative
classification:
  reversibility: two-way
  blast_radius: external
  nature: values
  knowledge: shared
decided_by: humans.owner
ratified_by: humans.owner
date: 2026-11-17
review_by: 2026-12-15
supersedes: []
applies_to:
  paths: []
  roles: []
  situations:
    - building or changing the Desk's Work map (FEAT-8 to FEAT-11)
    - deciding whether a public Desk page may show cost for one issue
    - choosing the Work map's default size
---

## Ruling

The Work map may show cost per issue, priced with `dashboard/spend.py`, on both the GitHub Pages Desk and the live Desk, and sizes by Cost by default. It shows each issue's cost and its share of what is on screen, and never sums cost into a total (GOV-0033).

## Applies when / does not apply when

- Applies when: building or changing the Work map's per-issue cost, its size options, or the public data that feeds them.
- Does not apply when: showing session cost, daily spend, a cap, an over-cap flag or any spend total, or putting cost on another Desk page, which is a new `security` question.

## Context

The owner is planning a Work map for the Desk: a treemap of open issues sized by cost and shaded by what that spend returned (Notion, Work map initiative, FEAT-8 to FEAT-11). The Desk shows no cost today, and the dashboard README says the public `state.json` carries no cost (GOV-0014, #397). Both Desks are public. The inputs are already public: each heartbeat comment carries `model`, `issue` and cumulative `token_counts`, so anyone can work out per-issue cost from the published price list. GOV-0033 bars engine spend totals, not per-issue figures. #1075 asked whether per-issue cost may be shown on a public page. The owner answered "Option 1 confirmed. Record: yes" in a comment on #1075.

## Options considered

1. **Show cost on both Desks** (chosen): size defaults to Cost everywhere; the page publishes a figure already derivable from public heartbeat comments.
2. **Show cost only on the live Desk, after Google login:** public builds default to Tokens; cost stays in local `swarm map` until there is access control.
3. **Do nothing:** no cost on any Desk; the Work map sizes by Tokens or Lines only.

## Deliberation

n/a. This is an authoritative decision by the owner, who confirmed option 1, the question's recommendation.

## Consequences

- The Work map may default to Cost on both Desks.
- The question's recommendation said this record should also amend the "no cost" line in `dashboard/README.md` (line 156) so later panels aren't confused. That edit is left to the PR that ships the Work map, so the README stays accurate until cost is shown.
- Showing session cost, daily spend, a cap, an over-cap flag or totals is outside this ruling. Each would be a new `security` question; this record neither allows nor bars them.
- The team accepts publishing per-issue cost in ready-made form. The owner can revert by switching the default size to Tokens.
- Expires on 2026-12-15 (the question's time to live) unless re-affirmed.
