# RETRACT — project documentation

Working name: RETRACT. Planning baseline: 16 October 2026.

Status: milestone 1 backend and milestone 2 interpretation code are implemented with passing offline tests. Real FalkorDB integration, persistence, and live classification have not yet been verified. No benchmark or production deployment is claimed. See the [implementation record](06-IMPLEMENTATION-STATUS.md), [Phase 2 notes](07-NATURAL-LANGUAGE-UPDATES.md), and [local setup instructions](../README.md).

## What we are building

A persistent project-memory service for coding agents. When a developer confirms that a project decision has changed, RETRACT supersedes the old fact, preserves the evidence and history, and flags explicitly linked plans that need review. A later agent session retrieves the current context and can trace why it changed.

Example: a browser application moves from bearer tokens to cookie sessions. RETRACT retires the old browser-authentication instruction, flags the plan that depended on it, and leaves unrelated CLI authentication and database decisions alone.

## Read these six files in order

| File | Purpose |
| --- | --- |
| [README.md](README.md) | Entry point, decisions, reading order, and agent handoff. |
| [01-PRODUCT.md](01-PRODUCT.md) | User problem, target audience, scope, positioning, and product rules. |
| [02-DEMO-AND-EVALUATION.md](02-DEMO-AND-EVALUATION.md) | Concrete demo, fixtures, success criteria, and honest comparisons. |
| [03-ARCHITECTURE.md](03-ARCHITECTURE.md) | Components, graph model, update policy, retrieval, and tool contracts. |
| [04-INFRASTRUCTURE-AND-COSTS.md](04-INFRASTRUCTURE-AND-COSTS.md) | Local setup strategy, free-tier limits, costs, and operational risks. |
| [05-BUILD-PLAN.md](05-BUILD-PLAN.md) | Ordered implementation milestones, scope cuts, and submission checklist. |

Keep these files together in this folder so relative links work. The six original files define the specification; [06-IMPLEMENTATION-STATUS.md](06-IMPLEMENTATION-STATUS.md) records what has actually been implemented and checked. Executable setup commands are in the [root README](../README.md).

## Decisions already made

- Implement a focused invalidate-style workflow directly on FalkorDB.
- Target developers using coding agents across sessions.
- Start with explicit developer updates and deliberately ingested documents.
- Use a local deployment for the main demo, with configured database persistence.
- Integrate one coding client through MCP, not several clients at once.
- Use graph relationships for affected-plan discovery and evidence retrieval.
- Treat ambiguous changes as pending. Newer text alone does not make a claim authoritative.
- Do not claim that memory invalidation itself is novel or that winning is guaranteed.

## First engineering gate

Before dashboard polish, prove all four outcomes:

1. A confirmed correction supersedes the intended fact.
2. A proposal leaves accepted memory unchanged.
3. A linked plan needs review while unrelated facts remain unchanged.
4. A fresh agent session retrieves the correction after service restart.

## Handoff to a coding agent

Read this README, then the product, architecture, demo/evaluation, infrastructure, and build-plan documents. Implement milestone 1 first. Use the graph as the authoritative memory store. Keep model extraction separate from deterministic state changes. Run the meaningful acceptance checks and record actual results before expanding scope. Update these documents when implementation decisions change. Never present target metrics or planned features as completed work.

## Hackathon fit

Intended track: Agent Memory and Coordination. FalkorDB must support central behavior. The submission needs a public repository, graph model, actual Cypher queries or algorithms, demo video, and a working deployment or complete local instructions. Disclose AI assistance and understand the submitted code.

Source: [Graph Hacks rules](https://www.wemakedevs.org/hackathons/falkordb/rules), checked 16 October 2026.
