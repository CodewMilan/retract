# Implementation and verification record

Updated 18 October 2026. This file reports actual observations separately from
the proposed behavior in the original specification.

## Latest: fresh coding-client construction verified

On 18 October, a fresh ephemeral Codex CLI 0.162.1 session at pre-frontend
commit `3452a9538f19907c4cb00e4248f2af00cc354639` completed two real recalls and
U1 history retrieval, visibly revised P1 using F5/S-U1, implemented `/settings`,
and passed 10 existing contract tests plus 10 Chromium scenarios against real
HTTP/PostgreSQL. The initial sandbox-blocked Chromium attempt is retained;
the approved retry passed. Memory snapshots remained identical at revision 7.

The [run record](12-FRESH-CLIENT-RUN.md) links raw client/MCP traces, the generated
patch, test output, and snapshots. This closes the fresh-client feature gate;
video, publication, and final submission review remain pending. Historical
unverified statements below are superseded by this result and the developer-machine
verification section, not evidence of new failures.

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
  is now implemented directly; the original fresh-agent exercise remains a
  separate unverified integration gate.
- Phase 3 offline checks, optional SDK/PostgreSQL checks, an actual-service probe,
  and a real MCP-to-graph integration test. See [Phase 3 notes](08-MCP-AND-CODING-CLIENT.md).

- A local neutral dashboard served by the same Python process: current/history,
  pending/proposals, affected plans, update outcomes, evidence, and actual API
  request activity. Project creation, accepted-fact entry, structured and natural
  updates, revision conflicts, and unchanged-event retries use the existing API.
- Bounded read snapshots with exact totals, explicit truncation, project isolation,
  and graph-derived cross-scope plan explanations. Static assets are packaged with
  the service, with restricted routes and CSP. See [Phase 4 notes](09-DASHBOARD.md).
- Phase 4 Python/JavaScript tests, opt-in Chromium interaction checks, and a real
  dashboard graph integration test. Browser checks and wheel validation are wired
  into CI, whose execution remains unobserved.
- A Phase 5 structured evaluator with 14 declared synthetic cases and actual-store
  observations for protected facts, stale recall, current values, plan precision/
  recall, history, revisions, replay, and service/storage latency. It creates only
  a UUID graph; failed runs preserve it, and successful runs delete only that graph.
- A fresh evidence-bundle runner, bounded working-tree/Git-history secret-pattern
  scanner, graph query guide, rehearsal instructions, dependency/AI/prior-art
  notices, and reviewable submission copy. No submission or publication occurred.
- Phase 5 evaluator/report tests include injected fact corruption, stale recall,
  wrong accepted values, over/under-flagged plans, lost historical secrets, owned
  graph cleanup boundaries, and blocked-result propagation. See
  [Phase 5 notes](10-EVALUATION-AND-RELEASE.md).

- The account-settings frontend at `/settings`: synthetic sign-in, cookie-session
  recovery, display-name editing, save/retry, expiry/reauthentication, owner-bound
  drafts, and confirmed sign-out. Static assets are included in the Python package.
- Actual frontend-client-to-HTTP-handler tests using controlled profile storage,
  static/CSP/origin checks, and an opt-in Chromium suite with optional actual
  PostgreSQL edit/restore. The ongoing build used code and approved notes after
  CLI recall failed; no successful memory retrieval or fresh-client generation
  is inferred. See [the account example](../examples/account-settings/README.md).

## Actual verification

Environment: macOS, Python 3.14.6 and the installed Python 3.12. Offline tests pass
under both interpreters. The configured CI target is Python 3.12; CI itself has
not yet been observed.

| Check | Observed result |
| --- | --- |
| Offline unittest discovery | 161 tests passed on Python 3.12 and 3.14; 13 FalkorDB, 2 PostgreSQL, and 1 SDK checks explicitly skipped. |
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
| Settings frontend HTTP/client tests | 15 Python contract/static checks and 15 JavaScript feature checks pass. JavaScript requests traverse the actual Python HTTP handler; only profile storage and cookie transport are test-controlled. |
| Phase 4 Python/API checks | 12 passed. Test-only repository model plus actual HTTP handler transport; real Cypher is separate. |
| Phase 4 JavaScript model checks | 7 passed with Node 24.14.1. |
| Full Python regression after Phase 4 | 151 discovered: 135 passed, 16 skipped on both Python versions. Compileall and JS syntax checks passed. |
| Phase 4 offline runner | Exited 0; report `reports/phase4-offline.json`. |
| Dashboard browser interactions/layout | Attempted; Chromium terminated during launch with sandbox Mach-port registration permission denied. Exited 1 before scenarios; report `reports/phase4-browser-attempt.json`. No screenshots or visual pass. |
| Dashboard real graph/live browser | Not verified; new real-graph test explicitly skipped without its dependency/service. |
| Wheel asset inclusion | Package-data configured; local wheel build unavailable because setuptools is missing. CI check prepared, not observed. |
| Phase 5 evaluator/report tests | 21 passed; controlled stores and faults validate evaluator behavior, not runtime benchmark numbers. |
| Full Python regression after Phase 5 | 172 discovered: 156 passed, 16 explicitly skipped on Python 3.12 and 3.14. Seven JavaScript checks pass. |
| Public-file secret-pattern scan | Passed over tracked/nonignored text files and reachable Git blobs, with no findings or exclusions. This is a bounded pattern scan, not an exhaustive security audit. |
| Phase 5 combined live attempt | Exited 1 with explicit `blocked_or_failed`; graph client missing, Groq key absent, MCP SDK missing, Chromium launch denied. Independent checks continued and source hashes stayed unchanged. Report: `reports/phase5-live-attempt/phase5.json`. |
| Standalone real memory evaluation | Exited 1 before database use because the client is unavailable; `evaluation` is null in `reports/phase5-memory-attempt.json`. |
| Phase 5 final offline bundle | Exited 0 with `offline_passed_live_unverified`; report: `reports/phase5-final/phase5.json`. Source/artifact hashes and test logs retained. |
| Runtime benchmark / comparative results | Not measured. Wrong invalidations, stale retrieval, plan precision/recall, classification accuracy, runtime latency, and usage remain unknown. Controlled fixture scores are not substituted. |
| Submission / working video | Draft and rehearsal instructions prepared; no published repository visibility, real coding-client feature evidence, or genuine working video verified. No form submitted. |
| Account-settings browser attempt | Exited 1 during Chromium sandbox startup before any scenario. DOM, keyboard, layout, actual-browser cookies, screenshots, and live PostgreSQL behavior remain unverified. Report: `reports/account-settings-browser-attempt.json`. |
| Continued-build memory recall | Actual CLI recall attempted for browser-api; service unavailable. No fact/source IDs retrieved, no memory changed. |
| Full regression after account-settings implementation | 177 Python tests: 161 passed, 16 skipped on Python 3.12 and 3.14. All 22 JavaScript checks pass. |
| Latest offline evidence bundle | `reports/account-settings-final/phase5.json`; source/artifact hashes, regression logs, and bounded release-pattern scan retained. |

