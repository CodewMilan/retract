let config = {mode: 'local'};
let clerk;
const appearance = {
  layout: {
    socialButtonsPlacement: 'top',
    socialButtonsVariant: 'blockButton',
  },
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
    borderRadius: '6.1875rem',
    fontFamily: 'Inter, system-ui, sans-serif',
    fontFamilyButtons: 'Inter, system-ui, sans-serif',
  },
  elements: {
    rootBox: {width: '100%'},
    cardBox: {width: '100%', boxShadow: 'none'},
    card: {width: '100%', background: 'transparent', boxShadow: 'none', border: 'none', padding: '0'},
    headerTitle: {fontFamily: '"Inter Tight", Inter, sans-serif', fontWeight: '600', letterSpacing: '-0.03em', fontSize: '1.35rem', textAlign: 'left'},
    headerSubtitle: {display: 'none'},
    socialButtons: {display: 'grid', gap: '0.5rem'},
    socialButtonsBlockButton: {borderRadius: '6.1875rem', border: '0', backgroundColor: '#e2e9f3', boxShadow: 'none', fontWeight: '500'},
    formButtonPrimary: {backgroundColor: '#000000', borderRadius: '6.1875rem', boxShadow: 'none', textTransform: 'none', fontWeight: '500'},
    formFieldInput: {borderRadius: '0', border: '1px solid #c5d3e8', boxShadow: 'none'},
    footerActionLink: {color: '#111111', fontWeight: '600', textDecoration: 'underline'},
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
const LOCAL_KEY = 'retract-local-auth';
function showShell() {
  $('auth-screen').hidden = true;
  document.querySelector('.shell').hidden = false;
}
function showAuthScreen() {
  document.querySelector('.shell').hidden = true;
  $('auth-screen').hidden = false;
}
function showAuth() {
  showAuthScreen();
  import('./auth-portrait.mjs').then(module => module.mountPortrait(document.querySelector('.auth-portrait'))).catch(() => {});
}
function bindLocalAuth(onEnter) {
  const form = $('local-auth');
  const out = $('local-sign-out');
  if (out && !out.dataset.bound) {
    out.dataset.bound = '1';
    out.onclick = () => { sessionStorage.removeItem(LOCAL_KEY); window.location.reload(); };
  }
  if (!form || form.dataset.bound) return;
  form.dataset.bound = '1';
  let signingUp = true;
  $('auth-toggle').onclick = () => {
    signingUp = !signingUp;
    $('auth-title').textContent = signingUp ? 'Welcome to Retract' : 'Welcome back';
    $('auth-signup-fields').hidden = !signingUp;
    $('auth-password').required = signingUp;
    $('auth-password').autocomplete = signingUp ? 'new-password' : 'current-password';
    $('auth-switch-copy').textContent = signingUp ? 'Already have an account?' : "Don't have an account?";
    $('auth-toggle').textContent = signingUp ? 'Log in' : 'Sign up';
    $('auth-error').hidden = true;
  };
  form.onsubmit = event => {
    event.preventDefault();
    const email = $('auth-email');
    const password = $('auth-password');
    const error = $('auth-error');
    if (!email.checkValidity()) {
      error.hidden = false;
      error.textContent = 'Enter a valid email address.';
      email.focus();
      return;
    }
    if (signingUp && password.value.length < 8) {
      error.hidden = false;
      error.textContent = 'Use at least 8 characters.';
      password.focus();
      return;
    }
    error.hidden = true;
    sessionStorage.setItem(LOCAL_KEY, '1');
    if (out) out.hidden = false;
    showShell();
    onEnter?.();
  };
}
function appOrigin() {
  return config.mode === 'hosted' && config.origin ? config.origin : location.origin;
}
function dashboardUrl() {
  return `${appOrigin()}/dashboard`;
}
function callbackUrl() {
  return `${appOrigin()}/sso-callback`;
}
function isClerkReturn() {
  return location.pathname === '/sso-callback'
    || location.search.includes('__clerk')
    || location.search.includes('rotating_token_nonce')
    || location.hash.includes('sso-callback');
}
let releaseWorkspace = () => {};
let signingOut = false;
function clerkMessage(error) {
  return error?.errors?.[0]?.longMessage || error?.errors?.[0]?.message || error?.message || 'Sign-in could not continue.';
}
function showClerkError(error) {
  const node = $('auth-error');
  node.hidden = false;
  node.textContent = clerkMessage(error);
}
async function finishClerkSession(sessionId) {
  await clerk.setActive({session: sessionId});
  enterClerkWorkspace();
}
function accountName(user) {
  return [user?.firstName, user?.lastName].filter(Boolean).join(' ') || user?.primaryEmailAddress?.emailAddress || 'Account';
}
function accountInitial(user) {
  return (accountName(user)[0] || 'A').toUpperCase();
}
function paintAvatar(node, user) {
  if (!node) return;
  node.replaceChildren();
  const initial = accountInitial(user);
  if (!user?.imageUrl) {
    node.textContent = initial;
    return;
  }
  const image = document.createElement('img');
  image.alt = '';
  image.src = user.imageUrl;
  image.onerror = () => { node.replaceChildren(initial); };
  node.append(image);
}
function fillAccountForm() {
  const user = clerk.user;
  if (!user) return;
  $('account-first').value = user.firstName || '';
  $('account-last').value = user.lastName || '';
  $('account-email').value = user.primaryEmailAddress?.emailAddress || '';
  paintAvatar($('account-photo'), user);
  $('account-error').textContent = '';
  $('account-saved').hidden = true;
}
function mountAccount() {
  const user = clerk.user;
  const menu = $('account-menu');
  if (!user || !menu) return;
  const label = accountName(user);
  for (const button of [$('account-menu'), $('account-menu-mobile')]) {
    if (!button) continue;
    button.hidden = false;
    button.setAttribute('aria-label', `Account, ${label}`);
  }
  $('account-label').textContent = label;
  paintAvatar($('account-avatar'), user);
  paintAvatar($('account-avatar-mobile'), user);
  const out = $('local-sign-out');
  if (out) out.hidden = true;
  if (menu.dataset.bound) return;
  menu.dataset.bound = '1';
  const open = () => { fillAccountForm(); $('account-dialog').showModal(); $('account-first').focus(); };
  menu.onclick = open;
  const mobile = $('account-menu-mobile');
  if (mobile) mobile.onclick = open;
  $('account-image').onchange = async () => {
    const file = $('account-image').files?.[0];
    $('account-image').value = '';
    if (!file) return;
    $('account-error').textContent = '';
    $('account-saved').hidden = true;
    if (file.size > 10 * 1024 * 1024) {
      $('account-error').textContent = 'Use a photo smaller than 10 MB.';
      return;
    }
    try {
      await clerk.user.setProfileImage({file});
      paintAvatar($('account-photo'), clerk.user);
      paintAvatar($('account-avatar'), clerk.user);
      paintAvatar($('account-avatar-mobile'), clerk.user);
    } catch (error) {
      $('account-error').textContent = clerkMessage(error);
    }
  };
  $('account-form').onsubmit = async event => {
    event.preventDefault();
    const button = event.submitter;
    $('account-error').textContent = '';
    $('account-saved').hidden = true;
    button.disabled = true;
    button.textContent = 'Saving…';
    $('account-form').setAttribute('aria-busy', 'true');
    try {
      await clerk.user.update({firstName: $('account-first').value.trim(), lastName: $('account-last').value.trim()});
      const name = accountName(clerk.user);
      $('account-label').textContent = name;
      for (const trigger of [$('account-menu'), $('account-menu-mobile')]) trigger?.setAttribute('aria-label', `Account, ${name}`);
      paintAvatar($('account-avatar'), clerk.user);
      paintAvatar($('account-avatar-mobile'), clerk.user);
      $('account-saved').hidden = false;
    } catch (error) {
      $('account-error').textContent = clerkMessage(error);
    } finally {
      button.disabled = false;
      button.textContent = 'Save';
      $('account-form').removeAttribute('aria-busy');
    }
  };
  $('account-sign-out').onclick = async () => {
    const button = $('account-sign-out');
    button.disabled = true;
    button.textContent = 'Signing out…';
    signingOut = true;
    try {
      // Clerk finishes sign-out by leaving the page. A second navigation here
      // cancels that handoff and the session cookie survives.
      if (!clerk.client?.sessions?.length) {
        window.location.replace(dashboardUrl());
        return;
      }
      await clerk.signOut({redirectUrl: dashboardUrl()});
    } catch (error) {
      signingOut = false;
      button.disabled = false;
      button.textContent = 'Sign out';
      $('account-error').textContent = clerkMessage(error);
    }
  };
}
function enterClerkWorkspace() {
  showShell();
  mountAccount();
  if (!clerk.listenerBound) {
    clerk.listenerBound = true;
    clerk.addListener?.(({session}) => {
      if (!session && !signingOut) window.location.assign(dashboardUrl());
    });
  }
  releaseWorkspace();
}
async function startOAuth(strategy) {
  const params = {strategy, redirectUrl: callbackUrl(), redirectUrlComplete: dashboardUrl()};
  $('auth-error').hidden = true;
  if ($('auth-title').textContent === 'Welcome back') await clerk.client.signIn.authenticateWithRedirect(params);
  else await clerk.client.signUp.authenticateWithRedirect(params);
}
function bindClerkForm() {
  $('auth-social').hidden = false;
  $('auth-or').hidden = false;
  $('auth-note').textContent = 'GitHub, Google, and email sign-up use your Retract account.';
  $('auth-status').hidden = true;
  $('local-auth').hidden = false;
  $('auth-github').onclick = () => startOAuth('oauth_github').catch(showClerkError);
  $('auth-google').onclick = () => startOAuth('oauth_google').catch(showClerkError);
  let signingUp = true;
  $('auth-toggle').onclick = () => {
    signingUp = !signingUp;
    $('auth-title').textContent = signingUp ? 'Welcome to Retract' : 'Welcome back';
    $('auth-signup-fields').hidden = !signingUp;
    $('auth-password').required = signingUp;
    $('auth-code-fields').hidden = true;
    $('auth-switch-copy').textContent = signingUp ? 'Already have an account?' : "Don't have an account?";
    $('auth-toggle').textContent = signingUp ? 'Log in' : 'Sign up';
    $('auth-error').hidden = true;
  };
  const form = $('local-auth');
  form.onsubmit = async event => {
    event.preventDefault();
    const email = $('auth-email');
    const password = $('auth-password');
    const error = $('auth-error');
    error.hidden = true;
    const signingUp = $('auth-title').textContent !== 'Welcome back';
    try {
      if (!email.checkValidity()) {
        error.hidden = false;
        error.textContent = 'Enter a valid email address.';
        email.focus();
        return;
      }
      if ($('auth-code-fields').hidden === false) {
        const attempt = await clerk.client.signUp.attemptEmailAddressVerification({code: $('auth-code').value.trim()});
        if (attempt.status === 'complete') await finishClerkSession(attempt.createdSessionId);
        else showClerkError(new Error('That code was not accepted.'));
        return;
      }
      if (signingUp) {
        if (password.value.length < 8) {
          error.hidden = false;
          error.textContent = 'Use at least 8 characters.';
          password.focus();
          return;
        }
        await clerk.client.signUp.create({emailAddress: email.value.trim(), password: password.value});
        await clerk.client.signUp.prepareEmailAddressVerification({strategy: 'email_code'});
        $('auth-code-fields').hidden = false;
        $('auth-code').focus();
        return;
      }
      const result = await clerk.client.signIn.create({identifier: email.value.trim(), password: password.value});
      if (result.status === 'complete') await finishClerkSession(result.createdSessionId);
      else showClerkError(new Error('Sign-in needs another step. Use GitHub or Google.'));
    } catch (failure) {
      showClerkError(failure);
    }
  };
}
async function mountClerk() {
  showAuthScreen();
  await script(`${config.issuer}/npm/@clerk/clerk-js@6/dist/clerk.browser.js`, config.publishable_key);
  clerk = window.Clerk;
  const done = dashboardUrl();
  await clerk.load({
    appearance,
    signInUrl: done,
    signUpUrl: done,
    afterSignInUrl: done,
    afterSignUpUrl: done,
    signInForceRedirectUrl: done,
    signUpForceRedirectUrl: done,
    signInFallbackRedirectUrl: done,
    signUpFallbackRedirectUrl: done,
    afterSignOutUrl: done,
  });
  const pending = new Promise(resolve => { releaseWorkspace = resolve; });
  if (isClerkReturn()) {
    try {
      await clerk.handleRedirectCallback({
        signInUrl: done,
        signUpUrl: done,
        continueSignUpUrl: done,
        signInForceRedirectUrl: done,
        signUpForceRedirectUrl: done,
        signInFallbackRedirectUrl: done,
        signUpFallbackRedirectUrl: done,
      }, to => {
        const target = new URL(to, location.origin);
        const onWorkspace = target.origin === location.origin && (target.pathname === '/dashboard' || target.pathname === '/sso-callback');
        window.location.assign(onWorkspace ? target.href : done);
      });
    } catch (error) {
      showClerkError(error);
    }
  }
  if (clerk.session) {
    if (location.pathname === '/sso-callback') {
      window.location.replace(done);
      return new Promise(() => {});
    }
    enterClerkWorkspace();
    return;
  }
  showAuth();
  bindClerkForm();
  return pending;
}
export async function initAuth() {
  const response = await fetch('/api/config', {cache: 'no-store'});
  if (!response.ok) throw new Error('Workspace configuration unavailable. Reload to retry.');
  config = await response.json();
  if (config.publishable_key && config.issuer) return mountClerk();
  if (config.mode === 'local') {
    if (sessionStorage.getItem(LOCAL_KEY) === '1') {
      bindLocalAuth();
      const out = $('local-sign-out');
      if (out) out.hidden = false;
      showShell();
      return;
    }
    $('local-auth').hidden = false;
    $('auth-status').hidden = true;
    showAuth();
    return new Promise(resolve => bindLocalAuth(resolve));
  }
  throw new Error('Workspace configuration unavailable. Reload to retry.');
}
export async function authHeaders() {
  if (config.mode === 'local') return {};
  const token = await clerk?.session?.getToken();
  if (!token) throw new Error('Your session ended. Reload and sign in again.');
  return {Authorization: `Bearer ${token}`};
}
export function authConfig() { return config; }
export function authFailed(error) {
  showAuth(); document.querySelector('.shell').hidden = true;
  $('auth-status').hidden = false; $('auth-status').textContent = error.message; $('auth-retry').hidden = false;
}
$('auth-retry').onclick = () => window.location.reload();
