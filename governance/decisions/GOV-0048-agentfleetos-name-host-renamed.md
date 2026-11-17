---
id: GOV-0048
title: The product, the repo and the engine host's units and paths are named AgentFleetOS; env vars, bot identities and markers stay
status: in-force
kind: ruling
question: "#1063"
domain: external
shape: authoritative
classification:
  reversibility: costly
  blast_radius: external
  nature: preference
  knowledge: held
decided_by: owner (mattmcalister), on #1063
ratified_by: humans.owner
date: 2026-11-17
review_by: 2027-02-28
supersedes: [GOV-0047]
applies_to:
  paths: ["ops/vps/"]
  roles: []
  situations:
    - writing the product's name in prose, UI text, openers or docstrings
    - writing or reading this repo's `owner/name` slug in code, config or tests
    - writing an engine host unit name, checkout path, state path or secrets path
    - touching a name that still says productswarm and deciding whether to change it
---

## Ruling

GOV-0047 stands, except for the engine host. The product is **AgentFleetOS**, and this repo is **`open-agentos/agentfleetos`**. In identifiers, paths and slugs, use lowercase `agentfleetos`. Agents change the product's name in prose and UI text, and the repo slug in code, config and tests, from productswarm to the new name.

The engine host now uses the new name too. The owner renamed it on 2026-11-17:

| Was | Is |
|---|---|
| `productswarm-{webhooks,watch,desk,backup}` units and `productswarm-backup.timer` | `agentfleetos-*` |
| `/home/swarm/productswarm` (checkout) | `/home/swarm/agentfleetos` |
| `/home/swarm/.productswarm` (state) | `/home/swarm/.agentfleetos`, with `.productswarm` left as a link to it |
| `/etc/productswarm` (secrets) | `/etc/agentfleetos` |

`ops/vps/` describes the host as it is, with the new names.

These keep their current names: the GitHub App identities `productswarm-<role>[bot]` and everything that matches them, hidden issue markers (`<!-- productswarm-… -->`), `productswarm-scratch`, the Notion integration and its page, the environment variables (`PRODUCTSWARM_HOME`, `PRODUCTSWARM_REPO`, `PRODUCTSWARM_APPS_DIR`) and the defaults the code falls back to (`~/.productswarm`, `~/.config/productswarm`), and historical records. The host's units set `PRODUCTSWARM_HOME=/home/swarm/.agentfleetos`.

## Applies when / does not apply when

- Applies when:
  - writing or editing text that names the product (READMEs, `PRODUCT.md`, `CLAUDE.md`, `roles/`, Desk page titles, launcher openers, docstrings, schema titles);
  - writing the slug `open-agentos/productswarm` in code, config or tests;
  - writing a host unit name or path in `ops/vps/` or in docs that describe the host.
- Does not apply when the name is any of these:
  - a bot identity, or a pattern, trust list or workflow that matches one;
  - a hidden marker that live issues carry;
  - an environment variable, or the `~/.productswarm` and `~/.config/productswarm` defaults in code. Renaming those changes the owner's Mac and the host together and needs its own question;
  - the scratch repo or the Notion integration;
  - a historical record: `governance/decisions/` and their INDEX lines, `research/`, `evals/results.md`, `evals/drills.md`, `heartbeat/examples/`, and everything under `classify/` (changing labelled text or the labelset prompt changes its hashes);
  - text in a closed issue or merged PR.

  Code that parses text the old name wrote, such as the launcher reading `for productswarm` back from a running session's command line, accepts both names.

## Context

GOV-0047 (#1042) renamed the product and the repo, and kept host paths, env vars and units under their old names. The owner then renamed the host's units and paths on 2026-11-17, while fixing the Desk. Its unit still searched `open-agentos/productswarm`, and GitHub's search API doesn't follow repo redirects, so the Desk had not published since the rename. GOV-0047 no longer described the host, and an agent following it could put the old names back. Raised as #1063.

## Options considered

1. **Record the host rename and keep the env vars.** Matches the host as it is. The env var names and code defaults don't change, so no code or Mac change is needed. Chosen.
2. **Also rename the env vars and code defaults.** This needs a coordinated change to `launcher/`, `heartbeat/`, `ops/`, the owner's Mac and the host, plus a migration of `~/.productswarm` on the Mac. It is the most risk, for names only the owner sees.
3. **Revert the host to the old names.** This brings back what GOV-0047 said, but undoes work already done and verified.

## Deliberation

n/a (authoritative). The owner made the host change and asked for the record to match it.

## Consequences

`ops/vps/` and the host agree on the new names, so re-provisioning from `ops/vps/` gives the same layout. `PRODUCTSWARM_HOME` names a folder called `.agentfleetos` on the host, which is accepted. The link from `.productswarm` keeps commands run by hand as `swarm` on the same state. Revisit when the env vars are renamed, or if the link causes confusion.
