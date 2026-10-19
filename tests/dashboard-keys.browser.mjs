/** Hosted connection UX with controlled identity and API responses. */
import assert from 'node:assert/strict';
import {readFile, mkdir} from 'node:fs/promises';
import {chromium} from 'playwright';
const root = new URL('../src/retract/web/', import.meta.url);
const origin = 'https://retract.test';
const browser = await chromium.launch({headless: true});
try {
  for (const width of [375, 1440]) {
    const context = await browser.newContext({viewport: {width, height: 900}, permissions: ['clipboard-read', 'clipboard-write']});
    const page = await context.newPage(); page.setDefaultTimeout(10000);
    const errors = []; page.on('pageerror', e => errors.push(e.message));
    let keys = []; let revocations = 0; let creations = 0; let failure = 0;
    await page.route(`${origin}/**`, async route => {
      const request = route.request(); const path = new URL(request.url()).pathname;
      const json = (body, status = 200) => route.fulfill({status, contentType: 'application/json', body: JSON.stringify(body)});
      const assets = {'/dashboard': ['index.html', 'text/html'], '/assets/dashboard.css': ['dashboard.css', 'text/css'], '/assets/dashboard.mjs': ['dashboard.mjs', 'text/javascript'], '/assets/dashboard-model.mjs': ['dashboard-model.mjs', 'text/javascript'], '/assets/agent-connect.mjs': ['agent-connect.mjs', 'text/javascript'], '/assets/auth.mjs': ['auth.mjs', 'text/javascript'], '/assets/loader.mjs': ['loader.mjs', 'text/javascript'], '/assets/gsap.min.js': ['gsap.min.js', 'text/javascript']};
      if (assets[path]) { const [file, contentType] = assets[path]; return route.fulfill({contentType, body: await readFile(new URL(file, root), 'utf8')}); }
      if (path.startsWith('/assets/fonts/')) return route.fulfill({contentType: 'font/woff2', body: await readFile(new URL(path.replace('/assets/', ''), root))});
      if (path.includes('/npm/@clerk/ui')) return route.fulfill({contentType: 'text/javascript', body: 'window.__internal_ClerkUICtor = function() {}'});
      if (path.includes('/npm/@clerk/clerk-js')) return route.fulfill({contentType: 'text/javascript', body: "window.Clerk = {load: async () => {}, session: {getToken: async () => 'fixture-token'}, mountUserButton: () => {}, addListener: () => () => {}}"});
      if (path === '/api/config') return json({mode: 'hosted', issuer: `${origin}/clerk`, publishable_key: 'pk_test_browser_fixture', origin});
      assert.equal(request.headers().authorization, 'Bearer fixture-token');
      if (path === '/api/projects') return json({projects: [], truncated: false});
      if (path === '/api/keys') return json({keys});
      if (path === '/account/keys') {
        if (failure) return json({error: failure === 409 ? 'Revoke an existing key before creating another (limit 10)' : 'Connection service unavailable'}, failure);
        const key = {id: `key-${++creations}`, name: request.postDataJSON().name, expires_at: 1893456000};
        keys.push(key); return json({...key, token: `rt_synthetic_${key.id}`});
      }
      if (path === '/account/keys/revoke') { assert.ok(keys.some(key => key.id === request.postDataJSON().id)); revocations++; keys = keys.filter(key => key.id !== request.postDataJSON().id); return json({revoked: true}); }
      return json({error: 'Unexpected request'}, 404);
    });
    await page.goto(`${origin}/dashboard`);
    await page.getByRole('button', {name: 'Create your first project', exact: true}).waitFor();
    const open = async () => { if (width <= 760) await page.locator('#menu-toggle').click(); await page.locator('#access-keys').click(); };
    await open();
    assert.equal(await page.locator('.connect-client').count(), 3); assert.equal(creations, 0);
    const connect = async client => {
      await page.locator(`[name=client][value=${client}]`).click();
      await page.waitForFunction(() => !document.querySelector('#key-form').hasAttribute('aria-busy'));
    };
    await mkdir('reports/agent-connect', {recursive: true});
    await page.screenshot({path: `reports/agent-connect/choose-${width}.png`});
    await connect('cursor');
    const link = new URL(await page.locator('#cursor-install').getAttribute('href'));
    assert.equal(link.protocol, 'cursor:'); assert.equal(link.host, 'anysphere.cursor-deeplink');
    const config = JSON.parse(Buffer.from(link.searchParams.get('config'), 'base64').toString('utf8'));
    assert.equal(config.env.RETRACT_API_KEY, 'rt_synthetic_key-1'); assert.equal(config.env.RETRACT_URL, origin);
    assert.equal(config.command, 'uvx'); assert.equal(await page.locator('#command-setup').isVisible(), false);
    await page.screenshot({path: `reports/agent-connect/cursor-${width}.png`});
    // Verify the browser action without launching the developer's editor.
    await page.locator('#cursor-install').evaluate(a => a.addEventListener('click', event => event.preventDefault(), {once: true}));
    await page.locator('#cursor-install').click();
    assert.match(await page.locator('#connect-status').innerText(), /Approve the install in Cursor/);
    await connect('claude');
    assert.match(await page.locator('#install-command').innerText(), /^claude mcp add .*--scope user --transport stdio retract -- uvx /);
    assert.ok((await page.locator('#install-command').innerText()).includes('RETRACT_API_KEY=rt_synthetic_key-2'));
    assert.equal(await page.locator('#cursor-install').getAttribute('href'), null);
    await page.locator('#install-copy').click();
    assert.equal(await page.evaluate(() => navigator.clipboard.readText()), await page.locator('#install-command').innerText());
    await connect('codex');
    assert.match(await page.locator('#install-command').innerText(), /^codex mcp add retract /);
    assert.ok((await page.locator('#install-command').innerText()).includes('RETRACT_API_KEY=rt_synthetic_key-3'));
    assert.equal(creations, 3); assert.deepEqual(keys.map(key => key.name), ['Cursor', 'Claude Code', 'Codex']);
    assert.equal(await page.locator('.connect-client svg').count(), 3);
    await page.screenshot({path: `reports/agent-connect/codex-${width}.png`});
    await connect('cursor'); assert.equal(creations, 3); // Reuse the prepared key within this dialog.
    await connect('codex');
    await page.locator('#key-management > summary').click();
    await page.getByRole('button', {name: 'Revoke Codex', exact: true}).click();
    assert.equal(revocations, 0);
    await page.getByRole('button', {name: 'Cancel', exact: true}).click(); assert.equal(revocations, 0);
    await page.getByRole('button', {name: 'Revoke Codex', exact: true}).click();
    await page.getByRole('button', {name: 'Confirm revocation of Codex', exact: true}).click();
    await page.waitForFunction(() => document.querySelector('#client-setup').hidden);
    assert.equal(revocations, 1); assert.equal(await page.locator('#install-command').textContent(), '');
    failure = 503; await connect('codex');
    assert.match(await page.locator('#key-error').innerText(), /Connection service unavailable/);
    assert.equal(await page.locator('#client-setup').isVisible(), false);
    failure = 409; await connect('codex');
    assert.match(await page.locator('#key-error').innerText(), /Revoke an existing key/);
    assert.doesNotMatch(await page.locator('#key-error').innerText(), /Refresh context/);
    assert.equal(await page.locator('#key-management').evaluate(node => node.open), true);
    failure = 0; await connect('codex'); assert.equal(creations, 4);
    await page.keyboard.press('Escape');
    await page.waitForFunction(() => document.querySelector('#install-command').textContent === '');
    assert.equal(await page.locator('#cursor-install').getAttribute('href'), null);
    await open();
    assert.equal(await page.locator('#client-setup').isVisible(), false);
    await connect('cursor'); assert.equal(creations, 5); // Old secrets were cleared on close.
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
    assert.deepEqual(errors, []);
    await context.close();
    console.log(`PASS ${width}px: three client buttons, Cursor install link, Claude/Codex commands, per-client credentials, clipboard, cleanup, reuse, revoke/cancel, failures and quota recovery`);
  }
} finally { await browser.close(); }
