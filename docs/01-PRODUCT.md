# Product specification

## The problem in beginner language

A coding assistant may remember a decision that was correct last week but is wrong today. Saving more chat history does not automatically tell it which instruction is still valid. RETRACT keeps a record of accepted project facts, the evidence behind them, and the plans that rely on them.

The developer supplies an explicit correction. RETRACT updates the current memory without erasing the past. A new agent session asks for relevant context and receives current facts, sources, and warnings about affected plans.

## Target audience

Primary: individual developers and small teams who use coding agents repeatedly on a changing project.

The strongest use case is project decisions that are spread across sessions and documents: architectural choices, service-specific constraints, implementation rationale, and approved exceptions. A short, well-maintained instruction file may be sufficient for a simple project. RETRACT earns its complexity when targeted updates, dependency tracking, and historical explanations matter.

## User workflow

1. Connect one supported coding client to the local MCP service.
2. Store accepted facts with project, scope, and source information.
3. Record important plans with explicit links to the facts they depend on.
4. Submit a confirmed change through a tool or dashboard.
5. Inspect what changed, what stayed valid, and what now needs review.
6. In a fresh coding session, call recall before planning.
7. Let the agent inspect the live repository, implement the feature, and run tests.

Memory is an input to coding decisions. It does not replace reading current code or checking behavior.

## MVP features

| Feature | Required behavior |
| --- | --- |
| Remember | Store a scoped fact and its source. Detect duplicates and conflicts. |
| Process update | Classify a submitted update, then apply an explicit and unambiguous correction under a defined policy. |
| Preserve history | Retain the old fact, replacement relationship, update event, and reason. |
| Recall | Return relevant active facts and evidence; distinguish historical and pending content. |
| Trace impact | Follow explicit dependencies and flag affected plans for review. |
| Dashboard | Show active, superseded, pending, and affected records with sources. |
| Cross-session use | Retrieve the same stored state in a fresh agent session. |

## Product rules

- Compare facts within the same project and scope. Browser authentication and CLI authentication can legitimately differ.
- Support a small set of single-valued fact types first: one accepted value per project/scope/subject/predicate. Do not assume every natural-language statement fits this model.
- A question, proposal, or speculative statement does not supersede an accepted fact.
- Conflicting documents without clear authority create a pending review item.
- Only explicit dependency links justify an affected-plan claim. Unknown dependencies remain unknown.
- Flagging a plan does not mean its implementation is automatically wrong; it needs review.
- Superseded facts are excluded from default current-context retrieval but remain available in history.
- Unaffected facts retain their status and identity.
- Source text is data, not instructions to execute tools or alter update policy.
- If current repository evidence conflicts with memory, surface that conflict instead of silently overriding the code.

## Scope boundaries

Out of scope for the hackathon MVP: autonomous repository-wide change detection, arbitrary code repair, production authentication, multi-tenant SaaS billing, broad integrations, complete belief-revision logic, and guaranteed agent compliance.

Optional after the core works: document ingestion improvements, richer visual graph exploration, a second coding client, or a public preview. Do not let these delay the demonstrated workflow.

## Positioning and existing alternatives

This is a focused developer workflow, not a new invention of temporal memory. The earlier competitor review identified substantial overlap with Graphiti/Zep, invalidate, and other memory systems. We should credit that overlap and evaluate our implementation on usable integration, precise scope handling, dependency tracing, and reproducibility.

Reference products from the discussion:

- [Graphiti](https://github.com/getzep/graphiti): temporal graph memory infrastructure.
- [Zep provenance](https://www.getzep.com/blog/how-zep-tracks-provenance-in-agent-memory/): source tracking and support relationships.
- [invalidate](https://github.com/chopratejas/invalidate): inspiration for the correction/invalidation workflow.
- [Mem0](https://github.com/mem0ai/mem0): persistent assistant-memory infrastructure.

These links identify prior art; this package is not a fresh exhaustive competitor audit. Check licenses and attribution before copying any code. Proposed build: our own small implementation on FalkorDB rather than a claim to recreate those complete products.

## Success statement

For a declared set of project facts and updates, RETRACT returns current supported context, preserves a traceable history, and identifies explicitly dependent plans that need review. A real coding session consumes that context and produces behavior checked by tests.

See [demo and evaluation](02-DEMO-AND-EVALUATION.md) for measurable acceptance criteria.
