# Retract — submission draft

Status: prepared copy, not submitted. Local runtime/database, live model,
browser, and [fresh coding-client feature](12-FRESH-CLIENT-RUN.md) checks
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
memory. An MCP adapter exposes remember, process_update, recall, history,
record_plan, revise_plan, handoff, and claim_handoff.
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

## Investigator agent: graph reasoning as tools

The **investigator agent** (`retract agent investigate`,
[investigator.py](../src/retract/investigator.py)) runs an autonomous
investigate-and-act loop over the memory graph. Groq `openai/gpt-oss-20b` picks
each step from read-only FalkorDB tools ([analysis.py](../src/retract/analysis.py)):
five detectors, `algo.pageRank` and `algo.betweenness` centrality, a 1–4 hop
variable-length blast radius, `shortestPath` tracing, and `algo.WCC` components.
It acts by handing a plan to the coding agent. Code guards that action: the
finding must be observed, the plan inspected first, and cited facts taken from
the graph. The same tools are the `analyze_graph` MCP tool.

Observed live run (real FalkorDB, real Groq, fresh graph after U1), 8 steps in
24 s, each model call succeeding first time:
1. `findings` returned `stale_plan:P1` and the cross-scope lead
   `cross_scope_drift:F2:U1`.
2. `trace` F2→U1 found no path.
3. The model asked for `findings` again; the repeat guard answered it from the
   notebook.
4. `blast_radius` on P1 returned `(P1)-[:DEPENDS_ON]->(F1)` and
   `(U1)-[:FLAGGED]->(P1)`.
5. `handoff` created `investigate-5d2f0c5e5da59453` for codex.
6. `handoff` on the F2 lead was rejected ("no live plan to hand off; report it
   instead").
7. `overview`.
8. `finish`.

In an earlier run the model tried to hand off before inspecting P1, and the
guard rejected it. A playbook re-run skipped P1 because it already had an open
handoff. A real Codex session given only `analyze_graph` and `history` ran
findings, blast radius, trace and PageRank. It reported
`F5 -[SUPERSEDES]-> F1 <-[DEPENDS_ON]- P1`, and resolved the F2 lead from the U1
source ("CLI authentication is unchanged"). Traces are in
[evidence/investigation-20261018](evidence/investigation-20261018). With the
reviewer's handoff already open, a live investigator run skipped P1 ("already
has a open handoff (review-e3cb279fb1df4915, codex)"), so the two agents did not
duplicate work.

## Coordination between agents

Two agents share one graph memory. The **reviewer agent**
(`retract agent review`, [agent.py](../src/retract/agent.py)) recalls flagged plans,
follows `DEPENDS_ON` and `SUPERSEDES` to see which dependency was replaced,
drafts a revised plan with Groq that may cite only current facts, and hands it
to the **coding agent** (Codex over MCP). The coding agent claims the handoff,
confirms the revision with `revise_plan`, implements it, and runs tests. The
reviewer never applies a revision itself; confirmation stays with the developer
and coding session.

Observed live run (real FalkorDB, real Groq `openai/gpt-oss-20b`, real MCP
stdio): correction U1 retired F1 and flagged P1; the reviewer reported "P1
depends on F1 (browser-api authentication), replaced by F5" and handed off a
draft citing F4 and F5; the MCP client recalled it, claimed it as `codex`, and
revised P1 to P2; recall then showed no affected plans, and a reviewer re-run
found nothing to do. The coding-client step in that run was a scripted MCP
client, not a Codex session.

The `handoff` and `claim_handoff` MCP tools let one agent leave scoped work for
another. A `Handoff` node `CONCERNS` a plan and `CITES` the facts the sender
relied on; `recall` lists open handoffs. On claim, the service follows
`SUPERSEDES` and `REVISES` paths and warns the receiver when a cited fact was
replaced or the plan was revised after the handoff was written. Only one agent
can claim a handoff.

`python scripts/stress_concurrency.py` exercises one service process over HTTP
against a disposable FalkorDB graph. A local run, kept out of git under
`reports/`, recorded 400 concurrent requests across two
projects (200 writes, 200 reads) with zero failures, zero lost writes, and zero
cross-project leaks; 24 writers racing on one stale revision produced 1 accept
and 23 conflicts; 24 agents claiming one handoff produced exactly 1 winner.
Writes are serialized within the process and guarded by the project revision;
this is a correctness result under contention, not a horizontal-scaling claim.
Hosted mode stores each signed-in account in a separate graph.

## Why the graph is central

`SUPPORTS` records evidence, `SUPERSEDES` preserves replacement history, and
`DEPENDS_ON` identifies affected plans. Updates retain `BASED_ON`, `RETIRED`,
`ACCEPTED`, and `FLAGGED` paths that explain the result. The runtime uses
FalkorDB as its authoritative store and has no in-memory substitute when it is
unavailable. The test-only model is not a production fallback.

See the [data model and actual-query guide](11-GRAPH-QUERIES.md),
[query implementation](../src/retract/graph.py), and [policy](../src/retract/policy.py).

## Running and evidence

Follow the [README](../README.md) for Python/Docker setup, explicit seed, service
startup, dashboard, and client connection. Structured updates need no model key.
The configured local addresses are memory API/UI `127.0.0.1:8100`, FalkorDB
`127.0.0.1:6380`, and the separate synthetic account API `127.0.0.1:8101`.

Run `python scripts/verify_phase5.py` for fresh offline evidence and
`python scripts/verify_phase5.py --live` for the prepared live checks after
installing dependencies and configuring Groq/PostgreSQL. The
[evaluation guide](10-EVALUATION-AND-RELEASE.md) defines measurements and the
[storyboard](02-DEMO-AND-EVALUATION.md) defines the planned working demo.
No hosted deployment, genuine demo video, complete live benchmark, or comparative
advantage is claimed here. Actual current observations are in the
[implementation record](06-IMPLEMENTATION-STATUS.md).

## Data, dependencies, and AI assistance

All committed fixture content and demo accounts are synthetic. Direct runtime
and development dependencies, license references, and related memory projects
are listed in [THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md).
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
