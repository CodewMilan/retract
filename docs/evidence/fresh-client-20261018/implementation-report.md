# Account settings construction — 2026-10-18

Implemented `/settings` in this isolated source checkout. No other checkout or
later Git revision was inspected for a solution. No subagents were spawned,
memory writes issued, or existing live service modified. The initial untracked
`node_modules` link was retained.

## Retrieved evidence and revised plan

Actual read-only RETRACT MCP calls, before implementation planning:

1. `mcp__retract__recall({"project_id":"account-settings","scope":"web-client/main","subjects":["browser-api"]})`
   returned active **F5**, source **S-U1**, affected plan **P1** (`needs_review`),
   and explanation path **U1 → P1 → F1 (DEPENDS_ON)**.
2. `mcp__retract__recall({"project_id":"account-settings","scope":"account-service/main","subjects":["profile","account-data"]})`
   returned **F3 / S-F3** (PostgreSQL) and **F4 / S-F4** (own profile only).
3. `mcp__retract__history({"project_id":"account-settings","event_id":"U1"})`
   confirmed applied event **U1**, source **S-U1**, retirement of **F1**, acceptance
   of **F5**, and flagging of **P1**. U1 changed revision 5 to 6; all three reads
   reported current project revision **7**. Both recalls had no pending conflicts
   in their requested scopes. These were direct connected MCP calls, not a
   programmatic MCP probe or a claim about the separate launcher logs.

P1's retrieved text assumed an Authorization bearer header while retaining
ownership checks. The revised implementation plan, explained visibly before
coding, replaces that assumption with F5's HTTP-only cookie sessions: recover
`/api/session`, use the returned user ID and CSRF token, submit same-origin
requests, and let the browser manage the cookie. Keep F3 PostgreSQL storage and
F4 ownership enforcement. This revision exists in the implementation and this
report only; P1 was not written back to graph memory.

Repository evidence inspected independently:

- [Task](AGENT_TASK.md) and [API README](README.md).
- [Backend](../../src/retract/demo.py): `DemoApp.session` rejects bearer headers;
  `dispatch` requires CSRF and enforces ownership; `PostgresProfiles` stores data.
- [Existing tests](../../tests/test_demo.py): cookie, bearer rejection, CSRF,
  ownership, validation, expiry, logout, origin, and storage failure contracts.
- [Current approved correction](notes/002-current-auth.md): agrees with F5/F3/F4.
- [Historical note](notes/001-original-auth.md): explicitly superseded F1.
- [Compose](../../compose.demo.yaml): synthetic PostgreSQL connection details.

No current memory/repository conflict was found. Memory identified the stale P1
dependency, but the backend and approved note independently reveal the correct
contract; success cannot be uniquely attributed to memory. The note mentions U2;
no separate U2 history call was made.

## Files changed

- `examples/account-settings/index.html`, `settings.css`, `settings.js`: accessible
  forms, synthetic account selection, session recovery/retry, save, sign-out,
  loading/saved/error states, responsive neutral light/dark styling. No bearer
  token storage, cookie reads, or Authorization construction in application JS.
- `src/retract/demo.py`: three explicit GET routes for the page, CSS, and JS,
  after existing Host/Origin validation; content types, no-store, nosniff, CSP;
  startup URL updated. API and PostgreSQL storage logic unchanged.
- `tests/account-settings.browser.mjs`: browser feature scenarios and network
  assertions against the real server, with explicitly controlled failure cases.
- `tests/account_settings_server.py`: free-port fixture using a disposable
  PostgreSQL schema, seeded only in that schema and dropped afterward.
- `package.json`: `test:settings` command.
- `examples/account-settings/README.md` and this report: usage and evidence.

## Exact results

`PYTHONPATH=src /Users/milan/graph/.venv/bin/python -m unittest tests.test_demo -v`
exited **0**: **10 tests ran in 0.001s; OK**. Existing tests were not weakened or
modified.

First `npm run test:settings` exited **1**, before any browser scenario ran:
Chromium launch failed under the macOS sandbox with
`bootstrap_check_in ... MachPortRendezvousServer ... Permission denied (1100)`.
The server had started at `http://127.0.0.1:50658`; schema
`settings_test_5534105a3ab24c3789630f34b228265f` was dropped in cleanup.

The identical command was retried with `require_escalated` to permit Chromium to
launch. It exited **0**, with **10 browser scenarios passed** and **no uncaught
page errors**:

1. Static routes, content types/security headers, Host/Origin protection, loading,
   signed-out state, initial keyboard focus.
2. Alice sign-in, real HTTP-only Strict cookie on PATCH, exact CSRF header, no
   Authorization header, exact own-profile URL/body, Enter submission, empty web
   storage, and session/name recovery after reload.
3. Cross-user GET/PATCH rejected with 403, missing-CSRF write rejected with 403,
   Bob's original PostgreSQL profile unchanged in a separate authenticated context.
4. Client whitespace validation; real backend 400 from an intentionally corrupted
   request; simulated 503; browser offline failure; preserved draft and retry.
5. Delayed save, disabled controls, duplicate submit suppression, literal text.
6. Simulated logout failure, successful logout CSRF/no-bearer request, cookie
   deletion, signed-out reload.
7. Simulated session/login failures and retries; real invalidated session on save;
   Bob re-login and save to `/api/profiles/bob`.
8. 375px light layout, no horizontal overflow.
9. 768px dark layout, no horizontal overflow.
10. 1280px light layout, no horizontal overflow.

Successful fixture: `http://127.0.0.1:50670`, schema
`settings_test_987db718e78d48528eda48c876a248af`. Cleanup explicitly reported that
schema dropped and the fixture exited 0. The fixture used the required interpreter
with `PYTHONPATH=src`. Both servers stopped; no service remains running.

`git diff --check` exited **0** with no output. Screenshots exist at
`reports/account-settings/settings-{375,768,1280}.png`; mobile/light and
tablet/dark were visually inspected. Code changes remain uncommitted in this
checkout; no reset or cleanup discarded the implementation.

## Limits

- Browser coverage is Chromium only; no Firefox, WebKit, real mobile device,
  screen-reader, or full accessibility audit was run.
- 503 scenarios used Playwright response interception; PostgreSQL was not stopped
  to simulate a real outage. Successful reads/writes and ownership checks used
  real PostgreSQL. Existing Python tests also cover an injected store exception.
- The browser invalidation test uses real logout, not waiting an hour. The
  existing contract test covers clock-driven expiry.
- Assets resolve from this source checkout; wheel packaging of example assets
  is outside this exercise. No public deployment or real-account auth was tested.
- Unrelated graph/dashboard suites and the standalone MCP probe were not run.
- Reports/screenshots are Git-ignored; this report and test sources preserve the
  reproducible procedure and exact observed outcomes in the reviewable diff.
