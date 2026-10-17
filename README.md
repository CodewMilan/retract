# RETRACT

Persistent project memory for coding agents. A confirmed, scoped correction
supersedes an outdated fact, keeps its evidence and history, and flags plans
with explicit dependencies on that fact.

The backend and optional natural-language adapter are implemented with passing
offline tests. Real FalkorDB integration, database persistence, and live model
quality remain **unverified**. MCP integration and the dashboard are not yet
implemented. See [the verification record](docs/06-IMPLEMENTATION-STATUS.md).

The product and remaining milestones are described in [docs/README.md](docs/README.md).

## Local setup

Requires Python 3.12+ and Docker with a running daemon. Run from this directory:

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
docker compose up -d --wait
retract serve
```

The API binds to `127.0.0.1:8100`; FalkorDB binds to `127.0.0.1:6380`. The
database uses a named volume and AOF with `appendfsync always`. The image pin
`falkordb/falkordb:6.0.2` is a candidate awaiting this project's integration run.
Configuration variables are listed in [.env.example](.env.example); export
overrides before starting the service. No API key or inference account is
needed for structured updates.

Use one service process per graph. A local file lock prevents accidental second
processes with the same database configuration. All clients send writes through
the API; other processes must not write directly to the graph. Host aliases,
other machines, and distributed writers are outside this MVP's guarantees.

## Run the structured demo

In another terminal with the virtual environment activated:

```sh
retract seed
retract recall account-settings web-client/main
retract call updates fixtures/confirmed-update.json
retract call updates fixtures/proposal.json
retract recall account-settings web-client/main
retract recall account-settings cli-client/main
retract recall account-settings account-service/main
retract history account-settings --fact F1
retract history account-settings --event U1
```

Expected behavior, pending a real database run: F1 becomes superseded, F5 becomes
active, P1 needs review, and F2–F4 remain unchanged. The MongoDB proposal does not
replace PostgreSQL. Calling the confirmed-update command again returns the
original result without repeating its effects. Reusing U1 for a different
request returns a conflict.

Seeding is explicit and refuses a project whose revision is already nonzero.
Startup never seeds or resets data. If a seed is interrupted, inspect the stored
state and continue individual actions from [the fixture](fixtures/demo-seed.json)
using `retract call`; do not delete existing memory to hide a partial run.

The Phase 1 demo uses deliberately structured inputs. Its `classification` is
supplied by the local developer workflow. An optional natural-language endpoint
now extracts that classification through Groq; see below.
The local API trusts the developer's source-authority declaration. It is not a
public authenticated service. A source excerpt must occur in the supplied source,
but that alone does not prove that a source or extraction is truthful.

## API

All POST routes accept JSON objects, with a 64 KiB request limit. Source text is
treated as data. The HTTP adapter uses the same `MemoryService` that later
dashboard and MCP adapters will use.

| Route | Inputs |
| --- | --- |
| `GET /health` | Checks a real database query; unavailable storage returns 503. |
| `POST /projects` | `project_id`, `name` |
| `POST /remember` | `project_id`, `scope`, `subject`, `predicate`, `value`, `source`; optional `fact_id`, `expected_revision` |
| `POST /plans` | `project_id`, `scope`, `text`, `dependency_fact_ids`; optional `plan_id`, `expected_revision` |
| `POST /updates` | See [confirmed update](fixtures/confirmed-update.json) and [proposal](fixtures/proposal.json). Optional `expected_revision` guards stale clients. |
| `POST /updates/natural` | Project/scope/subject/predicate, event ID, update text, source, developer confirmation; optional `expected_revision`. See [example](fixtures/natural-update.json). |
| `POST /recall` | `project_id`, `scope`; optional `subjects` list |
| `POST /history` | `project_id`, exactly one of `fact_id` or `event_id` |

Sources have `id`, `kind` (`developer` or `document`), `title`, `content`, and
`authority` (`developer`, `approved_document`, or `untrusted`, the default).
IDs are immutable within a project. All fact keys are single-valued combinations
of project, scope, subject, and predicate. Different values must go through the
correction workflow.

Only confirmed, authoritative corrections with a matching active target can
apply. Proposals are recorded as proposals, unrelated updates are ignored, and
ambiguous or unconfirmed corrections are pending. Pending claims are event data,
never accepted facts. Reviewing one requires a new event ID and current target;
the old event remains immutable. Every newly recorded event advances the project
revision, even when it leaves facts unchanged. Exact event retries return the
original revision and result.

Dependencies currently link plans directly to facts; a plan may depend on facts
in another scope within the same project. Affected-plan discovery follows these
stored relationships, without text similarity or inferred code dependencies.
Fact history traverses replacement relationships up to 32 edges. Recall uses
exact scope and optional subject filters; it does not perform semantic search.

## Natural-language updates

With `GROQ_API_KEY` set in the service's environment, submit natural language for
one selected scoped key:

```sh
retract call updates/natural fixtures/natural-update.json
```

The model classifies the update and extracts an evidence-backed candidate. The
same deterministic correction policy still requires developer confirmation and
source authority. The key stays server-side; the selected fact, submitted text,
and source content are sent to Groq. Other memory is excluded. Exact event replays
use the stored result without a model call. Structured updates remain usable
without inference configuration.

Run Phase 2's offline tests with `python scripts/verify_phase2.py`. To measure the
actual configured model on the 16 declared cases, run
`python scripts/verify_phase2.py --live` with the key configured. No live result
has been measured here. Details, bounds, failure behavior, and limitations are in
[the Phase 2 notes](docs/07-NATURAL-LANGUAGE-UPDATES.md).

Actual parameterized Cypher is in [graph.py](src/retract/graph.py). Each logical
mutation is one graph write guarded by the project revision. Database-level
failure behavior remains an integration gate; offline tests do not establish
atomicity or crash recovery.

## Verification

Development is organized into five phases in the build plan: graph-backed memory,
natural-language interpretation, one real coding-client integration, the dashboard,
then evaluation and submission. Each phase ends with its relevant tests and a
recorded result. A blocked or skipped exit-gate check keeps that phase in progress.
Phase 2's adapter was implemented at the user's request to continue; Phase 1's
unresolved database gate has not been counted as a pass.

Policy and application tests need only Python's standard library:

```sh
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

