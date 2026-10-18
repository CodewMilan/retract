let config = {mode: 'local'};
let clerk;
const $ = id => document.getElementById(id);
function script(src, key) {
  return new Promise((resolve, reject) => {
    const element = document.createElement('script');
    element.src = src; element.async = true; element.crossOrigin = 'anonymous';
    if (key) element.dataset.clerkPublishableKey = key;
    element.onload = resolve;
    element.onerror = () => reject(new Error('Sign-in could not load. Check your connection and retry.'));
    document.head.append(element);
  });
}
export async function initAuth() {
  const response = await fetch('/api/config', {cache: 'no-store'});
  if (!response.ok) throw new Error('Workspace configuration unavailable. Reload to retry.');
  config = await response.json();
  if (config.mode === 'local') { document.querySelector('.shell').hidden = false; return; }
  document.querySelector('.shell').hidden = true; $('auth-screen').hidden = false;
  await script(`${config.issuer}/npm/@clerk/ui@1/dist/ui.browser.js`);
  await script(`${config.issuer}/npm/@clerk/clerk-js@6/dist/clerk.browser.js`, config.publishable_key);
  clerk = window.Clerk;
  await clerk.load({ui: {ClerkUI: window.__internal_ClerkUICtor}});
  if (!clerk.session) {
    $('auth-status').textContent = 'Sign in or create an account to start your private workspace.';
    clerk.mountSignIn($('sign-in'), {routing: 'hash', forceRedirectUrl: config.origin});
    await new Promise(resolve => {
      const unsubscribe = clerk.addListener(({session}) => {
        if (session) { queueMicrotask(() => unsubscribe()); resolve(); }
      });
    });
    clerk.unmountSignIn($('sign-in'));
  }
  $('auth-screen').hidden = true; document.querySelector('.shell').hidden = false;
  $('account-controls').hidden = false;
  clerk.mountUserButton($('user-button'), {afterSignOutUrl: config.origin});
  clerk.addListener(({session}) => { if (!session) window.location.reload(); });
}
export async function authHeaders() {
  if (config.mode === 'local') return {};
  const token = await clerk?.session?.getToken();
  if (!token) throw new Error('Your session ended. Reload and sign in again.');
  return {Authorization: `Bearer ${token}`};
}
export function authFailed(error) {
  $('auth-screen').hidden = false; document.querySelector('.shell').hidden = true;
  $('auth-status').textContent = error.message; $('auth-retry').hidden = false;
}
$('auth-retry').onclick = () => window.location.reload();
