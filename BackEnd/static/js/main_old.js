// ===================== CONFIG =====================
const API_BASE = '';
const USE_MOCK_IF_FAILS = false; // we're serving from Flask, prefer real errors

// Auth state
let AUTH_TOKEN = localStorage.getItem('ss_token') || null;
let CURRENT_USER = null; // { id, email, name }

// Bind label
addEventListener('DOMContentLoaded', () => {
  document.getElementById('apiBaseLabel').textContent = location.origin;
});

// ===================== UTILITIES =====================
function showToast(title, body, type = 'info') {
  const icon = {
    success: 'bi-check-circle-fill text-success',
    danger: 'bi-x-circle-fill text-danger',
    warning: 'bi-exclamation-triangle-fill text-warning',
    info: 'bi-info-circle-fill text-info'
  }[type] || 'bi-info-circle-fill text-info';

  const toastEl = document.createElement('div');
  toastEl.className = 'toast align-items-center border-0 show';
  toastEl.role = 'alert';
  toastEl.innerHTML = `
    <div class="d-flex">
      <div class="toast-body">
        <i class="bi ${icon} me-2"></i><strong>${title}:</strong> ${body}
      </div>
      <button type="button" class="btn-close me-2 m-auto" data-bs-dismiss="toast"></button>
    </div>`;
  document.getElementById('toastContainer').appendChild(toastEl);
  setTimeout(() => toastEl.remove(), 3500);
}

function logActivity(msg) {
  const log = document.getElementById('activityLog');
  const t = new Date().toLocaleString();
  const line = document.createElement('div');
  line.textContent = `[${t}] ${msg}`;
  log.prepend(line);
}

function setSection(targetId) {
  document.querySelectorAll('.nav-link').forEach(a => a.classList.remove('active'));
  document.querySelectorAll('section').forEach(s => s.classList.add('d-none'));
  document.querySelectorAll(`[data-target="${targetId}"]`).forEach(a => a.classList.add('active'));
  document.getElementById(targetId).classList.remove('d-none');
}

function safeJSONParse(text, fallback = {}) { try { return JSON.parse(text); } catch { return fallback; } }

function setUserLabel() {
  const label = document.getElementById('userLabel');
  if (CURRENT_USER) label.textContent = `${CURRENT_USER.email}`; else label.textContent = 'Signed out';
}

function setBuilderReadOnly(readonly) {
  if (!window.editor) return;
  editor.setOption('readOnly', readonly ? 'nocursor' : false);
  document.getElementById('btnDeploy').disabled = !!readonly;
  document.getElementById('btnGenerateAI').disabled = !!readonly;
}

// ===================== AUTH =====================
async function api(path, options = {}) {
  const url = `${API_BASE}${path}`;
  const headers = Object.assign({ 'Content-Type': 'application/json' }, options.headers || {});
  if (AUTH_TOKEN) headers['Authorization'] = `Bearer ${AUTH_TOKEN}`;
  const init = Object.assign({}, options, { headers });
  try {
    const res = await fetch(url, init);
    // if unauthorized, force login
    if (res.status === 401) { showLogin(); return Promise.reject(new Error('Unauthorized')); }
    if (!res.ok) throw new Error(`${res.status}`);
    return await res.json();
  } catch (err) {
    if (USE_MOCK_IF_FAILS) return { __mock: true, error: err.message };
    throw err;
  }
}

async function me() { return await api('/me', { method: 'GET' }); }
async function login(email, password) { return await api('/auth/login', { method: 'POST', body: JSON.stringify({ email, password }) }); }

function showLogin() {
  document.getElementById('authOverlay').classList.remove('d-none');
}
function hideLogin() {
  document.getElementById('authOverlay').classList.add('d-none');
}

// ===================== CODEMIRROR =====================
let editor;
document.addEventListener('DOMContentLoaded', () => {
  editor = CodeMirror.fromTextArea(document.getElementById('codeEditor'), {
    mode: 'python', theme: 'dracula', lineNumbers: true, autoCloseBrackets: true, indentUnit: 4, tabSize: 4
  });
});

