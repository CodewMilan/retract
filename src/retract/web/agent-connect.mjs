const repository = 'git+https://github.com/CodewMilan/retract';
export const clients = {
  cursor: {name: 'Cursor', detail: 'Install directly in the editor'},
  claude: {name: 'Claude Code', detail: 'Connect with one terminal command'},
  codex: {name: 'Codex', detail: 'Connect with one terminal command'},
};

export function serverConfig(origin, token) {
  return {command: 'uvx', args: ['--from', repository, 'retract', 'mcp'],
    env: {RETRACT_URL: origin, ...(token ? {RETRACT_API_KEY: token} : {})}};
}

export function cursorInstallLink(config) {
  const bytes = new TextEncoder().encode(JSON.stringify(config));
  const encoded = btoa(Array.from(bytes, byte => String.fromCharCode(byte)).join(''));
  const link = new URL('cursor://anysphere.cursor-deeplink/mcp/install');
  link.searchParams.set('name', 'retract'); link.searchParams.set('config', encoded);
  return link.href;
}

// Quote values as data when a generated command is pasted into a POSIX shell.
const quote = value => /^[A-Za-z0-9_./:@%+=,-]+$/.test(value) ? value : `'${value.replaceAll("'", "'\"'\"'")}'`;
export function installCommand(client, config) {
  if (!['claude', 'codex'].includes(client)) throw new Error('Choose Claude Code or Codex for terminal setup.');
  const environment = Object.entries(config.env).flatMap(([key, value]) => ['--env', `${key}=${value}`]);
  // Claude's --env accepts multiple values. Put another option before the server
  // name so the name cannot be consumed as an environment variable.
  const args = client === 'claude'
    ? ['claude', 'mcp', 'add', ...environment, '--scope', 'user', '--transport', 'stdio', 'retract']
    : ['codex', 'mcp', 'add', 'retract', ...environment];
  return [...args, '--', config.command, ...config.args].map(quote).join(' ');
}
