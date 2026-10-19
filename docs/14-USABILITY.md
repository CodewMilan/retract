# Usability review — 19 October 2026

This pass used the repository's UI/UX Pro Max skill, a browser walkthrough of the
existing dashboard, automated interaction checks, and full workflows against an
isolated FalkorDB graph. It is a heuristic and functional review, not a study with
recruited users. The existing HTML, CSS, and JavaScript stack is retained.

## Problems and changes

| Friction observed | Implemented behavior |
| --- | --- |
| Eight equally prominent navigation choices exposed internal concepts. | Four primary destinations: Memory, Plans, Needs review, Handoffs. Suggestions and historical/diagnostic views sit under History & activity. |
| The phone layout placed the full project navigation above the work. | A compact top bar opens navigation on demand. Memory is visible immediately. |
| Four competing header actions made the next step unclear. | Add memory leads the memory view; New plan leads plan views. A decision's own detail panel offers its update action. |
| An empty inspector consumed space before anything was selected. | The list uses the available width. Selecting a record opens an adjacent panel on wide screens or a native dialog on smaller screens. |
| IDs and raw graph edges dominated detail panels. | Decisions, sources, linked plans, and status appear first. Stored IDs and exact relationship paths remain under Technical details. |
| Creating a project required a name and a technical ID. | A name generates the ID. An optional disclosure allows an explicit override. |
| Adding memory exposed six text fields at once. | Start with topic, decision, and source, plus explicit approval. Area, property, and source name have editable defaults. |
| The default update path required AI provider configuration. | Exact replacements work by default. AI interpretation is optional under Advanced options. Suggestions do not expose replacement confirmations. |
| Initial empty states described missing records without making setup easy. | Create-your-first-project and add-your-first-memory actions lead directly into the relevant form. Each other view explains its empty state. |
| Saving produced technical outcomes without a clear next step. | Plain-language confirmations show the actual result, before/after values, and a direct review action when plans were affected. |
| Navigation and filters disappeared on reload; dashboard query URLs returned 404. | Project, area, view, and search are preserved in the URL. Reload and browser Back work, with dashboard query routes explicitly supported. |
| Local users had no visible agent connection flow. | Both modes expose Connect an agent. Local mode supplies configuration and a project-specific prompt; hosted mode manages access keys. |
| An unfinished memory form was lost on dismissal. | Its values survive reopening within the same project and area in the current page. They are cleared after saving and isolated when changing project/area. |
| Access keys could be revoked with one accidental click. | Revocation has explicit confirm and cancel actions. One-time secrets and configuration are cleared on dialog close. |

The visual direction uses quiet neutral surfaces, the existing orange accent,
consistent type hierarchy, and stable button shapes. Marketing-oriented search
recommendations from the skill were not applied to the workspace. No UI framework
or runtime dependency was added.

## Verification

- **Controlled browser workflows:** 375, 768, 1024, and 1440 px. Source escaping,
  search, suggestions, corrections, revision-conflict recovery, graph paths,
  storage errors, first-run setup, generated IDs, draft recovery, local connection,
  URL state, browser Back/reload, keyboard shortcuts, and horizontal overflow.
- **Hosted connection workflows:** 375 and 1440 px with controlled identity/API
  responses. Authorization headers, key creation, clipboard content, secret
  cleanup, revocation confirmation, and cancellation.
- **Real database journeys:** 375, 768, 1024, and 1440 px against a separate local
  graph. Create project → save memory → link a plan → replace the decision → review
  and revise the affected plan → verify sources → reload a filtered URL. Final
  snapshots confirm one current and one replaced decision, one current and one
  previous plan, and no unresolved review after revision.
- **Accessibility:** axe scans of memory, add-memory, decision details, update,
  and local connection at 375, 768, and 1440 px, using WCAG A/AA tags through 2.2.
  A keyboard-inaccessible configuration scroller was fixed with a focusable,
  named region. These 15 checked states report no automated violations. Keyboard
  focus, Escape, mobile navigation, and native dialog behavior were also exercised.
- **Regression checks:** 23 JavaScript tests passed. Python discovery ran 224
  tests: 187 passed, 37 explicitly skipped. Syntax checks and `git diff --check`
  passed. Skipped integrations are not counted as passing.

The real workflow runner only accepts a local HTTP URL and creates synthetic
projects. Run it against an isolated graph, never an existing user's workspace:

```sh
FALKORDB_GRAPH=retract_ux_review retract serve --port 8111
# In another terminal:
npm run test:journey -- http://127.0.0.1:8111
```

Regular browser checks use controlled responses and need no database:

```sh
npm run test:browser
```

Browser screenshots, journey snapshots, and accessibility output from this run
are in `reports/ux-review/`. The comparison page is `reports/ux-review/index.html`.
Reports are intentionally git-ignored. Hosted key tests use a simulated identity;
this pass does not claim a fresh real-provider sign-in or OAuth completion.
