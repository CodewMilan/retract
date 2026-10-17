/** Cookie-session client. All session material is process-local to this page. */
export class AccountError extends Error {
  constructor(message, status = null) { super(message); this.name = 'AccountError'; this.status = status; }
}
export function displayName(value) {
  if (typeof value !== 'string' || !value.trim() || [...value.trim()].length > 80) {
    throw new AccountError('Use a display name with 1–80 characters.', 400);
  }
  return value.trim();
}
function userFrom(data, expectedId) {
  const user = data?.user;
  if (!user || !['alice', 'bob'].includes(user.id) || (expectedId && user.id !== expectedId)
      || typeof user.email !== 'string' || !user.email || typeof user.display_name !== 'string' || !user.display_name.trim()) {
    throw new AccountError('The account response is incomplete. Refresh your session to try again.', 502);
  }
  return {id: user.id, display_name: user.display_name, email: user.email};
}
export class AccountClient {
  #user = null;
  #csrf = null;
  #busy = false;
  constructor(fetcher = globalThis.fetch.bind(globalThis), timeout = 15000) { this.fetcher = fetcher; this.timeout = timeout; }
  get user() { return this.#user ? {...this.#user} : null; }
  clear() { this.#user = null; this.#csrf = null; }
  async #run(action) {
    if (this.#busy) throw new AccountError('Wait for the current request to finish.', 409);
    this.#busy = true;
    try { return await action(); } finally { this.#busy = false; }
  }
  async #request(path, method = 'GET', body, csrf) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), this.timeout);
    try {
      const headers = {Accept: 'application/json'};
      if (body !== undefined) headers['Content-Type'] = 'application/json';
      if (csrf) headers['X-CSRF-Token'] = csrf;
      const response = await this.fetcher(path, {method, headers, credentials: 'same-origin', cache: 'no-store',
        redirect: 'error', signal: controller.signal, ...(body !== undefined ? {body: JSON.stringify(body)} : {})});
      if (response.status === 401) this.clear();
      let data;
      try { data = await response.json(); } catch { throw new AccountError('The account service returned an unreadable response. Try again.', response.status); }
      if (!response.ok) {
        throw new AccountError(typeof data?.error === 'string' ? data.error.slice(0, 500) : 'The account request failed. Try again.', response.status);
      }
      return data;
    } catch (error) {
      if (error instanceof AccountError) throw error;
      throw new AccountError('Could not confirm the request. Your edits are preserved. Refresh the session to check the saved profile.');
    } finally { clearTimeout(timer); }
  }
  #acceptSession(data, expectedId) {
    const user = userFrom(data, expectedId);
    if (typeof data.csrf_token !== 'string' || !/^[\x21-\x7e]{1,256}$/.test(data.csrf_token)) {
      throw new AccountError('The session response is incomplete. Sign in again.', 502);
    }
    this.#user = user; this.#csrf = data.csrf_token;
    return this.user;
  }
  recover() {
    return this.#run(async () => {
      this.clear();
      try { return this.#acceptSession(await this.#request('/api/session')); }
      catch (error) { if (error.status === 401) return null; throw error; }
    });
  }
  login(userId) {
    return this.#run(async () => {
      if (!['alice', 'bob'].includes(userId)) throw new AccountError('Choose Alice or Bob.', 400);
      this.clear();
      return this.#acceptSession(await this.#request('/demo/login', 'POST', {user_id: userId}), userId);
    });
  }
  save(value) {
    return this.#run(async () => {
      const name = displayName(value);
      if (!this.#user || !this.#csrf) throw new AccountError('Sign in before saving your profile.', 401);
      const user = userFrom(await this.#request(`/api/profiles/${this.#user.id}`, 'PATCH', {display_name: name}, this.#csrf), this.#user.id);
      this.#user = user;
      return this.user;
    });
  }
  logout() {
    return this.#run(async () => {
      if (!this.#user) { this.clear(); return; }
      try { await this.#request('/demo/logout', 'POST', {}, this.#csrf); }
      catch (error) { if (error.status !== 401) throw error; }
      this.clear();
    });
  }
}
