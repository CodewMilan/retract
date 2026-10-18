# Phase 3 — MCP adapter and coding-client exercise

**18 October update:** the fresh coding-client construction exercise passed in
an isolated pre-frontend checkout, with actual recall/history, a visible P1 plan
revision, generated code, 10 contract tests, and 10 real Chromium/PostgreSQL
scenarios. See the [run record and preserved evidence](12-FRESH-CLIENT-RUN.md).
The older restricted-session observations below are retained as historical
notes; their unverified statuses are superseded by that run and the
[developer-machine verification](06-IMPLEMENTATION-STATUS.md).

Status: the adapter, Codex configuration generator, synthetic account API, and
offline checks are implemented. Codex CLI 0.162.1 recognizes the generated
configuration. A real fresh coding-client recall has not been observed. The
settings frontend is now implemented directly in the continuing build; its
controlled HTTP/client checks pass, while real-browser and PostgreSQL checks
remain unverified. Database, optional SDK, and real PostgreSQL checks remain
unverified in this restricted session. This is not a completed Phase 3 exit gate.

## Memory tools

Start the existing memory service, then let the coding client spawn the adapter:

```sh
retract serve
# The MCP client starts this child process:
retract mcp --activity-log reports/mcp-activity.jsonl
```

The adapter speaks newline-delimited JSON-RPC on stdio and calls the existing
local HTTP API. The backend remains the single graph writer. There is no memory
cache or second authoritative store in the adapter. API failures become visible
MCP tool errors, never fabricated context.

| MCP tool | API route | Behavior |
| --- | --- | --- |
| `remember` | `/remember` | Store an explicitly accepted scoped fact with a source. Conflicts require the update workflow. |
| `process_update`, `mode: structured` | `/updates` | Validate a structured classification/candidate, then use the existing deterministic policy. |
| `process_update`, `mode: natural` | `/updates/natural` | Select a scoped key and run Phase 2 extraction; Groq configuration stays in the backend. |
| `recall` | `/recall` | Current facts, sources, affected plans, pending conflicts, and revision. |
| `history` | `/history` | Exactly one fact or event target, with evidence and replacement history. |

Tool schemas describe effects and mark recall/history read-only. Metadata and
server instructions ask the agent to retrieve context before planning, inspect
the repository, cite fact/source IDs, and report contradictions. They do not
guarantee that a client/model will obey or call a tool.

## Transport boundaries

The small standard-library implementation supports only `initialize`,
`notifications/initialized`, `ping`, `tools/list`, and `tools/call`. It negotiates
2025-11-25, 2025-06-18, or 2025-03-26 and advertises only tools. It provides no
resources, prompts, tasks, sampling, HTTP MCP transport, streaming, or in-flight
cancellation. Requests are processed sequentially with bounded backend timeouts;
cancellation does not undo an accepted transition.

Messages are limited to 128 KiB; API request bodies to 64 KiB; API responses to
2 MiB. Unexpected fields are validated before a backend write. Protocol errors
and tool execution errors are distinct. Notifications cannot invoke writes.
Only protocol frames go to stdout. Optional JSONL activity logs contain actual
tool names, IDs, outcomes, and latency, excluding raw arguments/source text.

The adapter accepts only an explicit loopback HTTP endpoint, bypasses proxy
environment settings, and does not follow redirects. It receives no database or
Groq credentials in the generated configuration. Its sole endpoint setting is
`RETRACT_URL`, default `http://127.0.0.1:8100`.

This is a deliberately narrow implementation of the published stdio protocol,
not the official server SDK. An optional test uses the official Python client
for independent interoperability checking; that test has not run here because
the package cannot be installed. Source: [MCP transports](https://modelcontextprotocol.io/specification/2025-11-25/basic/transports),
[lifecycle](https://modelcontextprotocol.io/specification/2025-11-25/basic/lifecycle),
and [tools](https://modelcontextprotocol.io/specification/2025-11-25/server/tools).

## Codex configuration

Prepare configuration and a fresh-session launch script without editing user
settings:

```sh
python scripts/configure_codex.py --check
```

This writes `reports/phase3/codex.retract.toml`, `start-codex-retract.sh`, and a
configuration result. It uses the executing Python interpreter and absolute
repository paths, explicit tool allow-list, required startup, and a tool timeout.
The `--check` operation asks `codex mcp get` to parse a temporary configuration
override. That succeeded with installed Codex CLI 0.162.1. It does not initialize
the MCP server, call recall, or start a model session.

The generated launch script starts a new, ephemeral `codex exec --json` execution
of [the task](../examples/account-settings/AGENT_TASK.md). It uses a session-only
configuration override and the client's own configured account/model. It neither
changes approval settings nor bypasses the sandbox. Review it before running:

```sh
sh reports/phase3/start-codex-retract.sh
```

The actual client run has not been launched here. JSONL Codex events and MCP
activity are recorded locally when that run occurs. Inspect the genuine successful
`recall` calls, current fact/source IDs, generated code, and feature test results.
Do not count the configuration check or a manually supplied trace as observed
model behavior. Configuration fields were checked against [official OpenAI MCP
documentation](https://learn.chatgpt.com/docs/extend/mcp?surface=cli) and local CLI
help. The installed client's behavior is still the integration criterion.

## Account-settings fixture

The [synthetic account API](../examples/account-settings/README.md) exposes the
current cookie-session contract with profile ownership and CSRF checks. Its runtime
uses PostgreSQL so memory fact F3 is not contradicted by a SQLite fallback. It has
explicit Alice/Bob demo login, not real authentication. Only synthetic accounts
and localhost access are supported. The frontend is now served at `/settings`;
its implementation and tests are documented in the example README.

```sh
python -m pip install -e '.[demo,mcp-test]'
docker compose -f compose.demo.yaml up -d --wait
python -m retract.demo --seed
python -m retract.demo
```

The demo's own named volume and local port 8101 are separate from the memory
service. Demo seeding preserves edited profiles. SQL values are parameters, and
optional real PostgreSQL tests use disposable UUID schemas rather than modifying
the demo's public tables. The offline test-only store is not a runtime fallback.

The task requires the coding client to retrieve browser-authentication and
account-service facts, inspect the working backend and approved notes, implement
`/settings`, and run browser/request checks for cookie sessions, CSRF, ownership,
and the absence of bearer construction. Direct implementation and HTTP/client
tests now exist. Chromium startup is blocked here, so browser behavior remains
unverified. A fresh-client construction run must use the pre-frontend baseline
documented in the example README; a review on the current tree is not feature
generation.

## Checks

```sh
# Offline protocol, routing, fixture-contract, and config-generation tests:
python scripts/verify_phase3.py

# Optional official SDK interop and real PostgreSQL (requires packages and running PG):
python scripts/verify_phase3.py --sdk --postgres

# With the actual memory API seeded once and U1 applied:
python scripts/verify_phase3.py --probe
```

The probe launches a genuine new MCP process, then requests current F5, ownership
F4, and the F1/F5 history through the running API. It is a programmatic protocol
probe, not a coding client. Reports distinguish those outcomes and never set
`coding_client_recall_observed` to true from the probe. A separate real database
integration test also exercises MCP → HTTP → FalkorDB when Phase 1 tests run.

Current observations: offline checks pass, subprocess framing/EOF behavior passes,
generated shell syntax and Compose configuration pass, Codex parses the generated
configuration. No real SDK, PostgreSQL, successful service probe, or fresh coding
run has been verified. CI is configured to install optional test dependencies and
run SDK/PostgreSQL checks, but no CI result has been observed.
