// ===================== GLOBAL =====================
const API_BASE = '';
let AUTH_TOKEN = localStorage.getItem('ss_token') || null;
let CURRENT_USER = null;
let editor;
let currentDraftId = null;
let selectedProjectId = null;

// ===================== BASIC HELPERS =====================
async function api(path, options = {}) {
  const headers = { 'Content-Type': 'application/json', ...(options.headers || {}) };
  if (AUTH_TOKEN) headers['Authorization'] = "Bearer " + AUTH_TOKEN;
  const res = await fetch(API_BASE + path, { ...options, headers });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

function getEditorValue() {
  return editor ? editor.getValue() : document.getElementById('codeEditor').value;
}

// Robust toast system
function showToast(title, message, type = "info") {
  const colors = {
    success: "bg-success text-white",
    danger: "bg-danger text-white",
    warning: "bg-warning text-dark",
    info: "bg-info text-dark"
  };
  const cls = colors[type] || colors.info;

  const toastArea = document.getElementById("toastArea") || document.body;
  const toastId = "toast_" + Date.now();

  const toast = document.createElement("div");
  toast.className = "toast align-items-center border-0 " + cls;
  toast.id = toastId;
  toast.role = "alert";
  toast.ariaLive = "assertive";
  toast.ariaAtomic = "true";
  toast.innerHTML = [
    '<div class="d-flex">',
    '<div class="toast-body fw-semibold">',
    '<i class="bi bi-info-circle-fill me-2"></i><strong>', title, '</strong>: ', message,
    '</div>',
    '<button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast"></button>',
    '</div>'
  ].join('');
  toastArea.appendChild(toast);

  const bsToast = new bootstrap.Toast(toast, { delay: 4000 });
  bsToast.show();
  toast.addEventListener("hidden.bs.toast", () => toast.remove());
}

function safeJSONParse(text, fallback = {}) {
  try { return JSON.parse(text); } catch { return fallback; }
}

function initDarkMode() {
  const toggle = document.getElementById('darkToggle');
  if (!toggle) return;

  const currentTheme = localStorage.getItem('theme') || 'light';
  if (currentTheme === 'dark') {
    document.documentElement.setAttribute('data-bs-theme', 'dark');
    toggle.checked = true;
  }

  toggle.addEventListener('change', () => {
    const isDark = toggle.checked;
    const newTheme = isDark ? 'dark' : 'light';
    document.documentElement.setAttribute('data-bs-theme', newTheme);
    localStorage.setItem('theme', newTheme);
  });
}

function bindClick(id, handler) {
  const el = document.getElementById(id);
  if (el) el.addEventListener('click', handler);
}

// ===================== INITIALIZATION =====================
document.addEventListener('DOMContentLoaded', () => {
  initDarkMode();

  const el = document.getElementById('codeEditor');
  if (el) {
    editor = CodeMirror.fromTextArea(el, {
      mode: 'python',
      theme: 'dracula',
      lineNumbers: true,
      autoCloseBrackets: true,
      indentUnit: 4
    });
  }

  // Button bindings
  bindClick('btnSaveDraft', onSaveDraft);
  bindClick('btnDraftTest', onTestDraft);
  bindClick('btnSaveAndTest', onSaveAndTest);
  bindClick('btnPromote', onPromoteDraft);
  bindClick('btnReset', () => location.reload());

  bindClick('btnUpdateAgent', onUpdateAgent);
  bindClick('btnTestAgent', onTestAgent);
  bindClick('btnUpdateAndTest', onUpdateAndTest);
  bindClick('btnCancelEdit', resetToNewAgentMode);
  bindClick('btnNewFunction', resetToNewAgentMode);

  // Navigation handlers
  const navClickHandler = (e) => {
    const link = e.target.closest("a[data-target]");
    if (!link) return;
    e.preventDefault();
    setSection(link.dataset.target);
  };

  const sideNav = document.getElementById("sideNav");
  if (sideNav) sideNav.addEventListener("click", navClickHandler);

  const topTabs = document.getElementById("topTabs");
  if (topTabs) topTabs.addEventListener("click", navClickHandler);

  bindClick('btnGenerateAI', onGenerateAI);

  // Auth Handlers
  bindClick('btnLogin', login);
  bindClick('btnRegister', register);
  bindClick('btnLogout', logout);

  // Projects Handlers
  bindClick('btnCreateProject', createProject);
  bindClick('btnGenerateToken', generateToken);

  // Functions & Logs reloaders
  bindClick('btnReloadFunctions', () => loadFunctions('mine'));
  bindClick('btnReloadAvailable', () => loadFunctions('available'));
  bindClick('btnReloadLogs', loadLogs);
  bindClick('btnRefreshCharts', loadStats);

  // Auto-login or block
  if (AUTH_TOKEN) {
    hideLoginOverlay();
    fetchMe();
  } else {
    showLoginOverlay();
  }
});

function setSection(targetId) {
  document.querySelectorAll("section").forEach(sec => sec.classList.add("d-none"));
  const target = document.getElementById(targetId);
  if (target) target.classList.remove("d-none");

  document.querySelectorAll(".nav-link").forEach(a => a.classList.remove("active"));
  document.querySelectorAll("[data-target='" + targetId + "']").forEach(a => a.classList.add("active"));

  if (targetId === 'functionsSection') loadFunctions('mine');
  if (targetId === 'dashboardSection') loadStats();
  if (targetId === 'projectsSection') loadProjectsUI();
  if (targetId === 'logsSection') loadLogs();
}

// ===================== AUTH & LOGOUT =====================
function showLoginOverlay() {
  const el = document.getElementById('authOverlay');
  if (el) el.classList.remove('d-none');
}

function hideLoginOverlay() {
  const el = document.getElementById('authOverlay');
  if (el) el.classList.add('d-none');
}

async function login() {
  const email = document.getElementById('loginEmail').value.trim();
  const password = document.getElementById('loginPassword').value.trim();
  if (!email || !password) return showToast('Login', 'Please enter email and password.', 'warning');

  try {
    const res = await fetch('/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password })
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || 'Invalid credentials');

    AUTH_TOKEN = data.token;
    CURRENT_USER = data.user;
    localStorage.setItem('ss_token', AUTH_TOKEN);
    showToast('Login', "Welcome, " + data.user.name, 'success');
    hideLoginOverlay();
    onLoginSuccess();
  } catch (e) {
    showToast('Login', e.message, 'danger');
  }
}

async function register() {
  const name = document.getElementById('regName').value.trim();
  const email = document.getElementById('regEmail').value.trim();
  const password = document.getElementById('regPassword').value.trim();

  if (!name || !email || !password) return showToast('Register', 'All fields are required.', 'warning');

  try {
    const res = await fetch('/auth/register', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, email, password })
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || 'Registration failed');

    showToast('Register', 'Account created! Logging you in...', 'success');
    document.getElementById('loginEmail').value = email;
    document.getElementById('loginPassword').value = password;
    await login();
  } catch (e) {
    showToast('Register', e.message, 'danger');
  }
}

