import {initAuth, authHeaders, authFailed} from './auth.mjs';
import {views, number, rowsFor, updateRequest, RequestDraft} from './dashboard-model.mjs';
const $ = id => document.getElementById(id);
const state = {snapshot: null, project: '', scope: '', view: 'active', selection: null, ready: false, generation: 0, submitting: false, loadingProjects: false};
const drafts = {update: new RequestDraft(), remember: new RequestDraft(), plan: new RequestDraft()};
const id = prefix => `${prefix}-${crypto.randomUUID()}`;
const el = (tag, content, cls) => {
  const node = document.createElement(tag);
  if (content !== undefined) node.textContent = content;
  if (cls) node.className = cls;
  return node;
};
function notice(message = '') { $('notice').textContent = message; $('notice').hidden = !message; }
function ready(value) {
  state.ready = value;
  $('update').disabled = !value || !state.snapshot?.facts.some(f => f.status === 'active');
  $('remember').disabled = !value;
  $('new-plan').disabled = !value;
  $('project').disabled = state.submitting || state.loadingProjects;
  $('scope').disabled = !value || state.submitting;
}
async function api(route, body) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), route === '/updates/natural' ? 60000 : 15000);
  try {
    const response = await fetch(route, {method: body ? 'POST' : 'GET', signal: controller.signal,
      headers: {'Content-Type': 'application/json', 'X-Retract-Client': 'dashboard', ...await authHeaders()},
      ...(body ? {body: JSON.stringify(body)} : {})});
    const data = await response.json();
    if (!response.ok) { const error = new Error(data.error || `Request failed (${response.status})`); error.status = response.status; throw error; }
    return data;
  } catch (error) {
    if (error instanceof TypeError || error.name === 'AbortError') throw new Error('No service response. Your inputs are preserved. Retry unchanged to reuse the same request IDs.');
    throw error;
  } finally { clearTimeout(timer); }
}
function option(select, value, title) { const item = el('option', title); item.value = value; select.append(item); }
function drawNav() {
  $('navigation').replaceChildren();
  for (const [key, [title]] of Object.entries(views)) {
    const button = el('button');
    button.append(el('span', title));
    const count = key === 'activity' ? state.snapshot?.activity.length : state.snapshot?.counts[key];
    if (count !== undefined) button.append(el('span', number(count), 'mono'));
    if (key === state.view) button.setAttribute('aria-current', 'page');
    button.onclick = () => { state.view = key; state.selection = null; $('search').value = ''; render(); };
    $('navigation').append(button);
  }
}
function inspect(record, kind) {
  state.selection = record.id ?? record.recorded_at;
  renderRecords();
  const box = $('inspector'); box.replaceChildren(el('p', 'Evidence inspector', 'eyebrow'));
  box.append(el('h2', kind === 'fact' ? `${record.subject} / ${record.predicate}` : kind === 'activity' ? record.route : record.id));
  if (kind === 'activity') {
    box.append(el('p', `${record.client} · HTTP ${record.status} · ${number(record.elapsed_ms)} ms`, 'mono'),
      el('p', record.recorded_at, 'muted'), el('p', 'Client labels are supplied by callers. This entry records an API request, not proof that a coding agent completed its task.', 'muted'));
    return;
  }
  box.append(el('p', `${record.id} · ${record.scope}`, 'mono muted'),
    el('p', record.status || record.outcome, `badge ${['pending', 'proposal', 'needs_review'].includes(record.status || record.outcome) ? 'warning' : ''}`));
  if (record.value || record.text) box.append(el('p', record.value || record.text));
  if (record.reason) box.append(el('p', record.reason, 'muted'));
  if (record.result?.candidate) { box.append(el('h3', 'Candidate value'), el('p', record.result.candidate.value)); }
  const edges = state.snapshot.edges.filter(edge => {
    if (kind === 'fact') return (['SUPERSEDES'].includes(edge.relationship) && [edge.from.id, edge.to.id].includes(record.id)) ||
      (['SUPPORTS', 'DEPENDS_ON', 'RETIRED', 'ACCEPTED'].includes(edge.relationship) && edge.to.id === record.id);
    if (kind === 'plan') return (edge.relationship === 'DEPENDS_ON' && edge.from.id === record.id) || (edge.relationship === 'FLAGGED' && edge.to.id === record.id) || (edge.relationship === 'REVISES' && [edge.from.id, edge.to.id].includes(record.id));
    return ['BASED_ON', 'RETIRED', 'ACCEPTED', 'FLAGGED'].includes(edge.relationship) && edge.from.id === record.id;
  });
  box.append(el('h3', 'Recorded relationships'));
  if (!edges.length) box.append(el('p', 'No relationships in this snapshot.', 'muted'));
  for (const edge of edges) {
    box.append(el('pre', `${edge.from.id}\n  └─ ${edge.relationship} → ${edge.to.id}\n${edge.to.scope ? `Scope: ${edge.to.scope}` : ''}`));
    if (edge.relationship === 'DEPENDS_ON') box.append(el('p', `${edge.to.subject} / ${edge.to.predicate}: ${edge.to.value}\n${edge.to.status}`, 'muted'));
    const source = edge.relationship === 'SUPPORTS' ? edge.from : edge.relationship === 'BASED_ON' ? edge.to : null;
    if (source) {
      const details = el('details'); details.append(el('summary', `${source.title} · ${source.authority}`), el('p', source.content)); box.append(details);
    }
  }
  if (kind === 'plan') {
    if (record.review_reason) box.append(el('h3', 'Revision reason'), el('p', record.review_reason));
    if (record.status !== 'superseded') { const revise = el('button', 'Review and revise plan'); revise.disabled = !state.ready; revise.onclick = () => openPlan(record); box.append(revise); }
    for (const path of state.snapshot.explanation_paths.filter(p => p.plan.id === record.id)) {
      box.append(el('pre', `${path.event.id} ─ FLAGGED → ${record.id}\n${path.event.id} ─ RETIRED → ${path.fact.id}\n${record.id} ─ DEPENDS_ON → ${path.fact.id}`));
      box.append(el('p', `Update scope: ${path.event.scope}\nDependency scope: ${path.fact.scope}`, 'muted'));
    }
  }
  if (kind === 'fact' && record.status === 'active') {
    const button = el('button', 'Update this fact'); button.disabled = !state.ready; button.onclick = () => openUpdate(record.id); box.append(button);
  }
}
function renderRecords() {
  const container = $('records'); container.replaceChildren();
  if (!state.snapshot) {
    $('row-count').textContent = '';
    container.append(el('p', state.project ? 'Project memory is unavailable. Use Refresh to retry.' : 'No project selected. Create a project to begin.', 'empty'));
    return;
  }
  const rows = rowsFor(state.snapshot, state.view, $('search').value);
  $('row-count').textContent = `${number(rows.length)} shown`;
  if (!rows.length) { container.append(el('p', $('search').value ? 'No matching records. Try a different search.' : state.view === 'active' ? 'No accepted facts here yet. Remember a fact with its evidence to begin.' : 'No records in this view.', 'empty')); return; }
  const kind = ['active', 'superseded'].includes(state.view) ? 'fact' : ['affected', 'plans'].includes(state.view) ? 'plan' : state.view === 'activity' ? 'activity' : 'event';
  for (const row of rows) {
    const button = el('button', undefined, 'record'); button.setAttribute('aria-pressed', String((row.id ?? row.recorded_at) === state.selection));
    const top = el('div', undefined, 'record-top');
    top.append(el('strong', kind === 'fact' ? `${row.subject} / ${row.predicate}` : kind === 'activity' ? row.route : row.id),
      el('span', String(row.outcome ?? row.status), 'badge'));
    button.append(top, el('p', row.value || row.text || `${row.client} · ${number(row.elapsed_ms)} ms`),
      el('small', `${row.scope || 'Project'} · ${row.id || row.recorded_at}`, 'mono'));
    button.onclick = () => inspect(row, kind); container.append(button);
  }
}
function render() {
  drawNav(); $('title').textContent = views[state.view][0]; $('description').textContent = views[state.view][1];
  renderRecords();
  if (!state.selection) $('inspector').replaceChildren(el('p', 'Evidence inspector', 'eyebrow'), el('h2', 'Select a record'), el('p', 'Inspect its source, status, and recorded relationships.', 'muted'));
}
async function loadSnapshot({quiet = false} = {}) {
  const generation = ++state.generation;
  ready(false); state.selection = null; state.snapshot = null; render();
  $('context').textContent = state.project ? `${$('project').selectedOptions[0]?.textContent || state.project} / ${state.scope || 'All scopes'}` : 'Workspace memory';
  if (!state.project) { state.snapshot = null; render(); $('connection').textContent = 'No project selected'; $('snapshot-meta').textContent = 'Create a project to store memory.'; return true; }
  $('connection').textContent = 'Reading storage…'; $('records').setAttribute('aria-busy', 'true');
  $('records').replaceChildren(el('p', 'Reading project memory…', 'empty'));
  try {
    const snapshot = await api('/dashboard', {project_id: state.project, scope: state.scope || null});
    if (generation !== state.generation) return false;
    state.snapshot = snapshot;
    $('scope').replaceChildren(); option($('scope'), '', 'All scopes');
    for (const scope of snapshot.scopes) option($('scope'), scope, scope);
    if (state.scope && !snapshot.scopes.includes(state.scope)) option($('scope'), state.scope, state.scope);
    $('scope').value = state.scope;
    $('context').textContent = `${snapshot.project.name} / ${state.scope || 'All scopes'}`;
    $('snapshot-meta').textContent = `Revision ${number(snapshot.project.revision)} · Read ${new Date(snapshot.observed_at).toLocaleString()} · Refresh to check for changes. Request activity is kept in this process only.`;
    const caps = Object.entries(snapshot.truncated).filter(([, value]) => value).map(([key]) => key);
    notice(caps.length ? `Snapshot limits reached: ${caps.join(', ')}. Search covers loaded records only. Narrow the scope or inspect history through the API for omitted records.` : '');
    $('connection').textContent = 'Storage connected'; ready(true); render(); return true;
  } catch (error) {
    if (generation !== state.generation) return false;
    state.snapshot = null; $('connection').textContent = 'Storage unavailable';
    $('snapshot-meta').textContent = 'No current snapshot. Writes are disabled until a successful refresh.';
    if (!quiet) notice(error.message); render(); return false;
  } finally { if (generation === state.generation) $('records').removeAttribute('aria-busy'); }
}
async function loadProjects(preferred = state.project) {
  if (state.loadingProjects) return;
  state.loadingProjects = true; $('refresh').disabled = true;
  ready(false); $('connection').textContent = 'Loading projects…';
  try {
    const result = await api('/api/projects');
    $('project').replaceChildren();
    for (const project of result.projects) option($('project'), project.id, project.name);
    if (!result.projects.length) option($('project'), '', 'No projects yet');
    state.project = result.projects.some(p => p.id === preferred) ? preferred : result.projects[0]?.id || '';
    // A newly created project might fall beyond the bounded project picker.
    if (preferred && !result.projects.some(p => p.id === preferred) && result.truncated) { option($('project'), preferred, preferred); state.project = preferred; }
    $('project').value = state.project;
    await loadSnapshot();
    if (result.truncated) notice('Showing the first 100 projects. Open other projects by their ID through the API.');
  } catch (error) {
    state.snapshot = null; state.selection = null;
    notice(error.message); $('connection').textContent = 'Service unavailable'; $('project').replaceChildren(); option($('project'), '', 'Projects unavailable');
    $('snapshot-meta').textContent = 'No current snapshot. Refresh to retry.'; render();
  } finally { state.loadingProjects = false; $('refresh').disabled = false; ready(state.ready); }
}
function show(dialog) { $(dialog).showModal(); }
function openUpdate(target) {
  if (!state.ready) return;
  $('update-form').reset(); drafts.update.clear(); $('update-error').textContent = '';
  $('target').replaceChildren();
  for (const fact of state.snapshot.facts.filter(f => f.status === 'active')) option($('target'), fact.id, `${fact.subject} / ${fact.predicate} · ${fact.scope}`);
  if (target) $('target').value = target;
  targetChanged(); modeChanged(); show('update-dialog');
}
function targetChanged() {
  const fact = state.snapshot?.facts.find(f => f.id === $('target').value && f.status === 'active');
  $('before').textContent = fact ? `Current accepted value: ${fact.value}\n${fact.id} · revision ${number(state.snapshot.project.revision)}` : 'This fact is no longer current. Close and reopen the form.';
  $('confirmation').checked = false;
}
function modeChanged() { const structured = $('mode').value === 'structured'; $('structured-fields').hidden = !structured; $('replacement').required = structured; }
function displayResult(result, before) {
  const box = $('result'); box.replaceChildren(el('h2', `Recorded: ${result.outcome || result.status || 'project created'}`));
  if (result.reason) box.append(el('p', result.reason));
  if (result.event_id) {
    box.append(el('p', `Event ${result.event_id} · revision ${number(result.resulting_revision)}`, 'mono'));
    if (result.outcome === 'applied') box.append(el('p', `Before: ${before?.value ?? result.retired_fact_ids.join(', ')}\nAfter: ${result.candidate.value}`));
    else if (result.candidate) box.append(el('p', `Accepted value: ${before?.value ?? 'Unchanged'}\nCandidate (${result.outcome}): ${result.candidate.value}`));
    box.append(el('p', `Retired: ${result.retired_fact_ids.join(', ') || 'None'}\nAccepted: ${result.accepted_fact_ids.join(', ') || 'None'}\nPlans flagged: ${result.flagged_plan_ids.join(', ') || 'None'}`, 'mono'));
  } else if (result.plan_id) box.append(el('p', `Plan ${result.plan_id} · revision ${number(result.project_revision)}`, 'mono'));
  else if (result.fact_id) box.append(el('p', `Fact ${result.fact_id} · revision ${number(result.project_revision)}`, 'mono'));
  box.hidden = false;
}
async function submit(form, errorId, action) {
  if (state.submitting) return;
  const buttons = [...form.querySelectorAll('button')]; const fields = [...form.querySelectorAll('input,select,textarea')];
  const wasDisabled = fields.map(node => node.disabled);
  state.submitting = true; $('project').disabled = true; $('scope').disabled = true;
  buttons.forEach(node => node.disabled = true); fields.forEach(node => node.disabled = true);
  const primary = form.querySelector('[type=submit]'); const label = primary.textContent; primary.textContent = 'Recording…'; $(errorId).textContent = '';
  try { await action(); }
  catch (error) { $(errorId).textContent = error.message + (error.status === 409 ? ' Refresh context and review the current decision before submitting again.' : ''); }
  finally {
    state.submitting = false; buttons.forEach(node => node.disabled = false); fields.forEach((node, i) => node.disabled = wasDisabled[i]); primary.textContent = label; ready(state.ready);
  }
}
$('update-form').onsubmit = event => {
  event.preventDefault(); if (!state.ready) { $('update-error').textContent = 'Refresh context before recording an update.'; return; }
  const fact = state.snapshot.facts.find(f => f.id === $('target').value);
  if (!fact || fact.status !== 'active') { $('update-error').textContent = 'No current target. Refresh context and select an accepted fact.'; return; }
  const draft = {mode: $('mode').value, text: $('update-text').value, title: $('update-source-title').value,
    authority: $('authority').checked, confirmation: $('confirmation').checked,
    classification: $('classification').value, value: $('replacement').value};
  const request = drafts.update.prepare([state.project, state.snapshot.project.revision, fact, draft], () => updateRequest(state.project, state.snapshot.project.revision, fact, draft, {event: id('event'), source: id('source')}));
  submit(event.currentTarget, 'update-error', async () => {
    const result = await api(request.route, request.body);
    displayResult(result, fact); $('update-dialog').close(); drafts.update.clear();
    if (!await loadSnapshot()) notice('Update recorded successfully. Refresh failed; reload the context before making another change.');
  });
};
$('remember-form').onsubmit = event => {
  event.preventDefault(); if (!state.ready) { $('remember-error').textContent = 'Refresh the project before remembering a fact.'; return; }
  const values = ['fact-scope', 'subject', 'predicate', 'fact-value', 'fact-source-title', 'fact-evidence'].map(key => $(key).value);
  const [scope, subject, predicate, value, title, content] = values;
  const body = drafts.remember.prepare([state.project, state.snapshot.project.revision, values], () => ({project_id: state.project, scope, subject, predicate, value,
    expected_revision: state.snapshot.project.revision, fact_id: id('fact'), source: {id: id('source'), kind: 'developer', title, content, authority: 'developer'}}));
  submit(event.currentTarget, 'remember-error', async () => {
    const result = await api('/remember', body); displayResult(result); $('remember-dialog').close(); drafts.remember.clear();
    if (!await loadSnapshot()) notice('Fact recorded successfully. Refresh failed; reload before making another change.');
  });
};
$('project-form').onsubmit = event => {
  event.preventDefault(); const body = {project_id: $('project-id').value, name: $('project-name').value};
  submit(event.currentTarget, 'project-error', async () => { await api('/projects', body); $('project-dialog').close(); state.scope = ''; await loadProjects(body.project_id); });
};
$('refresh-context').onclick = async () => {
  if (state.submitting) return;
  $('refresh-context').disabled = true;
  const previous = $('target').value;
  if (await loadSnapshot()) {
    drafts.update.clear(); $('confirmation').checked = false; $('target').replaceChildren();
    for (const fact of state.snapshot.facts.filter(f => f.status === 'active')) option($('target'), fact.id, `${fact.subject} / ${fact.predicate} · ${fact.scope}`);
    if (state.snapshot.facts.some(f => f.id === previous && f.status === 'active')) $('target').value = previous;
    targetChanged(); $('update-error').textContent = 'Context refreshed. Review the current value and confirm again if appropriate.';
  } else $('update-error').textContent = 'Could not refresh context. Your draft is preserved.';
  $('refresh-context').disabled = false;
};
$('project').onchange = () => { state.project = $('project').value; state.scope = ''; $('result').hidden = true; loadSnapshot(); };
$('scope').onchange = () => { state.scope = $('scope').value; $('result').hidden = true; loadSnapshot(); };
$('refresh').onclick = () => { if (!state.submitting) loadProjects(); };
$('search').oninput = renderRecords;
$('target').onchange = targetChanged; $('mode').onchange = modeChanged;
$('update').onclick = () => openUpdate();
$('remember').onclick = () => { if (!state.ready) return; $('remember-form').reset(); $('fact-scope').value = state.scope; $('remember-error').textContent = ''; drafts.remember.clear(); show('remember-dialog'); };
$('new-project').onclick = () => { if (state.submitting) return; $('project-form').reset(); $('project-error').textContent = ''; show('project-dialog'); };
for (const button of document.querySelectorAll('[data-close]')) button.onclick = () => button.closest('dialog').close();
for (const dialog of document.querySelectorAll('dialog')) dialog.addEventListener('cancel', event => { if (state.submitting) event.preventDefault(); });
let reviewingPlan = null;
function planDependencies(selected = []) {
  $('plan-dependencies').replaceChildren();
  const facts = state.snapshot.facts.filter(f => f.status === 'active');
  for (const fact of facts) {
    const label = el('label', undefined, 'check'); const input = el('input');
    input.type = 'checkbox'; input.value = fact.id; input.checked = selected.includes(fact.id);
    label.append(input, el('span', `${fact.subject} / ${fact.predicate}: ${fact.value} · ${fact.scope}`));
    $('plan-dependencies').append(label);
  }
  if (!facts.length) $('plan-dependencies').append(el('p', 'No current facts in this scope. Remember a decision first, or save a plan without dependencies.', 'muted'));
}
function openPlan(plan = null) {
  if (!state.ready) return;
  reviewingPlan = plan; drafts.plan.clear(); $('plan-form').reset(); $('plan-error').textContent = '';
  $('plan-title').textContent = plan ? 'Review and revise plan' : 'Record a plan';
  $('plan-context').textContent = plan ? `Previous version: ${plan.id}. It will be preserved with its original dependencies.` : 'Record the decisions this plan relies on.';
  $('plan-scope').value = plan?.scope || state.scope; $('plan-scope').readOnly = Boolean(plan);
  $('plan-text').value = plan?.text || ''; $('plan-review-fields').hidden = !plan;
  $('plan-reason').required = Boolean(plan); $('plan-confirmation').required = Boolean(plan);
  const selected = plan ? state.snapshot.edges.filter(e => e.relationship === 'DEPENDS_ON' && e.from.id === plan.id).map(e => e.to.id) : [];
  planDependencies(selected); show('plan-dialog');
}
$('new-plan').onclick = () => openPlan();
$('plan-refresh').onclick = async () => {
  if (state.submitting) return;
  const selected = [...$('plan-dependencies').querySelectorAll('input:checked')].map(i => i.value);
  if (await loadSnapshot()) { drafts.plan.clear(); planDependencies(selected); $('plan-confirmation').checked = false; $('plan-error').textContent = 'Decisions refreshed. Review the selection and confirm again.'; }
  else $('plan-error').textContent = 'Could not refresh. Your plan text is preserved.';
};
$('plan-form').onsubmit = event => {
  event.preventDefault(); if (!state.ready) { $('plan-error').textContent = 'Refresh decisions before saving this plan.'; return; }
  const ids = [...$('plan-dependencies').querySelectorAll('input:checked')].map(i => i.value);
  if (ids.length > 32) { $('plan-error').textContent = 'Choose at most 32 dependencies.'; return; }
  const draft = {text: $('plan-text').value, dependency_fact_ids: ids, expected_revision: state.snapshot.project.revision, project_id: state.project};
  const signature = [draft, reviewingPlan?.id, $('plan-scope').value, $('plan-reason').value, $('plan-confirmation').checked];
  const request = drafts.plan.prepare(signature, () => reviewingPlan
    ? {route: '/plans/revise', body: {...draft, plan_id: reviewingPlan.id, replacement_plan_id: id('plan'), reason: $('plan-reason').value, confirmation: $('plan-confirmation').checked}}
    : {route: '/plans', body: {...draft, scope: $('plan-scope').value, plan_id: id('plan')}});
  submit(event.currentTarget, 'plan-error', async () => {
    const result = await api(request.route, request.body); displayResult(result); $('plan-dialog').close(); drafts.plan.clear();
    state.view = 'plans'; if (!await loadSnapshot()) notice('Plan saved. Refresh to see the current state.');
  });
};
$('access-keys').onclick = async () => {
  $('key-error').textContent = ''; $('key-secret').value = ''; $('key-created').hidden = true;
  show('keys-dialog'); await loadKeys();
};
async function loadKeys() {
  $('key-list').replaceChildren(el('p', 'Loading access keys…'));
  try {
    const result = await api('/api/keys'); $('key-list').replaceChildren();
    if (!result.keys.length) $('key-list').append(el('p', 'No access keys yet. Create one to connect your coding client.', 'muted'));
    for (const key of result.keys) {
      const row = el('div', undefined, 'key-row');
      row.append(el('span', `${key.name} · expires ${new Date(key.expires_at * 1000).toLocaleDateString()}`));
      const revoke = el('button', 'Revoke'); revoke.type = 'button'; revoke.setAttribute('aria-label', `Revoke ${key.name}`);
      revoke.onclick = async () => { revoke.disabled = true; try { await api('/account/keys/revoke', {id: key.id}); await loadKeys(); } catch (e) { $('key-error').textContent = e.message; revoke.disabled = false; } };
      row.append(revoke); $('key-list').append(row);
    }
  } catch (error) { $('key-list').replaceChildren(); $('key-error').textContent = error.message; }
}
$('key-form').onsubmit = event => {
  event.preventDefault(); submit(event.currentTarget, 'key-error', async () => {
    const result = await api('/account/keys', {name: $('key-name').value});
    $('key-secret').value = result.token; $('key-created').hidden = false; $('key-name').value = '';
    await loadKeys(); $('key-secret').focus(); $('key-secret').select();
  });
};
$('keys-dialog').addEventListener('close', () => { $('key-secret').value = ''; $('key-created').hidden = true; });
$('key-copy').onclick = async () => {
  try { await navigator.clipboard.writeText($('key-secret').value); $('key-copy').textContent = 'Copied'; }
  catch { $('key-error').textContent = 'Select the access key and copy it manually.'; }
};
render(); initAuth().then(() => loadProjects()).catch(authFailed);