function setEditorValue(code) { editor.setValue(code); editor.refresh(); }
function getEditorValue() { return editor.getValue(); }

// ===================== STATE =====================
let currentId = null;        // DB id when editing existing function
let currentOwnerId = null;   // owner of the loaded function
let functionsCache = [];     // my functions
let availableCache = [];     // public/available functions
let charts = { calls: null, success: null };

// ===================== API CALLS (Data) =====================
async function listFunctionsMine() {
  const data = await api('/functions?scope=mine');
  if (data.__mock) {
    return [
      { id: 101, description: 'Add two numbers', created_at: '2025-10-01 10:20', visibility: 'private', owner_id: 1 },
      { id: 102, description: 'Factorial calculator', created_at: '2025-10-02 09:12', visibility: 'public', owner_id: 1 }
    ];
  }
  return data.items || data;
}

async function listFunctionsAvailable() {
  const data = await api('/functions?scope=available');
  if (data.__mock) {
    return [
      { id: 201, description: 'Validate PAN number', created_at: '2025-10-03 17:44', owner_email: 'alice@example.com', owner_id: 2 },
      { id: 202, description: 'String title-case', created_at: '2025-10-04 11:20', owner_email: 'bob@example.com', owner_id: 3 }
    ];
  }
  return data.items || data;
}

async function getStats() {
  const data = await api('/stats');
  if (data.__mock) {
    return {
      totals: { functions: 5, calls24h: 26, successRate: 0.88, topFunction: 'Add two numbers' },
      byFunction: [
        { id: 101, label: 'Add two numbers', calls: 120 },
        { id: 102, label: 'Factorial', calls: 44 },
        { id: 201, label: 'Validate PAN', calls: 30 }
      ],
      outcomes: { success: 170, error: 24 }
    };
  }
  return data;
}

async function deploy(code, desc, visibility) {
  return await api('/deploy_function', {
    method: 'POST', body: JSON.stringify({ code, desc, visibility })
  });
}

async function test(code, args) {
  return await api('/test_function', {
    method: 'POST', body: JSON.stringify({ code, args })
  });
}

async function runById(id, api_args) {
  return await api('/ofa', {
    method: 'POST', body: JSON.stringify({ id, api_args })
  });
}

async function getFunction(id) { return await api(`/functions/${id}`); }
async function updateFunction(id, code, desc, visibility) {
  return await api(`/functions/${id}`, { method: 'PUT', body: JSON.stringify({ code, desc, visibility }) });
}
async function deleteFunction(id) { return await api(`/functions/${id}`, { method: 'DELETE' }); }

// ===================== UI BINDINGS =====================
document.addEventListener('DOMContentLoaded', async () => {
  // Sidebar & top tabs routing
  document.getElementById('sideNav').addEventListener('click', (e) => {
    const a = e.target.closest('a[data-target]');
    if (!a) return; e.preventDefault(); setSection(a.dataset.target);
  });
  document.getElementById('topTabs').addEventListener('click', (e) => {
    const a = e.target.closest('a[data-target]');
    if (!a) return; e.preventDefault(); setSection(a.dataset.target);
  });

  // Buttons
  document.getElementById('btnNewFunction').addEventListener('click', newFunction);
  document.getElementById('btnTest').addEventListener('click', onTest);
  document.getElementById('btnDeploy').addEventListener('click', onDeploy);
  document.getElementById('btnReset').addEventListener('click', resetBuilder);
  document.getElementById('btnGenerateAI').addEventListener('click', onGenerateAI);
  document.getElementById('btnReloadFunctions').addEventListener('click', loadFunctionsMine);
  document.getElementById('btnReloadAvailable').addEventListener('click', loadFunctionsAvailable);
  document.getElementById('btnRefreshAll').addEventListener('click', refreshAll);
  document.getElementById('btnQuickRun').addEventListener('click', onQuickRun);
  document.getElementById('btnClearLogs').addEventListener('click', () => { document.getElementById('activityLog').innerHTML = ''; });
  document.getElementById('btnLogout').addEventListener('click', doLogout);
  document.getElementById('btnLogin').addEventListener('click', doLogin);

  // Dark mode toggle
  document.getElementById('darkToggle').addEventListener('change', (e) => {
    document.documentElement.setAttribute('data-bs-theme', e.target.checked ? 'dark' : 'light'); editor.refresh();
  });

  // Filters
  document.getElementById('fnSearch').addEventListener('input', renderFunctionsTable);
  document.getElementById('availSearch').addEventListener('input', renderAvailableTable);
  document.getElementById('globalSearch').addEventListener('input', onGlobalSearch);

  // Boot: check session
  await bootAuth();
});

