# Phase 5: evaluation and reproducible demo

The evaluation scripts and submission draft are implemented. Full release
readiness remains unverified: this session cannot run the actual databases,
Groq evaluation, or browser, and no fresh coding-client feature run or working
video has been observed. Read the generated results as measurements and missing
checks, not a submission approval.

## Fresh evidence bundle

From a Git checkout with Python 3.12+ and Node 20+:

```sh
python scripts/verify_phase5.py
```

This runs the full offline Python suite, JavaScript checks, and the public-file
secret-pattern scan. It writes `phase5.json`, `RESULTS.md`, logs, and artifact
hashes in a new `reports/phase5-<run-id>/` directory. Supply `--report-dir` under
ignored `reports/` for a known location; it must be new or empty. A previous
passing report cannot be silently reused. The bundle records the public-source
file hashes before and after checks, installed Python package versions, actual
child exit codes, and the hashes of generated evidence files. Source changes
during verification fail that check.

Offline success leaves graph/model latency, invalidation/retrieval metrics,
classification accuracy, and usage null. Unit tests with the test-only store
verify report arithmetic and deliberately injected failures; their timings and
fixture scores are not published as runtime measurements.

For actual supported integration checks, prepare the runtime and browser:

```sh
python -m pip install -e '.[demo,mcp-test]'
npm install --ignore-scripts
npx playwright install chromium
docker compose -f compose.demo.yaml up -d --wait
# Export GROQ_API_KEY in this shell for live classification.
python scripts/verify_phase5.py --live
```

The live option deliberately makes up to 16 Groq evaluation requests and starts
the existing isolated Phase 1 Docker gate. It also requests official SDK/real
PostgreSQL checks and actual Chromium UI interactions for the dashboard and
account-settings feature. Install browser OS
prerequisites as needed (`npx playwright install --with-deps chromium` in Linux
CI). Each requested check runs even if an independent earlier check fails, so
missing dependencies remain visible in the result. The model runner stops on a
provider error rather than consuming the rest of the case budget.

The Phase 1 runner owns a separate Docker project, graph, and volume. It runs
real graph tests, the structured metric evaluator, then actual HTTP seeding,
correction, proposal, service/database restart, and exact replay. Passing runs
remove their own test resources. Failed runs preserve their database and print
an explicit cleanup command. Neither runner resets the application graph.
Psycopg tests require the already running synthetic demo PostgreSQL; they use
UUID schemas. Dashboard browser tests use controlled responses; see the
[Phase 4 guide](09-DASHBOARD.md) for an additional read-only live-service check.

The suite does not start a nested coding agent, publish a repository, submit a
form, or generate a pretend demo video. Its result always leaves those remaining
manual evidence items unverified. A real coding-client run and generated-feature
checks are separate from the programmatic MCP probe and offline API tests.

## Structured graph evaluation

Standalone command, with the actual FalkorDB service available:

```sh
python scripts/evaluate_memory.py
```

It connects to `FALKORDB_HOST`/`FALKORDB_PORT`, creates only a generated
`retract-eval-<uuid>` graph, and seeds each case into its own project. It ignores
the caller's `FALKORDB_GRAPH` for isolation. Passing runs delete only that owned
graph; `--keep` preserves it. Failures preserve it for inspection and record its
name. There is no runtime in-memory fallback. A missing package, unavailable
database, or incomplete evaluation yields a nonzero exit and null evaluation.

The 14 declared cases in [memory-eval.json](../fixtures/memory-eval.json) cover
confirmed correction, proposal, ambiguity, untrusted source, absent confirmation,
scope/project separation, unrelated update, unchanged value, wrong target,
stale revision, exact replay, event collision, and a retired target. Every case
includes the normal dependent plan, a cross-scope dependent plan, an unaffected
plan, and a plan with no dependencies. The evaluator checks actual stored facts,
values, sources, event history, returned recall, revision, plan status, and graph
explanation paths; an update response alone cannot establish success.

| Measurement | Definition |
| --- | --- |
| Wrong invalidations | Number of protected preexisting fact records changed or removed unexpectedly after each primary case update. The intended replacement target is excluded only in applied cases. |
| Stale retrievals | Returned “active” fact observations whose stored fact is missing or superseded, or whose returned status is not active. Wrong/missing current values and IDs are separate failing checks. |
| Affected-plan precision | Correctly flagged plans / all observed flagged plans, using declared dependency ground truth. Empty denominator is null. |
| Affected-plan recall | Correctly flagged plans / all expected affected plans. Empty denominator is null. |
| Update/recall/history/replay latency | Observed wall time around synchronous service/storage calls, p50 and nearest-rank p95 with sample counts. Includes storage/network work; excludes HTTP adapter, model, and setup. |

These are small, published synthetic fixtures, with no warmup or concurrent load.
Their results are not an accuracy estimate over arbitrary projects or a production
performance benchmark. A failed case stays failed even if some aggregate counts
are zero. The report records dataset version and exact fixture hashes.

