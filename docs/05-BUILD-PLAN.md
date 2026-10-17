# Build plan and submission checklist

Status: milestones 1–3 have implemented code and passing offline checks, but remain in progress. Real FalkorDB/restart checks, live model evaluation, and a real coding-client feature run remain unverified. Milestones 4–5 remain pending. See the [implementation record](06-IMPLEMENTATION-STATUS.md). Original estimate: 24–36 focused engineering hours for a developer familiar with the stack, including integration and demo preparation. Estimates are not a promise; prioritize a working vertical slice.

## Phase execution rule

Implement these milestones in order. After each phase, run its relevant checks,
fix failures, and record the actual results in the implementation record before
advancing. An unavailable dependency or skipped required check leaves the phase
in progress; it does not count as a pass. Continue to the next phase without a
new approval request once the current gate passes.

The user subsequently requested moving to the next phase while Phase 1 was
environment-blocked. Phase 2's adapter and offline tests were implemented on that
authorization; the earlier unresolved gate is retained explicitly. This does
not establish that either phase passed its full exit criteria.

Phase 1's complete repeatable check is `python scripts/verify_phase1.py` from an
activated environment with project dependencies installed. It includes the real
database suite and database/service restart retention in isolated test resources.

Phase 2's offline check is `python scripts/verify_phase2.py`; live model/policy
evaluation is `python scripts/verify_phase2.py --live` with `GROQ_API_KEY` configured.
The live run does not replace the database checks. See the [Phase 2 notes](07-NATURAL-LANGUAGE-UPDATES.md).

Phase 3's offline check is `python scripts/verify_phase3.py`. Optional SDK,
PostgreSQL, and live service-probe flags are documented in the
[Phase 3 notes](08-MCP-AND-CODING-CLIENT.md). The actual fresh coding-client task
and frontend feature checks remain separate required evidence. Independent
Phase 3 implementation continued at the user's next-phase request while earlier
environment-blocked gates stayed open.

## Milestone 1 — Graph-backed correction flow

Estimated effort: 6–8 hours.

- Start FalkorDB locally with a persistent volume.
- Define the node/relationship model and scoped single-value invariants.
- Seed the synthetic F1–F4 facts and P1 plan from the demo document.
- Implement remember, structured correction, recall, and history in the service.
- Keep writes consistent and replayed event IDs idempotent.
- Implement dependency traversal and evidence-path results.

Exit gate: a structured confirmed browser-auth correction supersedes F1, creates F5, flags P1, and leaves F2–F4 intact. History contains the old fact and source. Restart retains state without reseeding.

Do not build the polished dashboard before this gate passes.

## Milestone 2 — Natural-language update interpretation

Estimated effort: 4–6 hours.

- Add a model adapter with bounded inputs and schema-validated outputs.
- Separate confirmed changes, proposals, ambiguity, and unrelated updates.
- Apply deterministic source/scope/confirmation rules after extraction.
- Add clear error and rate-limit handling.
- Evaluate on fixture paraphrases and record results.

Exit gate: explicit correction applies; proposal does not mutate accepted state; uncertain conflict stays pending. Scope-specific updates do not leak into another scope or project.

If this fails, narrow the supported input format and disclose that limitation. Do not hide errors behind confidence scores.

## Milestone 3 — Real coding-client integration

Estimated effort: 4–6 hours.

- Select one MCP-capable coding client and document its tested configuration.
- Expose the four memory tools using the same service logic.
- Observe recall in a genuinely fresh agent session.
- Run the account-settings task against the working fixture application.
- Verify current session behavior and unchanged ownership requirements.

Exit gate: tool call and returned sources are visible, generated code is inspectable, and relevant tests run. Report any failed checks honestly. Do not claim every client will use the tools automatically.

## Milestone 4 — Minimal dashboard and trace

Estimated effort: 4–6 hours.

- Build views for active facts, history, pending updates, and affected plans.
- Add an update input and a readable before/after view.
- Show graph-derived evidence/dependency paths with short labels.
- Show actual tool activity and errors, not fabricated live statuses.

Exit gate: a developer can answer “what changed, why, and which plan needs review?” from the actual stored state. A plain evidence list is acceptable before graph-animation polish.

## Milestone 5 — Evaluation and submission

Estimated effort: 6–10 hours.

- Run the meaningful checks in the evaluation document.
- Record classification results, false invalidations, stale retrieval, and latency.
- Rehearse the complete demo and record the genuine working flow.
- Write actual installation, environment, seed, reset, and client-connection instructions.
- Include the exact implemented Cypher queries or graph algorithms.
- Verify the repository contains no secrets and uses only permitted demo data.
- Record dependencies, licenses/attribution, and AI assistance.

Exit gate: someone can reproduce the workflow from a clean setup using documented prerequisites, configuration, and commands. Mark any optional hosted URL accurately as preview/demo.

## Scope-cut order

If time is tight, remove these in order:

1. Public cloud hosting.
2. Graph animations and advanced dashboard polish.
3. Multiple coding clients.
4. Open-ended document ingestion and semantic search.
5. Multi-hop plan dependencies beyond the necessary demonstrated links.

Keep correction correctness, scope isolation, source/history, graph-based impact discovery, actual client integration, and persistence. They are the substance of the project.

## Go/no-go conditions

| Observation | Response |
| --- | --- |
| Model frequently treats questions as corrections | Keep ambiguous inputs pending and narrow supported updates. |
| Agent never calls recall | Fix the one supported integration before adding clients or UI features. |
| Correction only changes a database row | Add real stored dependency traversal and evidence retrieval before claiming graph value. |
| Baseline agent also solves the coding task | Report that result; emphasize measured context correctness and traceability. |
| Restart loses memory | Fix durability before recording a persistence claim. |
| Free API quota blocks rehearsal | Reduce model usage or explicitly choose a paid fallback; do not simulate live inference silently. |

## Hackathon submission

The published event window ends 18 October 2026 at 11:59 PM IST. Recheck the official schedule before submission.

- [ ] Public source repository.
- [ ] README explains the problem, target user, and supported workflow.
- [ ] Exact local setup instructions or a working deployment.
- [ ] Graph data model and actual queries/algorithms.
- [ ] Working-project demo video.
- [ ] Agent Memory and Coordination track identified.
- [ ] AI assistance disclosed; participant can explain implementation choices.
- [ ] Permitted public/synthetic data and dependency attribution.
- [ ] Actual evaluation results and known limitations.
- [ ] No unsupported originality, performance, or production-readiness claims.

Source: [official rules](https://www.wemakedevs.org/hackathons/falkordb/rules), checked 16 October 2026. Rules accept Docker, self-hosted, or cloud FalkorDB, and require it to support central functionality.

## Definition of done

A developer can store scoped project facts, submit a correction, inspect the preserved history and affected plans, and retrieve the corrected context from a fresh coding session. The graph drives the result, the example feature is checked with real tests, and the stored memory survives a service restart. All demonstrated behavior is reproducible from the submitted repository.
