import {test} from 'node:test';
import assert from 'node:assert/strict';
import {rowsFor, updateRequest, RequestDraft, number} from '../src/retract/web/dashboard-model.mjs';
const fact = {id: 'F1', subject: 'auth', predicate: 'method', scope: 'web/main', value: 'bearer', status: 'active'};
const snapshot = {facts: [fact, {...fact, id: 'old', status: 'superseded'}], plans: [], activity: [], updates: [{id: 'proposal', outcome: 'proposal'}, {id: 'applied', outcome: 'applied'}, {id: 'pending', outcome: 'pending'}]};
const draft = {mode: 'structured', title: 'Decision', text: 'Switch to cookies', value: 'cookies', classification: 'confirmed_change', authority: false, confirmation: false};
const ids = {event: 'U1', source: 'S1'};
test('views keep current, historical, and unaccepted records separate', () => {
  assert.deepEqual(rowsFor(snapshot, 'active'), [fact]);
  assert.equal(rowsFor(snapshot, 'superseded')[0].id, 'old');
  assert.deepEqual(rowsFor(snapshot, 'pending').map(r => r.id), ['proposal', 'pending']);
});
test('handoff view lists handoffs and searches agents and notes', () => {
  const handoffs = [{id: 'H1', scope: 'web/main', status: 'open', from_agent: 'retract-reviewer', to_agent: 'codex', plan_id: 'P1', note: 'Use cookie sessions'}];
  assert.deepEqual(rowsFor({...snapshot, handoffs}, 'handoffs'), handoffs);
  assert.equal(rowsFor({...snapshot, handoffs}, 'handoffs', 'CODEX').length, 1);
  assert.equal(rowsFor({...snapshot, handoffs}, 'handoffs', 'cookie').length, 1);
  assert.deepEqual(rowsFor(snapshot, 'handoffs'), []);
});
test('search is case insensitive and includes scope', () => {
  assert.equal(rowsFor(snapshot, 'active', ' BEARER ').length, 1);
  assert.equal(rowsFor(snapshot, 'active', 'web/main').length, 1);
  assert.equal(rowsFor(snapshot, 'active', 'none').length, 0);
});
test('structured request preserves target, evidence, revision and unchecked controls', () => {
  const request = updateRequest('project', 5, fact, draft, ids);
  assert.equal(request.route, '/updates');
  assert.equal(request.body.source.authority, 'untrusted');
  assert.equal(request.body.confirmation, false);
  assert.equal(request.body.candidate.excerpt, request.body.source.content);
  assert.equal(request.body.target_fact_id, 'F1');
  assert.equal(request.body.expected_revision, 5);
});
test('natural updates select a scoped key without constructing a model candidate', () => {
  const request = updateRequest('project', 5, fact, {...draft, mode: 'natural', authority: true, confirmation: true}, ids);
  assert.equal(request.route, '/updates/natural');
  assert.equal(request.body.source.authority, 'developer');
  assert.equal(request.body.subject, 'auth');
  assert.equal(request.body.candidate, undefined);
});
test('historical facts cannot become update targets', () => {
  assert.throws(() => updateRequest('project', 5, {...fact, status: 'superseded'}, draft, ids), /current fact/);
});
test('unchanged retries reuse the exact request and IDs; changed draft or refresh gets a new request', () => {
  const retry = new RequestDraft(); let serial = 0;
  const create = () => ({event_id: ++serial});
  const first = retry.prepare([draft, 5], create);
  assert.equal(retry.prepare([draft, 5], create), first);
  assert.notEqual(retry.prepare([{...draft, value: 'changed'}, 5], create), first);
  retry.clear(); assert.equal(retry.prepare([draft, 5], create).event_id, 3);
});
test('counts show exact grouped integers', () => assert.equal(number(12345), '12,345'));
