# Account-settings coding exercise

This is a small synthetic backend for the RETRACT demo. The settings frontend is
the task for a fresh coding session and is deliberately not implemented here.
The running fixture stores Alice and Bob's profiles in PostgreSQL. The login
endpoint selects those synthetic users without a password; keep it local and use
only the supplied fake accounts.

From the repository root, with the virtual environment activated:

```sh
python -m pip install -e '.[demo]'
docker compose -f compose.demo.yaml up -d --wait
python -m retract.demo --seed
python -m retract.demo
```

The account API is at `http://127.0.0.1:8101`; it is separate from the memory API
at port 8100. Seeding is explicit and retains existing profile edits. The demo
database uses its own named volume, separate from FalkorDB. Override the local
connection with `DEMO_DATABASE_URL` if necessary. The default credentials in
Compose are deliberately public synthetic demo credentials.

## Existing API contract

| Request | Behavior |
| --- | --- |
| `POST /demo/login` with `{"user_id":"alice"}` or `bob` | Select a synthetic account, set an HTTP-only `SameSite=Strict` session cookie, return `user` and `csrf_token`. |
| `GET /api/session` | Cookie required; return the current `user` and `csrf_token`. |
| `GET /api/profiles/<id>` | Cookie required; the ID must be the current user's own ID. |
| `PATCH /api/profiles/<id>` with `{"display_name":"..."}` | Cookie, own user ID, and `X-CSRF-Token` required. Trimmed name must contain 1–80 characters. Email/ID updates are rejected. |
| `POST /demo/logout` with `{}` | Cookie and CSRF required; invalidate the session and clear the cookie. |
| `GET /health` | Query PostgreSQL; unavailable storage fails explicitly. |

Writes require JSON and the same local origin. Browser API routes reject the old
Authorization bearer header, even if a cookie is also present. These are fixture
protections for the controlled task, not a production authentication framework.
Sessions expire after one hour and are intentionally not persistent; profile data
is persistent. RETRACT's project-memory persistence is a different requirement.

Inspect [the current backend](../../src/retract/demo.py),
[its contract tests](../../tests/test_demo.py), and the approved notes before
implementing the frontend. The test-only profile model is not used by the runtime
and does not establish PostgreSQL correctness.

## Run the memory-assisted task

Start the memory service, explicitly seed its fixture once, and apply U1:

```sh
retract seed
retract call updates fixtures/confirmed-update.json
retract call updates fixtures/proposal.json
python scripts/configure_codex.py --check
python scripts/verify_phase3.py --probe
```

Existing memory must not be reset or reseeded. If the project already contains
the correction, inspect it and proceed. The probe checks this declared U1/F5 demo
scenario and is a programmatic MCP client, not an agent.

Review `reports/phase3/codex.retract.toml` and the generated launch script. To run
the actual fresh coding-client exercise yourself:

```sh
sh reports/phase3/start-codex-retract.sh
```

This launches a new Codex execution of [AGENT_TASK.md](AGENT_TASK.md), with a
session-only MCP configuration override. It preserves the user's settings and
records visible Codex events in `reports/phase3/codex-session.jsonl`, plus tool
metadata in `reports/phase3/mcp-activity.jsonl`. It uses the client's configured
model and account. Inspect those genuine records, the generated changes, and
feature tests before claiming success. This fresh coding run has not happened
in the current session; no generated frontend or model reasoning is fabricated.
