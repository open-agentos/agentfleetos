# How to ship specs from Notion

You write a spec in Notion and mark it Ready. The swarm turns it into issues under a Goal, builds them, reviews them and merges them. Each feature's status and PR link come back to Notion without you copying anything.

```
Notion                          swarm specs                  GitHub
Initiative (the PRD)  ──┐
Feature (a spec), Ready ┼─ pull ──────────────────────▶  sub-issues under your Goal
                        │                                  │ planner orders, builders build,
                        │                                  │ reviewer reviews, merger merges
Status, Issue, PR  ◀────┴─ push ◀──────────────────────────┘
Spec edited later  ──────── diff ─▶ the lead adopts, defers or asks you
```

The code is `launcher/specs/` (GOV-0042). The token rules are GOV-0043.

## One-time setup

You need to own both the Notion workspace and the GitHub repo. Allow about 15 minutes.

### 1. Create the integration in Notion

1. Go to **Settings › Connections › Develop or manage integrations**, and create an **internal** integration named `productswarm`.
2. Give it only these capabilities:
   - Read content
   - Update content
   - Read comments
   - Insert comments

   Leave **Insert content** and **user information** off. The bridge refuses any call outside these, and it never writes a page body.
3. Copy the integration's secret.

### 2. Save the token

```bash
mkdir -p ~/.config/productswarm
pbpaste > ~/.config/productswarm/notion.token
chmod 600 ~/.config/productswarm/notion.token
```

Only `swarm specs` reads this file, and only at the moment it runs. If the file's mode is looser than `600`, or the file is a symlink or empty, the command refuses to run. There's no fallback to an environment variable, and the token never goes to an agent session or to the engine host.

### 3. Make the specs page

Create one page. Ours is "AgentFleetOS specs". Put two full-page databases under it, named exactly **Initiatives** and **Features**. The bridge checks their properties and stops if any is missing or has the wrong type. It never creates or changes them.

**Initiatives:** one row per PRD.

| Property | Type | Values |
|---|---|---|
| Name | Title | |
| Goal | URL | the GitHub Goal's URL, which you add later |
| Status | Status | Planned, Active, Done |

**Features:** one row per spec, each about one PR's worth of work.

| Property | Type | Values |
|---|---|---|
| Name | Title | |
| ID | Unique ID | prefix `FEAT`, so rows read FEAT-1, FEAT-2 and so on |
| Initiative | Relation | to Initiatives. Each feature has exactly one. |
| Status | Status | Draft, Ready, In progress, In review, Blocked, Shipped |
| Issue | URL | written by the bridge |
| PR | URL | written by the bridge |
| Last synced | Date | written by the bridge |

You can add other properties, such as a Repo text field or a rollup. The bridge ignores them.

### 4. Share the page with the integration

On the specs page, open **⋯ › Connections** and add `productswarm`. Share only this page. The databases under it are shared with it.

### 5. Point `swarm.toml` at the page

```toml
[specs]
backend = "notion"
parent_page = "<the specs page's id>"
```

The id is the 32 hex characters at the end of the page's URL. Dashes are optional.

## Writing specs

### The Initiative is the PRD

The page body is free text. Say what the initiative is, why it matters, who it's for, when it's done, the order of its features, and any rulings it needs. Leave **Goal** empty and **Status** on Planned until the Goal exists.

### Each Feature is one spec

The body uses exactly these five headings, in this order, and no others:

- `## Problem`: what's wrong or missing, and for whom.
- `## Scope`: what to build, specific enough to build from.
- `## Out of scope`: what not to build, including the neighbouring features.
- `## Acceptance criteria`: a to-do list (`- [ ]`). Each item is something a reviewer can check.
- `## Notes`: hints, links and dependencies.

Any other heading stops the pull with "unknown spec heading(s)". If you need structure inside a section, use bold text or lists.

Write each spec for an agent that has read nothing else. Builders and the reviewer read only the snapshot copied into the issue, never Notion. A link to a private page, or a mock-up only you can open, gives them nothing, so put what matters into the text.

### Draft and Ready

New features start in **Draft**, and drafts never leave Notion. **Moving a feature to Ready publishes it**: its spec is copied into a public GitHub issue (GOV-0043). Only you move a feature to Draft or Ready. The bridge writes the other four statuses.

