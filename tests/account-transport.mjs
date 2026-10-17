/** Test fixture transport through Python's real HTTP parser; no network listener. */
import {spawn} from 'node:child_process';
import {createInterface} from 'node:readline';
import {fileURLToPath} from 'node:url';
export class AccountTransport {
  constructor() {
    this.pending = []; this.cookie = ''; this.requests = [];
    this.child = spawn(process.env.PYTHON || 'python3', [fileURLToPath(new URL('./account_http_bridge.py', import.meta.url))], {stdio: ['pipe', 'pipe', 'inherit']});
    this.lines = createInterface({input: this.child.stdout});
    this.lines.on('line', line => {
      const waiter = this.pending.shift(); if (!waiter) return;
      clearTimeout(waiter.timer);
      try { const data = JSON.parse(line); if (data.bridge_error) throw new Error(data.bridge_error); waiter.resolve(data); }
      catch (error) { waiter.reject(error); }
    });
    const failed = error => { for (const waiter of this.pending.splice(0)) { clearTimeout(waiter.timer); waiter.reject(error); } };
    this.child.on('error', failed); this.child.on('exit', () => failed(new Error('Test HTTP bridge exited')));
  }
  exchange(request) {
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => { reject(new Error('Test HTTP bridge timed out')); this.child.kill(); }, 10000);
      this.pending.push({resolve, reject, timer});
      this.child.stdin.write(JSON.stringify(request) + '\n');
    });
  }
  async raw(path, {method = 'GET', headers = {}, body = ''} = {}) {
    const response = await this.exchange({path, method, headers, body});
    return new Response(Buffer.from(response.body_base64, 'base64'), {status: response.status, headers: response.headers});
  }
  async fetch(path, init = {}) {
    if (init.credentials !== 'same-origin') throw new Error('Client omitted same-origin credentials');
    const headers = {...init.headers, ...(this.cookie ? {Cookie: this.cookie} : {})};
    this.requests.push({path, ...init, headers});
    const response = await this.raw(path, {...init, headers});
    const cookie = response.headers.get('set-cookie');
    if (cookie) this.cookie = cookie.includes('Max-Age=0') ? '' : cookie.split(';', 1)[0];
    return response;
  }
  async reset() { this.cookie = ''; this.requests = []; await this.exchange({control: 'reset'}); }
  async close() {
    this.lines.close(); this.child.stdin.end();
    if (this.child.exitCode === null) {
      await Promise.race([new Promise(resolve => this.child.once('exit', resolve)), new Promise(resolve => { const timer = setTimeout(() => { this.child.kill(); resolve(); }, 1000); timer.unref(); })]);
    }
  }
}