## Model evaluation and comparisons

The separate Phase 2 live runner reports its configured model, prompt version,
16-case classification accuracy, policy outcomes, wrong application decisions,
latency, and provider-reported tokens. Its output is incorporated only when that
runner actually generated a live result in the same fresh bundle. Missing
provider counters stay unknown; retry/failure token totals are not inferred.
See [Phase 2](07-NATURAL-LANGUAGE-UPDATES.md). These published cases are declared
fixtures, not a claimed hidden held-out benchmark.

No plain-memory or instruction-file comparison has been run. If adding one,
keep the same source corrections, repository, task, model, and budget in each
condition. Report both successes and failures, and whether the agent found the
current contract by reading code independently. No causal improvement claim is
supported by the existing fixture tests.

## Demo rehearsal

Use the [four-to-five-minute storyboard](02-DEMO-AND-EVALUATION.md). On a fresh
application graph, start the real stack, seed explicitly once, and open the UI:

```sh
docker compose up -d --wait
retract serve
# In another terminal, same virtual environment:
retract seed
```

1. Inspect F1–F4, their source notes, and P1's stored dependencies. Do not reseed
   an already populated project; use a separate `FALKORDB_GRAPH` for another run.
2. Run `retract call updates fixtures/confirmed-update.json`. Show the returned
   retired/accepted/flagged IDs, F5 in current facts, F1 in history, and P1's path.
3. Run `retract call updates fixtures/proposal.json`. Show that F3 still says
   PostgreSQL and the unaccepted candidate is in the proposals view.
4. Prepare and run the actual fresh coding-client exercise using
   [Phase 3's instructions](08-MCP-AND-CODING-CLIENT.md). Retain its real session
   transcript, successful recall with fact/source IDs, inspected source files,
   generated code diff, and the actual cookie/CSRF/ownership feature-test output.
   Adapter tests and a hand-written transcript do not establish this step.
5. Perform the documented service/database restart without seeding and compare
   the actual before/after state. The isolated Phase 1 runner provides a repeatable
   automated version of this check.
6. Record the working workflow and visible test outcomes. Label any edits that
   shorten generation waits, and label a structured-input fallback if inference
   is unavailable. No genuine successful recording exists from this session.

The root README documents environment exports, setup, seed refusal, non-destructive
stop/restart, and client connection. There is no reset command that silently
wipes user memory. Failed isolated verification resources have their own printed
cleanup instructions.

## Public-file check and submission

```sh
python scripts/check_release.py
```

The bounded scanner checks tracked/nonignored working files and reachable Git
blobs for specified token, private-key, and credential-URL patterns. It reports
location/line/pattern only, never matched content. The documented synthetic demo
credential is explicitly excluded. Ignored local environment files, reports,
virtual environments, and dependency directories are outside public-file scope.
Binary/oversize files, symlinks, and shallow history make coverage incomplete.
No matches means no matches for these patterns, not proof of security or an
exhaustive guarantee about personal data. Review new data and recordings before
publishing. CI fetches full history for the same scan.

[SUBMISSION.md](SUBMISSION.md) contains reviewable project copy and the remaining
evidence checklist. [Graph queries](11-GRAPH-QUERIES.md) identify the implemented
algorithm and authoritative query source. [Dependency notices](../THIRD_PARTY_NOTICES.md)
record direct upstream license references, prior art, synthetic data, and AI
assistance. The owner has not selected a project license; no license was assigned
on their behalf.

The [official rules](https://www.wemakedevs.org/hackathons/falkordb/rules), rechecked
17 October 2026, require a public repository, README setup/model, actual queries,
a working demo video, a deployment or complete local instructions, the named
track, permitted data, and AI assistance disclosure. The stated submission
window closes 18 October 2026 at 11:59 PM IST. The prepared files are a draft;
repository visibility, working demo evidence, and successful submission are not
established by writing them.

## Observed verification in this session

On Python 3.12 and 3.14, all 156 offline Python tests pass; 16 actual-database/
optional-SDK checks are explicitly skipped. The 21 Phase 5 checks and 7 JavaScript
checks pass. A public-file/Git-history pattern scan found no matches and no
coverage exclusions. Compileall and diff whitespace checks pass.

The combined `--live` attempt exited 1 and retained
`reports/phase5-live-attempt/RESULTS.md`: FalkorDB client missing, Groq key absent,
MCP SDK missing, and Chromium denied during launch. No real metric or working
video was fabricated. The standalone graph evaluator also exits 1 with null
measurements. The final offline evidence bundle is in
`reports/phase5-final/RESULTS.md`; it explicitly remains live-unverified and
submission readiness is false.

The continued build now includes the account-settings page and its controlled
HTTP/client checks. The full JavaScript command covers both dashboard and
account clients; `--live` additionally requests the settings browser suite.
This implementation is separate from the still-unverified fresh coding-client
exercise. See the [account guide](../examples/account-settings/README.md), which
records its pre-frontend baseline and remaining real-browser/PostgreSQL gate.
