import {test, before, after, beforeEach} from 'node:test';
import assert from 'node:assert/strict';
import {AccountClient, AccountError, displayName} from '../src/retract/account_web/account-client.mjs';
import {AccountTransport} from './account-transport.mjs';
let transport;
before(() => { transport = new AccountTransport(); });
after(async () => { await transport.close(); });
beforeEach(async () => { await transport.reset(); });
const client = () => new AccountClient(transport.fetch.bind(transport));
test('signed-out recovery returns no fabricated user and save makes no request', async () => {
  const account = client(); assert.equal(await account.recover(), null);
  await assert.rejects(account.save('New name'), error => error.status === 401);
  assert.deepEqual(transport.requests.map(r => r.path), ['/api/session']);
});
test('actual HTTP login, cookie recovery and own-profile save carry CSRF without bearer headers', async () => {
  const account = client();
  assert.equal((await account.login('alice')).id, 'alice');
  assert.ok(transport.cookie.startsWith('retract_demo_session='));
  const fresh = client(); assert.equal((await fresh.recover()).id, 'alice');
  assert.equal((await fresh.save('  Alice Updated  ')).display_name, 'Alice Updated');
  const save = transport.requests.at(-1);
  assert.equal(save.path, '/api/profiles/alice'); assert.equal(save.method, 'PATCH');
  assert.deepEqual(JSON.parse(save.body), {display_name: 'Alice Updated'});
  assert.ok(save.headers['X-CSRF-Token']); assert.ok(save.headers.Cookie);
  for (const request of transport.requests) {
    assert.equal(new Headers(request.headers).has('authorization'), false);
    assert.equal(request.credentials, 'same-origin'); assert.equal(request.redirect, 'error');
  }
  assert.equal((await account.login('bob')).display_name, 'Bob Example');
});
test('the user snapshot cannot redirect a save to another account', async () => {
  const account = client(); await account.login('alice');
  account.user.id = 'bob';
  await account.save('Only Alice');
  assert.equal(transport.requests.at(-1).path, '/api/profiles/alice');
});
test('another user remains forbidden even with a valid session and CSRF', async () => {
  const account = client(); await account.login('alice'); await account.save('Alice Updated');
  const headers = transport.requests.at(-1).headers;
  for (const method of ['GET', 'PATCH']) {
    const response = await transport.raw('/api/profiles/bob', {method, headers, body: JSON.stringify({display_name: 'Wrong'})});
    assert.equal(response.status, 403);
  }
  assert.equal((await account.login('bob')).display_name, 'Bob Example');
});
test('invalid CSRF is rejected by the actual HTTP handler', async () => {
  const account = client(); await account.login('alice');
  const response = await transport.raw('/api/profiles/alice', {method: 'PATCH', body: JSON.stringify({display_name: 'Wrong'}),
    headers: {'Content-Type': 'application/json', Cookie: transport.cookie, 'X-CSRF-Token': 'wrong'}});
  assert.equal(response.status, 403);
  assert.equal((await account.recover()).display_name, 'Alice Example');
});
test('failed storage save never reports a new name and can be retried', async () => {
  const account = client(); await account.login('alice'); await transport.exchange({control: 'fail_save'});
  await assert.rejects(account.save('Retry Alice'), error => error.status === 503);
  assert.equal(account.user.display_name, 'Alice Example');
  assert.equal((await account.save('Retry Alice')).display_name, 'Retry Alice');
});
test('expired sessions clear local identity and require sign-in again', async () => {
  const account = client(); await account.login('alice'); await transport.exchange({control: 'expire'});
  await assert.rejects(account.save('Expired write'), error => error.status === 401);
  assert.equal(account.user, null);
  assert.equal((await account.login('alice')).display_name, 'Alice Example');
});
test('logout invalidates the server session and a new page stays signed out', async () => {
  const account = client(); await account.login('alice'); const oldCookie = transport.cookie;
  await account.logout(); assert.equal(account.user, null); assert.equal(transport.cookie, '');
  assert.equal(await client().recover(), null);
  assert.equal((await transport.raw('/api/session', {headers: {Cookie: oldCookie}})).status, 401);
});
test('a missing seed and an unavailable service fail clearly', async () => {
  const missing = new AccountClient(async () => Response.json({error: 'Demo profile missing; run the explicit seed command'}, {status: 404}));
  await assert.rejects(missing.login('alice'), /profile missing/); assert.equal(missing.user, null);
  const unavailable = new AccountClient(async () => { throw new TypeError('network down'); });
  await assert.rejects(unavailable.recover(), /Could not confirm/); assert.equal(unavailable.user, null);
});
test('malformed sessions never become signed in and malformed 401 clears identity', async () => {
  for (const body of [{user: null, csrf_token: 'csrf'}, {user: {id: 'alice', display_name: 'Alice', email: 'alice@example.test'}}]) {
    const account = new AccountClient(async () => Response.json(body));
    await assert.rejects(account.recover(), AccountError); assert.equal(account.user, null);
  }
  let reply = Response.json({user: {id: 'alice', display_name: 'Alice', email: 'alice@example.test'}, csrf_token: 'csrf'});
  const account = new AccountClient(async () => reply); await account.recover();
  reply = new Response('not json', {status: 401}); await assert.rejects(account.save('Name')); assert.equal(account.user, null);
});
test('validation counts Unicode characters and refuses empty or oversized names before a request', async () => {
  assert.equal(displayName('  Name  '), 'Name'); assert.equal(displayName('😀'.repeat(80)), '😀'.repeat(80));
  for (const value of ['', ' ', 'x'.repeat(81), '😀'.repeat(81)]) assert.throws(() => displayName(value), AccountError);
  const account = client(); await account.login('alice'); const count = transport.requests.length;
  await assert.rejects(account.save(' '), AccountError); assert.equal(transport.requests.length, count);
  assert.equal((await account.save('😀'.repeat(80))).display_name, '😀'.repeat(80));
});
test('concurrent submissions are refused until the pending request completes', async () => {
  let finish;
  const account = new AccountClient(() => new Promise(resolve => { finish = resolve; }));
  const first = account.recover(); await assert.rejects(account.login('bob'), error => error.status === 409);
  finish(Response.json({error: 'Sign in'}, {status: 401})); assert.equal(await first, null);
});
test('a cookie switched by another tab cannot write the old account', async () => {
  const alice = client(); const bob = client(); await alice.login('alice'); await bob.login('bob');
  await assert.rejects(alice.save('Wrong profile'), error => error.status === 403);
  assert.equal((await bob.recover()).display_name, 'Bob Example');
  assert.equal((await alice.recover()).id, 'bob');
});
test('a failed logout retains local identity until sign-out is confirmed', async () => {
  let fail = true;
  const account = new AccountClient((path, init) => path === '/demo/logout' && fail
    ? Promise.resolve(Response.json({error: 'Unavailable'}, {status: 503})) : transport.fetch(path, init));
  await account.login('alice'); await assert.rejects(account.logout(), error => error.status === 503);
  assert.equal(account.user.id, 'alice'); assert.equal((await client().recover()).id, 'alice');
  fail = false; await account.logout(); assert.equal(account.user, null);
});
test('timeout leaves no successful session and releases the pending-operation guard', async () => {
  let pending = true;
  const account = new AccountClient((path, init) => pending ? new Promise((resolve, reject) => {
    init.signal.addEventListener('abort', () => reject(new DOMException('Timed out', 'AbortError')), {once: true});
  }) : Promise.resolve(Response.json({error: 'Signed out'}, {status: 401})), 5);
  await assert.rejects(account.recover(), /Could not confirm/); assert.equal(account.user, null);
  pending = false; assert.equal(await account.recover(), null);
});
