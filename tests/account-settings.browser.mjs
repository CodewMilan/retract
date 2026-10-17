/** Real Chromium + actual Python HTTP handler, with test-only profile storage.
 * --live-url adds a real PostgreSQL-backed Alice edit/restore check on localhost.
 */
import assert from 'node:assert/strict';
import {mkdir} from 'node:fs/promises';
import {resolve} from 'node:path';
import {pathToFileURL} from 'node:url';
import {AccountTransport} from './account-transport.mjs';
const {chromium} = await import(process.env.PLAYWRIGHT_MODULE ? pathToFileURL(resolve(process.env.PLAYWRIGHT_MODULE)).href : 'playwright');
const screenshotDir = resolve('reports/account-settings/browser'); await mkdir(screenshotDir, {recursive: true});
const browser = await chromium.launch({headless: true});
try {
  for (const width of [375, 768, 1280]) {
    const transport = new AccountTransport();
    const context = await browser.newContext({viewport: {width, height: 900}, colorScheme: width === 768 ? 'dark' : 'light', reducedMotion: 'reduce'});
    try {
      const page = await context.newPage(); const errors = []; const saves = [];
      page.on('pageerror', error => errors.push(error.message));
      page.on('request', request => { if (request.method() === 'PATCH') saves.push(request); });
      await page.route('https://account.retract.test/**', async route => {
        const request = route.request(); const url = new URL(request.url());
        const response = await transport.exchange({method: request.method(), path: url.pathname,
          headers: await request.allHeaders(), body: request.postData() || ''});
        const headers = {...response.headers}; delete headers.Connection; delete headers['Content-Length'];
        await route.fulfill({status: response.status, headers, body: Buffer.from(response.body_base64, 'base64')});
      });
      await page.goto('https://account.retract.test/settings');
      await page.locator('#signed-out').waitFor();
      assert.equal(await page.locator('#profile').isVisible(), false);
      await page.locator('#sign-in').press('Enter'); await page.locator('#profile').waitFor();
      await page.waitForFunction(() => document.activeElement.id === 'display-name');
      assert.equal(await page.locator('#display-name').inputValue(), 'Alice Example');
      assert.equal(await page.locator('#email').isEditable(), false);
      const cookie = (await context.cookies()).find(cookie => cookie.name === 'retract_demo_session');
      assert.ok(cookie?.httpOnly); assert.equal(cookie.sameSite, 'Strict');
      assert.equal(await page.evaluate(() => document.cookie), '');
      await page.locator('#display-name').fill('  Alice Browser  '); await page.locator('#display-name').press('Enter');
      await page.locator('#message').filter({hasText: 'Profile saved for Alice Browser.'}).waitFor();
      const save = saves.at(-1); const headers = await save.allHeaders();
      assert.equal(new URL(save.url()).pathname, '/api/profiles/alice');
      assert.deepEqual(save.postDataJSON(), {display_name: 'Alice Browser'});
      assert.ok(headers.cookie?.includes('retract_demo_session=')); assert.ok(headers['x-csrf-token']); assert.equal(headers.authorization, undefined);
      const denied = await page.evaluate(async csrf => (await fetch('/api/profiles/bob', {method: 'PATCH', credentials: 'same-origin',
        headers: {'Content-Type': 'application/json', 'X-CSRF-Token': csrf}, body: JSON.stringify({display_name: 'Wrong'})})).status, headers['x-csrf-token']);
      assert.equal(denied, 403);
      await page.reload(); await page.locator('#profile').waitFor();
      assert.equal(await page.locator('#display-name').inputValue(), 'Alice Browser');
      await transport.exchange({control: 'fail_save'});
      await page.locator('#display-name').fill('Alice Retry'); await page.locator('#save').click();
      await page.locator('#error').filter({hasText: /storage unavailable/i}).waitFor();
      assert.equal(await page.locator('#display-name').inputValue(), 'Alice Retry');
      assert.equal(await page.locator('#message').isVisible(), false);
      await page.locator('#save').click(); await page.locator('#message').filter({hasText: 'Profile saved for Alice Retry.'}).waitFor();
      await transport.exchange({control: 'expire'});
      await page.locator('#display-name').fill('Alice retained draft'); await page.locator('#save').click();
      await page.locator('#signed-out').waitFor(); await page.locator('#sign-in').click(); await page.locator('#profile').waitFor();
      assert.equal(await page.locator('#display-name').inputValue(), 'Alice retained draft');
      await transport.exchange({control: 'expire'}); await page.locator('#save').click(); await page.locator('#signed-out').waitFor();
      await page.getByRole('radio', {name: /Bob Example/}).check(); await page.locator('#sign-in').click(); await page.locator('#profile').waitFor();
      assert.equal(await page.locator('#display-name').inputValue(), 'Bob Example');
      assert.equal(await page.locator('#email').inputValue(), 'bob@example.test');
      const literal = '<img src=x onerror=window.sourceExecuted=true>';
      await page.locator('#display-name').fill(literal); await page.locator('#save').click();
      await page.locator('#message').filter({hasText: `Profile saved for ${literal}.`}).waitFor();
      assert.equal(await page.locator('img').count(), 0); assert.equal(await page.evaluate(() => window.sourceExecuted), undefined);
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
      await page.screenshot({path: resolve(screenshotDir, `settings-${width}.png`), fullPage: true});
      await page.locator('#sign-out').click(); await page.locator('#signed-out').waitFor();
      await page.reload(); await page.locator('#signed-out').waitFor();
      assert.deepEqual(errors, []);
      console.log(`PASS ${width}px: cookie recovery, CSRF, ownership, save failure/retry, expiration, account isolation, sign-out, literal text, overflow`);
    } finally { await context.close(); await transport.close(); }
  }
  const index = process.argv.indexOf('--live-url');
  if (index !== -1) {
    const target = new URL(process.argv[index + 1]);
    if (target.protocol !== 'http:' || !['127.0.0.1', 'localhost'].includes(target.hostname) || target.pathname !== '/'
        || target.username || target.password || target.search || target.hash) throw new Error('Live URL must be a local HTTP origin');
    const context = await browser.newContext(); const page = await context.newPage();
    let original = null; let csrf = null;
    try {
      const health = await page.request.get(new URL('/health', target).href);
      assert.equal(health.status(), 200);
      assert.equal((await health.json()).storage, 'postgresql');
      page.on('request', request => { if (request.method() === 'PATCH') request.allHeaders().then(headers => { csrf = headers['x-csrf-token']; }); });
      await page.goto(new URL('/settings', target).href); await page.locator('#signed-out').waitFor();
      await page.locator('#sign-in').click(); await page.locator('#profile').waitFor();
      original = await page.locator('#display-name').inputValue();
      const changed = original === 'Alice browser verification' ? 'Alice alternate verification' : 'Alice browser verification';
      await page.locator('#display-name').fill(changed); await page.locator('#save').click();
      await page.locator('#message').filter({hasText: `Profile saved for ${changed}.`}).waitFor();
      await page.reload(); await page.locator('#profile').waitFor(); assert.equal(await page.locator('#display-name').inputValue(), changed);
      console.log('PASS real-service edit and session recovery; restoring the original synthetic Alice profile');
    } finally {
      try {
        if (original !== null) {
          const restored = await page.evaluate(async ({name, csrf}) => {
            const session = await (await fetch('/api/session', {credentials: 'same-origin'})).json();
            return (await fetch('/api/profiles/alice', {method: 'PATCH', credentials: 'same-origin', headers: {'Content-Type': 'application/json', 'X-CSRF-Token': session.csrf_token || csrf}, body: JSON.stringify({display_name: name})})).status;
          }, {name: original, csrf});
          assert.equal(restored, 200, 'Could not restore the original synthetic profile');
          await page.locator('#sign-out').click();
          await page.locator('#signed-out').waitFor();
        }
      } finally { await context.close(); }
    }
  }
  console.log('Account-settings browser scenarios passed. Default storage is a controlled test fixture; real PostgreSQL requires --live-url.');
} finally { await browser.close(); }
