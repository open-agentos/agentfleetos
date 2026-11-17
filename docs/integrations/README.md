# Integrations

How to connect AgentFleetOS to the tools around it. Each guide covers one-time setup, day-to-day use and what to do when something fails.

| Integration | What it does | Guide |
|---|---|---|
| Notion | Specs you write in Notion become issues the swarm builds, and their status and PR links come back to Notion | [notion.md](notion.md) |

Every integration follows the same rules:

- **A `swarm` command does the work.** The integration is a backend behind that command, so the swarm never depends on the tool directly. For specs, that command is `swarm specs`, and the backend is picked in `swarm.toml`'s `[specs]` table (GOV-0042).
- **Credentials stay on the owner's machine.** They are kept in a private file that only the command reads. They are never put in `swarm.toml`, the environment or an agent's session (GOV-0043 for Notion).
- **The owner decides what leaves the tool.** Nothing is published until the owner marks it ready.
