/** Hosted connection UX with controlled identity and API responses. */
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {chromium} from 'playwright';
const root = new URL('../src/retract/web/', import.meta.url);
const origin = 'https://retract.test';
const browser = await chromium.launch({headless: true});
try {
  for (const width of [375, 1440]) {
    const context = await browser.newContext({viewport: {width, height: 900}, permissions: ['clipboard-read', 'clipboard-write']});
    const page = await context.newPage(); page.setDefaultTimeout(10000);
    const errors = []; page.on('pageerror', e => errors.push(e.message));
    let keys = []; let revocations = 0;
    await page.route(`${origin}/**`, async route => {
      const request = route.request(); const path = new URL(request.url()).pathname;
      const json = (body, status = 200) => route.fulfill({status, contentType: 'application/json', body: JSON.stringify(body)});
      const assets = {'/dashboard': ['index.html', 'text/html'], '/assets/dashboard.css': ['dashboard.css', 'text/css'], '/assets/dashboard.mjs': ['dashboard.mjs', 'text/javascript'], '/assets/dashboard-model.mjs': ['dashboard-model.mjs', 'text/javascript'], '/assets/auth.mjs': ['auth.mjs', 'text/javascript']};
      if (assets[path]) { const [file, contentType] = assets[path]; return route.fulfill({contentType, body: await readFile(new URL(file, root), 'utf8')}); }
      if (path.startsWith('/assets/fonts/')) return route.fulfill({contentType: 'font/woff2', body: await readFile(new URL(path.replace('/assets/', ''), root))});
      if (path.includes('/npm/@clerk/ui')) return route.fulfill({contentType: 'text/javascript', body: 'window.__internal_ClerkUICtor = function() {}'});
      if (path.includes('/npm/@clerk/clerk-js')) return route.fulfill({contentType: 'text/javascript', body: "window.Clerk = {load: async () => {}, session: {getToken: async () => 'fixture-token'}, mountUserButton: () => {}, addListener: () => () => {}}"});
      if (path === '/api/config') return json({mode: 'hosted', issuer: `${origin}/clerk`, publishable_key: 'pk_test_browser_fixture', origin});
      assert.equal(request.headers().authorization, 'Bearer fixture-token');
      if (path === '/api/projects') return json({projects: [], truncated: false});
      if (path === '/api/keys') return json({keys});
      if (path === '/account/keys') {
        keys = [{id: 'key-fixture', name: request.postDataJSON().name, expires_at: 1893456000}];
        return json({token: 'rk_synthetic_fixture_only'});
      }
      if (path === '/account/keys/revoke') { assert.deepEqual(request.postDataJSON(), {id: 'key-fixture'}); revocations++; keys = []; return json({revoked: true}); }
      return json({error: 'Unexpected request'}, 404);
    });
    await page.goto(`${origin}/dashboard`);
    await page.getByRole('button', {name: 'Create your first project', exact: true}).waitFor();
    const open = async () => { if (width <= 760) await page.locator('#menu-toggle').click(); await page.locator('#access-keys').click(); };
    await open();
    assert.equal(await page.locator('#local-setup').isVisible(), false);
    await page.locator('#key-name').fill('Work laptop');
    await page.locator('#key-form button[type=submit]').click();
    await page.locator('#key-created').waitFor();
    assert.equal(await page.locator('#key-secret').inputValue(), 'rk_synthetic_fixture_only');
    const config = JSON.parse(await page.locator('#mcp-config').innerText());
    assert.equal(config.mcpServers.retract.env.RETRACT_API_KEY, 'rk_synthetic_fixture_only');
    await page.locator('#config-copy').click();
    assert.equal(await page.evaluate(() => navigator.clipboard.readText()), await page.locator('#mcp-config').innerText());
    await page.waitForFunction(() => !document.querySelector('#key-form').hasAttribute('aria-busy'));
    await page.keyboard.press('Escape');
    await page.waitForFunction(() => document.querySelector('#key-secret').value === '');
    assert.equal(await page.locator('#key-secret').inputValue(), '');
    assert.equal(await page.locator('#mcp-config').textContent(), '');
    await open();
    assert.equal(await page.locator('#config-copy').textContent(), 'Copy configuration');
    await page.getByRole('button', {name: 'Revoke Work laptop', exact: true}).click();
    assert.equal(revocations, 0);
    await page.getByRole('button', {name: 'Cancel', exact: true}).click();
    assert.equal(revocations, 0);
    await page.getByRole('button', {name: 'Revoke Work laptop', exact: true}).click();
    await page.getByRole('button', {name: 'Confirm revocation of Work laptop', exact: true}).click();
    await page.getByText('No access keys yet. Create one to connect your coding client.', {exact: true}).waitFor();
    assert.equal(revocations, 1); assert.deepEqual(errors, []);
    await context.close();
    console.log(`PASS ${width}px: hosted key setup, authorized API calls, clipboard, secret cleanup, revocation confirmation/cancel`);
  }
} finally { await browser.close(); }
