# Synthetic account settings

The account-settings page is implemented at `/settings`, served by the existing
Python demo process. Choose Alice or Bob, recover a session on reload, edit your
display name, save, and sign out. The runtime stores profiles in PostgreSQL and
uses the existing HTTP-only cookie/CSRF/own-profile contract. The supplied login
selects fake accounts without a password; it is a local synthetic fixture.

From the repository root, with the virtual environment activated:

```sh
python -m pip install -e '.[demo]'
docker compose -f compose.demo.yaml up -d --wait
python -m retract.demo --seed
python -m retract.demo
```

Open `http://127.0.0.1:8101/settings`. This is separate from RETRACT's memory
API/dashboard at port 8100. Seeding is explicit and retains existing profile
edits. The demo database has its own named volume. `DEMO_DATABASE_URL` overrides
the connection; the Compose credentials are public synthetic demo credentials.
Runtime PostgreSQL and browser layout remain unverified in this restricted
session; the implementation has passing HTTP/client checks described below.

## Frontend behavior

The page follows the project's approved neutral theme with a narrow profile
form, system light/dark preferences, labeled controls, and visible focus states.
It shows initial loading, signed-out, request-in-progress, error, unsaved, and
saved states. Failed saves retain the draft and offer retry/session refresh.
An expired session clears the visible profile. A draft can be restored after
signing back into the same account during this page's lifetime; switching to
another account discards that draft. Successful sign-out clears it. Reloading
loses unsaved input, while the stored profile/session is retrieved from the API.

Browser requests use `credentials: same-origin`; JavaScript never reads the
HTTP-only cookie or stores a bearer token. The returned CSRF token stays in
module memory, and PATCH/logout include it. The save target is derived from the
server session's user, never a form-controlled account ID. Only `display_name`
is submitted. Email is read-only. A server error never produces a saved message.
A failed logout preserves the visible identity until sign-out is confirmed.

Runtime assets are in [src/retract/account_web](../../src/retract/account_web),
so an installed Python package includes them without needing the examples folder
or a Node build. The demo serves only the explicit `/settings` and account asset
routes, under the existing loopback Host/Origin checks and a same-origin CSP.
Source/profile strings are inserted as text and field values, not HTML.

## API contract

| Request | Behavior |
| --- | --- |
| `GET /settings` | Static account page, no session required. |
| `POST /demo/login` with `{"user_id":"alice"}` or `bob` | Select a synthetic account, set an HTTP-only `SameSite=Strict` session cookie, return `user` and `csrf_token`. |
| `GET /api/session` | Cookie required; return current `user` and `csrf_token`. |
| `GET /api/profiles/<id>` | Cookie required; the ID must be the current user's own ID. |
| `PATCH /api/profiles/<id>` with `{"display_name":"..."}` | Cookie, own ID, and `X-CSRF-Token` required. Trimmed name contains 1–80 Unicode characters. Email/ID updates are rejected. |
| `POST /demo/logout` with `{}` | Cookie and CSRF required; invalidate session and clear cookie. |
| `GET /health` | Query PostgreSQL; unavailable storage fails explicitly. |

Writes require JSON and the same local origin. API routes reject Authorization
bearer headers even with a cookie present. Sessions expire after one hour and
are process-local; profile storage is persistent. RETRACT's graph persistence is
a separate requirement. The page does not change any of these backend rules.

## Checks

```sh
python scripts/verify_account_settings.py
# Or run the full JavaScript regression suite:
npm test
```

Observed: 15 Python HTTP/static/contract checks and 15 JavaScript feature checks
pass. The JavaScript tests execute the actual frontend client against the actual
Python HTTP handler through a test-only stdio transport, without a listening
socket. The profile store is a controlled test fixture. The tests cover cookie
recovery, CSRF, ownership, no bearer headers, own-user targets, failures/retries,
expiry, logout, account switching, validation, and timeouts. They do not prove
browser rendering, automatic browser cookie behavior, or PostgreSQL persistence.

Real Chromium checks with the same actual HTTP handler/test profile store:

```sh
npm install --ignore-scripts
npx playwright install chromium
python scripts/verify_account_settings.py --browser
```

That suite exercises the DOM, keyboard sign-in/save, HTTP-only cookie behavior,
CSRF/network requests, protected other-user writes, reload, failed-save draft
retention, expired-session reauthentication, cross-account draft isolation,
sign-out, text escaping, and 375/768/1280-pixel light/dark layouts. It records real
screenshots only if Chromium runs. The default browser origin is intercepted
locally; the test transport translates only that declared origin for the real
HTTP handler. It does not open external pages or stand in for real PostgreSQL.

With the actual demo running on PostgreSQL, add the optional live browser check:

```sh
python scripts/verify_account_settings.py --browser --live-url http://127.0.0.1:8101
```

The live check signs in as synthetic Alice, saves a temporary display name,
reloads, restores the original display name in `finally`, and signs out. It
fails if restoration fails. Use only the supplied synthetic demo. The browser
attempt in this session exited nonzero during Chromium sandbox startup; no
DOM/layout/live-PostgreSQL pass or screenshots are claimed. CI is configured to
run the controlled browser suite and verify wheel asset inclusion.

Reports: `reports/account-settings-offline.json`,
`reports/account-settings-browser-attempt.json`, and the latest full evidence
bundle under `reports/account-settings-final/`.

## Fresh coding-client evidence remains separate

This frontend was implemented directly during the continuing build, using
[the current backend](../../src/retract/demo.py), its tests, and the approved
[current authentication note](notes/002-current-auth.md). The attempted CLI
recall returned “Local service unavailable”; no fact/source IDs were retrieved.
No memory was reseeded, corrected, or fabricated to complete the feature.
This is not evidence of a successful fresh coding-client MCP recall.

For the original implementation exercise, use an isolated checkout at the
pre-frontend baseline `3452a9538f19907c4cb00e4248f2af00cc354639`. Run the configuration
generator from that checkout, with the installed runtime interpreter, so the
fresh client sees the original task without this completed frontend. Do not
remove the working frontend or reset memory in the current checkout. The original
[AGENT_TASK.md](AGENT_TASK.md) is retained as that exercise's acceptance contract.
A review-only run on the current tree must be reported as verification of an
existing feature, not independent feature generation.

Start the memory service, seed its fixture explicitly once, and apply U1 if it
has not already been applied. Existing memory must not be reset or reseeded:

```sh
retract seed
retract call updates fixtures/confirmed-update.json
retract call updates fixtures/proposal.json
python scripts/configure_codex.py --check
python scripts/verify_phase3.py --probe
```

The probe checks the declared U1/F5 scenario as a programmatic MCP client. It is
not an agent. Review the generated configuration/launch script, then run the
fresh coding-client exercise from the chosen baseline. Preserve actual client
and MCP traces, retrieved fact/source IDs, inspected repository evidence, changes,
and feature-test output before claiming that integration gate passed.
