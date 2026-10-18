# Fresh coding-client construction run

Verified locally on 18 October 2026 with Codex CLI 0.162.1. A new ephemeral
session retrieved existing graph context, revised the outdated settings plan,
implemented the feature in an isolated pre-frontend checkout, and passed its
contract and browser tests. The client exited 0.

The starting commit was `3452a9538f19907c4cb00e4248f2af00cc354639`.
The existing frontend in the main checkout was not used as the implementation
target. Its replacement was not merged: the generated feature is preserved as
an independently reviewable [patch](evidence/fresh-client-20261018/feature.patch).

## Evidence chain

The [unaltered JSONL client transcript](evidence/fresh-client-20261018/codex-session.jsonl)
records thread `01a14eba-ec99-7840-be40-88b0d0f69d67`. The
[adapter activity log](evidence/fresh-client-20261018/mcp-activity.jsonl) records
three successful calls from `codex-mcp-client`:

| Request | Tool and scope | Context supplied to the agent |
| --- | --- | --- |
| 2 | `recall`, `account-service/main` | F3/S-F3: PostgreSQL; F4/S-F4: own profile only. |
| 3 | `recall`, `web-client/main` | F5/S-U1: HTTP-only cookie sessions; P1 needs review because it depends on F1. |
| 4 | `history`, event U1 | Confirmed correction retired F1, accepted F5, and flagged P1. |

After inspecting the backend, existing tests, and approved note, the client
explicitly revised P1's bearer-header assumption to recover `/api/session`, use
its user ID and CSRF token, and let the browser send the HTTP-only cookie.
That visible statement precedes its first file change in the transcript.
The graph's P1 remains `needs_review`: this exercise revised the implementation
plan without writing a new accepted plan into memory.

The [before](evidence/fresh-client-20261018/memory-before.json) and
[after](evidence/fresh-client-20261018/memory-after.json) snapshots are identical
at revision 7. They include F1/F5 history, F2's unchanged CLI authentication,
unchanged F3/F4, U1's dependency path, and U2's proposal outcome. The first
snapshot was captured after the client's read-only recalls and before it
finished implementation. No memory mutation tool was enabled for this run.
Restart durability was verified separately in the earlier Phase 1 live gate;
no database restart was performed during this exercise.

## Checks and limits

[Captured test output](evidence/fresh-client-20261018/tests.log) establishes:

- 10 existing Python demo contract tests passed, without modifying those tests.
- 10 Chromium scenarios passed against a real HTTP server and disposable
  PostgreSQL schema, including actual cookie/CSRF save requests, no bearer
  header, ownership rejection, reload recovery, failed saves, sign-out, and
  layouts at 375/768/1280px. The fixture dropped its schema afterward.
- The first Chromium launch failed inside the macOS sandbox. The same command
  passed after automatic approval review allowed the required exception.
- `git diff --check` passed. The preserved patch was separately checked with
  `git apply --check` against an export of the exact baseline commit.

The 503 responses were simulated with Playwright; successful database writes
and ownership checks used real PostgreSQL. This was Chromium coverage, not a
full accessibility or cross-browser audit. Example assets resolve from a source
checkout; wheel packaging was outside this exercise. Memory was not shown to
be the unique cause of success: the backend and approved note also state the
correct contract. No video, publication, or submission occurred.

The client's [implementation report](evidence/fresh-client-20261018/implementation-report.md)
is preserved verbatim; its relative links refer to the generated checkout.
[SHA256.json](evidence/fresh-client-20261018/SHA256.json) identifies the artifacts.
They include local paths and synthetic fixture data, with no credentials beyond
the documented synthetic PostgreSQL password. A bounded secret-pattern check
passed before preserving the bundle.

## Reproduce

For another genuine construction run, create a new checkout at the baseline
above, install the optional demo dependencies and Playwright, and run
`scripts/configure_codex.py --check` there using that environment's Python.
Connect to the existing memory service with U1/F5/P1 already present; inspect
it without reseeding. Follow the original `AGENT_TASK.md`, require a visible
plan revision citing evidence IDs, and retain the raw client and MCP traces.
Use a new report directory for every run.

This run's [exact launch script](evidence/fresh-client-20261018/start-codex-retract.sh)
uses local absolute paths, `--json --ephemeral --approve-for-me`, and a
session-only MCP override allowing `recall` and `history`. `--approve-for-me`
selects workspace sandboxing with automatic approval review; installed CLI
0.162.1 rejected combining it with `--sandbox`. User settings were not edited.
See the official [non-interactive execution documentation](https://learn.chatgpt.com/docs/non-interactive-mode)
and [MCP configuration documentation](https://learn.chatgpt.com/docs/extend/mcp?surface=cli).

To replay the generated feature instead of generating a new one, apply
`feature.patch` to the baseline. Install the baseline's demo dependencies and
Playwright, start PostgreSQL from `compose.demo.yaml`, and set the Python
executable in `tests/account-settings.browser.mjs` to your installed environment
(the captured patch intentionally retains this machine's absolute path).
Run `PYTHONPATH=src python -m unittest tests.test_demo -v` and
`npm run test:settings`. Allow Chromium launch and loopback access as required by
your sandbox. This replays feature checks; it is not another fresh-agent run.