async function bootAuth() {
  if (!AUTH_TOKEN) { showLogin(); return; }
  try {
    const info = await me();
    if (info && info.id) {
      CURRENT_USER = info; setUserLabel(); hideLogin(); refreshAll();
    } else { showLogin(); }
  } catch (e) { showLogin(); }
}

async function doLogin() {
  const email = document.getElementById('authEmail').value.trim();
  const password = document.getElementById('authPassword').value.trim();
  if (!email || !password) return showToast('Login', 'Enter email and password.', 'warning');
  try {
    const res = await login(email, password);
    if (res && res.token) {
      AUTH_TOKEN = res.token; localStorage.setItem('ss_token', AUTH_TOKEN);
      CURRENT_USER = res.user; setUserLabel(); hideLogin(); refreshAll();
      showToast('Welcome', `Signed in as ${CURRENT_USER.email}`, 'success');
    } else { showToast('Login', 'Invalid response from server.', 'danger'); }
  } catch (e) {
    showToast('Login', 'Invalid credentials or server error.', 'danger');
  }
}

function doLogout() {
  AUTH_TOKEN = null; CURRENT_USER = null; localStorage.removeItem('ss_token'); setUserLabel(); showLogin();
}

function refreshAll() {
  loadFunctionsMine();
  loadFunctionsAvailable();
  loadStatsAndCharts();
  setSection('builderSection');
}

// ===================== BUILDER ACTIONS =====================
function newFunction() {
  currentId = null; currentOwnerId = CURRENT_USER ? CURRENT_USER.id : null;
  document.getElementById('currentFunctionId').textContent = '(new)';
  document.getElementById('currentOwnerLabel').textContent = 'you';
  document.getElementById('functionName').value = '';
  document.getElementById('functionDesc').value = '';
  document.getElementById('functionVisibility').value = 'private';
  setEditorValue(`def api_def(args):\n    \"\"\"\n    Describe your function here.\n    \"\"\"\n    return args\n`);
  document.getElementById('testParams').value = '{"sample": 1}';
  setBuilderReadOnly(false);
  setSection('builderSection');
  logActivity('Started a new function');
}

function resetBuilder() { newFunction(); showToast('Reset', 'Editor cleared.', 'warning'); }

async function onGenerateAI() {
  const prompt = document.getElementById('aiPrompt').value.trim();
  if (!prompt) return showToast('AI', 'Enter a prompt first.', 'warning');
  // Mock content — replace with your backend wired endpoint
  const code = `def api_def(args):\n    \"\"\"\n    Auto-generated function based on prompt:\n    ${prompt}\n    \"\"\"\n    # TODO: implement\n    return { 'ok': True, 'received': args }`;
  setEditorValue(code);
  showToast('AI', 'Function generated (mock).', 'success');
  logActivity('AI generated code from prompt');
}

async function onTest() {
  const code = getEditorValue();
  const args = safeJSONParse(document.getElementById('testParams').value, {});
  document.getElementById('outputBox').textContent = '⏳ Testing…';
  const res = await test(code, args);
  document.getElementById('outputBox').textContent = JSON.stringify(res, null, 2);
  showToast('Test', res.error ? 'Error during test' : 'Executed successfully.', res.error ? 'danger' : 'success');
  logActivity('Ran Test from Builder');
}

