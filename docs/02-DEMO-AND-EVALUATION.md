# Demo and evaluation

Status: proposed scenario and target outcomes, not measured results.

## Demo application

Use a tiny synthetic account-settings application with a working backend and a frontend feature to implement. Keep the initial application, source notes, and fixtures in the public repository.

Use an approved architecture note as the source of the authentication decision and its rationale. A package-manager change alone is not compelling because a coding agent may discover it from a lockfile.

## Seeded memory

| ID | Scope | Accepted fact or plan |
| --- | --- | --- |
| F1 | web-client/main | Browser API authentication uses bearer tokens. |
| F2 | cli-client/main | CLI API authentication uses bearer tokens. |
| F3 | account-service/main | Account data uses PostgreSQL. |
| F4 | account-service/main | Users may update only their own profile. |
| P1 | web-client/main | Settings-page implementation plan assumes the browser supplies an Authorization bearer header. |

P1 explicitly DEPENDS_ON F1 and F4. Each fact has a source. No inferred code dependency is implied.

Confirmed update U1: “Approved for web-client/main: browser authentication now uses HTTP-only cookie sessions. The old bearer-token instruction for the browser is replaced. CLI authentication is unchanged.”

Proposal U2: “Should we replace PostgreSQL with MongoDB?”

Expected state: F1 is superseded by F5, the accepted cookie-session fact. P1 needs review because of its dependency on F1. F2, F3, and F4 stay active. U2 remains a proposal and does not change F3.

## Four-to-five-minute demo

| Time | Action | Visible evidence |
| --- | --- | --- |
| 0:00–0:35 | Explain the old project decision and open the memory dashboard. | Facts, source notes, and P1 dependency links. |
| 0:35–1:15 | Submit U1 through the actual update API/tool. | F1 superseded; F5 active; P1 needs review. |
| 1:15–1:45 | Expand the explanation and submit U2. | Source-to-change-to-plan path; PostgreSQL remains accepted. |
| 1:45–3:30 | Start a new agent session and request the settings feature. | Actual recall tool call, returned facts, inspected repository, and resulting code change. |
| 3:30–4:15 | Run relevant feature tests. | Browser session behavior and ownership checks pass or fail visibly. |
| 4:15–5:00 | Restart services and recall again. | Same IDs, states, history, and evidence survive. |

Generation time may vary. A recorded demo may shorten waits with clearly identified cuts. Never present precomputed output as live execution or hide failed checks.

## Coding task and verification

Prompt: “Implement the account settings page using the project's current accepted decisions. Retrieve project memory before planning, inspect the repository, then implement and test.”

For this controlled application, the backend already exposes the current session contract. Test the frontend request behavior against that contract. Include a check that the implementation does not construct the old bearer-token flow and preserves the existing ownership requirement. Reuse the application's tested session and request protections; RETRACT is not designing an authentication framework.

The agent may independently discover the correct contract in code. That is acceptable. Demonstrate the actual context retrieved and traceability; do not claim memory uniquely caused success unless a controlled comparison supports it.

## Acceptance fixtures

| Case | Expected outcome |
| --- | --- |
| Explicit same-scope replacement | Old fact superseded; new fact active; source and event linked. |
| Unrelated subject | Existing unrelated facts unchanged. |
| Different scope | Browser update does not change CLI authentication. |
| Proposal or question | No accepted fact changed. |
| Ambiguous conflicting source | Pending review; no silent replacement. |
| Replayed event ID | No duplicate facts, events, or effects. |
| Explicit plan dependency | Dependent plan marked needs_review with an explanation path. |
| Plan with no affected dependency | Plan unchanged. |
| Current recall | Superseded facts absent from the active-facts list. |
| History recall | Old fact, replacement, source, and reason available. |
| Service restart | Stored state retained without silently reseeding. |
| Project isolation | Another project's facts do not appear or change. |
| Repository conflict | Agent reports inconsistency and checks current evidence. |

Use deterministic tests for graph updates and retrieval. Evaluate natural-language classification separately on held-out paraphrases, including questions, negations, and scope differences. Record model identifier, prompt version, and actual results. A small passing fixture set is not evidence of universal correctness.

## Metrics to report

- Wrong invalidations: number of unrelated or still-valid facts changed.
- Stale retrieval: number of superseded facts incorrectly returned as active.
- Affected-plan precision and recall against the explicit fixture links.
- Update classification accuracy on the declared evaluation set.
- Update/recall latency and tokens used, measured rather than guessed.
- Whether the real coding client's recall call occurred and feature checks passed.

If comparing against plain memory, keep the same model, repository, source updates, task, and budget. Include a simple maintained instruction-file baseline where practical. Do not withhold the correction from one condition to manufacture a win. Report failures and small sample size.

## Rehearsal and fallback

Use the local stack as the primary demo. Seed explicitly once before the run. Keep source notes, model configuration, and expected fixture outcomes reproducible. If inference is unavailable, demonstrate graph operations using clearly labeled structured input; this fallback does not establish natural-language classification performance. Preserve a genuine recorded successful run for submission.