## Shipping an initiative

1. **Open a Goal on GitHub.** Open it as yourself, with issue type **Goal** and no labels. Put these two lines anywhere in its body:

   ```
   Spec source: notion://<the Initiative page's id>
   Repo: open-agentos/agentfleetos
   ```

   `Repo:` is the repo the sub-issues go in. Use the repo's current name. GitHub redirects most calls after a rename, but not search.
2. **Link the Initiative back.** Paste the Goal's URL into the Initiative's **Goal** property and set its Status to **Active**.
3. **Move its features to Ready.**
4. **Pull,** first as a dry run:

   ```bash
   launcher/swarm specs pull 1080 --dry-run
   launcher/swarm specs pull 1080
   ```

   The argument is the Goal: `1080`, `#1080` or `owner/name#1080`. For each Ready feature, the pull opens one sub-issue under the Goal with a dated, hashed snapshot of the spec, and writes the issue's link into the feature. Running it again is safe. A feature that already has an Issue link is reported, not pulled again.
5. **The swarm builds it.** The planner orders the sub-issues, builders build from the snapshots, and the reviewer and merger take each PR through as usual.
6. **Push status back to Notion:**

   ```bash
   launcher/swarm specs push 1080
   launcher/swarm specs push 1080 --what-shipped "FEAT-8=swarm map now prices every issue's spend."
   ```

   Push sets each feature's status from its issue and PR:

   | On GitHub | Status in Notion |
   |---|---|
   | Issue open, no PR | In progress |
   | PR open | In review, with the PR link |
   | PR merged and issue closed | Shipped, with the PR link |
   | Issue closed with no merged PR, or a `hold` label | Blocked, with a reason |

   It also posts one comment per merged PR on the feature. The comment's text comes from the lead's `--what-shipped` paragraph. A merge without that paragraph gets no comment yet. Push only changes what differs, so it's safe to run again. `--dry-run` shows what it would write.

### When you edit a spec after it's pulled

```bash
launcher/swarm specs diff            # every open Goal with a Spec source line
launcher/swarm specs diff 1080       # one Goal
```

`diff` lists the features you've edited in Notion since their snapshot was taken. For each one, the lead decides:

- `--adopt FEAT-n`: replace the snapshot (open issue) or open a new sub-issue (closed issue);
- `--defer FEAT-n`: open a follow-up sub-issue that waits on the current one;
- `--ask FEAT-n`: put the question in the lead's report, writing nothing on GitHub.

Until then, the swarm keeps building from the old snapshot.

## When something goes wrong

| Message | What to do |
|---|---|
| `the following arguments are required: goal` | Name the Goal: `swarm specs pull 1080`. |
| `#N has no 'Spec source: <backend>://<initiative id>' line` | Add the `Spec source:` line to the Goal's body (step 1). |
| `#N isn't a Goal` / `isn't open` | Set the issue's type to Goal, or reopen it. |
| `#N was opened by …, not the owner` | Only Goals you opened can pull. Open a new Goal yourself. |
| `#N's body was edited by …, not only the owner` | Someone else edited the Goal's body. Open a fresh Goal, or have the edit removed from its history. |
| `unknown spec heading(s): …` | A feature uses a heading outside the five. Rename it or make it bold text. |
| A schema error naming Initiatives or Features | A database, property, type or status option doesn't match the tables above. Fix it in Notion. The bridge never changes it for you. |
| The token is refused | Check the file exists, isn't empty, isn't a symlink, and has mode `600`. |
| A feature you expected isn't pulled | It isn't Ready, it belongs to a different Initiative, or it already has an Issue link. |

## What the integration can and can't do

- **Reads** both databases, every feature's page body and its comments.
- **Writes** only a feature's Status (In progress, In review, Shipped, Blocked), Issue, PR and Last synced, plus one delivery comment per merged PR.
- **Never** writes a page body, creates or changes a database, or reads anything not shared with it.
- **Makes no model calls.** The lead writes the "what shipped" text and passes it in.
- **Runs only on your machine,** because the token lives there. The engine host doesn't pull or push yet.
