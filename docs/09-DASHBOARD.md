# Phase 4: memory dashboard

The local Python service serves the dashboard at `http://127.0.0.1:8100/dashboard`.
`http://127.0.0.1:8100/` is the marketing page.
Start it with `retract serve` after following the root README's database setup.
The dashboard is included as package data; it needs no Node process or frontend
build at runtime. Node and Playwright are development test tools only.

## Available workflow

Select a project and optionally filter by **Area** (the API's exact `scope`).
The primary views are **Memory**, **Plans**, **Needs review**, and **Handoffs**.
**History & activity** contains suggestions, previous decisions, change history,
and API activity. Search filters loaded records; `/` focuses it. Project, area,
view, and search are kept in the URL and survive reload and browser Back.
Selecting a record opens its source, status, and linked plans. Technical details
disclose stored IDs and graph paths. Details open beside the list on wide screens
and in a keyboard-accessible dialog on smaller screens.

Create a project by name; its agent-facing identifier is generated and can be
edited in the optional details. Use **Add memory** to enter a topic, decision,
source, and explicit approval. The area defaults to `project/main` (or the active
area); property and source name have editable defaults under organization details.
An unfinished memory draft survives dismissing and reopening the form in the same
project and area, in page memory only. No fixture is automatically inserted.
**Update this decision**, in the detail panel, targets a currently accepted key:

- Exact replacement and change type are the default, without a model dependency.
- Optional AI interpretation is under **Advanced options**. The service needs
  `GROQ_API_KEY`; submitted text and the selected fact are sent to Groq. No key
  is sent to the browser.

Authority and replacement confirmation start unchecked. A proposal, ambiguous
update, untrusted source, or unconfirmed correction cannot replace accepted
memory. The result panel displays the service's actual outcome, before/after
values for applied updates and a direct action to review affected plans. IDs and
relationships remain available in record details. Facts are
refetched after a successful write. A failed refresh disables further writes.

Changed drafts receive new event/source IDs. An unchanged update retry preserves
the exact request IDs and body, allowing the existing event replay contract to
handle a lost response. A revision conflict preserves the draft; **Refresh
context** rereads the current decision and clears replacement confirmation.
Review and confirm again before creating the new request. Remember-fact retries
also preserve their IDs, but a lost successful response may require a refresh
because that endpoint checks revisions before duplicate evidence.

Pending/proposal records are immutable events. To accept a reviewed candidate,
record a new update against the current fact; there is no destructive “approve
old event” operation. The dashboard does not resolve an affected plan or change
its dependencies automatically. **Review and revise plan** shows current decisions
to select, requires a reason and confirmation, and preserves the previous version.
Still-current linked decisions from another area remain selectable.

**Connect an agent** is available in both modes. Local mode provides an MCP
configuration and a project-specific prompt. Hosted mode creates revocable keys,
offers copyable configuration, clears one-time secrets when the dialog closes,
and requires a second click to confirm revocation. Closing a dialog is disabled
while its save is in progress.

## Read and activity contracts

- `GET /api/projects` returns up to 100 projects and a truncation flag.
- `POST /dashboard` accepts `project_id` and optional `scope` (null means all).
  It returns project revision, observation time, facts, events, affected plans,
  actual counts, evidence edges, explanation paths, available scopes, and request
  activity. Reads share the service lock and never change project revision.
- Each panel loads at most 200 records. Recent updates and pending/proposals
  have independent limits, so older pending records are not hidden by recent
  applied updates. Edges and explanation paths each cap at 1,000, scopes at 200.
  Truncation is explicit in both the response and UI. Counts are database totals
  for the selected scope; search operates on loaded records only.
- Source nodes and relationship endpoints are restricted to the selected project.
  Relationships may expose the exact scope of a dependency within that project.
  Replay fingerprints and internal serialized result fields are removed.

The graph reader uses the documented [`labels`, `type`, and `properties`
functions](https://falkordb.github.io/docs-staging/cypher/functions/). Query design
and controlled tests are not evidence that the chosen database image executes it;
the opt-in integration test remains required.

Request activity is an actual HTTP request metadata journal, capped at 200
entries for the service and 50 displayed per project/filter. It records route,
status, elapsed milliseconds, project/scope/event IDs, and caller label. It does
not retain raw source text, credentials, request bodies, or exception messages.
The MCP adapter supplies `X-Retract-Client: mcp`; the dashboard supplies
`dashboard`. Labels are caller-supplied, not authenticated proof of a coding
client's identity or task completion. Activity clears on service restart;
durable update history stays in FalkorDB. Dashboard reads, static files, and
health probes do not fill the activity journal.

## Interface and serving

The interface uses locally served fonts, neutral surfaces, and a light theme.
Secondary navigation collapses behind a Menu button on phones. Controls have
visible labels and focus styles; dialogs use native focus handling and Escape.
Request errors preserve inputs, empty states have explicit wording, and motion
is disabled under reduced-motion preferences. Source text is inserted with
`textContent`, never interpreted as HTML. Static paths are allow-listed and sent
with a restrictive same-origin CSP. Existing loopback Host/Origin checks apply.
No external fonts, scripts, telemetry, or assets are requested by the dashboard.

## Verification

```sh
python scripts/verify_phase4.py
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

Real Chromium interaction checks with controlled network responses:

```sh
npm install --ignore-scripts
npx playwright install chromium
python scripts/verify_phase4.py --browser
```

The browser suite covers 375/768/1024/1440-pixel layouts, reduced-motion settings,
source HTML escaping, filtering, missing model configuration, proposals,
corrections, stale retries, graph paths, storage errors, project creation, and
remembering a fact, generated identifiers, draft recovery, local agent setup,
URL state, browser Back, and keyboard controls. A separate hosted connection
suite checks clipboard, secret cleanup, and key revocation. It captures screenshots under
`reports/phase4/browser/` when it can run. These are UI checks with controlled
responses, not database evidence. CI is configured to run them.

With an actual running and seeded service, add a read-only browser smoke check:

```sh
python scripts/verify_phase4.py --browser --live-url http://127.0.0.1:8100/dashboard
RUN_FALKORDB_TESTS=1 python -m unittest tests.test_integration -v
```

The real graph suite now includes dashboard counts, replacement edges, isolation,
and cross-scope explanations. It is also part of the existing Phase 1 runner.

For the current usability pass and its browser/database evidence, see
[the usability review](13-USABILITY.md). The following describes the initial,
historical Phase 4 run, not the current interface validation.

Initially observed: 12 Phase 4 Python checks and 7 JavaScript checks pass. The complete
Python suite passes on Python 3.12 and 3.14: 135 passed, 16 explicitly skipped
(13 FalkorDB, 2 PostgreSQL, 1 MCP SDK). Chromium launch failed before any UI
scenario due to the sandbox's denied Mach-port registration; browser screenshots,
layout, keyboard interaction, and live dashboard behavior remain unverified.
Offline wheel building was also unavailable because the installed Python lacks
setuptools; CI includes a wheel asset check. Reports are
`reports/phase4-offline.json` and `reports/phase4-browser-attempt.json`.
The phase's actual-state/browser exit gate remains open, along with earlier
live database, model, and coding-client gates.
