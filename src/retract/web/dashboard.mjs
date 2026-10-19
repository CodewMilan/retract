import {initAuth, authHeaders, authFailed, authConfig} from './auth.mjs';
import {paintWait, holdControl} from './loader.mjs';
import {clients, serverConfig, cursorInstallLink, installCommand} from './agent-connect.mjs';
import {views, number, rowsFor, updateRequest, RequestDraft, statusLabel} from './dashboard-model.mjs';
const $ = id => document.getElementById(id);
const initial = new URLSearchParams(location.search);
const state = {snapshot: null, project: initial.get('project') || '', scope: initial.get('area') || '',
  view: Object.hasOwn(views, initial.get('view')) ? initial.get('view') : 'active', selection: null,
  ready: false, generation: 0, submitting: false, loadingProjects: false, loadingSnapshot: false, projectsError: false, searches: {}};
state.searches[state.view] = initial.get('q') || '';
const drafts = {update: new RequestDraft(), remember: new RequestDraft(), plan: new RequestDraft()};
let memoryContext = '';
const id = prefix => `${prefix}-${crypto.randomUUID()}`;
const el = (tag, content, cls) => {
  const node = document.createElement(tag);
  if (content !== undefined) node.textContent = content;
  if (cls) node.className = cls;
  return node;
};
const paths = {active: 'M4 4h16v16H4z M8 8h8 M8 12h8 M8 16h5', plans: 'M5 4h14v17H5z M9 2h6v4H9z M9 11h6 M9 15h4',
  affected: 'M12 3 2 21h20L12 3z M12 9v5 M12 17h.01', handoffs: 'M4 7h15 M15 3l4 4-4 4 M20 17H5 M9 13l-4 4 4 4',
  history: 'M4 4v6h6 M4 10a8 8 0 1 1 1 8 M12 8v5l3 2', memory: 'M5 4h14v16H5z M8 8h8 M8 12h8 M8 16h4'};
