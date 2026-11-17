# History

How AgentFleetOS got here: the versions before the current plan, with the issues and PRs behind each. [PRODUCT.md](../PRODUCT.md) says what the product is now. The open Goals on GitHub say what is happening now.

The product brief as it stood before it became an overview is [PRODUCT.md at 8fb86d5](https://github.com/open-agentos/agentfleetos/blob/8fb86d523fda89b3d8bad86e955929aefa763891/PRODUCT.md). That version has the department goal, its rulings (Q2 to Q5) and the operating model, with their issue numbers.

## v0 to v3

v0–v3 are the infrastructure the department goal stands on.

- **v0, swarm dashboard (done).** A heartbeat hook in every session records role, model, issue and rough cost (GOV-0002 to GOV-0004). The dashboard joins it with GitHub state to show each session, open PRs, `gov:question`s and spend.
- **v1, local launcher (done, GOV-0005).** `swarm.toml` lists roles, models and spend caps. `swarm up / ls / stop / launch` start and hand off sessions; `swarm inbox` is the ordered needs-you list; the reviewer runs by default. Caps only warn (GOV-0008).
- **v2, wake-up loop (done, GOV-0009).** `swarm watch` starts the right session on owner signals: `[review]`, `[build]`, `[record]`, `[answer]` and `[respond]`. Limits: GOV-0010 (interval, concurrency, caps), GOV-0011 and GOV-0021 (the bounded review loop), GOV-0012 (hard budget), GOV-0013 (headless permissions) and GOV-0014 (one-shot runs).
- **v3, evals, digest and Actions (in progress, GOV-0015).** Its stages are below.

## v3: evals, digest and Actions

GOV-0015 makes v3 three stages, in order: **B** quality evals, then **F** a phone-friendly "needs you" digest, then **C stage 1**, the reviewer running in GitHub Actions. C stage 2 (builders and docs in Actions) comes after these and is not planned. #526 defers C stage 2, except the lead's daily run if Q5 calls for it, and repurposes the digest as the daily report. The desk's v3 progress panel reads these tables.

### Stage B: evals (done)

B is read-only: it scores past PRs against a rubric and checks the reviewer against a bar for C stage 2 that the owner set.

| # | Issue | What | PR |
|---|---|---|---|
| B1 | #172 | Eval rubric and the pre-registered bar for C stage 2 (`evals/README.md`) | #197 |
| B2 | #173 | `evals/gather.py` picks the PR sample and gathers its issues, records and reviews | #181 |
| B3 | #174 | Score the sampled PRs against the rubric (`evals/results.md`) | #200 |
| B4 | #175 | Reviewer calibration and the result against the bar | #202 |
| B5 | #176 | `swarm cost` prints cost per merged PR from `watch.json` (local only) | #185 |

Result (`evals/results.md`, #202): **inconclusive, not passed.** The eval and the reviewer agreed on all 15 reviewed PRs, but the sample held no real defect, so the "misses" line of the bar wasn't tested. C stage 2 stays gated. The owner decides separately how to test whether the reviewer blocks a real defect.

### Stage F: needs-you digest

| # | Issue | What | PR |
|---|---|---|---|
| F1 | #210 | Needs you: flag `gov:question`s past their time to live | |
| F2 | #211 | `dashboard/digest.py`: render the needs-you list as phone-friendly Markdown | |
| F3 | #212 | `dashboard/digest.py --update`: keep the pinned digest issue current | |
| F4 | #213 | Digest workflow: propose `.github/workflows/digest.yml` for the owner to commit | |

### Stage C1: reviewer in Actions

| # | Issue | What | PR |
|---|---|---|---|
| C1.1 | #214 | `launcher/actions_review.py check`: should this PR event start a reviewer run? Retired by #262: the reconciler's `plan` replaced it | |
| C1.2 | #215 | `launcher/actions_review.py run`: one reviewer pass in Actions with GOV-0012, GOV-0013 and GOV-0014 limits | |
| C1.3 | #216 | `swarm watch`: a `review_in_actions` switch so the local loop leaves `[review]` to Actions | |
| C1.4 | #217 | Reviewer workflow: propose `.github/workflows/reviewer.yml` for the owner to commit | |
| C1.5 | #257 | Reconciler: `actions_review.py plan` lists the open PRs needing a review now (GOV-0020) | #269 |
| C1.6 | #258 | Reconciler: `plan` skips heads already in flight or already attempted, from the Actions run history | #275 |
| C1.7 | #259 | Reconciler workflow: the scheduled `reviewer.yml`, committed by the owner | #279 |
| C1.8 | #262 | Retire `actions_review.py check`; the launcher README and this brief describe the reconciler | |
| C1.9 | #260 | Reconciler switch-over: `review_in_actions` on locally; a bot PR reviewed by the reconciler alone | |

C1.5 to C1.9 are the reconciler (#255 stage 1, GOV-0020). Actions reviews now start from a sweep on `main` every 5 minutes, not from PR events, so one can lag a push by a few minutes or more. To review a PR now, or retry a failed one, the owner dispatches the workflow with its number (`gh workflow run reviewer.yml -f pr=N`). To fall back to local reviews, set `review_in_actions = false` and run `swarm watch` (`launcher/README.md`). #261 (PR pushes nudge an early sweep) is optional and comes after.

Order: B → F → C stage 1. C stage 2 is not planned.

v3's decisions are in GOV-0016 to GOV-0020 and GOV-0024 (the Actions reviewer's log, triggers, App key, workflow, reconciler and trusted authors). #208 (the model credential for Actions runs) is open; the owner's direction on it is a Claude subscription token for now. Workflow files stay the owner's: the swarm proposes them, and the owner commits them.
