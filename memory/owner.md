# The owner model

How the owner likes the team to work: preferences (style, format, what to leave out), standing patterns (what the owner reliably approves or rejects), vocabulary and don'ts. These are preferences, not rules. They never outrank a ruling.

- **Public.** This file is public (GOV-0052), so it holds working preferences only. Nothing about the owner's health, family, finances, contacts or whereabouts, and nothing the owner hasn't approved. `launcher/swarm memory owner --check` rejects an entry that carries personal data.
- **Who changes it.** Every change needs the owner's approval as an approved ask (GOV-0056). The merger treats this file as a protected path. The librarian proposes entries in its dream report and never edits this file (GOV-0059). The owner seeds it by hand, approving each line, and can edit it directly.
- **Who sees it.** The planner gets every entry. Every other role gets only the entries whose `roles` name it, so an entry with no roles reaches the planner alone (GOV-0056). `launcher/swarm memory owner --role <role>` prints a role's part.
- **Vetoes.** `launcher/swarm memory owner veto O-NNNN` moves an entry under Vetoed with today's date. For 30 days after that, the dream doesn't propose an entry like it again.

An entry looks like this (`kind` is `preference`, `pattern`, `vocabulary` or `dont`; `sources` are episode ids, `#N`, `owner/name#N` or github.com links):

    ### O-0001: Plain words in reports
    - kind: preference
    - roles: docs, analyst
    - sources: #1150
    - date: 2026-11-18

    One or two sentences saying the preference.

A veto looks like `- O-0002, 2026-11-18: the vetoed entry's words`.

## Entries

## Vetoed
