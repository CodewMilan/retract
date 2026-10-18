# RETRACT — the product we are building

Direction agreed: 18 October 2026.

This document is the product-direction source of truth for the hackathon MVP. Read it before the earlier planning documents. Where earlier wording makes the product appear complete once memory storage or the dashboard works, this document clarifies the required end-to-end outcome. Preserve compatible architecture and working code; do not interpret this as a request to rewrite the project.

Status: requirements and acceptance criteria. This document does not establish which features currently exist. Inspect the repository and verify behavior before reporting implementation status.

## 1. Product definition

**RETRACT gives a coding agent persistent, evidence-backed project memory that can be corrected, and helps it identify and revise plans that depend on outdated decisions.**

When a project decision changes, RETRACT preserves the previous decision, records the replacement and its source, and follows graph dependencies to affected plans. A later coding session retrieves that context, checks the current repository, revises its plan, implements the requested feature, and runs relevant tests.

The complete product demonstration is:

**Confirmed change → graph-based impact discovery → fresh-session retrieval → agent plan revision → code change → test result.**

Memory infrastructure is our core contribution. An existing coding agent supplies the execution capability. The hackathon submission demonstrates their working integration as one complete workflow.

## 2. User and problem

The primary user is a developer who uses a coding agent across multiple sessions on a changing project.

Project knowledge includes architecture decisions, component-specific exceptions, approved constraints, and the reasoning behind implementation plans. Old information can remain in previous conversations or saved plans after a decision changes.

The developer needs to know which context is accepted now, where it came from, and which saved plans require another look. The agent needs that same context before continuing work.

For a small, stable project, a maintained instruction file may be sufficient. RETRACT must demonstrate additional value through scoped corrections, explicit dependencies, preserved history, and usable evidence retrieval. Memory invalidation itself is not a novel invention.

## 3. Alignment with the hackathon

The intended track is **Agent Memory and Coordination**. The following is our interpretation of how to satisfy the brief; it is not an organizer's endorsement or a guarantee of judging outcomes.

| Brief requirement | Product behavior | Demonstration evidence |
| --- | --- | --- |
| Connected context | Facts, sources, and plans are related in FalkorDB. | Actual stored relationships and queries. |
| Memory across sessions | A new coding session retrieves previously corrected context. | Fresh session and real recall tool result. |
| Understanding relationships | A changed fact identifies the plans explicitly dependent on it. | Dependency path explaining each affected plan. |
| Traceable decisions | The agent cites retrieved evidence when revising its plan. | Source/fact IDs, visible plan revision, code diff, and test result. |
| Central graph functionality | Graph queries determine impact and retrieve supporting evidence. | Results change when relevant relationships change; no hardcoded impact list. |

The official rules require FalkorDB to be central, accept local deployments, and require reproducible submission materials. The demo must therefore show a working agent consuming graph-derived context, beyond screenshots of a memory dashboard.

