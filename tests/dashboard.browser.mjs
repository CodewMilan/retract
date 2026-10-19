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
  for (const width of [375, 768, 1024, 1440]) {
    const context = await browser.newContext({viewport: {width, height: 900}, colorScheme: width === 768 ? 'dark' : 'light', reducedMotion: 'reduce'});
    const page = await context.newPage(); const errors = []; page.on('pageerror', error => errors.push(error.message));
    page.setDefaultTimeout(10000);
    async function openMenu() { if (width <= 760 && await page.locator('#menu-toggle').getAttribute('aria-expanded') !== 'true') await page.locator('#menu-toggle').click(); }
    async function navigate(view) {
      await openMenu();
      if (['superseded', 'pending', 'updates', 'activity'].includes(view) && !await page.locator('#history-nav').evaluate(node => node.open)) await page.locator('#history-nav > summary').click();
      await page.locator(`[data-view="${view}"]`).click();
    }
    async function closeDetails() { if (await page.locator('#inspector').isVisible()) await page.getByRole('button', {name: 'Close details', exact: true}).click(); }
    async function updateDecision() { await closeDetails(); await page.locator('#memory-actions > summary').click(); await page.locator('#update').click(); }
    let snapshot = fixture(); const projects = [project]; let failSnapshots = false; let conflict = false; const submitted = [];
    await page.route('https://retract.test/**', async route => {
      const request = route.request(); const url = new URL(request.url());
      const resources = {'/dashboard': ['index.html', 'text/html'], '/assets/dashboard.css': ['dashboard.css', 'text/css'], '/assets/dashboard.mjs': ['dashboard.mjs', 'text/javascript'], '/assets/dashboard-model.mjs': ['dashboard-model.mjs', 'text/javascript'], '/assets/agent-connect.mjs': ['agent-connect.mjs', 'text/javascript'], '/assets/auth.mjs': ['auth.mjs', 'text/javascript'], '/assets/auth-portrait.mjs': ['auth-portrait.mjs', 'text/javascript'], '/assets/loader.mjs': ['loader.mjs', 'text/javascript'], '/assets/gsap.min.js': ['gsap.min.js', 'text/javascript']};
      if (request.method() === 'GET' && resources[url.pathname]) { const [name, contentType] = resources[url.pathname]; return route.fulfill({contentType, headers: {'Content-Security-Policy': "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'none'"}, body: await readFile(new URL(name, root), 'utf8')}); }
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
    await page.goto('https://retract.test/dashboard');
    await page.locator('#auth-email').fill('ada@retract.test');
    await page.locator('#auth-password').fill('local-pass');
    await page.locator('#local-auth button[type="submit"]').click();
    await page.locator('#auth-screen').waitFor({state: 'hidden'});
    await page.waitForFunction(() => document.querySelector('#connection').textContent === 'Storage connected');
    assert.equal(await page.locator('#inspector').isVisible(), false);
    assert.equal(await page.locator('#navigation > button').count(), 4);
    assert.equal(await page.locator('#history-nav').evaluate(node => node.open), false);
    assert.equal(await page.locator('#records .record').count(), 1);
    await page.locator('#records .record').click();
    await page.locator('#inspector .source-details summary').click();
    assert.equal(await page.locator('#inspector img').count(), 0);
    assert.equal(await page.evaluate(() => window.sourceExecuted), undefined);
    assert.ok(await page.locator('#inspector').innerText().then(text => text.includes(evil)));
    await closeDetails();
    await page.getByLabel('Search this view').fill('unmatched');
    await page.getByText('No matching results', {exact: true}).waitFor();
    await page.getByLabel('Search this view').fill('');
    await updateDecision();
    assert.equal(await page.locator('#mode').inputValue(), 'structured');
    await page.locator('#update-form .advanced summary').click();
    await page.locator('#mode').selectOption('natural');
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
    await navigate('pending');
    assert.equal(await page.locator('#records .record').count(), 1);
    await navigate('active');
    assert.ok((await page.locator('#records').innerText()).includes('bearer tokens'));
    await updateDecision();
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
    await navigate('affected'); await page.locator('#records .record').click();
    await page.locator('#inspector .technical-details summary').click();
    assert.ok((await page.locator('#inspector').innerText()).includes('P1 ─ DEPENDS_ON → F1'));
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
    await page.screenshot({path: resolve(reportDir, `dashboard-${width}.png`), fullPage: true});
    await closeDetails();
    failSnapshots = true; await page.locator('#refresh').click();
    await page.locator('#notice').filter({hasText: 'Storage unavailable'}).waitFor();
    assert.equal(await page.locator('#update').isDisabled(), true);
    assert.equal(await page.locator('#remember').isDisabled(), true);
    // Exercise the empty-project path and both creation forms using the real DOM.
    failSnapshots = false; projects.length = 0; snapshot = fixture(); snapshot.facts = [];
    snapshot.counts = {active: 0, superseded: 0, pending: 0, affected: 0, updates: 0};
    snapshot.edges = []; await page.reload();
    await page.getByText('Give your agents a place to remember', {exact: true}).waitFor();
    await page.getByRole('button', {name: 'Create your first project', exact: true}).click();
    await page.locator('#project-name').fill('Created project');
    assert.equal(await page.locator('#project-id').inputValue(), 'created-project');
    assert.equal(await page.locator('#project-form .advanced').evaluate(node => node.open), false);
    await page.locator('#project-form button[type=submit]').click();
    await page.getByText('What should your next agent know?', {exact: true}).waitFor();
    await page.getByRole('button', {name: 'Add your first memory', exact: true}).click();
    assert.equal(await page.locator('#fact-scope').inputValue(), 'project/main');
    assert.equal(await page.locator('#predicate').inputValue(), 'decision');
    assert.equal(await page.locator('#remember-form .advanced').evaluate(node => node.open), false);
    await page.locator('#subject').fill('auth');
    await page.keyboard.press('Escape'); await page.locator('#remember').click();
    assert.equal(await page.locator('#subject').inputValue(), 'auth');
    await page.locator('#fact-value').fill('cookies');
    await page.locator('#fact-evidence').fill('Approved cookies decision'); await page.locator('#fact-authority').check();
    await page.locator('#remember-form button[type=submit]').click();
    await page.locator('#remember-dialog').waitFor({state: 'hidden'});
    assert.ok((await page.locator('#records').innerText()).includes('cookies'));
    assert.equal(await page.locator('#result').isVisible(), true);
    await openMenu(); await page.locator('#access-keys').click();
    assert.equal(await page.locator('#key-management').isVisible(), false);
    assert.equal(await page.locator('.connect-client').count(), 3);
    assert.equal(await page.locator('#client-setup').isVisible(), false);
    await page.locator('[name=client][value=cursor]').click();
    const install = new URL(await page.locator('#cursor-install').getAttribute('href'));
    const config = JSON.parse(Buffer.from(install.searchParams.get('config'), 'base64').toString('utf8'));
    assert.equal(config.env.RETRACT_URL, 'https://retract.test');
    assert.equal(config.env.RETRACT_API_KEY, undefined);
    assert.ok((await page.locator('#agent-prompt').innerText()).includes('created-project'));
    await page.locator('[name=client][value=claude]').click();
    assert.ok((await page.locator('#install-command').innerText()).startsWith('claude mcp add '));
    assert.equal(await page.locator('#cursor-install').getAttribute('href'), null);
    await page.locator('[name=client][value=codex]').click();
    assert.ok((await page.locator('#install-command').innerText()).startsWith('codex mcp add retract '));
    await page.keyboard.press('Escape');
    await page.waitForFunction(() => document.querySelector('#install-command').textContent === '');
    // Query state survives navigation, reload, and the browser Back button.
    await page.locator('#search').fill('cookies');
    await page.waitForURL(url => url.searchParams.get('q') === 'cookies');
    assert.equal(new URL(page.url()).searchParams.get('q'), 'cookies');
    await navigate('plans'); await page.waitForURL(url => url.searchParams.get('view') === 'plans');
    await page.goBack();
    await page.waitForFunction(() => document.querySelector('#connection').textContent === 'Storage connected' && document.querySelector('#title').textContent === 'Memory');
    assert.equal(await page.locator('#search').inputValue(), 'cookies');
    await page.reload();
    await page.waitForFunction(() => document.querySelector('#connection').textContent === 'Storage connected');
    assert.equal(await page.locator('#search').inputValue(), 'cookies');
    await page.locator('#clear-search').click();
    assert.equal(new URL(page.url()).searchParams.has('q'), false);
    await page.locator('#title').focus(); await page.keyboard.press('/');
    assert.equal(await page.locator('#search').evaluate(node => document.activeElement === node), true);
    if (width <= 760) {
      await openMenu(); assert.equal(await page.locator('#content').evaluate(node => node.inert), true);
      await page.keyboard.press('Escape'); assert.equal(await page.locator('#menu-toggle').getAttribute('aria-expanded'), 'false');
      assert.equal(await page.locator('#content').evaluate(node => node.inert), false);
    }
    assert.deepEqual(errors, []);
    await context.close(); passed++;
    console.log(`PASS ${width}px: source safety, suggestions, corrections, stale retry, paths, recovery, first-run setup, defaults, agent connection, deep links, Back/reload, keyboard, overflow`);
  }
  const liveIndex = process.argv.indexOf('--live-url');
  if (liveIndex !== -1) {
    const target = new URL(process.argv[liveIndex + 1]);
    if (target.protocol !== 'http:' || !['127.0.0.1', 'localhost'].includes(target.hostname)) throw new Error('Live URL must be local HTTP');
    const page = await browser.newPage();
    await page.goto(target.href);
    if (await page.locator('#local-auth').isVisible()) {
      await page.locator('#auth-email').fill('ada@retract.test');
      await page.locator('#auth-password').fill('local-pass');
      await page.locator('#local-auth button[type="submit"]').click();
    }
    await page.waitForFunction(() => document.querySelector('#connection').textContent === 'Storage connected');
    assert.ok(await page.locator('#snapshot-meta').innerText().then(text => text.includes('Revision')));
    await page.close(); console.log('PASS read-only real-service dashboard smoke');
  }
  console.log(`${passed} browser viewport scenarios passed. Controlled network responses; database integration is separate.`);
} finally { await browser.close(); }