The real database suite creates and deletes only UUID-named test graphs, leaving
the application graph intact. Missing dependencies or an unavailable database
fail the opt-in run, rather than being counted as passes:

```sh
RUN_FALKORDB_TESTS=1 python -m unittest tests.test_integration -v
```

[CI](.github/workflows/test.yml) is configured to run that suite against
FalkorDB, but no CI run has been observed yet.

Run the complete Phase 1 gate from an activated environment with dependencies
installed:

```sh
python scripts/verify_phase1.py
```

This runs the offline tests and real database suite, creates the fixture through
the HTTP API, restarts both the database and service, and compares facts, IDs,
sources, plan warnings, revisions, history, and replay results without reseeding.
It also checks the actual database durability configuration. The runner owns a
separate UUID-named Compose project, dynamic local port, and persistent test
volume; it never restarts the application database. Passing runs clean up their
own resources. Failed runs preserve their test database and print its cleanup
command. Reports, snapshots, and service logs go to an ignored `reports/`
directory. The command exits nonzero if any required check cannot run or fails.
CI is configured to use this same gate and retain its report as an artifact.

For a manual persistence check after the structured demo, **without reseeding**:

```sh
retract recall account-settings web-client/main > /tmp/retract-recall-before.json
retract history account-settings --fact F1 > /tmp/retract-history-before.json
docker compose restart falkordb
docker compose up -d --wait
```

Stop `retract serve` with Ctrl-C and start `retract serve` again. Then:

```sh
retract recall account-settings web-client/main > /tmp/retract-recall-after.json
retract history account-settings --fact F1 > /tmp/retract-history-after.json
diff -u /tmp/retract-recall-before.json /tmp/retract-recall-after.json
diff -u /tmp/retract-history-before.json /tmp/retract-history-after.json
```

Both comparisons should be identical. This checks orderly restart retention;
it does not establish crash recovery. `docker compose stop` preserves the volume.
For isolated experiments, export a different `FALKORDB_GRAPH` and run one service
against it. There is intentionally no automatic destructive reset command.

## Next gate

Run the real FalkorDB suite and restart checks, fix any query/SDK incompatibility,
and pin the verified client and image versions. Run the Phase 2 live evaluation
and resolve any classifier failures. One MCP coding client and the dashboard
follow those gates as specified by [the build plan](docs/05-BUILD-PLAN.md).

Implementation was developed with OpenAI Codex assistance. Runtime dependency:
the official [FalkorDB Python client](https://github.com/FalkorDB/falkordb-py).
The correction workflow is inspired by the prior art credited in
[the product specification](docs/01-PRODUCT.md).
