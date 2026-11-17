---
id: GOV-0051
title: The Desk may run a first-party client-side app, with vendored and pinned third-party libraries
status: in-force
kind: ruling
question: "#1102"
domain: security
shape: authoritative
classification:
  reversibility: one-way
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
    - building or changing the Desk's Work map (FEAT-12, FEAT-13) or any Desk page that runs JavaScript
    - deciding whether the Desk may load a script or library, or fetch data in the browser
    - adding a third-party front-end library to the Desk
---

## Ruling

The Desk may run a client-side app made of this repo's own scripts plus vendored, pinned third-party libraries, in place of #396's one small inline script. The rules:

- Scripts are served as same-origin files beside the pages, each allowed by hash in the Content-Security-Policy (`script-src 'self'` plus hashes, `connect-src 'self'`).
- The browser fetches only same-origin JSON the build already publishes (`state.json`, `map.json`). It holds no token and makes no GitHub API calls.
- No `eval`, no `new Function`, and no `innerHTML` built from repo text; text goes in as text.
- Each third-party library (for example d3 for the treemap layout and transitions) is pinned to an exact version and vendored into the repo, so the site loads nothing from a CDN or any other third party. It is added in its own PR in the `dependencies` domain that states the version, licence, size and why it is needed, and the build checks it against a recorded hash. A further library needs such a PR, not a new question.
- A page no longer has to be complete with JavaScript off. With it off, a page shows a short notice and links to GitHub. The live refresh and meta refresh may go once the app replaces them.

## Applies when / does not apply when

- Applies when: building or changing Desk pages that run JavaScript, their CSP, their data fetches, or the libraries they vendor.
- Does not apply when: a browser app that calls GitHub or holds credentials (option 4; out of scope until Google login, #752), loading anything from a CDN or other third party, or changing which fields `state.json` publishes (GOV-0002, GOV-0004).

## Context

The owner is making the Work map (M9, #1080) the Desk's home page and retiring the Bridge. The map has lenses, a 1D/1W/1M window and an inspector, specified as FEAT-12 and FEAT-13 in Notion, and the owner wants it built as an interactive app. #396 (option 2, direction, no record) allowed only one small inline script, allowed by its `sha256`, doing a same-origin fetch of `state.json`, with no third-party code and every page complete without JavaScript. Lenses, windows and an inspector that switch in place don't fit that, and pre-rendering a page per lens and window is heavier to build and slower to use. The Desk is public (GitHub Pages and the live Desk), but everything it shows is already public in the repo. #1102 asked. The owner answered "Option 3 confirmed. Record: yes" in a comment on #1102.

## Options considered

1. **Keep #396's limits:** pre-rendered pages per lens and window; nothing new runs in the browser, but more pages per build and slower switching.
2. **A first-party client-side Desk:** own scripts only, same-origin and hashed, no third-party code.
3. **Option 2, plus vendored third-party libraries** (chosen): pinned, vendored, hash-checked, one PR per library. Most capable; adds third-party code to a public page, the supply-chain risk the `security` domain covers.
4. **A browser app that calls GitHub or holds credentials:** fresher data, but per-viewer rate limits, a token in the browser and login. Out of scope until #752.

## Deliberation

n/a. This is an authoritative decision by the owner, who confirmed option 3, the question's recommendation.

## Consequences

- Map work may use JavaScript and vendored libraries. FEAT-12 and FEAT-13 are built to the app variant, not the static one.
- What #396 asked of `poll.js` carries over: no `eval`, no HTML from repo text, same-origin only.
- The "page complete with JavaScript off" requirement from #396 is dropped; the page's notice and GitHub link replace it.
- The team accepts third-party code on a public page, limited by pinning, vendoring, the recorded hash and the per-library PR.
- #396 stays direction only; this record supersedes its limits for the Desk but is not a record of it.
- Expires on 2026-12-15 (the question's time to live) unless re-affirmed.
