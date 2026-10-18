# Phase 2 — Natural-language update interpretation

Status: adapter and deterministic integration implemented; offline tests pass.
Live classification quality is unmeasured. The earlier real database and restart
gate remains unresolved. Development continued at the user's explicit request
to move to the next phase; neither gate is represented as passed.

## Supported input

This first version interprets a change to one explicitly selected key:
`project_id`, `scope`, `subject`, and `predicate`. The caller selects those from
memory; RETRACT retrieves the matching active fact. The model receives that one
fact's scope/key/value, the update text, and the supplied source content. It does
not receive the full graph, history, unrelated sources, source authority,
developer confirmation, or application-generated IDs.

The natural-language endpoint does not accept a caller-supplied classification,
candidate, database query, or replacement ID. It uses a separate schema from the
structured Phase 1 endpoint. It replaces existing accepted facts; new facts still
use `remember`. Unknown targets result in pending events rather than creation of
accepted facts.

Start the existing local service with `GROQ_API_KEY` exported in its environment.
`GROQ_MODEL` defaults to `openai/gpt-oss-20b`. Keys stay server-side. No new Python
dependency is required for inference; the adapter uses HTTPS from the standard
library. Input text and evidence are sent to Groq only when this endpoint or live
evaluation is invoked. The structured endpoint continues to work without a key.

```sh
# Activate .venv and configure GROQ_API_KEY in your shell first.
retract serve
```

Against a freshly seeded demo project in another terminal:

```sh
retract call updates/natural fixtures/natural-update.json
retract recall account-settings web-client/main
retract history account-settings --event N1
```

The request is a JSON POST to `/updates/natural`; see
[the example](../fixtures/natural-update.json). Browser authentication must still
be on F1 for that example to demonstrate a replacement. If U1 was already applied,
the same extracted value may correctly produce `no_change`. Natural updates use
generated replacement IDs instead of promising the demo-specific F5 ID.

## Interpretation and mutation policy

Groq is asked for strict schema-constrained output containing a classification,
scope, and optional candidate. Local validation still checks every field, rejects
extra fields and malformed types, and requires candidate evidence to occur
verbatim in both the update text and source content. A valid extraction that does
not resolve the selected scope/key becomes ambiguous and pending.

The model cannot supply confirmation or source authority. After extraction,
the existing deterministic policy requires an explicit developer confirmation,
an authoritative source, and a matching active target before replacing a fact.
Proposals and unrelated changes are recorded without retiring facts; ambiguous
or unconfirmed changes remain pending. A schema guarantee does not establish
that a classification or extracted value is semantically correct; that still
requires evaluation and review.

Inference runs outside the application's write lock so recall can continue. The
subsequent transition checks the project revision captured before inference. A
concurrent write causes a 409 conflict rather than applying stale extraction.
The original natural request, rather than nondeterministic model output, defines
the event fingerprint. Exact recorded retries return the stored result without
calling Groq, including after a new service instance. Simultaneous first attempts
may each call the provider but can commit only one event/result.

Stored interpretation metadata includes the provider/model identifier, prompt
version `retract-extract-v2`, validated extraction, measured latency, number of
attempts, and any provider-reported token counters. Missing counters remain
unknown. Raw provider error bodies and credentials are not returned.

## Bounds and errors

- Natural update text: 4,000 characters. Source content: 6,000 characters.
- Serialized model context: 12,000 UTF-8 bytes. Oversize input is rejected rather
  than silently truncating evidence.
- Response: at most 32 KiB; incomplete, refused, or invalid output is rejected.
- Each provider attempt has a 15-second timeout. At most one retry is allowed for
  a transient connection/server error or a rate limit with a delay of at most two
  seconds. Longer rate limits are returned immediately to the caller.
- HTTP 400: invalid input; 409: stale revision/event or source conflict;
  429: model rate limit with `Retry-After`; 502: invalid/rejected extraction;
  503: missing credentials or unavailable model/storage.

Provider failures do not create an event or change accepted memory. An exact
request can be retried after the failure. No model fallback fabricates a result.

## Phase tests and live evaluation

Run the adapter, policy-integration, and report tests:

```sh
python scripts/verify_phase2.py
```

The offline report is explicitly marked `offline_passed_live_unverified` and
contains no claimed model-accuracy or live latency result. Full regression checks
remain `PYTHONPATH=src python3 -m unittest discover -s tests`.

With `GROQ_API_KEY` configured, run the declared live evaluation:

```sh
python scripts/verify_phase2.py --live --report reports/phase2-live.json
```

This invokes the actual configured model on
[16 synthetic cases](../fixtures/classification-eval.json): accepted changes,
paraphrases, proposals, negations, conditional/contradictory notes, scope/subject
differences, missing confirmation, untrusted evidence, and an embedded instruction.
Expected labels are kept out of model input. Cases are spaced eight seconds
apart by default; actual account limits can still interrupt a run. The runner
stops after a request error and reports unevaluated cases explicitly.

The report records raw/effective classifications, pure-policy outcomes, latency,
provider token usage, errors, and wrong application decisions. The declared small
fixture gate requires all 16 cases to complete with the expected classifications
and policy outcomes. These checks neither prove universal correctness nor
evaluate an actual coding client's behavior. The evaluation does not write a
graph, so its policy metrics must not be described as measured database
invalidations. The real database suite separately includes a natural-update
integration check with a controlled provider response.

No live run has happened in this session: no Groq key is configured. Classification
accuracy, real inference latency, actual token usage, and account limits remain
unknown. The next gate is to run that evaluation and the unresolved Phase 1 gate,
then fix actual failures before declaring either phase complete.

Implementation references: [Groq structured outputs](https://console.groq.com/docs/structured-outputs),
[chat completion API](https://console.groq.com/docs/api-reference), and
[rate-limit behavior](https://console.groq.com/docs/rate-limits).