Official source, checked 18 October 2026: [Graph Hacks rules](https://www.wemakedevs.org/hackathons/falkordb/rules).

## 4. Product surfaces

| Surface | Responsibility | Priority |
| --- | --- | --- |
| Landing page | Explain the value, show the demo, and provide setup instructions. | Minimal; secondary to working behavior. |
| Local MCP server | Expose memory operations to one tested coding client. | Required. |
| Project dashboard | Inspect current facts, history, sources, affected plans, and observed tool activity. | Required, with a small functional UI. |
| Existing coding client | Inspect code, consume context, revise a plan, edit files, and run tests. | Required integration. |

Coding occurs in the developer's existing client. The website is the companion interface. A separate editor plugin, browser-based IDE, or custom coding model is unnecessary for the MVP.

The dashboard and MCP adapter share the same service and authoritative graph state. A website chat box can be a future addition, but does not substitute for the real coding-client integration promised here.

## 5. Normal developer workflow

1. Start the local RETRACT service and persistent FalkorDB instance.
2. Connect one supported coding client using the documented MCP configuration.
3. Store scoped project facts with evidence. Record a saved implementation plan and the fact IDs it relies on through the service or dashboard.
4. Submit an explicitly confirmed change through the client or dashboard.
5. Inspect the accepted replacement, preserved history, and affected-plan warnings.
6. Start a fresh coding session and request a feature.
7. The configured agent calls recall before planning, examines the returned evidence, and checks the live repository.
8. It revises the relevant plan, makes the code change, and runs meaningful tests.

Tool availability alone does not guarantee tool usage. Demonstrate and document the actual supported client configuration. The developer initiates the task and confirms authoritative updates; the MVP does not autonomously monitor every repository change.

## 6. Canonical demo

Use a small synthetic account-settings application and an approved architecture note.

### Starting state

- F1: browser client authentication uses bearer tokens.
- F2: CLI authentication uses bearer tokens.
- F3: account data uses PostgreSQL.
- F4: users may update only their own profile.
- P1: saved settings-page plan depends on F1 and F4.

Facts carry project/component scope and supporting sources. P1's dependencies are actual graph relationships, not text annotations used only for display.

### Confirmed change

Submit: “Approved for the browser client: authentication now uses HTTP-only cookie sessions. Replace the old browser bearer-token decision. CLI authentication is unchanged.”

Expected RETRACT behavior:

1. Supersede F1 and create the accepted replacement F5 with its source.
2. Follow P1's dependency on F1 and mark P1 as needing review.
3. Preserve F2, F3, and F4 unchanged.
4. Retain the old fact and the event explaining its replacement.
5. Treat “Should we switch to MongoDB?” as a proposal, leaving F3 active.

### Agent action

Open a fresh coding session and request the account-settings feature. Show a real recall call returning F5, supporting evidence, and the P1 warning. The agent explains that P1 relied on a superseded decision, inspects the current backend/session contract, and revises the browser implementation plan.

Then show the actual code change and relevant test results. The current fixture backend should already provide a working session contract; this project is not building an authentication framework. Preserve existing request protections and ownership checks.

Finally, restart the memory service/database and retrieve the same fact IDs and history without reseeding. Fresh-session continuity and database restart durability are separate checks; demonstrate both.

### What the audience sees

Show the coding client and dashboard side by side. The dashboard explains the memory change and dependency path; the client shows retrieval, plan revision, code edits, and tests. A source-linked recorded run is acceptable evidence. Any edited waiting time or replay must be labeled honestly.

## 7. What FalkorDB actually does

Minimum relationships:

| Relationship | Use |
| --- | --- |
| Source SUPPORTS Fact | Retrieve and explain evidence. |
| Plan DEPENDS_ON Fact | Discover which saved plans need review. |
| NewFact SUPERSEDES OldFact | Preserve replacement history. |
| UpdateEvent RETIRED/ACCEPTED Fact | Explain the transition. |
| UpdateEvent FLAGGED Plan | Trace the impact of the correction. |

Project ownership and scope must constrain every operation. Store facts, sources, plans, and update events in FalkorDB. Use actual graph queries for impact discovery and evidence retrieval.

Verify graph dependence with a controlled fixture: changing a dependency edge changes the affected-plan result. An unrelated plan stays unchanged. Do not keep a hardcoded plan list or parallel authoritative store that supplies the same answers while the graph merely renders them.

When the graph is unavailable, report that context retrieval is unavailable. Do not silently substitute fabricated or seeded answers.

## 8. Required behavior and tool contract

- `remember`: store a fact with project, scope, and source; detect duplicates/conflicts.
- `process_update`: interpret a change, validate authority and scope, apply a confirmed correction, preserve history, and discover affected plans.
- `recall`: return relevant active facts, evidence, affected plans, and separately labeled pending conflicts.
- `history`: explain the previous state and replacement events.

Plan creation/dependency recording may use the existing service or dashboard; adding another MCP tool is optional. A code edit remains the coding agent's responsibility, not an implicit side effect of process_update.

Keep model interpretation separate from deterministic state transitions. Questions, uncertainty, conflicting sources, or unclear scope must not silently become accepted corrections. Preserve all unrelated facts. A fact's retirement flags dependent plans for review; it does not prove every dependent line of code is incorrect.

## 9. Traceability contract

The required evidence chain consists of:

1. The source and confirmed update that changed a fact.
2. The old fact, replacement fact, and affected-plan path.
3. The actual tool response supplied to the new agent session.
4. The agent's visible plan revision citing the relevant evidence.
5. The resulting code diff and test outcome.

For the MVP, items 1–3 can appear in RETRACT and items 4–5 in the coding client's transcript and repository. Use stable IDs to connect them. A unified run-history feature is optional.

Label retrieved information as “context supplied to the agent.” Do not claim to reveal hidden reasoning or prove that retrieval alone caused success. If code contradicts memory, surface the conflict and inspect the evidence. If an ordinary coding agent also succeeds, report that honestly.

## 10. Definition of done

- [ ] Real MCP calls work in one documented coding client.
- [ ] Confirmed scoped corrections change the intended fact only.
- [ ] Proposals and ambiguous updates leave accepted facts unchanged.
- [ ] Graph traversal identifies explicitly dependent plans and returns evidence paths.
- [ ] Current recall excludes superseded facts from its active-facts field.
- [ ] A fresh session retrieves the correction and affected-plan warning.
- [ ] The agent visibly revises the relevant plan after inspecting code.
- [ ] A real feature change and relevant tests are demonstrated.
- [ ] Memory/history survive service restart without reseeding.
- [ ] The dashboard reflects actual service state and observed activity.
- [ ] Setup, graph model, implemented queries, demo, and limitations are reproducible.

Until the fresh-session agent action works, describe the project as memory infrastructure under integration, not a completed end-to-end agent product.

## 11. Scope and delivery priorities

Build or verify in this order: graph-backed correction and impact discovery; persistence; real client retrieval; plan revision and tested code change; functional dashboard; landing page polish.

Preserve working implementation. Cut public hosting, extra clients, graph animations, automatic repository scanning, and broad document ingestion before cutting the complete demo. No multi-tenant SaaS, billing platform, unrestricted autonomous repair, or new editor is needed.

The submission needs a public repository, local setup or deployment, graph model and actual queries, working demo video, selected track, and disclosure of AI assistance. Use synthetic/public permitted data and understand the submitted code. These are submission requirements; the behavior above is our chosen product specification.

## 12. Instructions to Codex

Inspect the current code against this document before proposing changes. For each acceptance item, mark implemented-and-verified, implemented-but-unverified, mocked, or missing, with file/function references and actual check results. Documentation is not implementation evidence.

Identify the smallest gap preventing the full workflow. When implementation is authorized, fix that gap while preserving working features. Do not replace the product with a website-only chatbot, a graph viewer, or a generic memory CRUD application. Do not rebuild functional components solely to match a preferred framework.

The product is complete when a real coding agent uses persistent graph context to reconsider an outdated plan and produce an inspectable, tested change.