function icon(key) {
  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  for (const [name, value] of Object.entries({viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', 'stroke-width': '1.7', 'stroke-linecap': 'round', 'stroke-linejoin': 'round', 'aria-hidden': 'true'})) svg.setAttribute(name, value);
  const path = document.createElementNS(svg.namespaceURI, 'path'); path.setAttribute('d', paths[key] || paths.history); svg.append(path); return svg;
}
function action(label, fn, cls = 'secondary') { const button = el('button', label, cls); button.type = 'button'; button.onclick = fn; return button; }
function notice(message = '') { $('notice').textContent = message; $('notice').hidden = !message; }
function ready(value) {
  state.ready = value;
  $('update').disabled = !value || !state.snapshot?.facts.some(f => f.status === 'active');
  $('remember').disabled = !value; $('new-plan').disabled = !value;
  for (const button of document.querySelectorAll('[data-action="remember"]')) button.disabled = !value;
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
    if (error instanceof TypeError || error.name === 'AbortError') throw new Error('Could not reach Retract. Check your connection and try again. Your input is preserved.');
    throw error;
  } finally { clearTimeout(timer); }
}
function option(select, value, title) { const item = el('option', title); item.value = value; select.append(item); }
function syncLocation(push = false) {
  const url = new URL(location.href);
  for (const [key, value] of Object.entries({project: state.project, area: state.scope, view: state.view === 'active' ? '' : state.view, q: $('search').value})) {
    if (value) url.searchParams.set(key, value); else url.searchParams.delete(key);
  }
  if (url.href !== location.href) history[push ? 'pushState' : 'replaceState'](null, '', url);
}
function setView(key, {push = true, focus = true} = {}) {
  state.searches[state.view] = $('search').value;
  closeInspector(false); state.view = key; $('search').value = state.searches[key] || '';
  menu(false); render(); syncLocation(push);
  if (focus) $('title').focus({preventScroll: true});
}
function drawNav() {
  const nav = $('navigation'); const expanded = nav.querySelector('details')?.open;
  nav.replaceChildren();
  const add = (key, parent) => {
    const button = el('button', undefined, 'nav-item'); button.dataset.view = key;
    button.append(icon(key), el('span', views[key][0], 'nav-label'));
    const count = state.snapshot?.counts[key];
    if (count > 0 && ['active', 'affected', 'handoffs'].includes(key)) button.append(el('span', number(count), key === 'affected' ? 'nav-count attention' : 'nav-count'));
    if (key === state.view) button.setAttribute('aria-current', 'page');
    button.onclick = () => setView(key); parent.append(button);
  };
  for (const key of ['active', 'plans', 'affected', 'handoffs']) add(key, nav);
  const history = el('details', undefined, 'history-nav'); history.id = 'history-nav';
  const summary = el('summary'); summary.append(icon('history'), el('span', 'History & activity')); history.append(summary);
  history.open = ['superseded', 'pending', 'updates', 'activity'].includes(state.view) || Boolean(expanded);
  for (const key of ['pending', 'updates', 'superseded', 'activity']) add(key, history);
  nav.append(history);
}
const compact = matchMedia('(max-width: 1100px)');
const mobile = matchMedia('(max-width: 760px)');
function menu(open) {
  const visible = mobile.matches && open;
  document.querySelector('.shell').classList.toggle('menu-open', visible);
  $('menu-toggle').setAttribute('aria-expanded', String(visible)); $('menu-overlay').hidden = !visible;
  $('content').inert = visible;
}
function closeInspector(restoreFocus = true) {
  const selection = state.selection; state.selection = null;
  $('inspector').hidden = true; document.querySelector('.workspace').classList.remove('has-selection');
  if ($('record-dialog').open) $('record-dialog').close();
  if (restoreFocus) queueMicrotask(() => [...document.querySelectorAll('.record')].find(node => node.dataset.recordId === selection)?.focus({preventScroll: true}));
}
function placeInspector() {
  const box = $('inspector');
  if (compact.matches) {
    $('record-dialog').append(box);
    if (state.selection && !$('record-dialog').open) $('record-dialog').showModal();
  } else {
    if ($('record-dialog').open) { $('record-dialog').dataset.relocating = 'true'; $('record-dialog').close(); }
    document.querySelector('.workspace').append(box);
  }
}
function technicalDetails(record, edges = [], extra = '') {
  const details = el('details', undefined, 'technical-details'); details.append(el('summary', 'Technical details'));
  details.append(el('p', `${record.id || record.recorded_at}${record.scope ? ` · ${record.scope}` : ''}`, 'mono muted'));
  for (const edge of edges) details.append(el('pre', `${edge.from.id}\n  └─ ${edge.relationship} → ${edge.to.id}`));
  if (extra) details.append(el('pre', extra));
  return details;
}
function inspect(record, kind) {
  state.selection = record.id ?? record.recorded_at; renderRecords();
  const box = $('inspector'); box.hidden = false; box.replaceChildren();
  document.querySelector('.workspace').classList.add('has-selection');
  const head = el('div', undefined, 'dialog-head'); head.append(el('p', kind === 'fact' ? 'Saved decision' : kind === 'plan' ? 'Plan details' : kind === 'handoff' ? 'Agent handoff' : 'Details', 'eyebrow'));
  const close = action('×', () => { closeInspector(); renderRecords(); }, 'icon-button'); close.setAttribute('aria-label', 'Close details'); head.append(close); box.append(head);
  box.append(el('h2', kind === 'fact' ? record.subject : kind === 'activity' ? record.route : kind === 'plan' ? 'Implementation plan' : kind === 'handoff' ? `${record.from_agent} → ${record.to_agent || 'Any agent'}` : 'Decision update'));
  box.append(el('p', statusLabel(record.status || record.outcome), `badge ${['pending', 'proposal', 'needs_review'].includes(record.status || record.outcome) ? 'warning' : ''}`));
  if (kind === 'handoff') {
    box.append(el('p', record.note, 'detail-value'), el('h3', 'Is this context still current?'));
    if (!(record.warnings || []).length) box.append(el('p', 'The plan and its cited decisions are unchanged.', 'muted'));
    for (const warning of record.warnings || []) box.append(el('p', warning, 'before'));
    box.append(el('p', record.claimed_by ? `Claimed by ${record.claimed_by}` : `Waiting for ${record.to_agent || 'an agent'} to pick this up.`, 'muted'),
      technicalDetails(record, [], `${record.from_agent}\n  └─ HANDED_OFF → ${record.id}\n${record.id}\n  └─ CONCERNS → ${record.plan_id}` + (record.cited_facts || []).map(f => `\n  └─ CITES → ${f.fact_id}${f.changed ? ' (replaced)' : ''}`).join('')));
  } else if (kind === 'activity') {
    box.append(el('p', `${record.client} · HTTP ${record.status} · ${number(record.elapsed_ms)} ms`),
      el('p', new Date(record.recorded_at).toLocaleString(), 'muted'), el('p', 'This records a client request, not whether the agent completed its work.', 'hint'));
  } else {
    if (record.value || record.text) box.append(el('p', record.value || record.text, 'detail-value'));
    if (record.reason) box.append(el('p', record.reason, 'muted'));
    if (record.result?.candidate) box.append(el('h3', 'Proposed decision'), el('p', record.result.candidate.value));
    const edges = state.snapshot.edges.filter(edge => {
      if (kind === 'fact') return (edge.relationship === 'SUPERSEDES' && [edge.from.id, edge.to.id].includes(record.id)) ||
        (['SUPPORTS', 'DEPENDS_ON', 'RETIRED', 'ACCEPTED'].includes(edge.relationship) && edge.to.id === record.id);
      if (kind === 'plan') return (edge.relationship === 'DEPENDS_ON' && edge.from.id === record.id) || (edge.relationship === 'FLAGGED' && edge.to.id === record.id) || (edge.relationship === 'REVISES' && [edge.from.id, edge.to.id].includes(record.id));
      return ['BASED_ON', 'RETIRED', 'ACCEPTED', 'FLAGGED'].includes(edge.relationship) && edge.from.id === record.id;
    });
    const sources = edges.flatMap(edge => edge.relationship === 'SUPPORTS' ? [edge.from] : edge.relationship === 'BASED_ON' ? [edge.to] : []);
    if (sources.length) {
      box.append(el('h3', 'Source & context'));
      for (const source of sources) {
        const details = el('details', undefined, 'source-details'); details.append(el('summary', source.title), el('p', source.content));
        details.append(el('p', ['developer', 'approved_document'].includes(source.authority) ? 'Approved source' : 'Unverified source', 'hint')); box.append(details);
      }
    }
    if (kind === 'plan') {
      const dependencies = edges.filter(e => e.relationship === 'DEPENDS_ON');
      box.append(el('h3', 'Decisions this relies on'));
      if (!dependencies.length) box.append(el('p', 'No decisions linked to this plan.', 'muted'));
      for (const edge of dependencies) {
        const item = el('div', undefined, 'dependency'); item.append(el('strong', edge.to.subject), el('p', edge.to.value), el('span', statusLabel(edge.to.status), `badge ${edge.to.status === 'superseded' ? 'warning' : ''}`)); box.append(item);
      }
      if (record.review_reason) box.append(el('h3', 'Why this plan was revised'), el('p', record.review_reason));
      if (record.status !== 'superseded') { const revise = action('Review and revise plan', () => openPlan(record), 'primary'); revise.disabled = !state.ready; box.append(revise); }
    }
    if (kind === 'fact') {
      const plans = edges.filter(e => e.relationship === 'DEPENDS_ON');
      if (plans.length) {
        box.append(el('h3', 'Used by these plans'));
        for (const edge of plans) box.append(action(edge.from.text || edge.from.id, () => { setView('plans', {focus: false}); inspect(edge.from, 'plan'); }, 'linked-record'));
      }
      if (record.status === 'active') { const update = action('Update this decision', () => openUpdate(record.id), 'primary'); update.disabled = !state.ready; box.append(update); }
    }
    const explanation = (state.snapshot.explanation_paths || []).filter(p => p.plan.id === record.id).map(p => `${p.event.id} ─ FLAGGED → ${record.id}\n${p.event.id} ─ RETIRED → ${p.fact.id}\n${record.id} ─ DEPENDS_ON → ${p.fact.id}`).join('\n\n');
    box.append(technicalDetails(record, edges, explanation));
  }
  placeInspector();
  if (compact.matches) close.focus();
}
function emptyState(title, description, button) {
  const box = el('div', undefined, 'empty'); box.append(icon('memory'), el('h2', title), el('p', description, 'muted')); if (button) box.append(button); return box;
}
function waitState(label) {
  const box = el('div', undefined, 'list-wait');
  paintWait(box, {label});
  return box;
}
function renderRecords() {
  const container = $('records'); container.replaceChildren();
  const search = $('search').value; $('clear-search').hidden = !search;
  const onboarding = state.snapshot && !state.snapshot.facts.length && state.view === 'active' && !search;
  $('start-guide').hidden = !onboarding;
  document.querySelector('.workspace').hidden = Boolean(onboarding);
  $('toolbar').hidden = !state.snapshot; document.querySelector('.list-heading').hidden = !state.snapshot;
  if (!state.snapshot) {
    $('row-count').textContent = '';
    if (state.loadingSnapshot || state.loadingProjects) container.append(waitState(state.loadingSnapshot ? 'Reading project memory…' : 'Loading projects…'));
    else container.append(state.project || state.projectsError
      ? emptyState('Your memory could not load', 'Check your connection, then try again.', action('Try again', () => loadProjects(), 'primary'))
      : emptyState('Give your agents a place to remember', 'Create a project to keep decisions, sources, and plans together.', action('Create your first project', () => $('new-project').click(), 'primary')));
    return;
  }
  const rows = rowsFor(state.snapshot, state.view, search);
  $('row-count').textContent = `${number(rows.length)} ${search ? 'matching' : 'saved'}`;
  $('list-label').textContent = state.view === 'active' ? 'Saved decisions' : views[state.view][0];
  if (!rows.length) {
    const messages = {active: ['No memory in this area yet', 'Save a decision or choose another project area.'], plans: ['No plans yet', 'Save a plan and link the decisions it relies on.'], affected: ['Your plans are up to date', 'Plans appear here when a decision they rely on changes.'], handoffs: ['No handoffs yet', 'When an agent passes work to another agent, its context and next steps appear here.'], pending: ['No suggestions to review', 'Proposed changes appear here. Your approved decisions stay in Memory.'], superseded: ['No previous decisions yet', 'When a decision is replaced, its original source and history stay here.'], updates: ['No changes yet', 'Updates to your project decisions will appear here.'], activity: ['No recent requests', 'Connect an agent to start using your project memory.']};
    const [title, description] = search ? ['No matching results', 'Try a different search, or clear it to see everything in this area.'] : messages[state.view];
    container.append(emptyState(title, description, search ? action('Clear search', clearSearch) : state.view === 'plans' ? action('Create a plan', () => openPlan(), 'primary') : null)); return;
  }
  const kind = ['active', 'superseded'].includes(state.view) ? 'fact' : ['affected', 'plans'].includes(state.view) ? 'plan' : state.view === 'activity' ? 'activity' : state.view === 'handoffs' ? 'handoff' : 'event';
  for (const row of rows) {
    const button = el('button', undefined, 'record'); button.dataset.recordId = row.id ?? row.recorded_at;
    button.setAttribute('aria-pressed', String(button.dataset.recordId === state.selection));
    const top = el('div', undefined, 'record-top');
    const title = kind === 'fact' ? `${row.subject}${row.predicate && row.predicate !== 'decision' ? ` / ${row.predicate}` : ''}` : kind === 'activity' ? row.route : kind === 'handoff' ? `${row.from_agent} → ${row.to_agent || 'Any agent'}` : kind === 'plan' ? (row.text || 'Implementation plan') : (row.text || 'Decision update');
    const status = row.outcome ?? row.status;
    top.append(el('strong', title), el('span', statusLabel(status), `badge ${['needs_review', 'pending', 'proposal'].includes(status) ? 'warning' : ''}`));
    const summary = kind === 'handoff' ? row.note : kind === 'plan' ? '' : row.value || (kind === 'event' ? row.reason : '') || [row.client, `${number(row.elapsed_ms)} ms`].filter(Boolean).join(' · ');
    button.append(top); if (summary) button.append(el('p', summary));
    button.append(el('small', `${row.scope || 'Project'}${kind === 'handoff' && row.stale ? ' · Context changed' : ''}`, 'record-meta'));
    button.onclick = () => inspect(row, kind); container.append(button);
  }
}
function render() {
  drawNav(); $('title').textContent = views[state.view][0]; $('description').textContent = views[state.view][1];
  $('search').placeholder = `Search ${views[state.view][0].toLowerCase()}…`;
  const plans = ['plans', 'affected'].includes(state.view);
  $('new-plan').className = plans ? 'primary' : 'secondary'; $('remember').className = plans ? 'secondary' : 'primary';
  $('memory-actions').hidden = !['active', 'superseded'].includes(state.view);
  const count = state.snapshot?.counts.affected || 0; const banner = $('review-banner');
  banner.hidden = !count || state.view === 'affected'; banner.replaceChildren();
  if (count) { const text = el('div'); text.append(el('strong', `${number(count)} ${count === 1 ? 'plan needs' : 'plans need'} a second look`), el('p', 'A decision changed since this work was planned.')); banner.append(icon('affected'), text, action('Review plans', () => setView('affected'))); }
  renderRecords();
  if (!state.selection) closeInspector(false);
}
function clearSearch() { $('search').value = ''; state.searches[state.view] = ''; renderRecords(); syncLocation(); $('search').focus(); }

async function loadSnapshot({quiet = false} = {}) {
  const generation = ++state.generation;
  closeInspector(false); state.loadingSnapshot = Boolean(state.project);
  ready(false); state.snapshot = null; render();
  $('context').textContent = state.project ? `${$('project').selectedOptions[0]?.textContent || state.project} / ${state.scope || 'All areas'}` : 'Your workspace';
  if (!state.project) { state.snapshot = null; render(); $('connection').textContent = 'No project selected'; $('snapshot-meta').textContent = 'Create a project to store memory.'; return true; }
  $('connection').textContent = 'Reading storage…'; $('records').setAttribute('aria-busy', 'true');
  try {
    const snapshot = await api('/dashboard', {project_id: state.project, scope: state.scope || null});
    if (generation !== state.generation) return false;
    state.snapshot = snapshot; state.loadingSnapshot = false;
    $('scope').replaceChildren(); option($('scope'), '', 'All areas');
    for (const scope of snapshot.scopes) option($('scope'), scope, scope);
    if (state.scope && !snapshot.scopes.includes(state.scope)) option($('scope'), state.scope, state.scope);
    $('scope').value = state.scope;
    $('context').textContent = snapshot.project.name;
    $('snapshot-meta').textContent = `Last refreshed ${new Date(snapshot.observed_at).toLocaleTimeString([], {hour: 'numeric', minute: '2-digit'})} · Revision ${number(snapshot.project.revision)}`;
    const caps = Object.entries(snapshot.truncated).filter(([, value]) => value).map(([key]) => key);
    notice(caps.length ? `Snapshot limits reached: ${caps.join(', ')}. Search covers loaded records only. Narrow the scope or inspect history through the API for omitted records.` : '');
    $('connection').textContent = 'Storage connected'; ready(true); render(); syncLocation(); return true;
  } catch (error) {
    if (generation !== state.generation) return false;
    state.snapshot = null; state.loadingSnapshot = false; $('connection').textContent = 'Storage unavailable';
    $('snapshot-meta').textContent = 'No current snapshot. Writes are disabled until a successful refresh.';
    if (!quiet) notice(error.message); render(); return false;
  } finally { if (generation === state.generation) $('records').removeAttribute('aria-busy'); }
}
async function loadProjects(preferred = state.project) {
  if (state.loadingProjects) return;
  state.loadingProjects = true; $('refresh').disabled = true;
  state.projectsError = false;
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
    state.projectsError = true;
    notice(error.message); $('connection').textContent = 'Service unavailable'; $('project').replaceChildren(); option($('project'), '', 'Projects unavailable');
    $('snapshot-meta').textContent = 'No current snapshot. Refresh to retry.'; render();
  } finally { state.loadingProjects = false; $('refresh').disabled = false; ready(state.ready); render(); }
}
function show(dialog) {
  if ($('record-dialog').open) $('record-dialog').close();
  menu(false); $(dialog).showModal();
}
function openUpdate(target) {
  if (!state.ready) return;
  $('update-form').reset(); drafts.update.clear(); $('update-error').textContent = '';
  for (const details of $('update-form').querySelectorAll('details')) details.open = false;
  $('target').replaceChildren();
  for (const fact of state.snapshot.facts.filter(f => f.status === 'active')) option($('target'), fact.id, `${fact.subject} / ${fact.predicate} · ${fact.scope}`);
  if (target) $('target').value = target;
  targetChanged(); modeChanged(); show('update-dialog');
}
function targetChanged() {
  const fact = state.snapshot?.facts.find(f => f.id === $('target').value && f.status === 'active');
  $('before').textContent = fact ? `Current decision\n${fact.value}` : 'This decision has changed. Refresh context to load the latest version.';
  $('confirmation').checked = false;
}
function updateIntent() {
  const suggestion = $('mode').value === 'structured' && $('classification').value !== 'confirmed_change';
  $('update-form').querySelector('.confirm-group').hidden = suggestion;
  $('suggestion-note').hidden = !suggestion;
  if (suggestion) { $('authority').checked = false; $('confirmation').checked = false; }
}
function modeChanged() { const structured = $('mode').value === 'structured'; $('structured-fields').hidden = !structured; $('replacement').required = structured; updateIntent(); }
function displayResult(result, before) {
  const box = $('result'); box.replaceChildren();
  const head = el('div', undefined, 'dialog-head');
  head.append(el('h2', result.fact_id ? 'Memory saved' : result.plan_id ? 'Plan saved' : result.outcome === 'applied' ? 'Decision updated' : 'Update saved'));
  const dismiss = action('×', () => { box.hidden = true; }, 'icon-button'); dismiss.setAttribute('aria-label', 'Dismiss confirmation'); head.append(dismiss); box.append(head);
  if (result.event_id) {
    if (result.outcome === 'applied') box.append(el('p', `Before: ${before?.value ?? result.retired_fact_ids.join(', ')}\nAfter: ${result.candidate.value}`));
    else box.append(el('p', 'Your current memory is unchanged. The update and its source have been saved.'), ...(result.reason ? [el('p', result.reason, 'hint')] : []));
    if (result.flagged_plan_ids?.length) box.append(action(`Review ${number(result.flagged_plan_ids.length)} affected ${result.flagged_plan_ids.length === 1 ? 'plan' : 'plans'}`, () => setView('affected')));
  } else box.append(el('p', result.fact_id ? 'Your agents can now recall this decision and its source.' : 'If a linked decision changes, this plan will appear in Needs review.'));
  box.hidden = false;
}
async function submit(form, errorId, action, primary = form.querySelector('[type=submit]')) {
  if (state.submitting) return;
  const buttons = [...new Set([...form.querySelectorAll('button'), ...form.closest('dialog').querySelectorAll('[data-close]')])]; const fields = [...form.querySelectorAll('input,select,textarea')];
  const wasDisabled = fields.map(node => node.disabled);
  state.submitting = true; $('project').disabled = true; $('scope').disabled = true;
  buttons.forEach(node => node.disabled = true); fields.forEach(node => node.disabled = true);
  const release = holdControl(primary, errorId === 'key-error' ? 'Preparing…' : 'Saving…'); form.setAttribute('aria-busy', 'true'); $(errorId).textContent = '';
  try { await action(); }
  catch (error) {
    const conflict = errorId === 'key-error' ? '' : errorId === 'project-error' ? ' Choose a different project name or identifier.' : ' Refresh context and review the latest decision before trying again.';
    if (errorId === 'key-error' && error.status === 409) $('key-management').open = true;
    $(errorId).textContent = error.message + (error.status === 409 ? conflict : ''); $(errorId).focus();
  }
  finally {
    state.submitting = false; form.removeAttribute('aria-busy'); buttons.forEach(node => node.disabled = false); fields.forEach((node, i) => node.disabled = wasDisabled[i]); release(); ready(state.ready);
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
    const result = await api('/remember', body); displayResult(result); $('remember-dialog').close(); drafts.remember.clear(); memoryContext = '';
    state.view = 'active'; $('search').value = ''; state.searches.active = '';
    if (state.scope && state.scope !== scope) state.scope = scope;
    if (!await loadSnapshot()) notice('Fact recorded successfully. Refresh failed; reload before making another change.');
  });
};
$('project-form').onsubmit = event => {
  event.preventDefault(); const body = {project_id: $('project-id').value, name: $('project-name').value};
  submit(event.currentTarget, 'project-error', async () => {
    await api('/projects', body); $('project-dialog').close(); state.scope = ''; state.view = 'active'; state.searches = {}; $('search').value = '';
    await loadProjects(body.project_id);
  });
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
$('project').onchange = () => { state.project = $('project').value; state.scope = ''; state.searches = {}; $('search').value = ''; $('result').hidden = true; syncLocation(true); menu(false); loadSnapshot(); };
$('scope').onchange = () => { state.scope = $('scope').value; $('result').hidden = true; syncLocation(true); loadSnapshot(); };
$('refresh').onclick = () => { if (!state.submitting) loadProjects(); };
$('search').oninput = () => { state.searches[state.view] = $('search').value; closeInspector(false); renderRecords(); syncLocation(); };
$('clear-search').onclick = clearSearch;
$('target').onchange = targetChanged; $('mode').onchange = modeChanged;
$('classification').onchange = updateIntent;
$('update').onclick = () => { $('memory-actions').open = false; openUpdate(); };
$('remember').onclick = () => {
  if (!state.ready) return;
  const context = JSON.stringify([state.project, state.scope]);
  if (memoryContext !== context) {
    $('remember-form').reset(); $('fact-scope').value = state.scope || 'project/main'; $('remember-error').textContent = '';
    for (const details of $('remember-form').querySelectorAll('details')) details.open = false;
    drafts.remember.clear(); memoryContext = context;
  }
  show('remember-dialog');
};
let customProjectId = false;
$('new-project').onclick = () => { if (state.submitting) return; $('project-form').reset(); customProjectId = false; $('project-form').querySelector('details').open = false; $('project-error').textContent = ''; show('project-dialog'); };
$('project-id').oninput = () => { customProjectId = Boolean($('project-id').value); };
$('project-name').oninput = () => {
  if (!customProjectId) $('project-id').value = $('project-name').value.trim().normalize('NFKD').replace(/[\u0300-\u036f]/g, '').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '').slice(0, 160) || ($('project-name').value.trim() ? `project-${crypto.randomUUID().slice(0, 8)}` : '');
};
for (const button of document.querySelectorAll('[data-close]')) button.onclick = () => { if (!state.submitting) button.closest('dialog').close(); };
for (const dialog of document.querySelectorAll('dialog')) dialog.addEventListener('cancel', event => { if (state.submitting) event.preventDefault(); });
let reviewingPlan = null;
function planDependencies(selected = []) {
  $('plan-dependencies').replaceChildren();
  const candidates = [...state.snapshot.facts, ...state.snapshot.edges.flatMap(edge => [edge.from, edge.to])];
  const facts = [...new Map(candidates.filter(f => f.status === 'active' && f.subject && f.predicate && f.value).map(f => [f.id, f])).values()];
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
  $('plan-title').textContent = plan ? 'Review and revise plan' : 'New plan';
  $('plan-context').textContent = plan ? 'Review the latest decisions below and adjust the plan. The previous version stays in your history.' : 'Link the decisions this work depends on. If one changes, this plan will be flagged for review.';
  $('plan-form').querySelector('details').open = false;
  $('plan-scope').value = plan?.scope || state.scope || 'project/main'; $('plan-scope').readOnly = Boolean(plan);
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
    state.searches[state.view] = $('search').value; state.view = 'plans'; $('search').value = ''; state.searches.plans = '';
    if (state.scope && state.scope !== $('plan-scope').value) state.scope = $('plan-scope').value;
    if (!await loadSnapshot()) notice('Plan saved. Refresh to see the current state.');
  });
};
const connections = new Map();
let selectedClient = '';
let keysGeneration = 0;
function clearConnectionSetup() {
  selectedClient = ''; $('client-setup').hidden = true; $('cursor-install').hidden = true;
  $('cursor-install').removeAttribute('href'); $('command-setup').hidden = true;
  $('install-command').textContent = ''; $('connect-status').textContent = '';
  for (const button of $('key-form').querySelectorAll('[name=client]')) button.setAttribute('aria-pressed', 'false');
}
function showConnectionSetup(client, token) {
  selectedClient = client;
  const config = serverConfig(authConfig().origin || location.origin, token);
  $('client-setup').hidden = false;
  $('client-setup-title').textContent = client === 'cursor' ? 'Finish in Cursor' : `Add Retract to ${clients[client].name}`;
  $('client-instructions').textContent = client === 'cursor'
    ? 'Open Cursor and approve adding Retract. Your connection details are filled in for you.'
    : `Copy this command and run it once to add Retract to ${clients[client].name}.`;
  $('cursor-install').hidden = client !== 'cursor'; $('command-setup').hidden = client === 'cursor';
  $('cursor-install').removeAttribute('href'); $('install-command').textContent = ''; $('connect-status').textContent = '';
  if (client === 'cursor') $('cursor-install').href = cursorInstallLink(config);
  else $('install-command').textContent = installCommand(client, config);
  $('install-copy').textContent = 'Copy command';
  for (const button of $('key-form').querySelectorAll('[name=client]')) button.setAttribute('aria-pressed', String(button.value === client));
  if (client === 'cursor') $('cursor-install').focus(); else $('client-setup-title').focus();
}
$('access-keys').onclick = async () => {
  $('key-error').textContent = ''; clearConnectionSetup();
  const local = authConfig().mode === 'local';
  $('key-management').hidden = local; $('key-management').open = false;
  $('connection-note').textContent = local ? 'Connect on this computer, and keep your local Retract server running.' : 'We create a private, revocable access key for each agent you choose.';
  $('agent-prompt').textContent = state.project ? `Recall the current decisions for project "${state.project}"${state.scope ? ` in area "${state.scope}"` : ''} before you plan the work.` : 'List my Retract projects, then recall the current decisions before planning the work.';
  show('keys-dialog'); if (!local) await loadKeys();
};
$('key-form').onsubmit = event => {
  event.preventDefault(); if (state.submitting) return;
  const button = event.submitter; const client = button?.value;
  if (!Object.hasOwn(clients, client)) return;
  $('key-error').textContent = '';
  if (authConfig().mode === 'local' || connections.has(client)) { showConnectionSetup(client, connections.get(client)?.token); return; }
  submit(event.currentTarget, 'key-error', async () => {
    const result = await api('/account/keys', {name: clients[client].name});
    if (!result.id || !result.token) throw new Error('The access key could not be prepared. Try connecting again.');
    connections.set(client, result); showConnectionSetup(client, result.token); await loadKeys();
  }, button);
};
async function loadKeys() {
  const generation = ++keysGeneration;
  $('key-list').replaceChildren(); paintWait($('key-list'), {label: 'Loading access keys…'});
  try {
    const result = await api('/api/keys'); if (generation !== keysGeneration) return; $('key-list').replaceChildren();
    if (!result.keys.length) $('key-list').append(el('p', 'No access keys yet. Create one to connect your coding client.', 'muted'));
    for (const key of result.keys) {
      const row = el('div', undefined, 'key-row');
      row.append(el('span', `${key.name} · expires ${new Date(key.expires_at * 1000).toLocaleDateString()}`));
      const revoke = el('button', 'Revoke'); revoke.type = 'button'; revoke.setAttribute('aria-label', `Revoke ${key.name}`);
      revoke.onclick = async () => {
        if (!revoke.dataset.confirming) {
          revoke.dataset.confirming = 'true'; revoke.textContent = 'Confirm revoke'; revoke.setAttribute('aria-label', `Confirm revocation of ${key.name}`);
          const cancel = action('Cancel', () => { delete revoke.dataset.confirming; revoke.textContent = 'Revoke'; revoke.setAttribute('aria-label', `Revoke ${key.name}`); cancel.remove(); revoke.focus(); });
          row.append(cancel); return;
        }
        revoke.disabled = true;
        try {
          await api('/account/keys/revoke', {id: key.id});
          for (const [client, connection] of connections) if (connection.id === key.id) { connections.delete(client); if (selectedClient === client) clearConnectionSetup(); }
          await loadKeys();
        }
        catch (e) { $('key-error').textContent = e.message; revoke.disabled = false; }
      };
      row.append(revoke); $('key-list').append(row);
    }
  } catch (error) { if (generation === keysGeneration) { $('key-list').replaceChildren(); $('key-error').textContent = error.message; } }
}
$('keys-dialog').addEventListener('close', () => { connections.clear(); ++keysGeneration; clearConnectionSetup(); });
$('install-copy').onclick = async () => {
  try { await navigator.clipboard.writeText($('install-command').textContent); $('install-copy').textContent = 'Copied'; $('connect-status').textContent = 'Command copied. Paste it into your terminal to finish setup.'; }
  catch { $('connect-status').textContent = 'Select the command above and copy it manually.'; $('install-command').focus(); }
};
$('cursor-install').onclick = () => { $('connect-status').textContent = 'Approve the install in Cursor, then start a new conversation. If Cursor did not open, check that it is installed on this computer.'; };
$('menu-toggle').onclick = () => menu($('menu-toggle').getAttribute('aria-expanded') !== 'true');
$('menu-overlay').onclick = () => { menu(false); $('menu-toggle').focus(); };
mobile.addEventListener('change', () => menu(false));
compact.addEventListener('change', placeInspector);
$('record-dialog').addEventListener('close', () => {
  if ($('record-dialog').dataset.relocating) { delete $('record-dialog').dataset.relocating; return; }
  closeInspector(); renderRecords();
});
document.addEventListener('keydown', event => {
  if (event.key === 'Escape' && $('menu-toggle').getAttribute('aria-expanded') === 'true') { menu(false); $('menu-toggle').focus(); }
  if (event.key === '/' && !event.ctrlKey && !event.metaKey && !event.altKey && !event.target.closest('input,select,textarea,[contenteditable="true"]') && !document.querySelector('dialog[open]')) { event.preventDefault(); if (!$('toolbar').hidden) $('search').focus(); }
  if (event.key === 'Escape' && event.target === $('search')) clearSearch();
});
for (const button of document.querySelectorAll('[data-action="remember"]')) button.onclick = () => $('remember').click();
for (const form of document.querySelectorAll('form')) form.addEventListener('invalid', event => { for (const details of event.target.closest('details') ? [event.target.closest('details')] : []) details.open = true; }, true);
window.addEventListener('popstate', () => {
  const params = new URLSearchParams(location.search);
  closeInspector(false); state.project = params.get('project') || ''; state.scope = params.get('area') || '';
  state.view = Object.hasOwn(views, params.get('view')) ? params.get('view') : 'active'; $('search').value = params.get('q') || '';
  state.searches[state.view] = $('search').value; loadProjects(state.project); $('title').focus({preventScroll: true});
});
$('search').value = state.searches[state.view];
placeInspector(); render(); initAuth().then(() => loadProjects()).catch(authFailed);
