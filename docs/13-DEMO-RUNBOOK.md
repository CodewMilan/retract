# Demo runbook

Every step below runs real components: FalkorDB, the Retract HTTP service, the
Groq model, the MCP stdio server, a real Codex CLI session, PostgreSQL, and a
real browser. Nothing is replayed or mocked. Expected outputs are from the
rehearsal on 18 October 2026.

## 0. Prerequisites (once)

```sh
source .venv/bin/activate
docker compose up -d --wait                      # FalkorDB on 127.0.0.1:6380
docker compose -f compose.demo.yaml up -d --wait # PostgreSQL for the account app
set -a; source .env; set +a                      # GROQ_API_KEY for the model steps
```

Use a fresh graph name for each recording. Retract never resets an existing
graph; a new name starts a clean project without deleting old memory.

```sh
export FALKORDB_GRAPH=retract-demo-$(date +%H%M)
```

## 1. Start memory (terminal 1)

```sh
retract serve      # http://127.0.0.1:8100 — API, MCP backend, and dashboard
```

Open `http://127.0.0.1:8100/dashboard` beside the terminals.

## 2. Seed the project (terminal 2)

```sh
retract seed
retract recall account-settings web-client/main
```

Expected: F1 "bearer tokens" is active; P1 (settings page) depends on F1 and F4.

## 3. Confirmed correction, and a proposal that must not apply

```sh
retract call updates fixtures/confirmed-update.json
retract call updates fixtures/proposal.json
```

Expected: U1 `applied`, retired `F1`, accepted `F5` (HTTP-only cookie
sessions), flagged `P1`. The MongoDB proposal is `proposal` and retires nothing;
F3 PostgreSQL stays active. Dashboard: Superseded 1, Affected plans 1,
Pending & proposals 1. Click P1 to show the `U1 → FLAGGED → P1`,
`U1 → RETIRED → F1`, `P1 → DEPENDS_ON → F1` path.

## 4. Reviewer agent (first agent)

```sh
retract agent review account-settings web-client/main
```

Expected: `drafter: groq:openai/gpt-oss-20b`, one decision `handed_off` to
`codex`, reason "P1 depends on F1 (browser-api authentication), replaced by
F5", draft citing `F4` and `F5`. Dashboard → Agent handoffs shows it as open
with "Plan P1 still needs review". Running the command again prints
"Already handed off" and makes no model call.

## 4b. Investigator agent (graph algorithms, decides its own steps)

```sh
retract agent investigate account-settings > reports/demo-investigation.json
```

Takes 20–60 s, because Groq's free tier allows 8,000 tokens per minute and the
agent waits out rate limits. Expected:
- `findings` returns `stale_plan:P1` and `cross_scope_drift:F2:U1`.
- The model inspects with `blast_radius`, `trace` or `centrality`.
- The P1 handoff is **skipped**, because the reviewer's open handoff from step 4
  already covers it. Two agents, no duplicate work.
- The F2 lead is reported only, since no plan depends on F2.

The `outcomes` field lists each finding with what happened to it. If you skip
step 4, the investigator creates the P1 handoff itself
(`investigate-…`), and a later reviewer run skips it.

The model chooses its own path, so the exact step order varies between runs.
Show the `steps` array as it came out; don't promise a fixed order. The
`--playbook` flag runs a fixed order with no model.

## 5. Coding agent (second agent): real Codex session

Codex works in the pre-frontend checkout so it must build the page. The MCP
tools still run from this checkout.

```sh
git worktree add --detach /tmp/retract-baseline 3452a9538f19907c4cb00e4248f2af00cc354639
python scripts/configure_codex.py --check --workspace /tmp/retract-baseline \
  --developer-confirms-revision --report-dir reports/demo-codex
sh reports/demo-codex/start-codex-retract.sh
```

`--developer-confirms-revision` writes the developer's approval into the
prompt and sets `tools.revise_plan.approval_mode = "approve"` for this MCP
server only. Non-interactive `codex exec` otherwise rejects `revise_plan`
("requires approval, but approval policy is never"), which the rehearsal hit
before this setting existed. Without the flag, no tool is pre-approved. The session trace is in
`reports/demo-codex/codex-session.jsonl` and the real MCP calls are in
`reports/demo-codex/mcp-activity.jsonl`.

Expected tool sequence: `recall` → `claim_handoff` (as `codex`) → repository
inspection and code changes → tests → `revise_plan` (P1 → new plan citing F5).
Dashboard: Agent handoffs shows "claimed by codex"; Affected plans drops to 0;
All plans shows P1 superseded by the revision.

## 6. Show the feature Codex built

```sh
cd /tmp/retract-baseline
PYTHONPATH=src python -m retract.demo --seed
PYTHONPATH=src python -m retract.demo     # http://127.0.0.1:8101/settings
```

Sign in as Alice, edit the display name, save, reload. The browser uses the
HTTP-only cookie session and CSRF header; no bearer token is constructed.

## 7. Durability across restarts (no reseeding)

```sh
retract recall account-settings web-client/main > /tmp/before.json
docker compose restart falkordb && docker compose up -d --wait
# Ctrl-C terminal 1, then start `retract serve` again with the same FALKORDB_GRAPH
retract recall account-settings web-client/main > /tmp/after.json
diff /tmp/before.json /tmp/after.json && echo "identical after restart"
```

## 8. Concurrency and isolation evidence

```sh
python scripts/stress_concurrency.py
```

Expected `status: passed`: 400 concurrent requests with zero failures and zero
lost writes, no cross-project leaks, 1 of 24 stale writers accepted, and 1 of 24
handoff claimers winning.

## What to say plainly

- The reviewer drafts and hands off; it never revises a plan or changes a fact.
- The developer's confirmation for `revise_plan` is the explicit prompt flag.
- Concurrency results are for one service process, not horizontal scaling.
- Codex may also succeed partly from reading the repository; memory supplies
  context, it does not prove causation.
