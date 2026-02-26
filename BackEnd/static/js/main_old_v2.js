
// ===================== GLOBAL =====================
const API_BASE = '';
let AUTH_TOKEN = localStorage.getItem('ss_token') || null;
let CURRENT_USER = null;
let editor;
let currentDraftId = null;

// ===================== BASIC HELPERS =====================
async function api(path, options = {}) {
  const headers = { 'Content-Type': 'application/json', ...(options.headers || {}) };
  if (AUTH_TOKEN) headers['Authorization'] = `Bearer ${AUTH_TOKEN}`;
  const res = await fetch(API_BASE + path, { ...options, headers });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

function getEditorValue() {
  return editor ? editor.getValue() : document.getElementById('codeEditor').value;
}

function showToast(title, body, type = 'info') {
  const icon = {
    success: 'bi-check-circle-fill text-success',
    danger: 'bi-x-circle-fill text-danger',
    warning: 'bi-exclamation-triangle-fill text-warning',
    info: 'bi-info-circle-fill text-info'
  }[type] || 'bi-info-circle-fill text-info';

  // Ensure container exists
  let container = document.getElementById('toastContainer');
  if (!container) {
    container = document.createElement('div');
    container.id = 'toastContainer';
    container.className = 'toast-container position-fixed bottom-0 end-0 p-3';
    document.body.appendChild(container);
  }

  const toastEl = document.createElement('div');
  toastEl.className = 'toast align-items-center text-bg-light border-0 show shadow-sm mb-2';
  toastEl.role = 'alert';
  toastEl.innerHTML = `
    <div class="d-flex">
      <div class="toast-body">
        <i class="bi ${icon} me-2"></i><strong>${title}:</strong> ${body}
      </div>
      <button type="button" class="btn-close me-2 m-auto" data-bs-dismiss="toast"></button>
    </div>
  `;

  container.appendChild(toastEl);

  // Auto-remove after 4s
  setTimeout(() => toastEl.remove(), 4000);
}


function safeJSONParse(text, fallback = {}) {
  try { return JSON.parse(text); } catch { return fallback; }
}

// ===================== INITIALIZATION =====================
document.addEventListener('DOMContentLoaded', () => {
  // Init CodeMirror
  const el = document.getElementById('codeEditor');
  if (el) {
    editor = CodeMirror.fromTextArea(el, {
      mode: 'python', theme: 'dracula', lineNumbers: true, autoCloseBrackets: true, indentUnit: 4
    });
  }

  // Button bindings
  const btnSave = document.getElementById('btnSaveDraft');
  const btnTest = document.getElementById('btnDraftTest');
  const btnPromote = document.getElementById('btnPromote');
  if (btnSave) btnSave.addEventListener('click', onSaveDraft);
  if (btnTest) btnTest.addEventListener('click', onTestDraft);
  if (btnPromote) btnPromote.addEventListener('click', onPromoteDraft);
});

// ===================== DRAFT API =====================
async function saveDraft(desc, code, visibility, draftId) {
  const body = { description: desc, code, visibility };
  if (draftId) body.id = draftId;
  return api('/drafts', { method: 'POST', body: JSON.stringify(body) });
}

async function testDraftAPI(draftId, args) {
  return api(`/drafts/${draftId}:test`, { method: 'POST', body: JSON.stringify({ args }) });
}

async function promoteDraftAPI(draftId) {
  return api(`/drafts/${draftId}:promote`, { method: 'POST' });
}

// ===================== UI HANDLERS =====================
async function onSaveDraft() {
  console.log("clicked")
  const desc = document.getElementById('functionDesc').value.trim();
  const code = getEditorValue();
  const visibility = document.getElementById('functionVisibility').value;

  if (!desc) return showToast('Draft', 'Please add a description.', 'warning');
  if (!code.includes('def api_def')) return showToast('Draft', "Your code must define 'def api_def(args): ...'", 'warning');

  try {
    const res = await saveDraft(desc, code, visibility, currentDraftId);
    if (res.error) throw new Error(res.error);
    currentDraftId = res.id;
    const label = document.getElementById('currentDraftId');
    if (label) label.textContent = currentDraftId;
    showToast('Draft', `Saved draft #${currentDraftId}`, 'success');
  } catch (err) {
    showToast('Draft', err.message || 'Failed to save draft', 'danger');
  }
}

async function onTestDraft() {
  if (!currentDraftId) return showToast('Test', 'Please save the draft first.', 'warning');
  const args = safeJSONParse(document.getElementById('testParams').value, {});
  document.getElementById('outputBox').textContent = '⏳ Testing draft...';
  try {
    const res = await testDraftAPI(currentDraftId, args);
    document.getElementById('outputBox').textContent = JSON.stringify(res, null, 2);
    showToast('Test', res.error ? 'Error during test' : 'Executed successfully.', res.error ? 'danger' : 'success');
  } catch (e) {
    document.getElementById('outputBox').textContent = e.message;
    showToast('Test', 'Test failed', 'danger');
  }
}

async function onPromoteDraft() {
  if (!currentDraftId) return showToast('Promote', 'No draft to promote.', 'warning');
  try {
    const res = await promoteDraftAPI(currentDraftId);
    if (res.error) throw new Error(res.error);
    showToast('Promote', `Draft #${currentDraftId} promoted to prod #${res.id}`, 'success');
  } catch (e) {
    showToast('Promote', e.message || 'Promotion failed', 'danger');
  }
}