## Verification on the developer machine

Recorded 17 October 2026 on macOS with Docker Desktop, Python 3.14.6, Node
24.14.1, `falkordb` client 1.8.0, `falkordb/falkordb:6.0.2`, `postgres:17-alpine`,
`mcp` 1.30.0, and Playwright Chromium. These results supersede the "blocked"
rows above, which came from a sandbox without Docker or network access.

| Check | Observed result |
| --- | --- |
| Full Python suite with `RUN_FALKORDB_TESTS=1 RUN_DEMO_POSTGRES_TESTS=1` | 177 tests passed, none skipped (real FalkorDB, real PostgreSQL, official MCP SDK). |
| Structured demo via `retract serve` | Seed, U1 correction, replay, U2 proposal, scoped recall, and history behaved as documented on the real graph. |
| Phase 1 gate (`verify_phase1.py`) | Initially failed: the isolated database's ephemeral host port changed on container restart and the runner reused the old port. Fixed by re-reading the port after restart; the gate then passed, including restart without reseeding. Report: `reports/phase1-real/phase1.json`. |
| Real memory evaluation | 14/14 cases, 0 wrong invalidations, 0 stale retrievals, plan precision/recall 1.0; update p50 2.8 ms, recall p50 1.6 ms (small synthetic fixture). Report: `reports/memory-real.json`. |
| Phase 3 probe with SDK and PostgreSQL | Passed. Report: `reports/phase3-real.json`. |
| Dashboard browser (375/768/1280) and live read-only smoke | Passed; screenshots in `reports/phase4/browser/`. |
| Account settings browser and live PostgreSQL edit/restore | Passed; screenshots in `reports/account-settings/browser/`. |
| Real Codex MCP recall | `codex exec` (read-only sandbox) called `recall` and reported F5 and P1. Trace: `reports/phase3/codex-recall-smoke.jsonl`, `reports/phase3/mcp-activity.jsonl`. This is a recall smoke test, not the fresh feature-generation exercise. |
| Groq transport (18 October) | Two real-environment defects fixed: python.org macOS Python lacks root certificates (TLS now uses `certifi`), and Groq's edge rejected urllib's default User-Agent with Cloudflare error 1010 (a project User-Agent is now sent). |
| Live classification | Prompt `retract-extract-v1` scored 13/16 with one wrong application (a conditional approval applied). Prompt `retract-extract-v2` adds explicit modal/conditional/other-scope rules; across six `gpt-oss-20b` runs it scored 13–16/16 with zero wrong applications. Remaining misses are conservative (pending instead of proposal/ignored). |
| Natural update through the running API | Fresh graph, seeded, `/updates/natural` with the fixture: classified `confirmed_change`, retired F1, flagged P1, ~1.0 s model latency. |
| Phase 5 live bundle | `live_checks_passed_manual_evidence_unverified`: every automated check passed, including 16/16 live classification. Report: `reports/phase5-live/RESULTS.md`. Remaining evidence is manual (fresh coding-client feature run, video, publication). |


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

The five milestones are **in progress**, not complete. Their outstanding
gates are actual database integration/restart retention and live classification
evaluation, plus a real coding-client recall and generated feature checks, dashboard validation, and a genuine working demo. Follow
the commands in the [root README](../README.md), [Phase 2 notes](07-NATURAL-LANGUAGE-UPDATES.md),
[Phase 3 notes](08-MCP-AND-CODING-CLIENT.md), and [Phase 4 notes](09-DASHBOARD.md), and [Phase 5 notes](10-EVALUATION-AND-RELEASE.md), then append the real results here.
Do not silently replace skipped checks or controlled-response tests with claimed
database/model passes. Dashboard and evaluation code are implemented; their actual-state, browser, and reproducible working-demo gates remain open.
