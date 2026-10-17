# Implementation and verification record

Recorded 17 October 2026. This file reports actual observations separately from
the proposed behavior in the original specification.

## Implemented code

- Python application service with validated structured inputs and a separate,
  deterministic correction policy.
- FalkorDB repository with parameterized queries for facts, sources, events,
  direct plan dependencies, active retrieval, and replacement history.
- Project revision guards, serialized application writes, immutable source IDs,
  exact event replay, and conflicts for reused event IDs with different payloads.
- Local HTTP adapter and CLI, explicit F1–F4/P1 seed, U1 correction, and U2 proposal.
- Docker Compose configuration with a named data volume and AOF settings.
- Offline policy/application/API-dispatch tests and opt-in real FalkorDB tests.
- HTTP transport tests covering actual request parsing, errors, local-origin
  restrictions, malformed bodies, and unavailable storage, without binding ports.
- A complete Phase 1 runner using an isolated database and volume, real API calls,
  application/database restarts, snapshot comparison without reseeding, and
  post-restart event replay. It checks actual AOF settings and records reports.
- CI configuration for the same complete gate with retained result artifacts.
  It has not been run here.
- Optional Groq natural-language extraction for one selected scoped key, with
  bounded context, strict output validation, exact evidence checks, and the same
  deterministic policy used by structured updates.
- Natural-request replay fingerprints, extraction audit metadata, revision checks
  after inference, and explicit timeout/rate-limit/provider error responses.
- A Phase 2 runner and a 16-case declared live evaluation set. Offline reports
  do not claim model classification accuracy. See the [Phase 2 notes](07-NATURAL-LANGUAGE-UPDATES.md).
- A tools-only MCP stdio adapter that routes remember, process_update, recall,
  and history through the existing API. No second database writer or cache.
- Codex config and launch-script generation without editing user settings;
  actual installed CLI configuration recognition was checked.
- A separate synthetic account API with PostgreSQL runtime storage, cookie-session,
  CSRF, ownership, and explicit demo login/seed contracts. The settings frontend
  is the fresh-agent exercise and has not been generated.
- Phase 3 offline checks, optional SDK/PostgreSQL checks, an actual-service probe,
  and a real MCP-to-graph integration test. See [Phase 3 notes](08-MCP-AND-CODING-CLIENT.md).

## Actual verification

Environment: macOS, Python 3.14.6 and the installed Python 3.12. Offline tests pass
under both interpreters. The configured CI target is Python 3.12; CI itself has
not yet been observed.

| Check | Observed result |
| --- | --- |
| Offline unittest discovery | 123 tests passed on Python 3.12 and 3.14; 12 FalkorDB, 2 PostgreSQL, and 1 SDK checks explicitly skipped. |
| Python compileall | Passed for `src` and `tests`. |
| CLI help | Passed. |
| Docker Compose configuration validation | Passed. |
| Isolated verification Compose configuration | Passed. |
| Complete Phase 1 runner | Offline tests passed; command exited nonzero because the FalkorDB client cannot be installed in this session. Report: `reports/phase1-current/phase1.json`. |
| FalkorDB image startup | Blocked: this session cannot access the Docker daemon socket. |
| Python runtime dependency installation | Blocked: this session cannot resolve `pypi.org`. |
| Real Cypher/SDK integration | Not run; requires the preceding two checks. |
| Persistence across service/database restart | Not run. |
| Database failure atomicity/crash recovery | Not established. |
| Natural-language adapter/policy tests | 38 Phase 2 tests passed; provider responses are controlled fixtures. |
| Phase 2 offline runner | Exited 0 with `offline_passed_live_unverified`; report: `reports/phase2-offline.json`. |
| Phase 2 live runner | Exited 1 before any model call because no key is configured; report explicitly marks `blocked` and live evaluation `not_run`. |
| Live natural-language classification | Not evaluated: GROQ_API_KEY is not configured. Accuracy, actual inference latency, and usage remain unknown. |
| MCP subprocess protocol and routing | 18 tests passed, including a real child process handshake/list/ping and EOF. Controlled application tests use the test-only store. |
| Codex configuration | Generated config recognized by installed codex-cli 0.162.1. User settings unchanged. No model/tool call inferred. |
| Phase 3 offline runner | 30 tests passed; report: `reports/phase3-offline.json`. |
| Phase 3 real memory probe | Attempted; returned explicit tool errors because the memory service is unavailable. Exited 1 and recorded `blocked_or_failed` in `reports/phase3-probe.json`. No successful recall inferred. |
| Account API contract | 10 tests passed with a test-only profile store. Cookie/CSRF/ownership and rejection of bearer requests checked. |
| Real demo PostgreSQL storage | Not verified; optional dependency and Docker inaccessible here. |
| Official MCP SDK interoperability | Not run; optional package unavailable. |
| Real coding-client MCP call | Adapter/config/task implemented; a successful call by the actual coding client has not been observed. |
| Settings frontend feature tests | Not run; the frontend is the prepared fresh-agent task, not a claimed generated result. |
| Dashboard | Not implemented. |

The follow-up Phase 1 review fixed malformed-origin handling in the HTTP adapter
and rejects duplicate Content-Length headers. The complete database gate is
prepared and has been requested from the developer's unrestricted terminal;
there is no successful external result yet. The user then requested the next
phase, so Phase 2's independent code and offline checks were implemented while
preserving the unresolved Phase 1 gate. No database or live-model pass is claimed.

Offline application tests use a deliberately test-only repository model. They
verify orchestration, policy, replay, revisions, and isolation; they are not
evidence that Cypher works, that disk persistence works, or that a model can
classify text. A repository failure injected before commit only checks retry
behavior at the application boundary.

## Current implementation choices

The memory backend uses Python's standard-library HTTP server and CLI, with the
official FalkorDB client as its sole required external runtime dependency. No
framework or model API is required for the structured vertical slice. The optional natural
endpoint uses Groq through standard-library HTTPS and requires a server-side
GROQ_API_KEY.
The separate account fixture optionally requires Psycopg; SDK interoperability
tests optionally require the official MCP Python client. Neither is needed to
start the MCP adapter itself. This is a local prototype,
not a public production server. Source authority is explicitly supplied by the
trusted local developer workflow and is not independently authenticated.

Plan-to-fact dependencies are supported. Plan-to-plan traversal, ingestion,
embeddings, and graph visualization remain deferred. A correction is applied in
one guarded graph query; the actual database guarantees still need verification.
History traverses at most 32 replacement edges.

Implementation references: the official [Python client](https://github.com/FalkorDB/falkordb-py),
[parameterized graph queries](https://docs.falkordb.com/commands/graph.query),
[persistence configuration](https://docs.falkordb.com/operations/durability/persistence),
and [upstream FOREACH/rollback tests](https://github.com/FalkorDB/FalkorDB/blob/master/tests/flow/test_foreach.py).
The upstream tests informed the query design; they do not substitute for running
this project's correction rollback test against the chosen image.

The first three milestones are **in progress**, not complete. Their outstanding
gates are actual database integration/restart retention and live classification
evaluation, plus a real coding-client recall and generated feature checks. Follow
the commands in the [root README](../README.md), [Phase 2 notes](07-NATURAL-LANGUAGE-UPDATES.md),
and [Phase 3 notes](08-MCP-AND-CODING-CLIENT.md), then append the real results here.
Do not silently replace skipped checks or controlled-response tests with claimed
database/model passes. The dashboard remains pending.
