# Architecture and implementation contract

Status: proposed MVP design. Validate SDK compatibility and database guarantees during implementation; examples here describe intended behavior, not tested application code.

Implementation note, 17 October 2026: the Python service, local JSON HTTP adapter, CLI, parameterized graph repository, and optional Groq extraction adapter now exist. Direct plan-to-fact dependencies are supported in code; plan-to-plan traversal is deferred. Structured updates remain available without a model; natural updates select one scoped key and pass validated extraction into the same deterministic policy. Real database compatibility, persistence, and live model quality are still unverified. See the [implementation record](06-IMPLEMENTATION-STATUS.md) and [Phase 2 contract](07-NATURAL-LANGUAGE-UPDATES.md).

Phase 3 adds a narrow standard-library MCP stdio adapter, routing all four tools
through the same HTTP service. Codex configuration parsing is checked; official
SDK interop and an actual coding-client call remain unverified. The synthetic
account backend and frontend task are prepared separately. See the
[Phase 3 contract](08-MCP-AND-CODING-CLIENT.md).

## Components

| Component | Responsibility |
| --- | --- |
| Coding client | Calls memory tools, inspects live code, implements the feature, and runs tests. |
| Local MCP adapter | Exposes the memory operations to one selected coding client. Prefer local stdio for the MVP. |
| Python service | Owns validation, update policy, graph queries, and dashboard endpoints. |
| FalkorDB | Authoritative store for facts, sources, events, scopes, and dependencies. |
| Model API | Converts natural-language updates into structured candidate changes. |
| Browser dashboard | Displays actual service state, evidence paths, and tool activity. |

The MCP adapter and dashboard must use the same application service logic. Neither may maintain a separate authoritative memory cache. One backend can serve the dashboard's static assets to reduce infrastructure.

## Graph model

Every project-owned node has a project_id. IDs are stable and application-generated. Scope includes the relevant component and branch/environment where needed; never default a scoped correction to every environment.

| Node | Key fields |
| --- | --- |
| Project | id, name |
| Source | id, project_id, kind, title, content, recorded_at, authority |
| Fact | id, project_id, scope, subject, predicate, value, status, recorded_at, superseded_at |
| Plan | id, project_id, scope, text, status |
| UpdateEvent | id, project_id, text, classification, outcome, reason, recorded_at, expected_revision, resulting_revision |

Fact status: active or superseded. Plan status: current or needs_review. Unaccepted candidate claims stay on pending UpdateEvents and are not returned as accepted Facts.

| Relationship | Meaning |
| --- | --- |
| Project HAS_FACT Fact | Fact belongs to the project. |
| Source SUPPORTS Fact | Source records evidence for the fact. |
| Plan DEPENDS_ON Fact | Plan explicitly relies on the fact. |
| Plan DEPENDS_ON Plan | Optional explicit plan dependency; bounded traversal only. |
| NewFact SUPERSEDES OldFact | New accepted value replaces the old value within its scope. |
| UpdateEvent BASED_ON Source | Update cites its source. |
| UpdateEvent RETIRED OldFact | Update superseded this fact. |
| UpdateEvent ACCEPTED NewFact | Update accepted this fact. |
| UpdateEvent FLAGGED Plan | Update caused this plan to need review. |

Keep historical sources and facts intact. Source-deletion semantics and sophisticated multi-source truth maintenance are outside the MVP.

## Update pipeline

1. Validate project, scope, source, event ID, and input size.
2. Resolve candidate facts by project, scope, subject, and predicate. Do not send the full database to the model.
3. Ask the model to classify the text as confirmed_change, proposal, ambiguous, or unrelated, and extract a candidate value plus source excerpt.
4. Validate that structured output against the schema. Model output is a proposal to the policy layer, not arbitrary database instructions.
5. Require an explicitly confirmed update from the configured authoritative developer/document workflow. A model confidence score alone cannot authorize replacement.
6. If scope, target, or authority is unclear, record a pending event without changing active facts. An unconfirmed proposal also leaves them unchanged.
7. For an accepted replacement, preserve the old fact, create the new fact and replacement link, and record the evidence and event.
8. Traverse explicit dependencies to affected plans. Mark them needs_review and retain the path explaining each flag.
9. Commit the complete transition consistently and return a structured result.

For the MVP, serialize writes through one service process. Use supported atomic database operations and a project revision guard; verify the chosen transaction mechanism with the actual client. A failure must not expose a half-applied correction. Repeating an event ID returns its existing result. Do not claim distributed concurrency support.

Initial remember uses the same validation policy: a conflicting fact must enter the correction workflow rather than creating two active values for a single-valued key.

## Retrieval

For the demo, use explicit project/scope/topic filters and known fact subjects. Return active relevant facts with their sources, plus affected-plan warnings and pending conflicts as separate fields. Embeddings and open-ended semantic search are optional future work.

The service computes graph paths for both dependency impact and evidence retrieval. The dashboard renders those paths from the query result. The visual is not the reason for using a graph; the stored relationships drive the result.

A historical fact may appear in an explicitly labeled explanation, but must never appear in the active_facts field. Do not infer an unrecorded dependency merely because two pieces of text look similar.

## Proposed tool contracts

Names and shapes below are implementation targets; adapt them to the selected SDK without changing their semantics.

| Tool | Required inputs | Output |
| --- | --- | --- |
| remember | project_id, scope, fact fields, source | fact_id, status, duplicate/conflict outcome |
| process_update | project_id, scope, event_id, text, source, confirmation | classification, outcome, retired IDs, accepted IDs, flagged plan IDs, explanation paths |
| recall | project_id, scope, subjects/topics | active_facts, sources, affected_plans, pending_conflicts, project_revision |
| history | project_id, fact_id or event_id | historical facts, replacement links, sources, and events |

Recording a plan and its dependency IDs can initially be a dashboard/service operation. No fifth MCP tool is required for the first demo.

Example accepted update result:

```json
{
  "event_id": "U1",
  "outcome": "applied",
  "retired_fact_ids": ["F1"],
  "accepted_fact_ids": ["F5"],
  "flagged_plan_ids": ["P1"],
  "reason": "Confirmed replacement for web-client/main authentication",
  "source_id": "S2"
}
```

## Agent integration

Configure the selected client to call recall before planning and to cite returned fact/source IDs when explaining relevant decisions. Observe an actual tool call in testing. Exposing MCP tools does not guarantee that every client/model will call them; document the supported client and exact tested configuration.

The agent must inspect current code. If it disagrees with memory, report the conflict and resolve it from evidence. Do not claim to observe hidden model reasoning; trace visible sources, tool calls, changes, and checks.

## Operational boundaries

Keep the database and local service bound to localhost or a private container network. Keep API keys server-side and out of the repository. A public write endpoint requires authentication and usage controls; it is optional for the hackathon. Fail clearly when the database/model is unavailable rather than returning fabricated current context. Use parameterized database queries and validate all IDs/scopes.

See [evaluation](02-DEMO-AND-EVALUATION.md) for tests and [build plan](05-BUILD-PLAN.md) for implementation order.
