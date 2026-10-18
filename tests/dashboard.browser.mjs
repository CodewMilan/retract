/** Real Chromium interactions against controlled network responses; never a DB gate.
 * npm install && npx playwright install chromium && npm run test:browser
 * --live-url http://127.0.0.1:8100 adds a read-only real-service smoke check.
 */
import assert from 'node:assert/strict';
import {readFile, mkdir} from 'node:fs/promises';
import {resolve} from 'node:path';
import {pathToFileURL} from 'node:url';
const {chromium} = await import(process.env.PLAYWRIGHT_MODULE ? pathToFileURL(resolve(process.env.PLAYWRIGHT_MODULE)).href : 'playwright');
const root = new URL('../src/retract/web/', import.meta.url);
const project = {id: 'test-project', name: 'Browser test project', revision: 5};
const fact = {id: 'F1', project_id: project.id, scope: 'web/main', subject: 'auth', predicate: 'method', value: 'bearer tokens', status: 'active'};
const evil = '<img src=x onerror="window.sourceExecuted=true">';
function fixture() { return {project: {...project}, observed_at: '2026-10-17T10:00:00+00:00', facts: [{...fact}], plans: [], updates: [], activity: [], scopes: ['web/main'], counts: {active: 1, superseded: 0, pending: 0, affected: 0, updates: 0}, truncated: {}, explanation_paths: [], edges: [{relationship: 'SUPPORTS', from: {id: 'source', title: 'Original note', authority: 'approved_document', content: evil}, to: {...fact}}]}; }
const browser = await chromium.launch({headless: true});
const reportDir = resolve('reports/phase4/browser'); await mkdir(reportDir, {recursive: true});
let passed = 0;
try {
  for (const width of [375, 768, 1280]) {
    const context = await browser.newContext({viewport: {width, height: 900}, colorScheme: width === 768 ? 'dark' : 'light', reducedMotion: 'reduce'});
    const page = await context.newPage(); const errors = []; page.on('pageerror', error => errors.push(error.message));
    let snapshot = fixture(); const projects = [project]; let failSnapshots = false; let conflict = false; const submitted = [];
    await page.route('https://retract.test/**', async route => {
      const request = route.request(); const url = new URL(request.url());
      const resources = {'/': ['index.html', 'text/html'], '/assets/dashboard.css': ['dashboard.css', 'text/css'], '/assets/dashboard.mjs': ['dashboard.mjs', 'text/javascript'], '/assets/dashboard-model.mjs': ['dashboard-model.mjs', 'text/javascript'], '/assets/auth.mjs': ['auth.mjs', 'text/javascript']};
      if (resources[url.pathname]) { const [name, contentType] = resources[url.pathname]; return route.fulfill({contentType, headers: {'Content-Security-Policy': "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'none'"}, body: await readFile(new URL(name, root), 'utf8')}); }
      const json = (data, status = 200) => route.fulfill({status, contentType: 'application/json', body: JSON.stringify(data)});
      if (url.pathname === '/api/config') return json({mode: 'local'});
      if (url.pathname === '/api/projects') return json({projects, truncated: false});
      if (url.pathname === '/projects') {
        const body = request.postDataJSON(); const created = {id: body.project_id, name: body.name, revision: 0};
        projects.push(created); snapshot.project = created; return json(created);
      }
      if (url.pathname === '/remember') {
        const body = request.postDataJSON();
        assert.equal(body.source.authority, 'developer'); assert.equal(body.expected_revision, snapshot.project.revision);
        snapshot.facts.push({id: body.fact_id, ...body, status: 'active'}); snapshot.counts.active++;
        return json({fact_id: body.fact_id, outcome: 'created', project_revision: ++snapshot.project.revision});
      }
      if (url.pathname === '/dashboard') return failSnapshots ? json({error: 'Storage unavailable'}, 503) : json(snapshot);
      if (url.pathname === '/updates') {
        const body = request.postDataJSON(); submitted.push(body);
        if (conflict) return json({error: 'Stale project revision'}, 409);
        const applied = body.confirmation && body.source.authority === 'developer' && body.classification === 'confirmed_change';
        const result = {event_id: body.event_id, outcome: applied ? 'applied' : 'proposal', reason: applied ? 'Confirmed authoritative replacement' : 'Proposal preserves accepted memory', classification: body.classification,
          candidate: body.candidate, retired_fact_ids: applied ? ['F1'] : [], accepted_fact_ids: applied ? ['F5'] : [], flagged_plan_ids: applied ? ['P1'] : [], resulting_revision: ++snapshot.project.revision};
        snapshot.updates.unshift({id: body.event_id, scope: fact.scope, text: body.text, outcome: result.outcome, reason: result.reason, result});
        snapshot.counts.updates++;
        if (applied) {
          snapshot.facts[0].status = 'superseded'; snapshot.facts.push({...fact, id: 'F5', status: 'active', value: body.candidate.value});
          snapshot.counts.superseded = 1; snapshot.counts.affected = 1;
          const plan = {id: 'P1', scope: fact.scope, text: 'Build with auth', status: 'needs_review'}; snapshot.plans = [plan];
          snapshot.explanation_paths = [{event: {id: body.event_id, scope: fact.scope}, plan, fact: snapshot.facts[0]}];
        } else snapshot.counts.pending++;
        return json(result);
      }
      if (url.pathname === '/updates/natural') return json({error: 'Groq is not configured'}, 503);
      return json({error: 'Unexpected test request'}, 404);
    });
    await page.goto('https://retract.test/');
    await page.getByText('Storage connected', {exact: true}).waitFor();
    assert.equal(await page.locator('#records .record').count(), 1);
    await page.locator('#records .record').click();
    await page.locator('#inspector summary').click();
    assert.equal(await page.locator('#inspector img').count(), 0);
    assert.equal(await page.evaluate(() => window.sourceExecuted), undefined);
    assert.ok(await page.locator('#inspector').innerText().then(text => text.includes(evil)));
    await page.getByLabel('Search this view').fill('unmatched');
    await page.getByText('No matching records. Try a different search.').waitFor();
    await page.getByLabel('Search this view').fill('');
    await page.locator('#update').click();
    assert.equal(await page.locator('#authority').isChecked(), false);
    assert.equal(await page.locator('#confirmation').isChecked(), false);
    await page.locator('#update-text').fill('Switch to cookies');
    await page.locator('#update-form button[type=submit]').click();
    await page.getByText('Groq is not configured', {exact: true}).waitFor();
    assert.equal(await page.locator('#update-text').inputValue(), 'Switch to cookies');
    await page.locator('#mode').selectOption('structured');
    await page.locator('#classification').selectOption('proposal');
    await page.locator('#replacement').fill('cookies');
    await page.locator('#update-form button[type=submit]').click();
    await page.locator('#update-dialog').waitFor({state: 'hidden'});
    assert.equal(submitted[0].confirmation, false); assert.equal(submitted[0].source.authority, 'untrusted');
    await page.getByRole('button', {name: /Pending & proposals/}).click();
    assert.equal(await page.locator('#records .record').count(), 1);
    await page.getByRole('button', {name: /Current facts/}).click();
    assert.ok((await page.locator('#records').innerText()).includes('bearer tokens'));
    await page.locator('#update').click(); await page.locator('#mode').selectOption('structured');
    await page.locator('#replacement').fill('cookies'); await page.locator('#update-text').fill('Switch to cookies');
    await page.locator('#authority').check(); await page.locator('#confirmation').check();
    conflict = true;
    await page.locator('#update-form button[type=submit]').click();
    await page.locator('#update-error').filter({hasText: 'Stale project revision'}).waitFor();
    assert.equal(await page.locator('#replacement').inputValue(), 'cookies');
    const retryEvent = submitted.at(-1).event_id;
    await page.locator('#update-form button[type=submit]').click();
    await page.waitForFunction(() => !document.querySelector('#update-form button[type=submit]').disabled);
    assert.equal(submitted.at(-1).event_id, retryEvent);
    conflict = false;
    await page.locator('#refresh-context').click();
    await page.getByText('Context refreshed. Review the current value and confirm again if appropriate.').waitFor();
    assert.equal(await page.locator('#confirmation').isChecked(), false);
    await page.locator('#confirmation').check();
    await page.locator('#update-form button[type=submit]').click();
    await page.locator('#update-dialog').waitFor({state: 'hidden'});
    assert.notEqual(submitted.at(-1).event_id, retryEvent);
    assert.ok((await page.locator('#result').innerText()).includes('Before: bearer tokens\nAfter: cookies'));
    await page.getByRole('button', {name: /Affected plans/}).click(); await page.locator('#records .record').click();
    assert.ok((await page.locator('#inspector').innerText()).includes('P1 ─ DEPENDS_ON → F1'));
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
    await page.screenshot({path: resolve(reportDir, `dashboard-${width}.png`), fullPage: true});
    failSnapshots = true; await page.locator('#refresh').click();
    await page.getByText('Storage unavailable', {exact: true}).first().waitFor();
    assert.equal(await page.locator('#update').isDisabled(), true);
    assert.equal(await page.locator('#remember').isDisabled(), true);
    // Exercise the empty-project path and both creation forms using the real DOM.
    failSnapshots = false; projects.length = 0; snapshot = fixture(); snapshot.facts = [];
    snapshot.counts = {active: 0, superseded: 0, pending: 0, affected: 0, updates: 0};
    snapshot.edges = []; await page.reload();
    await page.getByText('No project selected. Create a project to begin.').waitFor();
    await page.locator('#new-project').click();
    await page.locator('#project-id').fill('created-project'); await page.locator('#project-name').fill('Created project');
    await page.locator('#project-form button[type=submit]').click();
    await page.getByText('No accepted facts here yet. Remember a fact with its evidence to begin.').waitFor();
    await page.locator('#remember').click();
    await page.locator('#fact-scope').fill('web/main'); await page.locator('#subject').fill('auth');
    await page.locator('#predicate').fill('method'); await page.locator('#fact-value').fill('cookies');
    await page.locator('#fact-evidence').fill('Approved cookies decision'); await page.locator('#fact-authority').check();
    await page.locator('#remember-form button[type=submit]').click();
    await page.locator('#remember-dialog').waitFor({state: 'hidden'});
    assert.ok((await page.locator('#records').innerText()).includes('cookies'));
    assert.deepEqual(errors, []);
    await context.close(); passed++;
    console.log(`PASS ${width}px: evidence, proposal, correction, stale retry, paths, failure, overflow`);
  }
  const liveIndex = process.argv.indexOf('--live-url');
  if (liveIndex !== -1) {
    const target = new URL(process.argv[liveIndex + 1]);
    if (target.protocol !== 'http:' || !['127.0.0.1', 'localhost'].includes(target.hostname)) throw new Error('Live URL must be local HTTP');
    const page = await browser.newPage();
    await page.goto(target.href); await page.getByText('Storage connected', {exact: true}).waitFor();
    assert.ok(await page.locator('#snapshot-meta').innerText().then(text => text.includes('Revision')));
    await page.close(); console.log('PASS read-only real-service dashboard smoke');
  }
  console.log(`${passed} browser viewport scenarios passed. Controlled network responses; database integration is separate.`);
} finally { await browser.close(); }