async function onDeploy() {
  const desc = document.getElementById('functionDesc').value.trim();
  const code = getEditorValue();
  const visibility = document.getElementById('functionVisibility').value;
  if (!desc) return showToast('Deploy', 'Please add a description.', 'warning');
  const res = currentId
    ? await updateFunction(currentId, code, desc, visibility)
    : await deploy(code, desc, visibility);

  if (res.error) return showToast('Deploy', res.error || 'Error', 'danger');

  if (!currentId && res.id) currentId = res.id;
  document.getElementById('currentFunctionId').textContent = currentId || '(new)';
  document.getElementById('currentOwnerLabel').textContent = 'you';
  showToast('Deploy', currentId ? `Saved #${currentId}.` : 'Saved.', 'success');
  await loadFunctionsMine();
  logActivity('Deployed/Updated function');
}

async function onQuickRun() {
  const id = currentId || prompt('Enter Function ID to run:');
  if (!id) return;
  const args = safeJSONParse(document.getElementById('testParams').value, {});
  document.getElementById('outputBox').textContent = `⏳ Running ID ${id}…`;
  const res = await runById(id, args);
  document.getElementById('outputBox').textContent = JSON.stringify(res, null, 2);
  showToast('Run', res.error ? 'Error during run' : 'Executed successfully.', res.error ? 'danger' : 'success');
  logActivity(`Executed function #${id}`);
}

// ===================== FUNCTIONS LIST (MINE) =====================
async function loadFunctionsMine() {
  const list = await listFunctionsMine();
  functionsCache = list;
  renderFunctionsTable();
  document.getElementById('statTotalFunctions').textContent = (functionsCache.length + (availableCache?.length||0));
}

function renderFunctionsTable() {
  const q = (document.getElementById('fnSearch').value || '').toLowerCase();
  const tbody = document.getElementById('functionsTableBody');
  tbody.innerHTML = '';
  functionsCache
    .filter(x => !q || (x.description || '').toLowerCase().includes(q) || String(x.id).includes(q))
    .forEach(fn => {
      const tr = document.createElement('tr');
      tr.innerHTML = `
        <td>${fn.id}</td>
        <td>${fn.description || ''}</td>
        <td>${fn.visibility || 'private'}</td>
        <td>${fn.created_at || ''}</td>
        <td class="text-end">
          <div class="btn-group">
            <button class="btn btn-sm btn-outline-primary" title="Edit"><i class="bi bi-pencil"></i></button>
            <button class="btn btn-sm btn-outline-success" title="Run"><i class="bi bi-play"></i></button>
            <button class="btn btn-sm btn-outline-danger" title="Delete"><i class="bi bi-trash"></i></button>
          </div>
        </td>`;

      const [btnEdit, btnRun, btnDelete] = tr.querySelectorAll('button');
      btnEdit.addEventListener('click', async () => {
        const res = await getFunction(fn.id);
        if (res.error) return showToast('Load', res.error, 'danger');
        currentId = res.id; currentOwnerId = res.owner_id || (CURRENT_USER && CURRENT_USER.id);
        document.getElementById('currentFunctionId').textContent = currentId;
        document.getElementById('currentOwnerLabel').textContent = 'you';
        document.getElementById('functionDesc').value = res.description || '';
        document.getElementById('functionName').value = res.description || '';
        document.getElementById('functionVisibility').value = res.visibility || 'private';
        setEditorValue(res.api_def || 'def api_def(args):\n    return args');
        setBuilderReadOnly(false);
        setSection('builderSection');
        showToast('Load', `Loaded #${fn.id} into editor.`, 'info');
        logActivity(`Loaded function #${fn.id} for editing`);
      });

      btnRun.addEventListener('click', async () => {
        const args = safeJSONParse(document.getElementById('testParams').value, {});
        const res = await runById(fn.id, args);
        setSection('builderSection');
        document.getElementById('outputBox').textContent = JSON.stringify(res, null, 2);
        showToast('Run', res.error ? 'Error during run' : `Executed #${fn.id}.`, res.error ? 'danger' : 'success');
        logActivity(`Ran function #${fn.id} from list`);
      });

      btnDelete.addEventListener('click', async () => {
        if (!confirm(`Delete function #${fn.id}?`)) return;
        const res = await deleteFunction(fn.id);
        if (res.error) showToast('Delete', res.error, 'danger');
        else { showToast('Delete', `Deleted #${fn.id}.`, 'success'); await loadFunctionsMine(); }
        logActivity(`Deleted function #${fn.id}`);
      });

      tbody.appendChild(tr);
    });
}

