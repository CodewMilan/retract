export const views = {
  active: ['Current facts', 'Accepted decisions for the selected project and scope.'],
  superseded: ['Superseded facts', 'Historical decisions remain available as evidence.'],
  pending: ['Pending & proposals', 'These updates have not replaced accepted memory.'],
  affected: ['Affected plans', 'Plans whose recorded dependencies need review.'],
  plans: ['All plans', 'Current plans and preserved versions, with their recorded dependencies.'],
  handoffs: ['Agent handoffs', 'Work passed between agents, with what the sender relied on and what has changed since.'],
  updates: ['Update history', 'Recorded update outcomes, evidence, and revision changes.'],
  activity: ['Request activity', 'Recent API requests in this service process. Clears on restart.'],
};
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
