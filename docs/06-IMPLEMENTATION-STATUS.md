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

## Actual verification

Environment: macOS, Python 3.14.6 and the installed Python 3.12. Offline tests pass
under both interpreters. The configured CI target is Python 3.12; CI itself has
not yet been observed.

| Check | Observed result |
| --- | --- |
| Offline unittest discovery | 55 tests passed on Python 3.12 and 3.14; 10 real database tests explicitly skipped. |
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
| Natural-language classification | Not implemented or evaluated. |
| Real coding-client MCP call | Not implemented or observed. |
| Settings application feature tests | Demo application not yet implemented. |
| Dashboard | Not implemented. |

The follow-up Phase 1 review fixed malformed-origin handling in the HTTP adapter
and rejects duplicate Content-Length headers. The complete database gate is
prepared and has been requested from the developer's unrestricted terminal;
there is no successful external result yet. Phase 2 remains pending.

Offline application tests use a deliberately test-only repository model. They
verify orchestration, policy, replay, revisions, and isolation; they are not
evidence that Cypher works, that disk persistence works, or that a model can
classify text. A repository failure injected before commit only checks retry
behavior at the application boundary.

## Current implementation choices

The initial backend uses Python's standard-library HTTP server and CLI, with the
official FalkorDB client as its sole runtime dependency. No framework or model
API is required for the structured vertical slice. This is a local prototype,
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

The first milestone is **in progress**, not complete. Its exit gate requires an
actual database run and restart retention before model extraction or dashboard
work advances. Follow the commands in the [root README](../README.md) and append
the real results here. Do not silently replace skipped checks with claimed passes.
