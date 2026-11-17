# AgentFleetOS

**Run a team of AI agents the way you run a department.** You set the direction and the team does the work. You hear back without checking on it. You step in only where you choose to.

This brief says what AgentFleetOS is, who it's for and how it works. It changes when the product's direction changes, not when work moves. For what's happening now, see [Where things stand](#where-things-stand).

## Problem

AI coding agents can do real work, but running several of them still means doing the manager's job by hand. Someone has to say what to work on, start each session, check what each one is doing, judge its output and merge it. They also have to remember why each decision was made. The agents speed up, but the person directing them becomes the bottleneck, and most of their attention goes to process rather than to the product.

A department head doesn't work like that. They set goals, delegate authority, get reports and step in on exceptions. AgentFleetOS gives one person that relationship with a team of agents.

## Users

- **Now: the owner,** who runs one product with an agent team and acts as its C-team.
- **Next: consultants** who deliver software for clients with agent teams, and need to run several fleets and show clients what was done and why.
- **Later: their clients,** who want private reports on the work done for them. Design for them, but don't build for them yet.

## What it is

AgentFleetOS is a swarm of agent sessions with roles, plus the tools to direct, watch and govern them. GitHub is the system of record.

- **Roles.** Each session has one role:
  - the **planner**, who is the team's lead;
  - **builder**, **reviewer**, **docs**, **designer** and **analyst**.

  Each role acts on GitHub as its own App, and everything it writes records which model wrote it. A separate **merger** App merges a PR only when the rules allow it.
- **The plan.** The owner's open Goals and Areas on GitHub, and the issues under them. A Goal is an outcome with a done test. An Area is ongoing work to keep healthy. Work that sits under the plan can go ahead without the owner approving each issue.
- **Governance.** `GOVERNANCE.md` says who may decide what. `governance/jurisdictions.yml` lists each role's domains. Decisions that aren't a role's to make become questions for the owner, and the answers become rulings in `governance/decisions/`. Governance isn't the product, but it's what lets agents act without asking every time.
- **The engine.** `swarm watch` starts the right session when something needs doing: a PR to review, an issue to build, a ruling to record, a report to write. It runs on the owner's Mac or on a small host, with a spend cap on each run.
- **The Desk.** A read-only web page with the owner's view: what the team is doing, where the plan stands, what waits on the owner, and where the money goes.
- **Integrations.** Specs can come from the owner's own tools, starting with Notion. They come in as issues and report their status back ([docs/integrations/](docs/integrations/README.md)).

## Operating model

**One lead reports to the owner.** The planner keeps the plan with the owner, turns it into small issues, runs the other roles and reports back. The owner can also talk to any role directly.

| Habit | What happens |
|---|---|
| **The plan** | The owner opens, edits and closes Goals and Areas. The lead proposes changes to them and plans the work within them. |
| **Daily report and briefing** | Every working day the lead writes a report and a short briefing. The report covers what was done against the plan, what's next, risks, what agents did on the owner's authority, and a few asks. The briefing tells the owner where things stand in plain words. |
| **Weekly check-in** | For each Goal and Area: moved, at risk or slipped; what changes; and what the lead needs. |
| **Delegated authority** | Standing grants say what roles may do without asking. A role asks for anything beyond them, and the owner's approval lets it act on the owner's authority. Every use is reported. |
| **One-on-ones** | The owner asks one role a question, and that role answers in plain words. |
| **Call-ins** | The lead calls in several roles on one problem, and folds their answer into the plan. |
| **Research** | The analyst researches what the plan needs and keeps the record in `research/`. |
| **Review and merge** | The reviewer checks each PR against its issue and the rules. The merger merges a PR when the rules allow it. Everything else waits for the owner. |

**What the owner keeps:**
- setting direction: opening, editing and closing Goals and Areas;
- granting authority and approving asks;
- answering governance questions;
- approving changes to protected paths (`governance/`, `ops/`, workflows);
- choosing what leaves their own tools, such as marking a spec Ready.

## Principles

- **Command first.** Every read and every act is a `swarm` command before it is a page, a comment or a button. The Desk and any later interface are thin layers over those commands.
- **By hand twice, then automate.** A ritual runs manually at least twice before anything is built to run it.
- **Small, reviewable steps.** One issue, one PR. Each PR closes exactly one issue under the plan.
- **Decisions on the record.** A choice that sets a pattern gets a decision record. Only merged records are rulings, never a comment or a chat.
- **Honest numbers.** The Desk shows where effort and spend go, per piece of work. It doesn't invent totals or targets the owner hasn't set.
- **Readable by anyone.** Plain words, no meaning carried by colour alone, and layouts that don't move under you.

## Not doing

- **Governance as the product.** It's the infrastructure that lets agents act alone.
- **A hosted service (SaaS).** AgentFleetOS runs on the owner's GitHub, Mac and host.
- **A second user before the first outside project's readiness review.**
- **Agents merging their own work outside the rules,** or changing `GOVERNANCE.md`, `jurisdictions.yml` or workflows without the owner.

## Where things stand

This brief doesn't track progress. These do:

- **The plan:** the open Goal and Area issues on the AgentFleetOS Project Board.
- **Today:** the Desk, and the daily report on the pinned report issue.
- **Rulings:** [governance/INDEX.md](governance/INDEX.md).
- **How we got here:** [docs/history.md](docs/history.md), and the closed Goals on GitHub.
- **How to use it:** [README.md](README.md) and each component's README.