function logout() {
  AUTH_TOKEN = null;
  CURRENT_USER = null;
  localStorage.removeItem('ss_token');
  showToast('Logout', 'Signed out successfully.', 'info');
  showLoginOverlay();
}

async function fetchMe() {
  try {
    const data = await api('/me');
    CURRENT_USER = data;
    onLoginSuccess();
  } catch (e) {
    console.warn("Session expired");
    logout();
  }
}

function onLoginSuccess() {
  document.getElementById('userLabel').textContent = CURRENT_USER.email;
  loadDropdownProjects();
}

// ===================== PROJECTS =====================
async function loadDropdownProjects() {
  try {
    const projects = await api('/projects');
    const sel = document.getElementById('functionProject');
    if (!sel) return;
    sel.innerHTML = '<option value="">None (Personal Workspace)</option>';
    projects.forEach(p => {
      const opt = document.createElement('option');
      opt.value = p.id;
      opt.textContent = p.name;
      sel.appendChild(opt);
    });
  } catch (e) {
    console.error("Failed to load projects", e);
  }
}

async function loadProjectsUI() {
  try {
    const projects = await api('/projects');
    const tbody = document.getElementById('projectsTableBody');
    tbody.innerHTML = '';
    if (projects.length === 0) {
      tbody.innerHTML = '<tr><td colspan="2" class="text-center text-muted">No projects found.</td></tr>';
      return;
    }

    projects.forEach(p => {
      const tr = document.createElement('tr');
      tr.innerHTML = [
        '<td class="fw-semibold">', p.name, '</td>',
        '<td class="text-end">',
        '<button class="btn btn-sm btn-outline-primary" onclick="viewTokens(', p.id, ', \'', p.name.replace(/'/g, "\\'"), '\')">View Tokens</button>',
        '</td>'
      ].join('');
      tbody.appendChild(tr);
    });
  } catch (e) {
    showToast('Projects', e.message, 'danger');
  }
}

async function createProject() {
  const input = document.getElementById('newProjectName');
  const name = input.value.trim();
  if (!name) return showToast('Project', 'Please enter a name', 'warning');

  try {
    await api('/projects', { method: 'POST', body: JSON.stringify({ name }) });
    showToast('Project', 'Project created.', 'success');
    input.value = '';
    loadProjectsUI();
    loadDropdownProjects();
  } catch (e) {
    showToast('Project', e.message, 'danger');
  }
}

window.viewTokens = async function (projId, projName) {
  selectedProjectId = projId;
  document.getElementById('tokenProjectLabel').textContent = "Tokens for: " + projName;
  document.getElementById('btnGenerateToken').classList.remove('d-none');

  try {
    const tokens = await api("/projects/" + projId + "/tokens");
    const tbody = document.getElementById('tokensTableBody');
    tbody.innerHTML = '';
    if (tokens.length === 0) {
      tbody.innerHTML = '<tr><td colspan="2" class="text-muted">No tokens generated yet.</td></tr>';
      return;
    }
    tokens.forEach(t => {
      const tr = document.createElement('tr');
      tr.innerHTML = [
        '<td><code class="user-select-all">', t.token, '</code></td>',
        '<td class="small text-muted">', new Date(t.created_at).toLocaleString(), '</td>'
      ].join('');
      tbody.appendChild(tr);
    });
  } catch (e) {
    showToast('Tokens', e.message, 'danger');
  }
}

async function generateToken() {
  if (!selectedProjectId) return;
  try {
    await api("/projects/" + selectedProjectId + "/tokens", { method: 'POST' });
    showToast('Tokens', 'Generated new API token!', 'success');
    const pName = document.getElementById('tokenProjectLabel').textContent.replace('Tokens for: ', '');
    viewTokens(selectedProjectId, pName);
  } catch (e) {
    showToast('Tokens', e.message, 'danger');
  }
}

// ===================== DRAFT API =====================
async function saveDraft(desc, code, visibility, projId, draftId) {
  const body = { description: desc, code, visibility, project_id: projId };
  if (draftId) body.id = draftId;
  return api('/drafts', { method: 'POST', body: JSON.stringify(body) });
}

async function testDraftAPI(draftId, args) {
  return api("/drafts/" + draftId + ":test", { method: 'POST', body: JSON.stringify({ args }) });
}

async function promoteDraftAPI(draftId) {
  return api("/drafts/" + draftId + ":promote", { method: 'POST' });
}

async function onSaveDraft() {
  const desc = document.getElementById('functionDesc').value.trim();
  const code = getEditorValue();
  const visibility = document.getElementById('functionVisibility').value;
  const project_id = document.getElementById('functionProject').value;

  if (!desc) {
    showToast('Draft', 'Please add a description.', 'warning');
    return false;
  }
  if (!code.includes('def api_def')) {
    showToast('Draft', "Your code must define 'def api_def(args): ...'", 'warning');
    return false;
  }

  try {
    const res = await saveDraft(desc, code, visibility, project_id, currentDraftId);
    if (res.error) throw new Error(res.error);
    currentDraftId = res.id;
    const label = document.getElementById('currentFunctionId');
    if (label) label.textContent = currentDraftId;
    showToast('Draft', "Saved draft #" + currentDraftId, 'success');
    return true;
  } catch (err) {
    showToast('Draft', err.message || 'Failed to save draft', 'danger');
    return false;
  }
}

async function onSaveAndTest() {
  const btn = document.getElementById('btnSaveAndTest');
  const originalHtml = btn ? btn.innerHTML : '';
  if (btn) { btn.innerHTML = '<span class="spinner-grow spinner-grow-sm me-2" role="status"></span>Running...'; btn.disabled = true; }
  try {
    const saved = await onSaveDraft();
    if (saved) await onTestDraft();
  } catch (e) { console.error(e); }
  finally { if (btn) { btn.innerHTML = originalHtml; btn.disabled = false; } }
}

async function onTestDraft() {
  const draftIdElem = document.getElementById("currentFunctionId");
  const draftId = draftIdElem ? draftIdElem.textContent.trim() : currentDraftId;
  if (!draftId || isNaN(draftId)) return showToast("Test", "No draft ID found to test.", "warning");

  const args = safeJSONParse(document.getElementById("testParams").value, {});
  document.getElementById("outputBox").textContent = "⏳ Running test...";

  try {
    const res = await api("/drafts/" + draftId + ":test", { method: "POST", body: JSON.stringify({ args }), });
    if (res.error) {
      showToast("Test", res.error, "danger");
      document.getElementById("outputBox").textContent = JSON.stringify(res, null, 2);
    } else {
      const msg = res.success ? "✅ Test passed (" + (res.latency_ms || 0) + " ms)" : "❌ Test failed";
      showToast("Test", msg, res.success ? "success" : "warning");
      document.getElementById("outputBox").textContent = JSON.stringify(res, null, 2);
    }
  } catch (e) {
    showToast("Test", e.message || "Error testing draft", "danger");
    document.getElementById("outputBox").textContent = e.message;
  }
}

async function onPromoteDraft() {
  if (!currentDraftId) return showToast('Promote', 'No draft to promote.', 'warning');
  try {
    const res = await promoteDraftAPI(currentDraftId);
    if (res.error) throw new Error(res.error);
    showToast('Promote', "Draft #" + currentDraftId + " promoted to prod #" + res.id, 'success');
  } catch (e) {
    showToast('Promote', e.message || 'Promotion failed', 'danger');
  }
}

// ===================== EDIT & TEST AGENT API =====================
let currentEditId = null;

function resetToNewAgentMode() {
  currentEditId = null;
  currentDraftId = null;
  document.getElementById('currentFunctionId').textContent = '(new)';
  document.getElementById('functionDesc').value = '';
  document.getElementById('functionVisibility').value = 'private';
  document.getElementById('functionProject').value = '';
  document.getElementById('testParams').value = '';
  if (editor) {
    editor.setValue('def api_def(args):\n    return args');
  } else {
    document.getElementById('codeEditor').value = 'def api_def(args):\n    return args';
  }

  const draftGroup = document.getElementById('actionDraftGroup');
  const editGroup = document.getElementById('actionEditGroup');
  if (draftGroup) draftGroup.classList.remove('d-none');
  if (editGroup) editGroup.classList.add('d-none');

  setSection('builderSection');
}

window.editFunction = async function (id) {
  try {
    const fn = await api("/functions/" + id);
    currentEditId = id;
    currentDraftId = null;

    document.getElementById('currentFunctionId').textContent = id;
    document.getElementById('functionDesc').value = fn.description || '';
    document.getElementById('functionVisibility').value = fn.visibility || 'private';
    document.getElementById('functionProject').value = fn.project_id || '';

    if (editor) {
      editor.setValue(fn.api_def || '');
    } else {
      document.getElementById('codeEditor').value = fn.api_def || '';
    }

    const draftGroup = document.getElementById('actionDraftGroup');
    const editGroup = document.getElementById('actionEditGroup');
    if (draftGroup) draftGroup.classList.add('d-none');
    if (editGroup) editGroup.classList.remove('d-none');

    setSection('builderSection');
  } catch (e) {
    showToast('Edit', e.message, 'danger');
  }
}

window.cloneFunction = async function (id) {
  try {
    const fn = await api("/functions/" + id);
    const body = {
      desc: (fn.description || "Clone") + " (Copy)",
      code: fn.api_def,
      visibility: fn.visibility || "private",
      project_id: fn.project_id
    };

    await api('/deploy_function', { method: 'POST', body: JSON.stringify(body) });
    showToast('Clone', 'Agent duplicated successfully', 'success');
    loadFunctions('mine');
  } catch (e) {
    showToast('Clone', e.message, 'danger');
  }
}

async function onUpdateAgent() {
  if (!currentEditId) return false;

  const desc = document.getElementById('functionDesc').value.trim();
  const code = getEditorValue();
  const visibility = document.getElementById('functionVisibility').value;
  const project_id = document.getElementById('functionProject').value;

  if (!desc) {
    showToast('Update', 'Please add a description.', 'warning');
    return false;
  }
  if (!code.includes('def api_def')) {
    showToast('Update', "Your code must define 'def api_def(args): ...'", 'warning');
    return false;
  }

  try {
    const body = { desc, code, visibility, project_id };
    await api('/functions/' + currentEditId, { method: 'PUT', body: JSON.stringify(body) });
    showToast('Update', 'Agent updated successfully', 'success');
    return true;
  } catch (e) {
    showToast('Update', e.message, 'danger');
    return false;
  }
}

async function onTestAgent() {
  if (!currentEditId) return showToast("Test", "No agent ID found to test.", "warning");

  const args = safeJSONParse(document.getElementById("testParams").value, {});
  document.getElementById("outputBox").textContent = "⏳ Running test...";

  try {
    const res = await api("/ofa", { method: "POST", body: JSON.stringify({ id: currentEditId, api_args: args }) });
    if (res.error) {
      showToast("Test", res.error, "danger");
      document.getElementById("outputBox").textContent = JSON.stringify(res, null, 2);
    } else {
      const msg = res.success ? "✅ Test passed (" + (res.latency_ms || 0) + " ms)" : "❌ Test failed";
      showToast("Test", msg, res.success ? "success" : "warning");
      document.getElementById("outputBox").textContent = JSON.stringify(res, null, 2);
    }
  } catch (e) {
    showToast("Test", e.message || "Error testing agent", "danger");
    document.getElementById("outputBox").textContent = e.message;
  }
}

async function onUpdateAndTest() {
  const btn = document.getElementById('btnUpdateAndTest');
  const originalHtml = btn ? btn.innerHTML : '';
  if (btn) { btn.innerHTML = '<span class="spinner-grow spinner-grow-sm me-2" role="status"></span>Running...'; btn.disabled = true; }
  try {
    const saved = await onUpdateAgent();
    if (saved) await onTestAgent();
  } catch (e) { console.error(e); }
  finally { if (btn) { btn.innerHTML = originalHtml; btn.disabled = false; } }
}

// ===================== FUNCTIONS LIST =====================
window.deleteFunction = async function (id) {
  if (!confirm("Delete function #" + id + "?")) return;
  try {
    await api("/functions/" + id, { method: 'DELETE' });
    showToast('Functions', 'Deleted function ' + id, 'success');
    loadFunctions('mine');
  } catch (e) {
    showToast('Functions', e.message, 'danger');
  }
}

window.viewFunction = async function (id) {
  try {
    const fn = await api("/functions/" + id);
    alert("Source code for #" + id + ":\n\n" + fn.api_def);
  } catch (e) {
    showToast('Functions', e.message, 'danger');
  }
}

async function loadFunctions(scope = 'mine') {
  try {
    const fns = await api("/functions?scope=" + scope);
    const tb = document.getElementById(scope === 'mine' ? 'functionsTableBody' : 'availableTableBody');
    tb.innerHTML = '';
    if (!fns || fns.length === 0) {
      tb.innerHTML = '<tr><td colspan="5" class="text-center text-muted">No functions found.</td></tr>';
      return;
    }
    fns.forEach(f => {
      const tr = document.createElement('tr');
      if (scope === 'mine') {
        const projName = f.project_name ? '<span class="badge bg-secondary">' + f.project_name + '</span>' : '<span class="text-muted small">Personal</span>';
        const visBadge = f.visibility === 'public' ? 'bg-primary' : 'bg-secondary';
        tr.innerHTML = [
          '<td class="fw-bold">#', f.id, '</td>',
          '<td><div class="fw-semibold">', f.description || 'No description', '</div><div>', projName, '</div></td>',
          '<td><span class="badge ', visBadge, '">', f.visibility, '</span></td>',
          '<td class="small text-muted">', new Date(f.created_at).toLocaleString(), '</td>',
          '<td class="text-end text-nowrap">',
          '<button class="btn btn-sm btn-outline-secondary me-1" onclick="editFunction(', f.id, ')" title="Edit"><i class="bi bi-pencil"></i></button>',
          '<button class="btn btn-sm btn-outline-info me-1" onclick="cloneFunction(', f.id, ')" title="Duplicate"><i class="bi bi-copy"></i></button>',
          '<button class="btn btn-sm btn-outline-dark me-1" onclick="viewApiSnippet(', f.id, ', ', f.project_id || 'null', ')" title="API Snippet"><i class="bi bi-code-square"></i></button>',
          '<button class="btn btn-sm btn-outline-danger" onclick="deleteFunction(', f.id, ')" title="Delete"><i class="bi bi-trash"></i></button>',
          '</td>'
        ].join('');
      } else {
        const projName = f.project_name ? '<span class="badge bg-secondary">' + f.project_name + '</span>' : '<span class="text-muted small">Personal</span>';
        tr.innerHTML = [
          '<td class="fw-bold">#', f.id, '</td>',
          '<td><div class="fw-semibold">', f.description || 'No description', '</div><div>', projName, '</div></td>',
          '<td><span class="badge bg-light text-dark border">', f.owner_email, '</span></td>',
          '<td class="small text-muted">', new Date(f.created_at).toLocaleString(), '</td>',
          '<td class="text-end">',
          '<button class="btn btn-sm btn-outline-primary" onclick="viewFunction(', f.id, ')">View Source</button>',
          '</td>'
        ].join('');
      }
      tb.appendChild(tr);
    });
  } catch (e) {
    showToast('Functions', e.message, 'danger');
  }
}

// ===================== LOGS =====================
async function loadLogs() {
  try {
    const logs = await api('/logs');
    const tb = document.getElementById('logsTableBody');
    tb.innerHTML = '';
    if (!logs || logs.length === 0) {
      tb.innerHTML = '<tr><td colspan="6" class="text-center text-muted py-4">No recent executions.</td></tr>';
      return;
    }
    logs.forEach(lg => {
      const tr = document.createElement('tr');
      const badge = lg.success
        ? '<span class="badge bg-success"><i class="bi bi-check-circle me-1"></i>Success</span>'
        : '<span class="badge bg-danger"><i class="bi bi-exclamation-triangle me-1"></i>Error</span>';

      const pName = lg.project_name ? lg.project_name : '<span class="text-muted">Personal</span>';

      tr.innerHTML = [
        '<td class="font-monospace text-muted">#', lg.id, '</td>',
        '<td class="fw-semibold">', lg.function_name || 'Unknown Function', '</td>',
        '<td>', pName, '</td>',
        '<td>', badge, '</td>',
        '<td><span class="badge rounded-pill text-bg-light border">', lg.latency_ms, ' ms</span></td>',
        '<td class="small text-muted">', new Date(lg.created_at).toLocaleString(), '</td>'
      ].join('');
      tb.appendChild(tr);
    });
  } catch (e) {
    showToast('Logs', e.message, 'danger');
  }
}

// ===================== STATS =====================
let callsChart, successChart;
async function loadStats() {
  try {
    const data = await api('/stats');
    document.getElementById('statTotalFunctions').textContent = data.totals.functions;
    document.getElementById('statCalls24h').textContent = data.totals.calls24h;
    document.getElementById('statSuccessRate').textContent = (data.totals.successRate * 100).toFixed(1) + '%';
    document.getElementById('statTopFunction').textContent = data.totals.topFunction || 'N/A';

    renderCharts(data.byFunction, data.outcomes);
  } catch (e) {
    showToast('Stats', 'Could not load stats', 'warning');
  }
}

function renderCharts(byFn, outcomes) {
  if (callsChart) callsChart.destroy();
  if (successChart) successChart.destroy();

  const ctxCalls = document.getElementById('chartCalls');
  if (ctxCalls && byFn.length > 0) {
    callsChart = new Chart(ctxCalls, {
      type: 'bar',
      data: {
        labels: byFn.map(x => (x.label || 'Fn ' + x.id).substring(0, 15)),
        datasets: [{
          label: 'Total Calls',
          data: byFn.map(x => x.calls),
          backgroundColor: '#0d6efd',
          borderRadius: 4
        }]
      },
      options: { responsive: true, maintainAspectRatio: false }
    });
  }

  const ctxSuc = document.getElementById('chartSuccess');
  if (ctxSuc && (outcomes.success > 0 || outcomes.error > 0)) {
    successChart = new Chart(ctxSuc, {
      type: 'doughnut',
      data: {
        labels: ['Success', 'Error'],
        datasets: [{
          data: [outcomes.success, outcomes.error],
          backgroundColor: ['#198754', '#dc3545']
        }]
      },
      options: { responsive: true, maintainAspectRatio: false }
    });
  }
}

// ===================== AI GENERATION =====================
async function onGenerateAI() {
  const prompt = document.getElementById('aiPrompt').value.trim();
  const current_code = getEditorValue();
  if (!prompt) return showToast('AI', 'Please provide a prompt.', 'warning');

  const btnAI = document.getElementById('btnGenerateAI');
  const loadingUI = document.getElementById('aiLoadingUI');

  if (btnAI) btnAI.style.display = 'none';
  if (loadingUI) loadingUI.style.display = 'flex';

  showToast('AI', 'Generating function...', 'info');

  try {
    const res = await api('/generate_function', {
      method: 'POST',
      body: JSON.stringify({ prompt, current_code }),
    });

    if (res.error) throw new Error(res.error);

    if (typeof editor !== "undefined" && editor && typeof editor.setValue === "function") {
      editor.setValue(res.code || "");
      editor.refresh();
    } else {
      const codeBox = document.getElementById("codeEditor");
      if (codeBox) codeBox.value = res.code || "";
    }

    if (res.description) {
      const descField = document.getElementById("functionDesc");
      if (descField) descField.value = res.description;
    }

    showToast('AI', 'Code & description generated successfully!', 'success');
  } catch (e) {
    showToast('AI', e.message || 'Error generating code.', 'danger');
  } finally {
    if (btnAI) btnAI.style.display = '';
    if (loadingUI) loadingUI.style.display = 'none';
  }
}

// ===================== API SNIPPET =====================
window.copyToClipboard = function (elementId) {
  const el = document.getElementById(elementId);
  if (!el) return;
  el.select();
  document.execCommand("copy");
  showToast("Copied", "Copied to clipboard!", "success");
}

window.viewApiSnippet = async function (fnId, projId) {
  const modalObj = new bootstrap.Modal(document.getElementById('apiSnippetModal'));

  const spanWarning = document.getElementById('snippetTokenWarning');
  const spanToken = document.getElementById('snippetToken');
  const inpEndpoint = document.getElementById('snippetEndpoint');
  const txtBody = document.getElementById('snippetBody');
  const txtCurl = document.getElementById('snippetCurl');

  spanWarning.classList.add('d-none');
  spanToken.textContent = "loading...";

  // Endpoint URL
  const endpoint = window.location.origin + "/ofa";
  inpEndpoint.value = endpoint;

  // JSON Body
  const reqBody = {
    id: fnId,
    api_args: {}
  };
  const bodyStr = JSON.stringify(reqBody, null, 2);
  txtBody.value = bodyStr;

  modalObj.show();

  let tokenToUse = AUTH_TOKEN; // Fallback to personal JWT

  try {
    if (projId) {
      const tokens = await api("/projects/" + projId + "/tokens");
      if (tokens && tokens.length > 0) {
        tokenToUse = tokens[0].token;
      } else {
        spanWarning.classList.remove('d-none');
      }
    } else {
      spanWarning.classList.remove('d-none');
      spanWarning.innerHTML = '<br><i class="bi bi-info-circle-fill"></i> No project assigned. Using your session JWT.';
    }
  } catch (e) {
    console.warn("Could not fetch project token:", e);
    spanWarning.classList.remove('d-none');
  }

  spanToken.textContent = tokenToUse;

  // cURL construction
  const curlCmd = `curl -X POST "${endpoint}" \\
  -H "Content-Type: application/json" \\
  -H "Authorization: Bearer ${tokenToUse}" \\
  -d '${JSON.stringify(reqBody)}'`;

  txtCurl.value = curlCmd;
}
