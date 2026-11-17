# Swarm dashboard

Read-only pages showing what every agent session is doing and how the swarm is governed: three of them, the [Work map](#the-work-map), [Crew](#crew) and [Governance](#governance-page), joined by one nav (#1113). Built by `generate.py`: Python stdlib only, static HTML files. Crew and Governance load one small script that [refreshes their panels](#live-refresh) from `state.json` (option 2 of gov question #396, which reversed #26's "no JavaScript"), and the Work map one that draws its treemap; Effort's drill-down loads none. Each script is a same-origin file in `js/` beside the pages, allowed by its hash (#1106, option 3 of #1102). Every page but the Work map's treemap is complete with JavaScript off.

## Generate it

```bash
python3 dashboard/generate.py            # writes dashboard/out/ (git-ignored)
open dashboard/out/workmap.html
```

Options: `--repo owner/name` (default: this checkout's `origin`), `--out PATH` (`index.html`, which sends the browser to the Work map; the pages, `fonts/` and `js/` are written beside it), `--days N` (include sessions that stopped in the last N days, default 14), `--idle-minutes N` (default 15).

It reads GitHub through `gh api`, so inside a swarm session it acts as the role's App.

## Pages

One build writes three pages, and the fonts, into the `--out` page's directory, joined by one nav on every page, **Map · Crew · Governance** (#1113, which merged seven pages from two generations):

| Page | What it shows |
|---|---|
| `workmap.html`, the **Work map** | The owner's home, served at `/` on the live Desk (#1082): a treemap of what each issue cost and what it returned ([the Work map](#the-work-map)), with the [counts strip](#the-strip-and-the-tape) above it and the lead's daily briefing, six lists (Needs you first) and the [tape](#the-strip-and-the-tape) under it. Selecting a Goal, Area or role shows its view in the Selected panel |
| `crew.html`, **Crew** | One row per role plus the merger App, working or idle, each opening its role view on the Work map; then `#floor` ([On the floor](#on-the-floor)), `#sessions` (the sessions table), `#reviewer` (the [Actions reviewer](#actions-reviewer)), `#grants` ([grants in use](#grants-in-use)) and `#effort` ([Effort](#effort)). See [Crew](#crew) |
| `governance.html`, **Governance** | `#rulings` (the full [decision log](#governance)), `#questions` (open and lapsed gov questions), `#committees` (the [committee desk](#committee-desk) and each open committee's [round grid](#committees), then [past committees](#past-committees)' cards and their grids), `#authority` (the [authority map](#authority-map)), `#precedent` ([precedent in use](#precedent-in-use)) and `#trends` ([What the numbers say](#what-the-numbers-say) and [How the questions went](#how-the-questions-went)). See [Governance](#governance-page) |

Every page opens with the [header](#header) and the nav, carries `noindex` and a [Content-Security-Policy](#live-refresh), reloads itself every 300 seconds, and fits a phone's width (only `.scroll` boxes scroll sideways). `generate.render(model)` returns the pages by file name. The build also writes `effort.html`, the PRs behind each segment of Crew's [Effort](#effort) bars (#1013), linked from those bars rather than the nav.

**Retired pages** (#1113). Each old address is a page that only sends the browser to its new home (`generate.REDIRECTS`), with a link for a browser that doesn't follow it:

| Old page | Goes to |
|---|---|
| `index.html`, the old desk | `workmap.html` |
| `commissions.html` | `workmap.html?group=goal` |
| `agents.html`, `operations.html` | `crew.html` |
| `decisions.html` | `governance.html` |
| `authority.html` | `governance.html#authority` |
| `bridge.html` (#1114) | `/` |

They go to `workmap.html` rather than `/` because Pages serves `index.html` at `/`: a redirect to `/` from `index.html` would loop, and a query on `/` would be lost on the way through `index.html`. `index.html` is still the `--out` page, so `dashboard.yml` and `swarm desk` need no change.

**Where each old panel went.** `test_pages.py` lists every panel the old pages drew and checks each lands in its home's section and on no other page:

- Today's report: the Work map's Briefing and tape (`LATE`), and its asks in Needs you (#1114). The plan and the trouble panel: each Goal's view on the Work map (#1115) and the strip's flagged count. The wire: the tape. Commissions: the Work map grouped by Goal, its drawer the Goal's view. The Agents drawer: the role view.
- The needs-you list: the Work map's Needs you list, from the same `needs_you()` as `swarm inbox`. Its tiles: the strip's counts. Open pull requests: each role's view, and Needs you for those waiting on the owner.
- **Removed:** v3 progress, since that phase is over, and spend per day and "spent today", since they're totals (GOV-0033). Each session's own estimate stays in Crew's sessions table, and `spend.py`'s pricing stays for the Work map (`swarm map`).

### Look

`layout.py` holds the look and the page shell every page uses, so colours and fonts are set in one place: paper `#F4F3EE`, ink, agents blue `#1F4FB8` (active sessions), owner amber `#A35A00` (what waits on the owner), and red `#C2361B` only for live marks and blocks (#397). Text is IBM Plex Sans, numbers, times and code Plex Mono, headings Plex Sans Condensed.

The fonts are **self-hosted**, so the public page loads nothing from a third party. `static/fonts/` holds the Latin-1 subset, as woff2, of only the four faces the CSS uses (Sans 400 and 600, Mono 400, Sans Condensed 600), from IBM's `@ibm/plex-sans` 1.1.0, `@ibm/plex-mono` 2.5.0 and `@ibm/plex-sans-condensed` 2.0.0 packages, with their SIL Open Font License. Together they add 82,776 bytes (87,232 with the licence) to the published site. `generate.py` copies them to `fonts/` beside the pages on every build, before writing the pages. A character outside Latin-1 (an arrow, say) falls back to the system font.

## The Work map

`workmap.html` (`workmap_page.py` and `workmap.js`, #1082, FEAT-9 under M9 #1080) draws the [Work map data](#work-map-data) as a squarified treemap: one box per issue, inside one box per group. The live Desk serves it at `/` (`launcher/desk.py`). It adds no API calls: the build passes it the same data it writes to `map.json`. Top to bottom:

- **Title**, then the [counts strip](#the-strip-and-the-tape), then the **key**: one line saying what size, shade and the markers mean.
- **Controls**, segmented buttons, the current one filled ink: Group by (Effort, Goal, Role, Stage; default Effort), Size (Cost, Tokens, Lines changed; default Cost, per GOV-0049), Colour (Yield, Velocity, Change; default Yield) and Window (Hour, Day, Week, Month; default Day). The viewer's choices are kept in this browser's `localStorage` (`agentfleetos.workmap`), wrapped in `try`; without it the defaults stand. The URL wins over it (see [Links](#links)).
- **Breadcrumb**, e.g. "All effort types › Capability". Clicking a group's header zooms into that group; the breadcrumb's first part zooms back out.
- **The treemap**, `clamp(460px, 68vh, 640px)` tall, beside the [Selected panel](#the-selected-panel). A group's header shows its name and its share of what's shown as a percentage, never an amount. Issues with no size in the window are left off, and the legend says how many. A box big enough shows its title on one line, cut with an ellipsis, and under it, in mono, its size and its colour measure. Hover or focus shows its title, number, Goal, effort, role and stage, then its cost, tokens, lines and outcomes. Clicking a box, or pressing Enter on it, selects it; boxes are reached with Tab.
- **Shade**, one warm ramp from light to dark (`#F3EFE7` … `#64523E`), with light text on the three darkest. **Yield** is outcomes per $100, per million tokens or per 1k lines (the size chosen), with the median of what's shown at the middle and twice the median or more darkest (if the median is 0, any outcome is darkest). **Velocity** is tokens per hour across the window, on a square-root scale from 0 to the most shown. **Change** is log2(this window's cost ÷ baseline), from ¼ of usual (lightest) to 4× (darkest). A row with no baseline, or an unpriced cost, is hatched and says so; one with a baseline of 0 is darkest and says "new".
- **Markers**, each a shape as well as a colour, so none relies on colour alone: no outcome (spend in the window, no outcome) is an umber folded corner, top right; needs you a 3px amber inset outline; blocked a 5px red left edge; selected a 2px dashed outline.
- **Legend** under the map: the ramp with its end labels for the colour chosen, a swatch per marker, and how many issues were left off.
- **Briefing**, moved from the Bridge (M8, #1029): the lead's newest daily briefing, whole, one paragraph per chapter, from the report issue's comments the desk already reads (`report.py` takes the newest planner comment starting `**Briefing`, without its first line or signature). It links to the comment, and says so when it's from before today. It shows here only.
- **Lists**, six of them under the Briefing ([the lists](#the-lists), #1084).
- **Tape** at the foot of the page ([the strip and the tape](#the-strip-and-the-tape), #1114).

### The Selected panel

The panel (#1083, FEAT-10) tells one issue's story beside the map: 320px wide, the map frame's height and top. Below 900px wide it goes under the map at 460px. Each section is always there at a fixed height, and text is cut rather than wrapped past it, so selecting or clearing an issue changes no element's size or position on the page. Top to bottom:

1. **Selected**, with the issue number on the right.
2. **Title**, at most two lines, linking the issue, then a context line: effort, role and Goal, plus "◆ needs you" (amber, with the shape and words) and "idle this window" (no spend and no outcome in the window, or not in its rows at all) when they apply.
3. **Stage**: four labelled segments, Queued, Building, In review, Merging. Past stages are light, the current one umber with a bold label, and a blocked issue shows red stripes at the stage it stopped in (`blocked_at`), with "blocked at …" in words. A closed issue shows every stage past.
4. **Waits on / Holds up** (#1115): the issues in its `blocked_by` and `blocks`, each one a button that selects it (or a link to GitHub when it isn't on the map), else "nothing". While an issue is selected, the boxes it holds up get a thin dashed outline.
5. **Cost, last 14 days**: one bar per UTC day, to scale against the issue's peak day, today darkest; a dark dot under each day with an outcome. Labelled "14d ago", "today" and "peak $X" (the tallest bar). The header gives the 14 days' cost for this one issue and its outcome count: a per-issue figure, not a sum across issues, so GOV-0033 doesn't bar it. An issue idle in the window still shows its 14 days.
6. **Yield against its group**: one line from 0 to the largest yield, a light dot per issue on the map in the same group (the Group by chosen) and window, a tick at their median, and this issue as a large ink dot. Labelled 0, the median and the maximum; the header names the group and its size.
7. **Numbers**, in two columns: cost, tokens, lines, outcomes, yield (per the chosen size unit) and change against usual (the window's cost against its baseline).

**A Goal, Area or role** (#1115, FEAT-13). Grouped by Goal or Role, each group header has an "i" button that selects that Goal or role; clicking the header itself still zooms. The role and Goal in an issue's context line select them too, as does any element with `data-wm-sel="goal-N"`, `"role-NAME"` or `"#N"` (the [tape](#the-strip-and-the-tape)). The panel keeps its size: the head and title stay, and in place of the issue's sections one area scrolls inside the same box.

- A Goal or Area: its type, criteria met of total and its date; the done test, each criterion with its status ("unmeasured: not known to be on track" for one that isn't measured); what's stuck and why nothing will start it; what waits on you; the authority used under it in the last 24 hours; its open sub-issues, each with its go status, its PR and its share of the Goal's size in the window, as a percentage (never a summed amount, GOV-0033); and a link to it on GitHub. It's what the Commissions drawer showed (`commissions.build`), carried in the page's JSON block under `scopes`.
- A role: what it does and whether it's working, idle or blocked; what it's on now; its merged PRs and sessions in the window (Month shows the 14 days the Desk reads), its open PRs and those with changes requested at head; the merger's calls on its PRs in the last 24 hours; and how to ask it something (`Ask: <role>: …` on the report issue, GOV-0029). It's what the Agents drawer showed (`agents.build`), under `roles`.

### Links

The URL holds the view (#1115): `?group=goal&size=cost&colour=yield&w=week&zoom=M9#issue-1012`, with `#goal-987`, `#role-builder` or `#unattributed` for the other selections. Every control is written, so a copied URL shows the same view in a browser with other saved choices. Opening it restores the controls, zoom and selection, and the URL wins over `localStorage`. A new selection is a history entry, so Back and Forward step through selections; a control or zoom change replaces the current entry.

Empty, it keeps the same sections and size, with grey placeholder bars, dashes and "Click a box, or an item in a list below, to see it here." Clicking a box selects it, and clicking it again clears it. Any element in the page with a `data-wm-ref` attribute (the Work map's [lists](#the-lists)) selects that issue the same way. The panel redraws when the window, size or grouping changes.

The map's rows are in the page itself, in a `<script type="application/json">` block with `<`, `>` and `&` escaped, so it draws on GitHub Pages and the live Desk as soon as it loads. `workmap.js` reads it and builds nodes with `createElement` and text nodes only (no `innerHTML`, no `eval`); it's served as `js/workmap.js` and the page's CSP allows it by hash. With JavaScript off the page says the map needs it, and the Briefing still shows. Each issue's 14-day series is the same in every window, so the page carries it once, under `days`: `dates` and `of` (ref → `[cost, outcomes]` per day).

**No total** (GOV-0033): boxes show their own issue's figures, headers a percentage, and the tooltip and Selected panel one issue's. Selecting a box or changing a control changes nothing's size or position outside the map: the breadcrumb is one line and the legend a fixed height.

**Month** isn't in `map.json`: the Desk reads 14 days of heartbeats, too few for a month and its baseline. Picking it says so and points to `swarm map --window month`.

### The lists

Six lists under the Briefing (#1084, FEAT-11) name the exceptions a small box hides. They come in two rows of three, two columns below 900px wide and one below 600px. Each has an uppercase heading with its count on the right, a one-line description, and exactly five 50px rows. A list with fewer items keeps its height, and an empty one shows one muted sentence. Each row shows the title on one line, cut with an ellipsis, with **You** (needs you, amber) and **Blocked** (red) flags in words where they apply. The list's value is on the right in mono, and under the title is a muted line with the issue number and some context. Clicking a row, or pressing Enter on it, selects the issue in the [Selected panel](#the-selected-panel) and outlines its box on the map, and the row gets a dashed outline. Every list follows the window, the zoom (only the zoomed group's issues) and the size. Changing a control or selecting an item changes no list's height or position.

| List | Who's in it | Order | Value, and the line under |
|---|---|---|---|
| Needs you | issues in the needs-you list, then the [decisions waiting](#the-strip-and-the-tape) its rows don't show | largest size first, then the decisions oldest first | size; stage and role. A decision: how long it has waited; its ref, where it comes from and why |
| Blocked | stage `blocked` | largest first | size; "was <stage>" (`blocked_at`) and role |
| Spend, no outcome | size above zero in the window, no outcome | largest first | size; stage and role |
| Running hot | cost at least 1.5× a baseline above zero | highest first | +N%; usual and now |
| Gone quiet | cost under half a baseline above zero, or idle in the window (no tokens, cost or outcome) after spend in the next longer window (hour→day, day→week, week→month) | idle first, then the lowest share | −N% or "idle"; usual and now, or the longer window's figure |
| Best yield | at least one outcome and a size above zero | highest yield first | N per $100, per M tokens or per 1k lines |

Running hot and Gone quiet compare cost, as the map's Change colour does. An issue with no baseline, a baseline of 0 or no price is in neither, except as idle. The unattributed row is in no list. An issue may be in several. A heading's count is every match in the zoomed group, not just the five shown. It is a number of issues, not an amount (GOV-0033).

`workmap.py`'s `lists()` holds the rules. The page carries every window's matches for every size, in order, as `lists` → window → size → list → `[ref, value, figure]`, and `workmap.js` keeps those in the zoomed group. Gone quiet's idle issues are left off the map, so a row may come from another window's data, and the Selected panel says "idle this window". The Desk reads no month, so in the week window Gone quiet has no idle part, and its description says so. In the month window each list says the Desk has no month data.

## The strip and the tape

The Work map retired the Bridge (#1114, FEAT-12): `bridge.html` only sends the browser to `/`, and its shared left column went. What it showed is on the Work map: the Briefing (#1082), what waits on the owner in Needs you and stuck items in Blocked (#1084), each Goal's criteria when it is selected (#1115), and the rest in the strip and the tape. `strip.py` builds both from data the build already reads, so they add no API calls.

**The strip** sits between the title and the map controls, one line high (it wraps on a phone). Counts only, never money (GOV-0033):

- **Goals and Areas flagged**, of the open ones. A Goal or Area is flagged when something under it is stuck, one of its criteria is failing, or its date is missed.
- **Decisions waiting**, with the oldest one's age.
- **Agents working**, of the live sessions.
- **Authority used** in `swarm trouble`'s window.

Picking "flagged" or "decisions waiting" sets Group by to Goal and outlines the matching boxes: a red frame round each flagged Goal, or an ink outline on each issue a decision is about (the needs-you issues, the questions, and the issues a waiting PR closes). Picking it again clears the outline. It never resizes anything. With JavaScript off the counts still show and the two picks are disabled.

**Decisions waiting** (`strip.decisions()`) are as the Bridge listed them, each issue or PR once, oldest first: `swarm trouble`'s waiting items, open gov questions not ruled, sessions blocked on a question, PRs the merger left for the owner or that GOV-0011 hands to the owner, and today's daily report's asks. Those the Needs you list's own rows don't already show join it, after its rows, when the map isn't zoomed (a decision belongs to no group). The list then shows all its items, scrolling inside its five rows' height, and counts them all. A decision about an issue on the map selects it; any other links to where it's answered on GitHub. `needs_you()`, and so `swarm inbox`, are unchanged.

**The tape** sits at the foot of the page, under the lists. It is newest first, holds at most 20 items, and sits in a 360px box that scrolls inside itself. It shows:

- the daily report (`LATE`, in red, when it's late);
- each item `swarm trouble` says is stuck (`STUCK`, in red);
- the PRs a role's App merged in the last 7 days (`SHIPPED`, or `DELIVERED` for a title starting "Brief");
- the owner's acts on GitHub (`ORDER`, the Bridge's Orders received), with branch creation and deletion left out;
- today's governance events from [the wire](#the-wire).

Each item has a time, a role or "owner", and a link to GitHub. Its text is a template filled from fields, never a summary of anyone's text. An item about an issue on the map is a button that selects it in the [Selected panel](#the-selected-panel). On a phone, each item's text goes under its time, role and kind.

## Crew

`crew.html` (#1113) is who's doing what. It opens with one row per role (planner, builder, reviewer, analyst, designer, docs) plus the merger App, grouped as **working** (a live session that's active or blocked; for the merger, a call in the last 24 hours) and **idle** (`agents.py`, from the Agents page, #932). Each row shows what the role does, what it's on now or the last PR it merged, and its merged-PR count over the build's window, and links to the role's view on the Work map (`workmap.html?group=role#role-<name>`, #1115): its record, current work, recent merges, the authority it used and how to ask it something. Then, each in a section the brief's links land on:

- `#floor`: [On the floor](#on-the-floor), what each live session is doing, and [the watcher](#the-watcher);
- `#sessions`: every live session (status, role, model, issue, PR, last activity and its own spend estimate), with stopped ones collapsed, and the [spend method](#spend);
- `#reviewer`: the [Actions reviewer](#actions-reviewer)'s sweeps, success rate and commit-to-review time;
- `#grants`: [grants in use](#grants-in-use);
- `#effort`: [Effort](#effort), linking to `effort.html`.

There's no spend total, cap or cost per result (GOV-0033), and no reassign or one-on-one buttons (#760).

## Governance page

`governance.html` (#1113) is how the swarm is governed, in six sections:

- `#rulings`: the full [decision log](#governance);
- `#questions`: open gov questions and lapsed ones;
- `#committees`: the [committee desk](#committee-desk) while one is open, then each open committee's [round grid](#committees) ("No open committees." when none is), then [past committees](#past-committees)' cards and, collapsed under them, their round grids;
- `#authority`: the [authority map](#authority-map);
- `#precedent`: [precedent in use](#precedent-in-use);
- `#trends`: [What the numbers say](#what-the-numbers-say) and [How the questions went](#how-the-questions-went).

## Effort

`effort.py` (#1013, FEAT-4 under M7 #987) shows what kind of work the swarm ships. It reads only `classify/cache/effort.json`, which `swarm classify run effort` writes (#1012): no model call, no credential and no API call. `main()` reads it from the checkout.

- **Crew's Effort panel** (on the desk until #1113): a stacked bar per open Goal for the last 7 days and the 7 before, one segment per label (capability blue, governance amber, knowledge ink, upkeep grey: layout.py's colours), with the share that fixes recent work hatched. Each segment links to its PRs on `effort.html`. Below, the capability share of all merged PRs in the cache by week (from Monday, UTC, the last 8 weeks) as a line and a sentence. With no cache it says so; an unreadable cache says why.
- **`swarm daily`:** an "Effort risks" section for the report's Risks and mitigations: a line for each Goal where upkeep is more than half of its PRs merged in the last 7 days.

The cache, schema 1 (#1012 writes it; this is what the desk reads):

```json
{"schema": 1, "labelset": "effort", "classifier": "model",
 "updated_at": "2026-11-13T09:00:00Z",
 "prs": {"1009": {"repo": "open-agentos/agentfleetos", "title": "...",
                  "merged_at": "2026-11-13T08:00:00Z", "label": "upkeep",
                  "fix": false, "fixes": null, "goal": "open-agentos/agentfleetos#987",
                  "hash": "...", "labeller": "model"}}}
```

`label` is one of capability, upkeep, governance or knowledge; `classifier` is `model` or `paths` (the baseline the cache falls back to). `goal` is the open Goal the PR's issue sits under, as `owner/repo#N` or a bare number in this repo, or null; `repo` defaults to the desk's. An entry with another label or no `merged_at` is left out and counted on the panel. `state.json` carries the counts as `effort`.

## Work map data

`workmap.py` (#1081, FEAT-8 under M9 #1080) works out what each issue cost and what it returned, for the [Work map page](#the-work-map) and `launcher/swarm map`. The build writes it to **`map.json`** beside the pages: the rows for the last hour, day and week (`DESK_WINDOWS`), each window ending with the current UTC hour. Per GOV-0049 it may publish cost per issue on both Desks. It never sums cost across issues (GOV-0033): no total field, no total line, and nothing of it reaches `state.json`. If its read fails, the pages are still written and `map.json` isn't.

- **Spend.** Each session's token deltas between consecutive heartbeat events go to the issue of its latest `working_on` before the later event, so a switch splits them; tokens before any `working_on` go to the `unattributed` row. Deltas are priced with `spend.py`'s prices for the event's model (list-price equivalent, not what was billed). An unknown model gives tokens and no cost: the row's `unpriced_tokens` counts them, and `cost` is null if none were priced. Spend and outcomes are kept per issue per UTC hour.
- **Outcomes**, each once, in its hour: a PR closing the issue merged, the reviewer App's first approval at that PR's head, the issue closed. They count equally.
- **Each row:** `issue`, `ref`, `title`, `url`, `state`, `cost`, `unpriced_tokens`, `tokens`, `lines` (additions plus deletions of its PRs' commits in the window), `outcomes` and `outcome_kinds`, `goal` (the owner's open Goal or Area above it: `number`, `lead`, `title`, `kind`), `effort` (the `effort.json` label of its latest merged PR, else its latest classified PR, else `unclassified`), `role` (most cost in the window), `stage` (`blocked`, `merging`, `review`, `building`, `queued`, or null when closed or none applies), `blocked_at` (the stage a blocked issue stopped in: what its stage would be without the block, counting it as go, so `queued` at least; null when it isn't blocked), `needs_you`, `blocked_by` and `blocks` (the issue numbers that hold it up and that it holds up, #1115: from `**Waits on:**` lines read as `swarm watch` reads them, sub-issue links below the owner's Goals and Areas, and GitHub blocked-by links; a link with a closed end is dropped), `baseline` (its mean cost over the four windows before, null when the 14 days read don't reach back that far, as for a week) and `days` (14 `date`, `cost`, `outcomes`, ending today).
- **Rows:** every open issue under the owner's open Goals and Areas (two levels, as the plan reads them), every issue closed in the window, every issue with spend or an outcome in it, and the `unattributed` row, last.
- **Lists:** `map.json`'s `lists` are the Work map's six lists for each window and size (`desk_lists()`, #1084), so an open map can redraw from the file alone (#1138).

**API calls:** it reuses the build's issues, heartbeat comments, open PRs and their reviews, the plan and the needs-you list, and adds one paginated GraphQL search for the PRs updated in the last 14 days, with their closing issues, approvals and commits: one query per 50 PRs.

## Header

Every page's masthead shows a red **LIVE** mark, `built HH:MM UTC` (the full time on hover, and a `<time datetime>` the `state.json` poll, #411, can use to grey the mark out once the data is stale; a static page can't know its own age when viewed), and when the owner last acted, in owner amber (`activity.py`, #402, part 3 of #397): "Owner last acted 8m ago: labelled #411 `ready`", linking the issue, PR, comment, commit or branch.

The owner is `identities.humans.owner` in `governance/jurisdictions.yml` (`committees.owner_login()`). Their last act is their newest event, by `created_at`, in the repo's public events (`repos/{repo}/events`), read 100 a page, newest first, up to the 3 pages (300 events) the API keeps, stopping at the first page with an owner event once it has also read back to UTC midnight (for the wire). If none of those is the owner's, it says "Owner: no activity in the last N days", N being how far back the events read go (leaving out the oldest tenth, so a few late arrivals don't stretch it). If the owner or the events can't be read, it says "Owner: unknown" and the page still builds. [The wire](#the-wire) (#405) reuses the same events (`model["activity"]`), so they're read once a build.

What the events API does here (checked 2026-11-05):

- New events show up about **30 seconds** after they happen.
- The list is in event-id order, not quite time order: a few events arrive late with their original time (pushes and branch creations from two days earlier, listed among today's events). That's why the newest `created_at` wins, not the first event listed.
- **Labels** show up: `IssuesEvent` `labeled` carries the label's name. `unlabeled` carries none.
- **Merges** show up as `PullRequestEvent` with action `merged` (not `closed` with `merged`), and their actor is the PR's **author**, not who merged it. So the owner merging an agent's PR doesn't count as the owner's act; the `IssuesEvent` `closed` that the PR's `Closes #N` makes in the owner's name a few seconds later does.
- 300 events covered about 15 hours of this repo on 2026-11-05.

**API calls added per build:** 1 to 3 REST calls (one per page of events). Only the page reads them (`fetch(..., with_activity=True)` in `main()`); `swarm inbox`, `swarm watch` and the digest don't.

## Where it's published

**Moving to the engine host (#664).** `launcher/swarm desk` serves the same pages live on the engine host behind Caddy, rebuilt from GitHub on each webhook nudge (see `launcher/README.md`). Once it is running there, the owner retires `dashboard.yml` and Pages; until then both publish, and the rest of this section describes Pages. `generate.py --prev PATH` makes a build carry precedent's counts forward from a `state.json` on disk instead of the Pages copy.

`.github/workflows/dashboard.yml` regenerates the pages every 15 minutes (plus a manual run) and publishes it to GitHub Pages at <https://open-agentos.github.io/agentfleetos/>. It runs on a schedule only, never on issue, comment or PR events, and its token can read the repo but not write to it (`pages` and `id-token` are only for the deploy), per the owner's choice on #32.

GitHub runs that schedule hours apart here, so the nudge in `.github/workflows/digest-nudge.yml` (shared with the digest) dispatches `dashboard.yml` on `main` when something happens: an issue or PR is opened, closed, reopened or relabelled, a PR is pushed or reviewed, or a Discussion post or comment is created or edited (#351). The nudge passes no event data and holds no secrets; `dashboard.yml` itself still runs only on its schedule and dispatch, and the schedule stays as the safety net. An open page reloads itself every 300 seconds with a `<meta http-equiv="refresh">` tag (plain HTML, no script), so it picks up a rebuild within about five minutes; with JavaScript on, an open desk [picks it up](#live-refresh) within 15 seconds of Pages serving the new `state.json`.

### How often it rebuilds

The workflow's token (`GITHUB_TOKEN`) gets about 1,000 REST calls and 1,000 GraphQL points an hour, shared with the digest. When every nudge rebuilt the page at well over 100 calls each, a busy hour ran it out and every run failed (#392). So:

- **Nudged rebuilds are spaced.** A rebuild started by the nudge (a `workflow_dispatch` by `github-actions[bot]`) first looks for the last `dashboard.yml` run that published: it lists the newest 5 successful runs and reads their jobs, newest first, until one whose `deploy-pages` step succeeded (2 to 6 Actions API calls). A run that skipped also ends `success`, so it doesn't count. If the last publish was less than 5 minutes ago, it prints one line and exits 0 without publishing. The schedule and the next event catch up. A scheduled run and a person's manual dispatch always rebuild. So the page rebuilds at most about every 5 minutes from nudges, plus the schedule.
- **A rebuild costs about 23 REST calls and 20 GraphQL queries** (the [Work map data](#work-map-data) adds 1 to 4) (it was 258 calls on 2026-11-04), plus [precedent in use](#precedent-in-use)'s 2 to about 20 REST calls and 1 to 5 GraphQL queries, and the [header](#header)'s 1 to 3. Tracking-issue comments, the reviewer section's reviews and commits, and the red check's reviews are read 20 or 25 issues or PRs to a GraphQL query (`ghql.py`); an issue or PR with more than 100 comments or reviews falls back to REST. The Actions reviewer section reads the newest 15 sweeps, one jobs call each.
- **A low allowance skips cleanly.** Before fetching, `generate.py` reads `gh api rate_limit`, which doesn't count against the allowance. If fewer than 100 REST calls or 55 GraphQL points are left (`PAGE_NEEDS`), it prints one line and exits 0 without publishing, so the last good page stays up and the run isn't a failure. `digest.py --update` does the same below 30 of each (`DIGEST_NEEDS`) and leaves the issue as it was.

When `generate.py` skips, it writes no page, so `dashboard.yml` must skip its upload and deploy steps for the run to end green: `if: hashFiles('_site/index.html') != ''` on both. That's a workflow change, so it's proposed in #392's PR for the owner to commit (#32); until then a skipped run fails at the upload step, and the last good page still stays up.

The page is **public**, because this repo is. It shows nothing that isn't already public in the repo's issues and comments, and it carries `noindex` so search engines skip it, per the owner's choice on #33. GitHub may delay scheduled runs, and disables them on public repos after 60 days without repo activity.

## state.json

Each build also writes `state.json` beside `index.html` (so `_site/state.json` on Pages): the data the page shows, as JSON, with no HTML strings (`state.py`, #400). It's written only when the page is, so a skipped build leaves both as they were. Timestamps are RFC 3339 in UTC (`2026-11-05T07:20:08Z`); dates are `YYYY-MM-DD`.

| Key | What |
|---|---|
| `schema` | `1` |
| `built_at`, `repo`, `idle_minutes` | when and for which repo it was built, and the idle threshold |
| `owner_last_acted` | the [header](#header)'s owner line: `status` (`acted`, `none` or `unknown`); with `acted`, `kind` (the event's action, e.g. `labeled`, `closed`, `pushed`), `text` (`labelled #411 ready`), `time` and `link`; with `none`, `days` |
| `needs_you` | the needs-you list below, without over-cap items |
| `floor` | [on the floor](#on-the-floor): `cards`, each with `session_id`, `role`, `model`, `status`, `started_ts`, `run_minutes`, `issue`, `pr`, `gov_question`, `activity` (the plain words), `events_per_slot` (six counts, oldest first) and `slots_used` (`editing`, `reading`, `commands`); and `idle`, each with `session_id`, `role` and `idle_minutes` |
| `watcher` | [the watcher](#the-watcher): `status` (`ok`, `missing`, `not_owner`, `several` or `malformed`); when `ok`, also `issue`, `checked` (when its state last changed), `age_minutes`, `stale`, and `running`, `held`, `skipped` and `failed` with #456's fields only. No cost |
| `sessions` | each session's `session_id`, `role`, `model`, `status`, `issue`, `pr`, `gov_question`, `last_event`, `last_ts`, `started_ts` and `tracking_issue` |
| `prs` | open PRs: `number`, `title`, `url`, `author`, `draft`, `review`, `created_ts`, `closes`, `needs_owner` |
| `gov_questions` | open `gov:question`s with their fields, time to live and the `session_id`s waiting on them |
| `governance` | recent and flagged records, counts by shape and domain, lapsed questions |
| `committees`, `reviewer_runs` | those sections' data; `reviewer_runs.unreviewed` is PR numbers |
| `committee_desk` | each open committee as the desk shows it: `discussion`, `url`, `question`, `question_title`, `question_url`, `round`, `max_rounds`, `waiting_on`, `seats` (each `seat`, `role`, `model`, `recommendation`, `swing` (`moved`, `held` or null), `moved_from`, `summary`, `round`, `posted`, `url`) and `consensus` (`agree`, `seats`, `converging`, `consensus`, `text`); `[]` when none is open |
| `trends` | [What the numbers say](#what-the-numbers-say): `days`, `first_day`, `min_count`, and each trend's `name`, `sentence`, `too_few` and `series` (one `{date, value}` per day; `value` is `null` on a day with no data) |
| `questions_went` | [How the questions went](#how-the-questions-went): `days`, `first_day`, `total`, the counts `asked_by` (`agents`, `owner`, `other`), `decided_by` (`owner`, `committee`, `lapsed`, `open`) and `became` (`record`, `direction`, `nothing`), and `questions`, each question's `number` and its three categories |
| `precedent` | [precedent in use](#precedent-in-use): `version`, `from` (the window's first day), `counts` (record → day → `n`, `agents`, `owner`, `reviewer`), `totals`, `findings`, `records` (`id`, `date`, `status`) and `read` (where this build started reading, what it carried from, and its calls). The next build carries `counts` forward |
| `wire` | [the wire](#the-wire): `day`, `events` (whether the repo's events could be read) and `items`, newest first, each with `kind` (`opened`, `ruled`, `lapsed`, `record`, `red` or `convened`), `time`, `number`, `text` and `link`, plus `record` on a `record` item; `[]` items on a quiet day |
| `past_committees` | each ended committee's card: `discussion`, `url`, `question`, `question_title`, `question_url`, `record` (`id`, `url`, or null), `summary` (the INDEX.md ruling, or null), `consensus` (`text`, `consensus`, `dissent`), `rounds_used`, `max_rounds`, `stopped_early`, `models`, `diversity_met`, `minutes`, `swing` and `seats`; `[]` when none has ended |
| `grants` | [grants in use](#grants-in-use) (#713): `mode` (`off`, `shadow`, `live`, or null if `swarm.toml` couldn't be read), `read` (whether the merger's comments could be read) and `calls`, newest first, one per PR: `number`, `title` (null if it couldn't be read), `group` (`merged`, `enqueued`, `would` or `left`), `queued` (true when the merger enqueued it, so a `merged` call merged through the queue), `reason` (the merger's words), `time` and `link` (the comment) |
| `effort` | [Effort](#effort) (#1013): `status` (`ok`, `missing` or `error`); when `ok`, `classifier`, `goals` (each `ref` with `this` and `last`: `total`, `fixes`, `by` and `fix_by` label) and `trend` (`week`, `capability`, `total`) |
| `desk` | what the [live refresh](#live-refresh) draws on Crew and Governance: `mast` (the masthead's LIVE mark, build time and owner line) and each panel (`floor`, `grants`, `effort`, `committee_desk`, `past_committees`, `precedent`, `trends`, `questions_went`) as a node tree, or `null` for a panel that can't be one |

It carries **no cost**: no session cost, daily spend, cap, over-cap flag or spend totals (GOV-0014; #397). It's public like the page (#33), and sessions and PRs keep only the fields the page shows. Later panels add their slice to `state.py`. Cost per issue is in [`map.json`](#work-map-data), a separate file, never here (GOV-0049).

## Live refresh

With JavaScript on, an open Crew or Governance page redraws its panels from `state.json` every 15 seconds, without a reload (`live.py` and `poll.js`, #411, option 2 of #396; the desk did until #1113). It's how they feel live between the 300-second reloads.

**The Work map** (#1138, per GOV-0051) refreshes itself the same way from `map.json`: `workmap.js` fetches `map.json?t=…` with `cache: "no-store"`, same origin, on `poll.js`'s 15 seconds while the tab is visible (and as soon as it's shown again), and when the file's `built_at` is newer than the data on screen it turns the file into what the page's JSON block carries and redraws the map, the lists and the Selected panel in place. The view (Group by, Size, Colour, Window), the zoom and the selection stay; a zoomed group or a selected issue the new data no longer has is dropped, as on opening the page. A file it can't draw is ignored. It updates the masthead's build time and greys the LIVE mark on the same 15 minutes. The page's Goals, roles, strip and lists of decisions waiting aren't in `map.json`, so they change with the 300-second reload, which stays until #1135. The page's JSON block carries the timings as `live` (`every`, `stale`, in ms) from `live.py`. `map.json` carries each window's lists (`workmap.desk_lists`) for it.

- **One renderer.** The panels are still drawn in Python. Each build turns each desk panel's HTML into a node tree in `state.json["desk"]`: a node is a string (text) or `[tag, {attr: value}, child, …]`. The script turns the tree back into DOM nodes with `createElement`, `setAttribute` and text nodes. It never uses `innerHTML` or `eval`, and never parses HTML, so text from the repo stays text.
- **Allow lists.** Only the tags and attributes in `live.py` may appear, and links only to `https://` URLs, a page beside the desk or a fragment. The build checks them, and the script checks them again. A panel with anything else is `null` in `state.json`, so the desk keeps it as drawn until its next reload; the build doesn't fail. A test draws every panel fixture the panels' own tests use, so new markup that isn't allowed shows up as a failing test, not as a panel that quietly stops refreshing.
- **Boxes.** Crew and Governance draw each live panel inside `<div data-panel="NAME">` (an empty panel still gets its box), and the masthead's LIVE mark, build time and owner line are `data-panel="mast"` (the page name around them stays). `state.json` carries both pages' boxes, and the script redraws each box on the page whose name it carries. A new panel joins by adding itself to `generate.crew_panels()` or `generate.governance_panels()`. Crew's role rows and sessions table, and Governance's decision log, questions, round grids and authority map, aren't boxes: they change with the 300-second reload.
- **Only forward.** The script fetches `state.json?t=…` with `cache: "no-store"`, same origin, every 15 seconds while the tab is visible, and applies it only if its `built_at` is newer than the data on screen (the `data-built-at` on `<body>`), since Pages' cache can serve an older copy than the page.
- **Stale mark.** When the data on screen is more than 15 minutes old, the script adds `stale` to the masthead's LIVE mark (#402), which greys it out. Builds often run further apart than that (see [How often it rebuilds](#how-often-it-rebuilds)), so a grey mark is common and honest.
- **CSP.** Every page carries a `<meta http-equiv="Content-Security-Policy">`: `default-src 'none'`, `script-src 'self'` plus the live script's `sha256` hash on Crew and Governance, `'self'` plus `workmap.js`'s on the Work map (#1082) and `'none'` elsewhere, `style-src 'unsafe-inline'` (the page's `<style>` and the precedent table's cell shading), `font-src`, `connect-src 'self'`, `base-uri 'none'` and `form-action 'none'`. `live.script()` fills `poll.js`'s settings and allow lists in at build time, and the hash is of that exact text.
- **Scripts as files** (#1106, option 3 of #1102). No page carries an inline script. `generate.py` writes each script a page loads into `js/` beside the pages (`js/poll.js`, `js/workmap.js`) before it writes any page, and the page loads it with `<script src="js/<file>" integrity="sha256-…">`, the same hash its CSP names, so the browser runs only the bytes the page was built with. A test fails the build if any Desk script contains `eval(`, `new Function` or `innerHTML` (#396's rule, carried over by #1102). The live Desk serves `js/` too (`launcher/desk.py`).
- **Vendored libraries** (#1107, GOV-0051). A third-party front-end library is pinned to one exact version and vendored into `static/vendor/`; the site loads nothing from a CDN or any other third party. `static/vendor/manifest.json` lists each file under `"files"` with its `file`, `library`, `version` (exact, e.g. `7.9.0`, never `^7` or `7.x`), `licence`, `source` (the `https://` URL it was taken from) and `sha256` (hex, of the file's bytes). Before it fetches anything or writes any page, `generate.py` checks every file against the manifest (`layout.vendored()`) and fails the build, naming every problem, if a file differs from its hash, a file has no entry, an entry has no file, or an entry is incomplete. File names follow the Desk's own scripts (`[a-z][a-z0-9_-]*.js`, so `d3.min.js` comes in as `d3.js`), which is what the live Desk serves, and can't reuse one of their names. The checked files are copied into `js/` beside the Desk's own scripts. A page loads one with `layout.page(..., libs=layout.libs("d3.js"))`: it gets a `<script src="js/d3.js" integrity="sha256-…">` before the page's own script, and its hash joins the page's CSP. The manifest starts empty.

  **Adding a library.** Each library comes in its own PR in the `dependencies` domain (per #1102). Its body states the version, the licence, the size and why it's needed. The PR adds the file as published at its exact-version URL, unchanged (keep its licence header), plus one manifest entry, whose `sha256` is `shasum -a 256 dashboard/static/vendor/<file>`. A further library needs its own such PR, not a new question. Libraries are third-party code, so the Desk's own no-`eval`/no-`innerHTML` test doesn't scan them; the PR says how the Desk uses the library within GOV-0051's rules.
- **JavaScript off.** Nothing changes: the page is complete as built, and the meta refresh stays.

It adds **no API calls** per build: browser fetches hit Pages, not the API, and need no token.

## Plan, report and grants: layout

This is the spec for the desk's three M3 panels (#711, under #685). Since #1113 the report and plan panels are retired (the Work map's Briefing, tape and Goal view show what they did, and the data below still feeds them) and grants in use is on Crew. #712 built the report and plan panels (`report.py`, `plan.py`); #713 builds the grants panel.

Two notes on #712's build. "Today" is the build machine's local time, as for `[daily]`, so a desk built in Actions needs `TZ` set to the owner's timezone. The plan panel's go is GOV-0031's scope and the owner's `ready`; it doesn't read GOV-0026's `**Milestone:**` lines, which stop counting on 2026-11-16.

The owner opens the desk to answer three questions without opening Claude Code: *did today's report land, and what does it ask me?*, *where does the plan stand?* and *what did agents do on my authority?* The panels answer them in that order, above everything else on the desk:

| # | Panel (`data-panel`) | Heading | Why here |
|---|---|---|---|
| 1 | `report` | Today's report | Its asks are the only thing on the desk that waits on the owner. |
| 2 | `plan` | Plan | The state of every Goal and Area, and why any Task isn't moving. |
| 3 | `floor` | On the floor | Who is on what (#403, unchanged). |
| 4 | `grants` | Grants in use | What the merger did or would do without the owner's click. |

The wire, the committee desk and the rest follow as today. Each new panel joined the desk's panel list in that order (now `generate.crew_panels()` and `generate.governance_panels()`), so it gets its `data-panel` box and [live refresh](#live-refresh), and its markup stays inside `live.py`'s allow lists. Each fits a phone's width with no sideways scroll, and owner amber marks only what waits on the owner (the asks, and "Left for you").

### Today's report

**What counts.** The newest comment on `[watch] report_issue` (`swarm.toml`, #249 today) by `productswarm-planner[bot]` whose body starts `**Daily report`. A comment starting `**Monday check-in` is the check-in. "Today" and the 10:00 cut-off are in the owner's local time, the timezone `[daily]` uses (`daily_at`). Working days are Mon–Fri, as for `[daily]`.

**What it shows**, top to bottom:

1. The report's first line, its bold state sentence, as written, linking the comment, with `posted 08:34` in Plex Mono.
2. **Asks**: the numbered items under the report's `Asks` heading, at most 5, in amber. Each is its bold lead-in (e.g. "#655 (GOV-0032)") and the rest of its first sentence, cut to about 120 characters, with a link to the first `#N` in it, or to the report if it has none.
3. On a Monday, one line: "Monday check-in: " and the check-in's first line, linking it.

**States** (exact words):

| When | Shows |
|---|---|
| Today's report is posted | as above |
| Working day, before 10:00, none yet | "Today's report is due at 08:30." (from `daily_at`), then the last report's first line, labelled "Last report, Fri 11-06:" |
| Working day, 10:00 or later, none yet | "**No report yet today.** It was due at 08:30." in amber, then the last report's first line as above |
| Saturday or Sunday | "No report on weekends." then the last report's first line as above |
| No report at all in the comments read | "No daily report found on #249." |
| A report with no `Asks` heading, or none it can read | "Asks: couldn't read them; open the report." linking it |
| The report issue couldn't be read | "Couldn't read #249; the report may be there." |

`[daily]` being off (`daily = false`) changes nothing here: the panel shows what was posted, not who started it.

**API calls:** 1 or 2 REST calls, the report issue's comments since 4 days ago (`?since=`), enough to reach Friday's report on a Monday or Tuesday.

### Plan

**What counts.** The plan is the open Goal and Area issues the owner (`identities.humans.owner`) opened (GOV-0031). A Goal or Area opened by anyone else isn't listed as plan; it gets one quiet line at the panel's foot: "Not plan: #N, a Goal opened by productswarm-planner[bot] (GOV-0031)."

**What it shows.** One block per Goal or Area, Goals first, then Areas, each by issue number:

- **Its line:** `M3` (or whatever the title opens with) in Plex Mono, the title, linking the issue, then "4 open, 2 done" counting its direct sub-issues.
- **Its open sub-issues**, one line each, by number: the number and title, linked, and a status:
  - **go** (agents blue): go under GOV-0031 or by the owner's `ready`;
  - **waiting on #711** (ink): its only reasons are open blocked-by issues;
  - **not go:** and the reason (amber), in the words of `swarm.scope_refusal()`, so the desk and `swarm watch` say the same thing, e.g. "not go: @mattmcalister commented on #712: that's a veto until @mattmcalister labels it `ready`";
  - **PR #714** after the status, when an open PR closes it.
- **Sub-issues of a sub-issue** (a mission's Tasks) are indented one level under it, the same way. Deeper levels show only a count: "and 3 more below".
- Closed sub-issues aren't listed; "2 done" carries them.

**States:**

| When | Shows |
|---|---|
| No open Goal or Area by the owner | "No plan: the owner has no open Goal or Area." |
| A Goal with no open sub-issues | its line, then "Nothing open under it." |
| A sub-issue's links couldn't be read | "status unknown: couldn't read its links" in place of its status |
| The Goals couldn't be read | "Couldn't read the plan from GitHub." |

**API calls:** GraphQL only, through `ghql.py`: one search for open Goal and Area issues in the repo, then each Goal's sub-issues two levels deep with each one's blocked-by, author, type, labels and closing PRs, batched about 20 to a query. About 2 to 4 queries for 5 Goals. Any repo of the org (GOV-0031) is left for later: today every Goal is in this repo.

### Grants in use

**What counts.** The merger's comments (`productswarm-merger[bot]`) on PRs in the last 24 hours, one line per PR, newest first, its latest call winning:

| Comment starts | Group | Line |
|---|---|---|
| `Merged under` | Merged | "#701 merged under standing grant, 14:02" |
| `Enqueued under`, PR not merged yet | Enqueued | "#701 enqueued under standing grant, 14:02" |
| `Enqueued under`, PR since merged | Merged | "#701 merged under standing grant via the queue, 14:02" |
| `Would merge` | Would merge (shadow) | "#701 would merge (standing grant), 14:02" |
| `Left for the owner` | Left for you (amber) | "#653 left for you: not opened by productswarm-builder[bot], 09:15" |

When `main` requires a merge queue (#663), the merger enqueues and GitHub merges later, so an enqueued PR moves from Enqueued to Merged once GitHub has merged it (#746). The time stays the enqueue comment's.

Each line links the comment; the PR number links the PR, and the PR's title follows the number. The reason is the merger's own words after the colon, without the sha or `-- merger`.

The panel opens with one line for the merger's mode, from `[merger] mode` in `swarm.toml` on `main`: "The merger is in shadow: it says what it would merge and merges nothing." / "The merger is live." / "The merger is off."

**States:**

| When | Shows |
|---|---|
| No merger comments in 24 hours | the mode line, then "No merger calls in the last 24 hours." |
| The comments couldn't be read | "Couldn't read the merger's calls." |

Other uses of delegated authority (call-ins, `Research:`, agents' `decide`s) stay in the daily report's section 4; this panel shows only the merger.

**Built** in `grants.py` (#713). It parses the four bodies `launcher/merger.py` writes (a test checks them against the merger's own `would_body`, `merged_body`, `enqueued_body` and `left_body`), keeps comments on PRs only, and checks each comment's own time, since `?since=` filters on the last update. Times are UTC, like the wire's. The mode line reads `[merger]` with the merger's own `load_switch`, so a bad table shows "The merger is off." as the merger treats it; if `swarm.toml` can't be read it says "The merger's mode couldn't be read from swarm.toml." Until #712 adds the report and plan panels, the grants panel sits right after the floor.

**API calls:** 1 or 2 REST calls, the repo's issue comments since 24 hours ago (`repos/{repo}/issues/comments?since=`), filtered to the merger. A PR's title comes from the open PRs the build already reads; a merged or closed PR's title costs one more REST call.

### What each build needs

The three panels add about 3 REST calls (plus one per merged or closed PR in the grants panel) and 2 to 4 GraphQL queries. #712 and #713 raise `PAGE_NEEDS` to match, and add their data to `state.json` under `report`, `plan` and `grants`.

## On the floor

Crew's `#floor` shows a card for each active or blocked session (`floor.py`, #403, part 4 of #397; on the desk until #1113). It's built from the heartbeat events `generate.py` already reads, so it adds **no API calls** per build.

A card shows the role (in agents blue; a blocked card has a red edge), the model, how long the session has run (its first event to now), what it's doing in plain words, and an activity line: events per 5-minute slot over the last 30 minutes, as inline SVG. Under the line it says in how many of those six slots the session was editing, reading or running commands. Idle sessions share one quiet line, e.g. "idle: docs 40 min, reviewer 2 h". Stopped sessions aren't on the floor. Nothing on the floor shows tokens or cost.

The plain words come from the session's latest event and its tool names, through one table, `floor.TEMPLATES`; the first row that matches wins:

| Situation | Tools in the latest event | Words |
|---|---|---|
| blocked on a question | any | Waiting on #396 |
| `pr_opened` | any | Opened PR #394 |
| any | Edit, Write or NotebookEdit | Editing files on #392 |
| any | Bash | Running commands on #392 |
| any | only Read, Grep or Glob | Reading code on #392 |
| `session_started` | none of these | Starting up |
| any | none of these, or no tool names | Working on #392 |

"on #392" is the session's issue, or "on PR #391" if it has only a PR, or nothing.

What today's events can't give: words like "Running tests" or "Checking the diff of PR #391", and counts of files read, edited or tests run. An event lists only the distinct tool names used since the previous one (heartbeat/SCHEMA.md), never commands, paths or counts (GOV-0002). Showing those needs a new captured field, which is a `security` question for the owner; once one is ruled, it adds rows to `TEMPLATES`, not new logic.

### The watcher

Under the cards, the floor shows what `swarm watch` is doing (`floor.watcher()`, #459, part 3c of #444), from the `[watch]` issue the watcher keeps current (#458, GOV-0025). The issue comes with the open issues `generate.py` already lists, so it adds **no API calls** per build.

- builder on #405 since 11:09
- held: #407, 2 of 2 running
- skipped: #439, the role has no spend_cap_usd in swarm.toml
- failed: #51 build, at its cap, 10:02

**What it accepts.** Only the open issue whose body starts with `<!-- productswarm-watch -->` and that the owner opened (`humans.owner` in `jurisdictions.yml`; GOV-0025). Marked issues anyone else opened are ignored; if the owner opened none, the floor says so, and if they opened more than one, it says to close all but one. From the body's fenced `json` it keeps only #456's fields, each checked by shape (a ref is `#N` or `PR #N`, times are RFC 3339 with an offset, an ending is one of `watch.ENDINGS`' codes), and drops any entry that fails. A held or skipped reason is kept only if it is one of `watch.REASONS`' sentences; any other text is dropped and the line shows the code. No cost (#456).

**When it's stale.** The watcher edits the issue only when its state changes (#458), so `checked` is when that last happened, not its last check. Once it is older than two `[watch] interval_minutes` (from the committed `swarm.toml`), the floor says "watcher last published 40 min ago" and shows the lists as of then, not as current: the loop may be quiet or stopped, and the issue can't tell which.

## Needs you

One ordered list of everything waiting on the owner (L5). `launcher/swarm inbox` prints it, and the Work map's Needs you list shows its issues (#1084; it was the operations page's first section until #1113). Both come from `needs_you()` in `generate.py`, so they always agree.

| Order | What | Within the kind |
|---|---|---|
| 1 | Sessions blocked on a `gov:question`, with the question | longest blocked first |
| 2 | Open `gov:question`s nobody is blocked on and the owner hasn't labelled `gov:ruled`, with their time to live | oldest first |
| 3 | Open PRs that aren't drafts, waiting for review or merge | oldest first |
| 4 | Sessions over their role's spend cap (warn only, GOV-0008) | furthest over first |

Idle sessions aren't listed: `swarm ls` and the floor show them. A ruled question's next step is docs or the planner, so it's left out too; a record PR for it still shows as a PR (#469).

Each item links to its question, PR or session tracking issue. An empty list says "Nothing is waiting on you." The list is built only from the GitHub data below, so it shows nothing that isn't already public (GOV-0002, GOV-0004).

## Digest

`dashboard/digest.py` renders the same list as short Markdown for a pinned GitHub issue that the owner reads on GitHub mobile (v3 F2, GOV-0015):

```bash
python3 dashboard/digest.py --print                       # prints the issue body; read-only
python3 dashboard/digest.py --update --repo OWNER/REPO     # writes it into the pinned issue
```

It starts with a hidden `<!-- productswarm-digest -->` marker and a count, then one heading per kind that has items, in the order above. Each bullet is the `#N` or `PR #N` reference, the title cut to about 60 characters, and the same detail and age as `swarm inbox`. Session items link to their tracking issue. It ends with the update time and the dashboard's Pages URL. It uses no tables, so nothing scrolls sideways on a phone. It reuses `fetch()`, `build()` and `needs_you()`, so it can't disagree with the page or `swarm inbox`, and like them it shows no local-only state (`watch.json` runs, held triggers, run cost). `--print` never writes to GitHub.

### Keeping the pinned issue current

`--update` (v3 F3) finds the one **open** issue whose body starts with `<!-- productswarm-digest -->` and replaces its body with the digest. Its only write is that one `PATCH repos/OWNER/REPO/issues/N`. It never creates, pins, labels, closes or comments on an issue. If there's no marked issue, or more than one, it says so and exits 1 without writing.

It edits only when the list changed. The comparison ignores the "Updated" line and the ages (`5m ago`, `just now`), which change with the clock alone, so a run where only time passed leaves the issue alone. Ages in the issue are therefore as of its "Updated" time. Editing an issue body sends no notification. It uses whatever `gh` is signed in as (`GH_TOKEN`); in the workflow that's the job's `GITHUB_TOKEN`, whose edits don't start other workflows.

Set the issue up once, by hand:

1. Open an issue titled, say, "Needs you", whose body starts with the marker line:

   ```
   <!-- productswarm-digest -->
   ```

   The rest of the body doesn't matter: the first `--update` replaces it.
2. Pin it (issue page → "Pin issue").
3. Run `python3 dashboard/digest.py --update --repo OWNER/REPO` once to fill it.

The digest issue isn't a `[heartbeat]` tracking issue or a `gov:question`, so it never appears in the needs-you list itself.

## The wire

Today's governance events, UTC, newest first (`wire.py`, #405, part 6 of #397). They're on the Work map's [tape](#the-strip-and-the-tape) (#1114); the desk's wire panel retired (#1113). Each reads like "09:14 Owner ruled on #396" and is linked. Every item is a template filled from fields (a time, a number, a record ID), never a summary of anyone's text. An item shows once per kind and number, at its earliest time today.

| Item | Text | Events (`activity.py`) | Fallback, already read |
|---|---|---|---|
| question opened | Question #439 opened | `IssuesEvent` `opened`, labelled `gov:question` | the question history (`questions.py`): created today |
| ruling | Owner ruled on #396 | `IssuesEvent` `labeled` `gov:ruled` by the owner | the question history's label events |
| lapse | Question #388 lapsed | `IssuesEvent` `labeled` `gov:lapsed` by the owner | the question history's label events |
| record merged | GOV-0021 merged, answering #396 | `IssuesEvent` `closed` on a `gov:question` that has a record in the checkout | the question history's close events |
| red | Reviewer requested changes on PR #438 | `PullRequestReviewEvent` `changes_requested` by `productswarm-reviewer[bot]` | the reviewer's reviews of open PRs |
| committee convened | Committee convened on #311 | not used | the owner's `**Convening a committee**` comment (`committees.py`) |

A record's merge is read from its question closing (the record PR's `Closes #N`), because the events API's merge event carries no title or files. It counts only when a record in the checkout names that question in its front matter `question:`, and it links the record file. The question history covers only questions created in the window, so the fallbacks miss an older question's ruling or lapse when the events can't be read.

**Planted defect caught** is left out: #331 is closed, and no gate issue posts a fixed result line (such as `**Gate: pass**`) to read. A future gate issue that does can add it.

**API calls added per build:** none of its own. To cover all of today, the header's events read (#402) now also reads on until a page ends before UTC midnight, still at most 3 pages; on a busy day it may read a second or third page where it used to stop at the first.

## What the numbers say

Governance's `#trends` (#406): each one is a sentence and a sparkline, never a bare count. `questions.py` gathers the `gov:question` history once per build ([How the questions went](#how-the-questions-went) reuses it); `trends.py` turns it into sentences and inline SVG.

| Trend | Sentence | Sparkline, one point per UTC day |
|---|---|---|
| Questions per merged PR | "0.8 questions per merged PR this week, down from 1.4 the week before." | questions asked that day ÷ PRs merged that day; a gap on a day nothing merged |
| Median hours to decide | "Median 6.2 hours to decide (14 questions; 2 not decided yet)." | the median hours of the questions decided that day; a gap on a day none was |
| Records a day | "1.3 records a day; none since 3 Nov." (or "the latest today") | records dated that day |

- **The window** is `--days` whole UTC days, today the last (14 by default). "This week" is the last 7 of them and "the week before" the 7 before. A question counts if it was **created** in the window, open or closed.
- **Decided** means the first time the owner (`humans.owner` in `jurisdictions.yml`) added `gov:ruled` or `ready`; failing that, the first time it was closed. Hours to decide run from creation to then. A label someone else added doesn't count (GOV-0006).
- **Sentences are templates filled from numbers** (#397). A direction word ("up from", "down from", "the same as") appears only when both weeks had at least 3 merged PRs, and is chosen from the two rounded figures.
- **"Too few to tell"** under 3 merged PRs this week, decided questions or records in the window. With one or two values a ratio or median moves by half or more when one more arrives, so it can't show a trend; 3 is the smallest count with a middle value. The trend's `too_few` is then true and its line is grey.
- **Sparklines** are inline SVG with no axes or labels, scaled to the series' own maximum. Each has `role="img"` and a `<title>` and `aria-label` listing every day's value as its text alternative.

**API calls added per build (#392):** 1 REST call per 100 questions updated in the window (the `issues?labels=gov:question&state=all&since=` list), 1 search call per 100 PRs merged in the window (`search/issues`, which has its own rate limit), and 1 GraphQL query per 25 questions for their label and close events (`timelineItems`). Record dates come from the checkout. Against this repo on 2026-11-05: 35 questions and 103 merged PRs in 14 days took 1 REST page, 2 search pages and 2 GraphQL queries, from 3 `gh` invocations (the whole rebuild: 47). Only the page reads these (`fetch(..., with_questions=True)`); `swarm inbox`, `swarm watch` and the digest don't.

## How the questions went

Governance's three breakdowns of the questions created in the window (#407), under the trends, each a templated sentence and a stacked bar of counts, e.g. "Decided by: the owner 9, a committee 1, lapsed 2, still open 3." `questions.went()` reads the same history as [What the numbers say](#what-the-numbers-say), plus the decision records in the checkout (`committees.records()`) and which questions a committee Discussion serves.

- **Asked by:** **the owner** if the owner opened it, or the first word of its `### Raised by` is "owner" or the owner's login (so #396, opened by a bot with "owner (drafted by the coordinator)", is the owner's); otherwise **agents** for a `productswarm-*[bot]` author, else **someone else** (shown only when there is one).
- **Decided by**, the first that fits: **a committee** if a committee Discussion serves it or its record's `shape:` is `committee`; **the owner** if the owner added `gov:ruled` or `ready` or it has a record; **lapsed** if it carries `gov:lapsed`; **the owner** if it was closed; otherwise **still open**.
- **Became:** **a record** if a file in `governance/decisions/` has `question: "#N"`; **direction only** if the owner added `gov:ruled` or `ready` and there's no record (not precedent, GOV-0006); otherwise **nothing yet**.

A label only counts if the owner added it, as for the trends. The bar repeats the sentence, so it is `aria-hidden`.

**API calls added per build:** none beyond [What the numbers say](#what-the-numbers-say)'s. The author, body and labels come with the questions list it already reads.

## What it reads

- **Sessions:** `[heartbeat]` tracking issues (GOV-0003). An issue counts only if its body starts with the heartbeat marker and it was opened by a `productswarm-<role>[bot]` App. Events are read from the first `jsonl` fence of comments **by that same App**; events whose `session_id`, `role` or `repo` don't match the issue, or that carry fields outside the remote schema (such as `prompt`), are dropped. The local spool is never read, so prompt text never reaches the page (GOV-0002).
- **Open PRs** and the issues they close.
- **`gov:question` issues**: the open ones, with the sessions blocked on each, and `gov:lapsed` ones closed within `--days`.
- **The `gov:question` history** for [What the numbers say](#what-the-numbers-say): every question created in the window, its label and close events, PRs merged in the window, and each record's front-matter `date:` from the checkout.
- **`governance/INDEX.md`** and **`governance/jurisdictions.yml`**, from the checkout the page is built in (`dashboard.yml` checks out `main`).
- **The repo's public events**, 1 to 3 pages, for the [header](#header)'s owner line.
- **Reviewer workflow runs and jobs** from the Actions API, and the reviews and commits of the PRs they reviewed (see [Actions reviewer](#actions-reviewer)). Never job logs.
- **Committee Discussions** (`committees.py`, #353): every Discussion in the "Committees" category, through `gh api graphql`, plus the `gov:question` each one serves (from a `<!-- productswarm-committee question=N -->` marker, else the `Committee for #N:` title) and that question's record in `governance/decisions/` (front matter `question: "#N"`). Members come from the `## Members` or `### Members` table, the post order from rule 1 under `Rules`, and round posts are top-level comments headed `Round N: <seat>` by that seat's App. From each post it keeps only the round, seat, author, time, link, signature model, the first bold phrase of its Recommendation and the first sentence of its Position (#404). From the owner's comments on the question it keeps only whether the convening, summary and ruling comments exist, when, and their links, so no cost line or other text reaches the page. It derives status (convened, round N, summary, ratified, record), §7.2 diversity, the next seat, rounds used of 3 and posts per member per UTC day against §8's 6. A Discussion that doesn't match #314's layout shows as "unparsed". A token that can't read Discussions gives a note and the rest of the page still builds. Only the page reads these (`fetch(..., with_committees=True)` in `main()`); `swarm inbox`, `swarm watch` and the digest skip the GraphQL calls. The page shows them in the Committees section below.

## Governance

`governance.py` builds this section (#355). It replaced the page's old "Open gov questions" table and still shows everything that table did.

- **Decision log:** Governance's `#rulings`, every row of `governance/INDEX.md`, newest first (#401; `governance.rulings()`). Each row shows the ID (linked to its file), the one-line ruling, domain, shape, status and review-by date. A record whose review-by date has passed is marked "review date passed", because it is not precedent until someone re-affirms it (GOVERNANCE.md §6). One due within 30 days is marked "review due soon". The index itself is a link.
- **Open gov questions:** a line of counts by shape and by domain, then one row per question. Each row shows its labels, its domain (`### Domain` in the template body), and its shape: an owner's `gov:shape/*` label if there is one, otherwise the body's `### Suggested shape`, marked "suggested". It also shows whether the question is blocking (the `gov:blocking` label or a "yes" under `### Blocking?`), its age, its time to live with days left or "past TTL", and the sessions waiting on it.
- **Lapsed questions:** questions labelled `gov:lapsed`, open, or closed within `--days`, each with its time to live. A muted line notes that a lapsed default is not precedent (GOVERNANCE.md §8).

The needs-you list and its past-TTL flag don't change. This section is for reading, not for acting on. It needs no new token permission: the index comes from the checkout, and the questions come from the issues the page already fetches.

## Precedent in use

On Governance's `#precedent`, `precedent.py` (#408, part 9 of #397) counts how often each GOV record is cited, as a grid of records (newest first) by UTC day over the page's window (from the first record's date, if that's later), then each record's total, by agents, by the owner and **by reviewer**. The grid scrolls in its own box at phone width.

- **A citation** is a `GOV-NNNN` mention in an issue or PR body, an issue or PR comment, a PR review, or a PR review comment, created in the window. A text cites a record once, however often it names it. It counts only on or after the record's front-matter `date:`, and only for a record in `governance/decisions/`; the cell for a day before the record was made is blank.
- **Left out:** signature lines (`-- builder (claude-opus-5-5)`), tracking issues, the pinned digest issue, and review comments on files under `governance/`.
- **Who:** agents are `productswarm-*[bot]`; the owner is `humans.owner` in `governance/jurisdictions.yml`; the reviewer column is `productswarm-reviewer[bot]`, which also counts as an agent. Anyone else counts only in the total.
- **Findings** are templates filled from the counts: the newest in-force record's citations on its first day ("GOV-0021, the newest record, was cited 27 times on its first day (2026-11-04) and 30 in all."), the share by agents and by the owner, and the in-force records not cited in the window.

**Cost.** Bodies come with the issue list the page already reads. Comments are `issues/comments?since=` and `pulls/comments?since=`, 100 a page, and reviews are one GraphQL query per 25 PRs updated in the window. Reading the whole 14-day window took 9 REST calls and 5 GraphQL queries on 2026-11-05 (8 pages of issue comments), and grows with traffic. So each build fetches the last published `state.json` from the Pages URL (not the API), keeps its counts for the days before its build day, and reads only from the start of that day: 2 REST calls and 1 GraphQL query. It reads the whole window when there's no published copy, its `precedent.version` differs, or it doesn't reach back to the window's first day. A comment created before that day but edited later isn't counted again.

## Committees

`committees.render()` draws the committees `committees.py` reads (#354). On Governance's `#committees` (#1113), open committees, with the unparsed and read-problem lines (`part="open"`), follow the [committee desk](#committee-desk). Committees that ended (record merged, or the question closed) follow the [past committees](#past-committees)' cards, in a collapsed "Round grids of the N ended committees" `<details>` (`part="ended"`). With no committees the section says "No open committees."; with none ended, there's no "Past committees".

For each committee:

- **Header:** the question, linked with its title, and the Discussion, then the timeline: convened → round 1 … round N → summary → ratified → record GOV-NNNN. Each step reached is dated and linked to its comment, round post or record file. The current step is bold and the steps not reached yet are muted.
- **Members:** seat, role, model and evidence base from the Discussion's table, then "§7.2 diversity met: 2 models, 3 evidence bases" (or "not met").
- **Round grid:** a row per member and a column per round. Each cell links to the post, shows its time (UTC) and that post's recommendation phrase. If a post's signature names another model than the table, the cell says "signed <model>". The next empty cell says "waiting on <seat>", which can open a new round's column. Before a summary, a post the reader counts as missed says "missed". Once a summary exists, the cells of rounds that never ran say "stopped early" if rule 6 stopped the committee. Other empty cells stay blank. The grid scrolls in its own box at phone width.
- **Last line:** convergence ("all agree after round N" when every member's last-round phrase matches; otherwise "dissent: <seats>" for the seats whose latest phrase differs from the majority's, or "no majority"), "rounds used: N of 3" (§7.4), and "nobody over 6 posts a day" or a red "over 6 posts a day" with the seat, count and UTC day (§8).

Phrases are compared as text, ignoring case and spacing. So #314 shows "dissent: proposer": its round-2 phrase is "Option 3 as 3c" and the other two say "Option 3 as 3c+E".

Discussions that don't match #314's layout are listed as muted "Unparsed" links. Read problems ("can't read Discussions", a question that couldn't be read, a marker that disagrees with the title) go on one muted line. A repo with no Committees category shows nothing. The section shows no cost and no post or summary text beyond each recommendation phrase.

## Committee desk

`committees.desk()` draws each open committee at the top of Governance's `#committees` (#404), styled like an election-night desk. With no open committee there's none of it. It reads only what `committees.build()` derives, so it adds no API calls.

- **Band** (dark): a red "LIVE" mark, "Committee", the question (linked, with its title), "Round N of 3" (the round the next post belongs to), "waiting on <seat>" (or "rounds over" once no seat is due) and the Discussion's link.
- **A card per seat:** seat, role and model; the seat's latest recommendation, large (the Recommendation section's first bold phrase, from `phrase()`; "no recommendation yet" without one); its swing from its previous post, "moved from <phrase>" or "held" (nothing on its first post); the first sentence of its **Position** section in quotes, as written (only emphasis and code marks dropped), cut at a word break to about 140 characters ("no Position section" without one); and a link to the post with its round and time. The seat that's up next has a blue top edge.
- **Consensus bar:** how many seats share the most common latest recommendation, as "k of N"; "k of N · converging" when that number rose since the end of the previous round; "consensus" when every seat's latest phrase matches. Phrases compare as text, ignoring case and spacing, like `same()`. So #314 reads "1 of 3" after round 1 and "2 of 3 · converging" after round 2.

Red is used only for the LIVE mark. The same data is `committee_desk` in `state.json`.

## Past committees

`committees.past()` puts a card per ended committee (record merged, or its question closed) on Governance under "Past committees", newest Discussion first (#409). With none ended there's no heading. The full round grids follow the cards, collapsed. It reads only what `committees.build()` derives and the INDEX.md rows the governance section already parses, so it adds no API calls.

- **Record:** its ID, linked to the file, or "no record yet".
- **Summary:** the record's one-line ruling from `governance/INDEX.md`, quoted as it stands there. Nothing is written for the card. Without a record it says "no ruling recorded"; with a record that has no INDEX row yet, "not in governance/INDEX.md yet".
- **Consensus:** "consensus after round N" when every seat's last-round phrase matches, else "dissent: <seats>" (or "no majority after round N"), from the same comparison as the Committees section's last line (`outcome()`).
- **Numbers:** rounds used of 3 (and "stopped early" if rule 6 stopped it), the members' models and whether §7.2 was met, whole minutes from the first round post to the last, and the swing: how many seats changed their recommendation between any two of their posts.

So #314's card reads GOV-0021, "dissent: proposer", 2 of 3 rounds, two models (§7.2 met), and a swing of 3 of 3 seats. The same data is `past_committees` in `state.json`.

## Authority map

`authority.py` draws Governance's `#authority` from `governance/jurisdictions.yml` in the checkout (#410; `authority.html` until #1113). It's reference, not live data, so it isn't in `state.json` and adds no API calls.

- **One row per domain**, in file order: its name, description and note (and "always one-way" where the file says so), who decides (agents in blue, the owner in amber, "nobody: ask" when `decide` is empty), the owner, who ratifies, who is vote-eligible and the default shape. An identity reference the file's `identities` doesn't list shows as written, in grey.
- **Records:** the domain's in-force rows of `governance/INDEX.md` (the same rows the governance section parses), counted and linked to the decision log (`#rulings`), with those past their review-by date named.
- Above the table, the file's `quorum` and `consent_window`; below it, any domain an in-force record names that the file doesn't list.

It's stdlib only, so `authority.read()` understands just this file's shape: nested `key: value` mappings, `[a, b]` lists, quoted strings and comments. Anything else (block lists, block scalars, odd indents, duplicate keys) or a domain without `owner` or `default_shape` makes the page say "can't read governance/jurisdictions.yml" and draw no table, rather than guess. `test_authority.py` fails if any domain in the real file is missing from the page.

## Actions reviewer

`reviewer_runs.py` builds Crew's `#reviewer` (#356). It covers the last 7 days:

- **Sweeps:** runs of `reviewer.yml` (the newest 15 at most, #392), each with when and how it started (`schedule`, `nudge` for a `workflow_dispatch` by `github-actions[bot]` from `reviewer-nudge.yml`, or `manual (<login>)` for a person's dispatch), its conclusion, and the `review #N <sha>` jobs it ran (`REVIEW_JOB` in `launcher/actions_review.py`). A successful sweep with no review jobs says "nothing to review".
- **Success rate:** "N of M review jobs succeeded", counting finished review jobs, not sweeps, and listing the ones that didn't succeed.
- **Commit to review:** for each head the reviewer App reviewed in the window, the time from that commit's committer date to the App's first review of it; the median and the longest. GitHub doesn't give push time, so this is commit time. A review counts for the commit it was made on, never for a later head.
- **Unreviewed builder heads:** a count of the builder PRs `unreviewed()` flags, linked. They're in the needs-you list too.

Only the page reads it (`fetch(..., with_actions=True)` in `main()`): `swarm ls`, `swarm inbox`, `swarm watch` and the digest make no Actions API calls. It reads run, job, review and commit metadata only. It **shows no cost** and never fetches job logs, where GOV-0016 puts `total_cost_usd` (#348). It needs `actions: read` on the workflow's token; without it the section shows one muted line ("can't read Actions runs: the token needs `actions: read`") and the rest of the page still builds.

## Status

Per [heartbeat/SCHEMA.md](../heartbeat/SCHEMA.md):

| Status | When |
|---|---|
| stopped | latest event is `stopped`, or the tracking issue is closed |
| blocked | latest event other than `heartbeat`/`prompt_submitted` is `blocked`, and its gov question is still open |
| idle | no event for more than 15 minutes |
| active | otherwise |

A session's current issue is the most recent `issue` any of its events carried.

## Spend

Each session's spend in Crew's sessions table is an **API list-price equivalent**, per the method in gov question #28. The owner asked for tokens to be split by payment plan if a session can tell. It can't without a new heartbeat field (#31), so every session is priced at list price whatever its plan. `spend.py` multiplies each session's latest cumulative `token_counts` by the model's list price. Cache writes are priced at the 1-hour rate. A non-null `cost_usd` on an event wins over the estimate. This isn't what was billed: sessions on a subscription aren't charged per token.

There's no spend per day, "spent today" or other total (GOV-0033; removed in #1113). The same prices give the Work map its costs (`swarm map`).

Prices are in `spend.PRICES`, copied from the [pricing page](https://platform.claude.com/docs/en/about-claude/pricing) on the date in `PRICES_AS_OF`, which Crew shows. When prices change, update both. Sessions with no token counts, or on a model missing from the table, show "—".

## Tests

```bash
python3 -m unittest discover -s dashboard
```

They use canned data and a fake `gh`, and never touch GitHub.
