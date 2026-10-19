import assert from 'node:assert/strict';
import test from 'node:test';
import {spawnSync} from 'node:child_process';
import {serverConfig, cursorInstallLink, installCommand} from '../src/retract/web/agent-connect.mjs';

test('Cursor install links carry a single server configuration with UTF-8 values', () => {
  const config = serverConfig('https://retract.example', 'synthetic-雪-token');
  const url = new URL(cursorInstallLink(config));
  assert.equal(url.protocol, 'cursor:'); assert.equal(url.host, 'anysphere.cursor-deeplink');
  assert.equal(url.pathname, '/mcp/install'); assert.equal(url.searchParams.get('name'), 'retract');
  assert.deepEqual(JSON.parse(Buffer.from(url.searchParams.get('config'), 'base64').toString('utf8')), config);
  assert.equal(Object.hasOwn(config, 'mcpServers'), false);
});

function shellArguments(client, config) {
  const executable = client === 'claude' ? 'claude' : 'codex';
  const stub = `${executable}() { printf '%s\\0' "$@"; }; `;
  const result = spawnSync('/bin/sh', ['-c', stub + installCommand(client, config)], {encoding: 'utf8'});
  assert.equal(result.status, 0, result.stderr);
  return result.stdout.split('\0').slice(0, -1);
}
for (const client of ['claude', 'codex']) {
  test(`${client} commands preserve the credentials as arguments and launch the real stdio entrypoint`, () => {
    const config = serverConfig('https://retract.example', "synthetic token'$(printf INJECTED)");
    const args = shellArguments(client, config);
    assert.ok(args.includes(`RETRACT_API_KEY=${config.env.RETRACT_API_KEY}`));
    assert.ok(args.includes('RETRACT_URL=https://retract.example'));
    const separator = args.indexOf('--');
    assert.deepEqual(args.slice(separator + 1), [config.command, ...config.args]);
    if (client === 'claude') assert.deepEqual(args.slice(separator - 5, separator), ['--scope', 'user', '--transport', 'stdio', 'retract']);
    else assert.deepEqual(args.slice(0, 3), ['mcp', 'add', 'retract']);
  });
  test(`${client} local setup has no empty or fabricated access key`, () => {
    const args = shellArguments(client, serverConfig('http://127.0.0.1:8100'));
    assert.ok(args.includes('RETRACT_URL=http://127.0.0.1:8100'));
    assert.equal(args.some(arg => arg.startsWith('RETRACT_API_KEY=')), false);
  });
}

test('unsupported clients cannot receive a misleading terminal command', () => {
  assert.throws(() => installCommand('cursor', serverConfig('http://localhost:8100')), /Choose Claude Code or Codex/);
});
