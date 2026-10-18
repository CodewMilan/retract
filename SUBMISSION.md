# RETRACT — submission draft

Status: prepared copy, not submitted. Local runtime/database, live model,
browser, and [fresh coding-client feature](docs/12-FRESH-CLIENT-RUN.md) checks
have passed. Working-video, publication, and final submission review remain
pending. Older checklist entries below must be reconciled with the verification
record before submission.

**Track:** Agent Memory and Coordination.

**One line:** Project memory that preserves why a decision changed and shows
which recorded plans need review.

## Problem and user

Developers reuse coding assistants across sessions while project decisions
change. An old instruction can remain in memory without a clear indication that
it was replaced. RETRACT is for individual developers and small teams who need
scoped current context, evidence, and an explanation of affected plans.

## What the project implements

A local Python service stores project facts, sources, updates, and explicit plan
dependencies in FalkorDB. A confirmed authoritative correction supersedes the
matching active fact, preserves its evidence/history, and flags plans linked to
that fact. Proposals and ambiguous or unconfirmed changes stay outside accepted
memory. An MCP adapter exposes remember, process_update, recall, and history.
A neutral browser dashboard displays the same service state and actual API
request metadata. Optional Groq extraction feeds the same deterministic policy.

In the synthetic example, browser authentication changes from bearer tokens to
HTTP-only cookie sessions. The expected graph transition replaces F1 with F5
and flags P1 while preserving CLI authentication, PostgreSQL, and profile
ownership. The actual backend for the fresh coding exercise already exposes a
cookie/CSRF/ownership contract. Its settings frontend is now implemented, with
passing controlled HTTP/client checks. A fresh coding-client recall/construction
run, real browser behavior, and PostgreSQL-backed feature checks remain
unverified integration steps.

## Why the graph is central

`SUPPORTS` records evidence, `SUPERSEDES` preserves replacement history, and
`DEPENDS_ON` identifies affected plans. Updates retain `BASED_ON`, `RETIRED`,
`ACCEPTED`, and `FLAGGED` paths that explain the result. The runtime uses
FalkorDB as its authoritative store and has no in-memory substitute when it is
unavailable. The test-only model is not a production fallback.

See the [data model and actual-query guide](docs/11-GRAPH-QUERIES.md),
[query implementation](src/retract/graph.py), and [policy](src/retract/policy.py).

## Running and evidence

Follow the [README](README.md) for Python/Docker setup, explicit seed, service
startup, dashboard, and client connection. Structured updates need no model key.
The configured local addresses are memory API/UI `127.0.0.1:8100`, FalkorDB
`127.0.0.1:6380`, and the separate synthetic account API `127.0.0.1:8101`.

Run `python scripts/verify_phase5.py` for fresh offline evidence and
`python scripts/verify_phase5.py --live` for the prepared live checks after
installing dependencies and configuring Groq/PostgreSQL. The
[evaluation guide](docs/10-EVALUATION-AND-RELEASE.md) defines measurements and the
[storyboard](docs/02-DEMO-AND-EVALUATION.md) defines the planned working demo.
No hosted deployment, genuine demo video, complete live benchmark, or comparative
advantage is claimed here. Actual current observations are in the
[implementation record](docs/06-IMPLEMENTATION-STATUS.md).

## Data, dependencies, and AI assistance

All committed fixture content and demo accounts are synthetic. Direct runtime
and development dependencies, license references, and related memory projects
are listed in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
OpenAI Codex assisted with implementation, tests, and documentation. The
participant must review and understand the graph model, code, and actual results.
This is a focused implementation of established memory/invalidation ideas,
without a claim of inventing them.

## Evidence required before submission

- [ ] Confirm a public repository URL and access from a signed-out browser.
- [ ] Run the real graph/integration/restart gates and inspect the metric report.
- [ ] Run live model evaluation, or clearly disclose the structured-only fallback.
- [ ] Observe the real coding client's recall and inspect generated feature tests.
- [ ] Run dashboard browser checks and the live service smoke check.
- [ ] Record and link the actual working demo; disclose any shortened waits.
- [ ] Review source and recording data, dependency notices, and project licensing.
- [ ] Review claims against the exact evidence bundle and submit through the event form.

The [official Graph Hacks rules](https://www.wemakedevs.org/hackathons/falkordb/rules)
were rechecked on 17 October 2026. The stated deadline is 18 October 2026,
11:59 PM IST. No form has been submitted or public resource published by this work.
