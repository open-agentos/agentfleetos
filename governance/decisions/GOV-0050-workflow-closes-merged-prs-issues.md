---
id: GOV-0050
title: A workflow closes a merged PR's linked issues at merge time; the merger keeps `issues: read`
status: in-force
kind: ruling
question: "#1109"
domain: security
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
  paths: [".github/workflows/close-linked-issues.yml", "roles/planner.md"]
  roles: [planner]
  situations:
    - an issue stays open after the merger App merged the PR that closes it
    - building or changing how merged PRs' closing issues get closed
    - proposing `issues: write` or any other issue right for the merger App
---

## Ruling

A workflow, `.github/workflows/close-linked-issues.yml`, closes a PR's still-open closing issues in this repo as soon as the PR merges into `main`. It uses the workflow's own `GITHUB_TOKEN`, with `issues: write` for that one job. The merger App keeps `issues: read` (GOV-0028 unchanged). The planner's daily sweep (GOV-0041) stays, as a backstop for anything the workflow misses. This amends GOV-0041, which stays in force.

## Applies when / does not apply when

- Applies when: a PR merges into `main` with closing issues still open in this repo, whoever merged it.
- Does not apply when: the closing issue is in another repo. The workflow's token can't write there; the planner's sweep and GitHub's own close still cover it.
- Does not apply when: an issue was reopened after its PR merged. The workflow runs once, at merge, so it never closes it again.

## Context

GOV-0041 chose to have the planner close these issues in its daily run, so the merger's key gains no issue right. In practice the sweep missed them: on 2026-11-17 six issues were still open after merger merges, the oldest from 2026-11-13 (#991, #992, #1007, #1021, #1075, #1083), and the owner found open issues that should have been closed confusing. GOV-0041 asks to be revisited "if the planner's sweep misses issues". The owner chose this fix in #1109.

## Options considered

1. **Grant the merger `issues: write`** (GOV-0041 option 1): fixes it at merge time, but the merger's key could then edit, label and close any issue, including `ready` and `gov:ruled`.
2. **A workflow closes them with its own token** (chosen): fixes it at merge time; the token lives only for that job, runs main's copy of the file with no PR code, and only closes the PR's own closing issues.
3. **Keep only the planner's sweep** (GOV-0041 as is): issues stay open for a day or more, and longer when the daily run misses them.

## Deliberation

n/a. This is an authoritative decision by the owner on #1109.

## Consequences

- A merger merge closes its linked issues within about a minute. Go and blocked-by checks (GOV-0031) stop seeing them open.
- The workflow's `GITHUB_TOKEN` can write issues during that job. It runs from `main` under `pull_request_target`, checks nothing out and runs no PR code.
- Issues the workflow closes start no workflows, since GitHub doesn't start workflows from `GITHUB_TOKEN` actions. `digest-nudge.yml` listens for `issues: closed`, so it won't fire for these closes; it already fires on the PR's own `closed` event, and the digest may show the issue open until its next run.
- The planner's daily step from GOV-0041 normally finds nothing to close. It stays, and still lists what it closes in its report.
