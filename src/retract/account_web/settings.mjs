import {AccountClient, displayName} from './account-client.mjs';
const $ = id => document.getElementById(id);
const client = new AccountClient();
const state = {busy: false, draft: null, booting: true, focus: null};
function message(text = '') { $('message').textContent = text; $('message').hidden = !text; }
function error(text = '') { $('error').textContent = text; $('error').hidden = !text; $('retry').hidden = !text; }
function fieldError(text = '') {
  $('name-error').textContent = text; $('name-error').hidden = !text;
  $('display-name').setAttribute('aria-invalid', String(Boolean(text)));
}
function changed() {
  const user = client.user;
  return Boolean(user && $('display-name').value.trim() !== user.display_name);
}
function controls() {
  for (const control of document.querySelectorAll('button,input')) control.disabled = state.busy;
  $('save').disabled = state.busy || !changed();
  $('edit-state').textContent = changed() ? 'Unsaved changes' : 'No unsaved changes';
  for (const form of [$('login-form'), $('profile-form')]) form.setAttribute('aria-busy', String(state.busy));
}
function render() {
  const user = client.user;
  $('loading').hidden = !state.booting;
  $('signed-out').hidden = state.booting || Boolean(user);
  $('profile').hidden = state.booting || !user;
  if (user) {
    $('display-name').value = state.draft?.owner === user.id ? state.draft.value : user.display_name;
    $('email').value = user.email;
    $('signed-in-as').textContent = `Signed in as ${user.email}`;
    $('avatar').textContent = [...user.display_name.trim()][0]?.toUpperCase() || '';
  } else if (!state.booting) {
    // The in-memory draft remains owner-bound after expiration, never visible
    // in another account's form. Successful sign-out discards it explicitly.
    $('display-name').value = ''; $('email').value = '';
    $('signed-in-as').textContent = ''; $('avatar').textContent = '';
  }
  controls();
}
async function perform(label, button, action) {
  if (state.busy) return;
  state.busy = true; error(); controls();
  const previous = button?.textContent;
  if (button) button.textContent = label;
  try { await action(); }
  catch (failure) {
    message();
    error(failure.status === 401 ? 'Your session expired. Sign in again to continue. Your draft is kept for this account until you leave the page.'
      : failure.status === 403 ? 'Your session changed or this profile is unavailable. Refresh your session before trying again.' : failure.message);
    render();
    if (!client.user) state.focus = 'sign-in';
  } finally {
    state.busy = false;
    if (button) button.textContent = previous;
    controls();
    if (state.focus) { $(state.focus).focus(); state.focus = null; }
  }
}
async function recover() {
  await perform('Checking…', $('retry'), async () => {
    state.booting = true; render();
    try {
      const user = await client.recover();
      if (user && state.draft?.owner !== user.id) state.draft = null;
      message(user ? 'Session restored.' : '');
    } finally { state.booting = false; render(); }
  });
}
$('login-form').onsubmit = event => {
  event.preventDefault();
  const account = document.querySelector('input[name=user_id]:checked').value;
  perform('Signing in…', $('sign-in'), async () => {
    const user = await client.login(account);
    if (state.draft?.owner !== user.id) state.draft = null;
    fieldError(); message(`Signed in as ${user.display_name}.`); render(); state.focus = 'display-name';
  });
};
$('display-name').oninput = () => {
  const user = client.user;
  if (user) state.draft = {owner: user.id, value: $('display-name').value};
  fieldError(); message(); controls();
};
$('profile-form').onsubmit = event => {
  event.preventDefault();
  try { displayName($('display-name').value); }
  catch (failure) { fieldError(failure.message); $('display-name').focus(); return; }
  const value = $('display-name').value;
  perform('Saving…', $('save'), async () => {
    const user = await client.save(value);
    state.draft = null; fieldError(); render(); message(`Profile saved for ${user.display_name}.`);
  });
};
$('sign-out').onclick = () => perform('Signing out…', $('sign-out'), async () => {
  await client.logout(); state.draft = null; fieldError(); message('Signed out.'); render(); state.focus = 'sign-in';
});
$('retry').onclick = () => recover();
render(); recover();
