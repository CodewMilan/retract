let config = {mode: 'local'};
let clerk;
const appearance = {
  options: {
    unsafe_disableDevelopmentModeWarnings: true,
  },
  variables: {
    colorPrimary: '#000000',
    colorDanger: '#ff4500',
    colorSuccess: '#000000',
    colorBackground: '#ffffff',
    colorInputBackground: '#ffffff',
    colorInputText: '#000000',
    colorText: '#000000',
    colorTextSecondary: '#686562',
    colorTextOnPrimaryBackground: '#ffffff',
    borderRadius: '0px',
    fontFamily: 'Inter, system-ui, sans-serif',
    fontFamilyButtons: 'Inter, system-ui, sans-serif',
  },
  elements: {
    rootBox: {width: '100%'},
    cardBox: {width: '100%', boxShadow: 'none'},
    card: {width: '100%', background: 'transparent', boxShadow: 'none', border: 'none', padding: '0'},
    headerTitle: {fontFamily: '"Inter Tight", Inter, sans-serif', fontWeight: '500', letterSpacing: '-0.02em', fontSize: '1.75rem'},
    headerSubtitle: {color: '#686562', fontSize: '1rem'},
    socialButtonsBlockButton: {borderRadius: '999px', border: '1px solid #c5d3e8', boxShadow: 'none'},
    formButtonPrimary: {backgroundColor: '#000000', borderRadius: '999px', boxShadow: 'none', textTransform: 'none', fontWeight: '500'},
    formFieldInput: {borderRadius: '0', border: '1px solid #c5d3e8', boxShadow: 'none'},
    footerActionLink: {color: '#ff4500', fontWeight: '500'},
    footer: {background: 'transparent'},
    footerItem: {display: 'none'},
    logoBox: {display: 'none'},
    dividerLine: {background: '#c5d3e8'},
  },
};
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
  await clerk.load({appearance, ui: {ClerkUI: window.__internal_ClerkUICtor}});
  if (!clerk.session) {
    $('auth-status').hidden = true;
    clerk.mountSignIn($('sign-in'), {
      appearance,
      routing: 'hash',
      withSignUp: true,
      forceRedirectUrl: `${config.origin}/dashboard`,
      signUpForceRedirectUrl: `${config.origin}/dashboard`,
    });
    await new Promise(resolve => {
      const unsubscribe = clerk.addListener(({session}) => {
        if (session) { queueMicrotask(() => unsubscribe()); resolve(); }
      });
    });
    clerk.unmountSignIn($('sign-in'));
  }
  $('auth-screen').hidden = true; document.querySelector('.shell').hidden = false;
  $('account-controls').hidden = false;
  clerk.mountUserButton($('user-button'), {appearance, afterSignOutUrl: config.origin});
  clerk.addListener(({session}) => { if (!session) window.location.reload(); });
}
export async function authHeaders() {
  if (config.mode === 'local') return {};
  const token = await clerk?.session?.getToken();
  if (!token) throw new Error('Your session ended. Reload and sign in again.');
  return {Authorization: `Bearer ${token}`};
}
export function authConfig() { return config; }
export function authFailed(error) {
  $('auth-screen').hidden = false; document.querySelector('.shell').hidden = true;
  $('auth-status').hidden = false; $('auth-status').textContent = error.message; $('auth-retry').hidden = false;
}
$('auth-retry').onclick = () => window.location.reload();