// ===================== AVAILABLE (VIEW-ONLY) =====================
async function loadFunctionsAvailable() {
  const list = await listFunctionsAvailable();
  availableCache = list;
  renderAvailableTable();
  document.getElementById('statTotalFunctions').textContent = (functionsCache.length + availableCache.length);
}

function renderAvailableTable() {
  const q = (document.getElementById('availSearch').value || '').toLowerCase();
  const tbody = document.getElementById('availableTableBody');
  tbody.innerHTML = '';
  availableCache
    .filter(x => !q || (x.description || '').toLowerCase().includes(q) || String(x.id).includes(q) || (x.owner_email||'').toLowerCase().includes(q))
    .forEach(fn => {
      const tr = document.createElement('tr');
      tr.innerHTML = `
        <td>${fn.id}</td>
        <td>${fn.description || ''}</td>
        <td>${fn.owner_email || fn.owner_id || ''}</td>
        <td>${fn.created_at || ''}</td>
        <td class="text-end">
          <div class="btn-group">
            <button class="btn btn-sm btn-outline-secondary" title="View"><i class="bi bi-eye"></i></button>
            <button class="btn btn-sm btn-outline-success" title="Run"><i class="bi bi-play"></i></button>
          </div>
        </td>`;

      const [btnView, btnRun] = tr.querySelectorAll('button');
      btnView.addEventListener('click', async () => {
        const res = await getFunction(fn.id);
        if (res.error) return showToast('Load', res.error, 'danger');
        currentId = res.id; currentOwnerId = res.owner_id;
        document.getElementById('currentFunctionId').textContent = currentId;
        document.getElementById('currentOwnerLabel').textContent = res.owner_email || `user:${res.owner_id}`;
        document.getElementById('functionDesc').value = res.description || '';
        document.getElementById('functionName').value = res.description || '';
        document.getElementById('functionVisibility').value = res.visibility || 'public';
        setEditorValue(res.api_def || 'def api_def(args):\n    return args');
        setBuilderReadOnly(true); // view-only
        setSection('builderSection');
        showToast('View', `Viewing public function #${fn.id} (read‑only).`, 'info');
        logActivity(`Viewing public function #${fn.id}`);
      });

      btnRun.addEventListener('click', async () => {
        const args = safeJSONParse(document.getElementById('testParams').value, {});
        const res = await runById(fn.id, args);
        setSection('builderSection');
        document.getElementById('outputBox').textContent = JSON.stringify(res, null, 2);
        showToast('Run', res.error ? 'Error during run' : `Executed #${fn.id}.`, res.error ? 'danger' : 'success');
        logActivity(`Ran public function #${fn.id}`);
      });

      tbody.appendChild(tr);
    });
}

function onGlobalSearch(e) {
  const term = (e.target.value || '').toLowerCase();
  document.getElementById('fnSearch').value = term; renderFunctionsTable();
  document.getElementById('availSearch').value = term; renderAvailableTable();
}

