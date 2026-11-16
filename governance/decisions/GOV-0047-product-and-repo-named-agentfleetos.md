---
id: GOV-0047
title: The product and the repo are named AgentFleetOS; the productswarm-* bot identities stay
status: in-force
kind: ruling
question: "#1042"
domain: external
shape: authoritative
classification:
  reversibility: costly
  blast_radius: external
  nature: preference
  knowledge: held
decided_by: owner (mattmcalister), on #1042
ratified_by: humans.owner
date: 2026-11-16
review_by: 2027-02-28
supersedes: []
applies_to:
  paths: []
  roles: []
  situations:
    - writing the product's name in prose, UI text, openers or docstrings
    - writing or reading this repo's `owner/name` slug in code, config or tests
    - touching a name that still says productswarm and deciding whether to change it
---

## Ruling

The product is **AgentFleetOS**, and this repo is **`open-agentos/agentfleetos`**. In identifiers, paths and slugs, use lowercase `agentfleetos`. The owner renames the repo on GitHub once this record merges. After that, agents change the product's name in prose and UI text, and the repo slug in code, config and tests, from productswarm to the new name.

These keep their current names: the GitHub App identities `productswarm-<role>[bot]` and everything that matches them, hidden issue markers (`<!-- productswarm-… -->`), `productswarm-scratch`, the Notion integration and its page, host paths, env vars and units (`~/.productswarm`, `PRODUCTSWARM_HOME`, `ops/`), and historical records.

## Applies when / does not apply when

- Applies when: writing or editing text that names the product (READMEs, `PRODUCT.md`, `CLAUDE.md`, `roles/`, Desk page titles, launcher openers, docstrings, schema titles), or the slug `open-agentos/productswarm` in code, config or tests.
- Does not apply when: the name is any of these:
  - a bot identity, or a pattern, trust list or workflow that matches one;
  - a hidden marker that live issues carry;
  - a host path, env var, systemd unit or anything in `ops/` (the owner's, in a separate change);
  - the scratch repo or the Notion integration;
  - a historical record: `governance/decisions/` and their INDEX lines, `research/`, `evals/results.md`, `evals/drills.md`, `heartbeat/examples/`, and everything under `classify/` (changing labelled text or the labelset prompt changes its hashes);
  - text in a closed issue or merged PR.

  Code that parses text the old name wrote, such as the launcher reading `for productswarm` back from a running session's command line, accepts both names.

## Context

The engine host serves at agentfleetos.app (#687), and the owner wants the product and the repo to match it. "productswarm" appears about 680 times in 120 files. Most are bot identities, host names, markers or history, not the product's name in prose. Raised as #1042.

## Options considered

1. **Rename the product and the repo, and leave the bot identities.** Prose, UI text and the slug change, and nothing that identifies a running App or a live issue does. Chosen.
2. **Rename everything, bot Apps included.** This needs new App registrations and changes to the trust list (GOV-0024), the merger (GOV-0028) and workflows. It is the most risk for the least visible gain.
3. **Do nothing.** The domain and the repo keep different names.

## Deliberation

n/a (authoritative). The owner chose Option 1 and asked that the bot identities stay.

## Consequences

The repo slug changes. GitHub redirects old URLs, API calls and git remotes, so nothing breaks at the rename. Agents update the slug in code and tests as ordinary work. The owner updates local and host remotes, and renames host paths, env vars and units in a separate change. Bots keep posting as `productswarm-<role>[bot]`, so the old name stays visible on GitHub. That is accepted. Revisit if the App names cause confusion, or if a new App is registered anyway.
