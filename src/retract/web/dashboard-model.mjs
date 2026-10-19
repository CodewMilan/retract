export const views = {
  active: ['Memory', 'The decisions your agents should work from.'],
  superseded: ['Previous decisions', 'Replaced decisions stay here with their original sources.'],
  pending: ['Suggestions', 'Proposed changes. Your current memory stays unchanged until a change is approved.'],
  affected: ['Needs review', 'A linked decision changed. Review these plans before continuing the work.'],
  plans: ['Plans', 'Work your agents are planning, and the decisions it relies on.'],
  handoffs: ['Handoffs', 'Context and next steps passed between agents.'],
  updates: ['Change history', 'What changed, why it changed, and which plans were affected.'],
  activity: ['API activity', 'Recent requests from connected clients. This log clears when the service restarts.'],
};
export const statusLabel = value => ({active: 'Current', current: 'Current', superseded: 'Replaced', needs_review: 'Needs review',
  pending: 'Pending', proposal: 'Suggestion', applied: 'Applied', open: 'Open', claimed: 'Claimed',
  ignored: 'Unchanged', ambiguous: 'Needs clarification', confirmed_change: 'Agreed change'}[value] || String(value ?? 'Recorded').replaceAll('_', ' '));
export const number = value => new Intl.NumberFormat('en-US', {maximumFractionDigits: 0}).format(value);
export function rowsFor(snapshot, view, search = '') {
  let rows = view === 'active' || view === 'superseded'
    ? snapshot.facts.filter(f => f.status === (view === 'active' ? 'active' : 'superseded'))
    : view === 'affected' ? snapshot.plans.filter(p => p.status === 'needs_review')
    : view === 'plans' ? snapshot.plans
    : view === 'activity' ? snapshot.activity
    : view === 'handoffs' ? (snapshot.handoffs ?? [])
    : snapshot.updates.filter(e => view !== 'pending' || ['pending', 'proposal'].includes(e.outcome));
  const term = search.toLowerCase().trim();
  return term ? rows.filter(row => [row.id, row.subject, row.predicate, row.value, row.scope, row.text,
    row.outcome, row.route, row.client, row.status, row.note, row.from_agent, row.to_agent, row.plan_id,
    row.claimed_by].some(v => String(v ?? '').toLowerCase().includes(term))) : rows;
}
export function updateRequest(project, revision, fact, draft, ids) {
  if (!fact || fact.status !== 'active') throw new Error('Select a current fact first.');
  const body = {project_id: project, scope: fact.scope, event_id: ids.event,
    text: draft.text, source: {id: ids.source, kind: 'developer', title: draft.title,
      content: draft.text, authority: draft.authority ? 'developer' : 'untrusted'},
    confirmation: draft.confirmation, expected_revision: revision};
  if (draft.mode === 'natural') {
    return {route: '/updates/natural', body: {...body, subject: fact.subject, predicate: fact.predicate}};
  }
  return {route: '/updates', body: {...body, classification: draft.classification,
    target_fact_id: fact.id, candidate: {subject: fact.subject, predicate: fact.predicate,
      value: draft.value, excerpt: draft.text}}};
}
// Reuse the exact event/source IDs after an uncertain network result. Changed drafts
// receive new IDs. Revisions stay part of the signature until explicit refresh.
export class RequestDraft {
  prepare(signature, create) {
    const key = JSON.stringify(signature);
    if (key !== this.key) { this.request = create(); this.key = key; }
    return this.request;
  }
  clear() { this.key = undefined; this.request = undefined; }
}