// ===================== DASHBOARD / CHARTS =====================
async function loadStatsAndCharts() {
  const stats = await getStats();
  const totals = stats.totals || { functions: 0, calls24h: 0, successRate: 0, topFunction: '—' };
  document.getElementById('statCalls24h').textContent = totals.calls24h;
  document.getElementById('statSuccessRate').textContent = totals.successRate ? Math.round(totals.successRate * 100) + '%' : '—';
  document.getElementById('statTopFunction').textContent = totals.topFunction || '—';

  const byFn = stats.byFunction || [];
  const labels = byFn.map(x => x.label || ('#' + x.id));
  const values = byFn.map(x => x.calls || 0);

  const outcomes = stats.outcomes || { success: 0, error: 0 };

  // Calls by function (bar)
  const ctx1 = document.getElementById('chartCalls');
  charts.calls && charts.calls.destroy();
  charts.calls = new Chart(ctx1, {
    type: 'bar',
    data: { labels, datasets: [{ label: 'Calls', data: values }] },
    options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } } }
  });

  // Success vs Errors (doughnut)
  const ctx2 = document.getElementById('chartSuccess');
  charts.success && charts.success.destroy();
  charts.success = new Chart(ctx2, {
    type: 'doughnut',
    data: { labels: ['Success', 'Error'], datasets: [{ data: [outcomes.success, outcomes.error] }] },
    options: { responsive: true, maintainAspectRatio: false }
  });

  document.getElementById('btnRefreshCharts').onclick = loadStatsAndCharts;
}
let currentDraftId = null;

async function onTestDraft() {
  if (!currentDraftId) return showToast('Test', 'Save the draft first.', 'warning');
  const args = safeJSONParse(document.getElementById('testParams').value, {});
  document.getElementById('outputBox').textContent = '⏳ Testing draft...';
  const res = await testDraft(currentDraftId, args);
  document.getElementById('outputBox').textContent = JSON.stringify(res, null, 2);
  showToast('Test', res.error ? 'Error during draft test' : 'Draft executed successfully.', res.error ? 'danger' : 'success');
  logActivity(`Tested draft #${currentDraftId}`);
}

async function onPromoteDraft() {
  if (!currentDraftId) return showToast('Promote', 'No draft to promote.', 'warning');
  const res = await promoteDraft(currentDraftId);
  if (res.error) return showToast('Promote', res.error, 'danger');
  if (res.id) {
    currentId = res.id;
    document.getElementById('currentFunctionId').textContent = res.id;
    showToast('Promote', `Promoted draft #${currentDraftId} to prod #${res.id}`, 'success');
    logActivity(`Promoted draft #${currentDraftId} to prod #${res.id}`);
  }
}
// ===================== DRAFTS (Option A) =====================
let currentDraftId = null;

// --- API Helpers ---
async function saveDraft(desc, code, visibility, draftId) {
  const body = { description: desc, code, visibility };
  if (draftId) body.id = draftId;
  return api('/drafts', { method: 'POST', body: JSON.stringify(body) });
}

async function testDraft(draftId, args) {
  return api(`/drafts/${draftId}:test`, { method: 'POST', body: JSON.stringify({ args }) });
}

async function promoteDraft(draftId) {
  return api(`/drafts/${draftId}:promote`, { method: 'POST' });
}

// --- UI Handlers ---
document.addEventListener('DOMContentLoaded', () => {
  const btnSave = document.getElementById('btnSaveDraft');
  const btnTest = document.getElementById('btnDraftTest');
  const btnPromote = document.getElementById('btnPromote');
  if (btnSave) btnSave.addEventListener('click', onSaveDraft);
  if (btnTest) btnTest.addEventListener('click', onTestDraft);
  if (btnPromote) btnPromote.addEventListener('click', onPromoteDraft);
});

async function onSaveDraft() {
  const desc = document.getElementById('functionDesc').value.trim();
  const code = getEditorValue();
  const visibility = document.getElementById('functionVisibility').value;
  if (!desc) return showToast('Draft', 'Please add a description.', 'warning');
  if (!code.includes('def api_def')) return showToast('Draft', "Your code must define 'def api_def(args): ...'", 'warning');

  try {
    const res = await saveDraft(desc, code, visibility, currentDraftId);
    if (res.error) throw new Error(res.error);
    currentDraftId = res.id;
    const draftLabel = document.getElementById('currentDraftId');
    if (draftLabel) draftLabel.textContent = currentDraftId;
    showToast('Draft', `Saved draft #${currentDraftId}`, 'success');
    logActivity(`Saved draft #${currentDraftId}`);
  } catch (e) {
    showToast('Draft', e.message || 'Error saving draft', 'danger');
  }
}
