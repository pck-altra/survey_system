'use strict';

// ================================================================
// CONFIG
// ================================================================
const API_BASE = 'http://localhost:8000/api';
const TOKEN_KEY = 'survey_token';
const USER_KEY  = 'survey_user';

// ================================================================
// API CLIENT
// ================================================================
async function api(path, options = {}) {
  const token = localStorage.getItem(TOKEN_KEY);
  const headers = { 'Content-Type': 'application/json', ...options.headers };
  if (token) headers['Authorization'] = `Bearer ${token}`;

  const res = await fetch(`${API_BASE}${path}`, { ...options, headers });
  const body = await res.text();

  if (!res.ok) {
    let msg = body;
    try { msg = JSON.parse(body).detail || body; } catch (_) {}
    throw new Error(msg);
  }

  if (res.status === 204) return null;
  try { return JSON.parse(body); } catch (_) { return body; }
}

// ================================================================
// AUTH HELPERS
// ================================================================
function getToken()  { return localStorage.getItem(TOKEN_KEY); }
function getUser()  { try { return JSON.parse(localStorage.getItem(USER_KEY) || 'null'); } catch (_) { return null; } }

function setAuth(token, user) {
  localStorage.setItem(TOKEN_KEY, token);
  localStorage.setItem(USER_KEY, JSON.stringify(user));
}

function clearAuth() {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
}

function requireAuth() {
  if (!getToken()) showView('auth');
}

// ================================================================
// VIEW ROUTING
// ================================================================
function showView(name, data = {}) {
  document.querySelectorAll('.view').forEach(el => el.classList.add('hidden'));
  const nav = document.getElementById('nav-bar');

  if (name === 'auth') {
    nav.classList.add('hidden');
    document.getElementById('view-auth').classList.remove('hidden');
    document.getElementById('form-login').classList.remove('hidden');
    document.getElementById('form-register').classList.add('hidden');
  } else {
    nav.classList.remove('hidden');
    document.getElementById(`view-${name}`).classList.remove('hidden');
  }

  if (name === 'dashboard')  renderDashboard();
  if (name === 'editor')     initEditor(data);
  if (name === 'fill')       initFillSurvey(data);
  if (name === 'stats')      renderStats(data);
}

// ================================================================
// TOAST
// ================================================================
let toastTimer;
function showToast(msg, type = 'info') {
  const el = document.getElementById('toast');
  el.textContent = msg;
  el.className = `toast ${type}`;
  el.classList.remove('hidden');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.add('hidden'), 3000);
}

// ================================================================
// AUTH TAB SWITCHING
// ================================================================
document.querySelectorAll('.tab-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    const tab = btn.dataset.tab;
    document.getElementById('form-login').classList.toggle('hidden', tab !== 'login');
    document.getElementById('form-register').classList.toggle('hidden', tab !== 'register');
  });
});

// ================================================================
// AUTH FORMS
// ================================================================

// Remember where the user was trying to go before being bounced to login.
function pendingRedirect() {
  const r = new URLSearchParams(window.location.search).get('redirect');
  return r ? decodeURIComponent(r) : null;
}

function goAfterAuth() {
  const target = pendingRedirect();
  if (target) {
    // Strip the redirect param from our own URL so it doesn't re-trigger
    const url = new URL(window.location.href);
    url.searchParams.delete('redirect');
    window.history.replaceState({}, '', url.toString());
    window.location.replace(target);
  } else {
    showView('dashboard');
  }
}

document.getElementById('form-login').addEventListener('submit', async e => {
  e.preventDefault();
  const errEl = document.getElementById('login-error');
  errEl.classList.add('hidden');
  const username = document.getElementById('login-username').value.trim();
  const password = document.getElementById('login-password').value;

  try {
    const data = await api(`/auth/login?username=${encodeURIComponent(username)}&password=${encodeURIComponent(password)}`, { method: 'POST' });
    // Store the token *immediately* before any subsequent API calls,
    // otherwise /auth/me (and the fill start endpoints) would race ahead
    // without an Authorization header and return 401.
    setAuth(data.access_token, { username });
    const user = await api('/auth/me');
    setAuth(data.access_token, user);  // refresh with the real user info
    showToast(`欢迎回来，${user.username}！`, 'success');
    goAfterAuth();
  } catch (err) {
    errEl.textContent = err.message;
    errEl.classList.remove('hidden');
  }
});

document.getElementById('form-register').addEventListener('submit', async e => {
  e.preventDefault();
  const errEl = document.getElementById('reg-error');
  errEl.classList.add('hidden');
  const username = document.getElementById('reg-username').value.trim();
  const password = document.getElementById('reg-password').value;

  try {
    const user = await api('/auth/register', {
      method: 'POST',
      body: JSON.stringify({ username, password }),
    });
    // auto-login after register
    const token = await api(`/auth/login?username=${encodeURIComponent(username)}&password=${encodeURIComponent(password)}`, { method: 'POST' });
    setAuth(token.access_token, user);
    showToast(`注册成功，${user.username}！`, 'success');
    goAfterAuth();
  } catch (err) {
    errEl.textContent = err.message;
    errEl.classList.remove('hidden');
  }
});

// ================================================================
// NAVIGATION
// ================================================================
document.getElementById('nav-dashboard').addEventListener('click', () => showView('dashboard'));
document.getElementById('nav-create').addEventListener('click', () => showView('editor', {}));
document.getElementById('nav-logout').addEventListener('click', () => {
  clearAuth();
  showView('auth');
  showToast('已退出登录', 'info');
});

document.getElementById('btn-back-list').addEventListener('click', () => showView('dashboard'));
document.getElementById('btn-back-from-stats').addEventListener('click', () => showView('dashboard'));

// ================================================================
// DASHBOARD
// ================================================================
async function renderDashboard() {
  const listEl = document.getElementById('survey-list');
  listEl.innerHTML = '<p class="meta">加载中...</p>';

  try {
    const data = await api('/surveys/');
    const surveys = data.items || [];

    if (surveys.length === 0) {
      listEl.innerHTML = '<p class="meta">暂无问卷，<button class="btn secondary small" id="empty-create">创建一个</button></p>';
      document.getElementById('empty-create')?.addEventListener('click', () => showView('editor', {}));
      return;
    }

    listEl.innerHTML = surveys.map(s => `
      <div class="survey-card">
        <div class="info">
          <div class="title">${escHtml(s.title)}</div>
          <div class="meta">
            <span class="status-badge status-${s.status}">${statusText(s.status)}</span>
            &nbsp;创建于 ${fmt(s.created_at)}
            ${s.token ? `&nbsp;·&nbsp;Token: <code>${s.token}</code>` : ''}
          </div>
        </div>
        <div class="actions">
          <button class="btn secondary small" onclick="showView('editor', {surveyId:'${s.id}', edit:true})">编辑</button>
          ${s.status === 'published' ? `<button class="btn secondary small" onclick="copyToken('${s.token}')">复制链接</button>` : ''}
          ${s.status !== 'draft' ? `<button class="btn secondary small" onclick="showView('stats', {surveyId:'${s.id}', title:'${escHtml(s.title)}'})">统计</button>` : ''}
          ${s.status === 'draft' ? `<button class="btn primary small" onclick="publishSurvey('${s.id}')">发布</button>` : ''}
          ${s.status === 'published' ? `<button class="btn danger small" onclick="closeSurvey('${s.id}')">关闭</button>` : ''}
          ${s.status === 'draft' ? `<button class="btn danger small" onclick="deleteSurvey('${s.id}')">删除</button>` : ''}
        </div>
      </div>
    `).join('');
  } catch (err) {
    listEl.innerHTML = `<p class="form-error">加载失败: ${err.message}</p>`;
  }
}

// ================================================================
// SURVEY EDITOR
// ================================================================
// Global editor state
let editorState = { surveyId: null, survey: null, questions: [] };

async function initEditor({ surveyId = null, edit = false } = {}) {
  editorState = { surveyId, survey: null, questions: [] };

  document.getElementById('editor-title').textContent = edit ? '编辑问卷' : '创建问卷';
  document.getElementById('form-survey-meta').reset();

  if (edit && surveyId) {
    try {
      const s = await api(`/surveys/${surveyId}`);
      editorState.survey = s;
      document.getElementById('survey-title').value = s.title || '';
      document.getElementById('survey-desc').value = s.description || '';
      document.getElementById('survey-anon').checked = s.allow_anonymous || false;

      const qs = await api(`/surveys/${surveyId}/questions`);
      editorState.questions = qs;
      renderQuestionList();

      // If published, hide meta + question forms
      const isPublished = s.status !== 'draft';
      document.getElementById('form-survey-meta').querySelector('button').disabled = isPublished;
      document.getElementById('btn-add-question').style.display = isPublished ? 'none' : '';
      document.getElementById('btn-publish-survey').style.display = isPublished ? 'none' : '';
    } catch (err) {
      showToast('加载问卷失败: ' + err.message, 'error');
    }
  }
}

function renderQuestionList() {
  const el = document.getElementById('question-list');
  if (!editorState.questions.length) {
    el.innerHTML = '<p class="meta">暂无题目</p>';
    return;
  }
  el.innerHTML = editorState.questions.map(q => `
    <div class="question-item">
      <div class="q-header">
        <span class="q-title">${q.order}. ${escHtml(q.title)}</span>
        <span class="q-type">${typeLabel(q.type)}</span>
      </div>
      ${q.options ? `<div class="q-meta">选项: ${q.options.join('、')}</div>` : ''}
      <div class="q-meta">${q.required ? '✅ 必答' : '❌ 选答'} · ${nextRuleLabel(q.next_rule)}</div>
      <div class="q-actions">
        <button class="btn secondary small" onclick="openEditModal(${q.order})">编辑</button>
        <button class="btn danger small" onclick="deleteQuestion(${q.order})">删除</button>
      </div>
    </div>
  `).join('');
}

// Save meta (create or update)
document.getElementById('form-survey-meta').addEventListener('submit', async e => {
  e.preventDefault();
  const title = document.getElementById('survey-title').value.trim();
  const description = document.getElementById('survey-desc').value.trim();
  const allow_anonymous = document.getElementById('survey-anon').checked;

  try {
    if (!editorState.surveyId) {
      // Create
      const s = await api('/surveys/', {
        method: 'POST',
        body: JSON.stringify({ title, description, allow_anonymous }),
      });
      editorState.surveyId = s.id;
      editorState.survey = s;
      document.getElementById('editor-title').textContent = '编辑问卷';
      showToast('问卷已创建', 'success');
    } else {
      // Update
      const s = await api(`/surveys/${editorState.surveyId}`, {
        method: 'PATCH',
        body: JSON.stringify({ title, description, allow_anonymous }),
      });
      editorState.survey = s;
      showToast('问卷已保存', 'success');
    }
  } catch (err) {
    showToast('保存失败: ' + err.message, 'error');
  }
});

// Publish
document.getElementById('btn-publish-survey').addEventListener('click', async () => {
  if (!editorState.surveyId) { showToast('请先保存问卷基本信息', 'error'); return; }
  try {
    const s = await api(`/surveys/${editorState.surveyId}/publish`, { method: 'POST' });
    editorState.survey = s;
    showToast(`发布成功！Token: ${s.token}`, 'success');
    document.getElementById('btn-publish-survey').style.display = 'none';
    document.getElementById('btn-add-question').style.display = 'none';
    document.getElementById('form-survey-meta').querySelector('button').disabled = true;
  } catch (err) {
    showToast('发布失败: ' + err.message, 'error');
  }
});

// ================================================================
// BRANCH ROW HELPERS (by_option jump config)
// ================================================================

/**
 * Render branch config rows for a given set of options.
 * prefix: 'q-' for add form, 'edit-q-' for edit modal.
 * existing: array of {when, goto} from an existing next_rule.branches.
 */
function renderBranchRows(prefix, options, existing) {
  const container = document.getElementById(`${prefix}-branch-rows`);
  if (!container) return;
  container.innerHTML = (options || []).map((opt, i) => {
    const saved = existing ? (existing.find(b => b.when === opt) || {}) : {};
    const gotoVal = saved.goto !== undefined && saved.goto !== null ? String(saved.goto) : '';
    return `<div style="display:flex;gap:8px;align-items:center;margin-bottom:4px;">
      <span style="flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" title="${escHtml(opt)}">${escHtml(opt)}</span>
      <input type="number" min="1" placeholder="下一题" value="${gotoVal}"
             data-option="${escAttr(opt)}"
             style="width:80px;" />
    </div>`;
  }).join('');
}

/**
 * Read branch rows from the DOM and return a branches array.
 */
function readBranchRows(prefix) {
  const container = document.getElementById(`${prefix}-branch-rows`);
  if (!container) return [];
  const rows = container.querySelectorAll('input[data-option]');
  return Array.from(rows).map(row => {
    const opt = row.dataset.option;
    const val = row.value.trim();
    return { when: opt, goto: val ? parseInt(val, 10) : null };
  }).filter(b => b.goto !== null);
}

/**
 * Rebuild next_rule based on the selected mode and branch config.
 */
function buildNextRule(nextMode, branches) {
  if (nextMode === 'by_option') {
    return { mode: 'by_option', fallback: 'next', branches };
  }
  if (nextMode === 'end') {
    return { mode: 'default', fallback: 'end' };
  }
  return { mode: 'default', fallback: 'next' };
}

// ================================================================
// QUESTION TYPE CHANGE — toggle options + reset branch visibility
// ================================================================
document.getElementById('q-type').addEventListener('change', () => {
  const type = document.getElementById('q-type').value;
  const optBox = document.getElementById('q-options-box');
  optBox.classList.toggle('hidden', type === 'text' || type === 'number');
  const ruleSel = document.getElementById('q-next-rule');
  ruleSel.value = 'next';
  document.getElementById('q-branches-box').classList.add('hidden');
});

// ================================================================
// NEXT RULE CHANGE — show/hide branch config
// ================================================================
document.getElementById('q-next-rule').addEventListener('change', () => {
  const mode = document.getElementById('q-next-rule').value;
  const branchesBox = document.getElementById('q-branches-box');
  if (mode === 'by_option') {
    const type = document.getElementById('q-type').value;
    if (type === 'single' || type === 'multi') {
      const raw = document.getElementById('q-options').value.trim();
      const opts = raw ? raw.split('\n').map(o => o.trim()).filter(Boolean) : [];
      renderBranchRows('q', opts, []);
    }
    branchesBox.classList.remove('hidden');
  } else {
    branchesBox.classList.add('hidden');
  }
});

// ================================================================
// OPTIONS CHANGE — re-render branch rows if in by_option mode
// ================================================================
document.getElementById('q-options').addEventListener('input', () => {
  const mode = document.getElementById('q-next-rule').value;
  if (mode !== 'by_option') return;
  const raw = document.getElementById('q-options').value.trim();
  const opts = raw ? raw.split('\n').map(o => o.trim()).filter(Boolean) : [];
  renderBranchRows('q', opts, []);
});

// ================================================================
// ADD QUESTION
// ================================================================
document.getElementById('btn-add-question').addEventListener('click', async () => {
  if (!editorState.surveyId) { showToast('请先保存问卷基本信息', 'error'); return; }

  const type    = document.getElementById('q-type').value;
  const title   = document.getElementById('q-title').value.trim();
  const required = document.getElementById('q-required').checked;

  let options = null;
  if (type === 'single' || type === 'multi') {
    const raw = document.getElementById('q-options').value.trim();
    if (!raw) { showToast('请填写选项', 'error'); return; }
    options = raw.split('\n').map(o => o.trim()).filter(Boolean);
  }

  const nextMode = document.getElementById('q-next-rule').value;
  const branches = readBranchRows('q');
  const next_rule = buildNextRule(nextMode, branches);

  try {
    const q = await api(`/surveys/${editorState.surveyId}/questions`, {
      method: 'POST',
      body: JSON.stringify({ type, title, required, options, next_rule }),
    });
    editorState.questions.push(q);
    renderQuestionList();
    // clear form
    document.getElementById('q-title').value = '';
    document.getElementById('q-options').value = '';
    document.getElementById('q-required').checked = false;
    document.getElementById('q-next-rule').value = 'next';
    document.getElementById('q-branches-box').classList.add('hidden');
    document.getElementById('q-branch-rows').innerHTML = '';
    showToast('题目已添加', 'success');
  } catch (err) {
    showToast('添加题目失败: ' + err.message, 'error');
  }
});

// Modal state: which question order is being edited
let editModalOrder = null;

// Open edit modal and populate fields
function openEditModal(order) {
  const q = editorState.questions.find(x => x.order === order);
  if (!q) return;
  editModalOrder = order;

  document.getElementById('modal-title').textContent = `编辑题目 ${order}`;
  document.getElementById('edit-q-type').value = q.type;
  document.getElementById('edit-q-title').value = q.title;
  document.getElementById('edit-q-required').checked = q.required;
  document.getElementById('edit-q-options').value = (q.options || []).join('\n');

  // toggle options visibility
  const optBox = document.getElementById('edit-q-options-box');
  optBox.classList.toggle('hidden', q.type === 'text' || q.type === 'number');

  // next rule fallback
  const rule = q.next_rule || {};
  const sel = document.getElementById('edit-q-next-rule');
  if (rule.mode === 'by_option') {
    sel.value = 'by_option';
    const branchesBox = document.getElementById('edit-q-branches-box');
    renderBranchRows('edit-q', q.options || [], rule.branches || []);
    branchesBox.classList.remove('hidden');
  } else {
    sel.value = (rule.mode === 'default' && rule.fallback === 'end') ? 'end' : 'next';
    document.getElementById('edit-q-branches-box').classList.add('hidden');
    document.getElementById('edit-q-branch-rows').innerHTML = '';
  }

  document.getElementById('edit-modal').classList.remove('hidden');
}

// Close modal
function closeEditModal() {
  document.getElementById('edit-modal').classList.add('hidden');
  editModalOrder = null;
}

document.getElementById('modal-close-btn').addEventListener('click', closeEditModal);
document.getElementById('modal-backdrop').addEventListener('click', closeEditModal);

// Edit modal: next rule change — show/hide branch config
document.getElementById('edit-q-next-rule').addEventListener('change', () => {
  const mode = document.getElementById('edit-q-next-rule').value;
  const branchesBox = document.getElementById('edit-q-branches-box');
  if (mode === 'by_option') {
    const q = editorState.questions.find(x => x.order === editModalOrder);
    if (q && (q.type === 'single' || q.type === 'multi')) {
      renderBranchRows('edit-q', q.options || [], []);
    }
    branchesBox.classList.remove('hidden');
  } else {
    branchesBox.classList.add('hidden');
    document.getElementById('edit-q-branch-rows').innerHTML = '';
  }
});

// Edit modal: options change — re-render branch rows if in by_option mode
document.getElementById('edit-q-options').addEventListener('input', () => {
  const mode = document.getElementById('edit-q-next-rule').value;
  if (mode !== 'by_option') return;
  const raw = document.getElementById('edit-q-options').value.trim();
  const opts = raw ? raw.split('\n').map(o => o.trim()).filter(Boolean) : [];
  renderBranchRows('edit-q', opts, []);
});

// Save edit
document.getElementById('form-edit-question').addEventListener('submit', async e => {
  e.preventDefault();
  if (editModalOrder === null) return;

  const title   = document.getElementById('edit-q-title').value.trim();
  const required = document.getElementById('edit-q-required').checked;
  const nextMode = document.getElementById('edit-q-next-rule').value;
  const branches = readBranchRows('edit-q');
  const next_rule = buildNextRule(nextMode, branches);

  const q = editorState.questions.find(x => x.order === editModalOrder);
  let options = null;
  if (q.type === 'single' || q.type === 'multi') {
    const raw = document.getElementById('edit-q-options').value.trim();
    if (!raw) { showToast('请填写选项', 'error'); return; }
    options = raw.split('\n').map(o => o.trim()).filter(Boolean);
  }

  try {
    const updated = await api(`/surveys/${editorState.surveyId}/questions/${editModalOrder}`, {
      method: 'PUT',
      body: JSON.stringify({ title, required, options, next_rule }),
    });
    // sync local state
    const idx = editorState.questions.findIndex(x => x.order === editModalOrder);
    if (idx !== -1) editorState.questions[idx] = updated;
    renderQuestionList();
    closeEditModal();
    showToast('题目已更新', 'success');
  } catch (err) {
    showToast('保存失败: ' + err.message, 'error');
  }
});

// Delete question
async function deleteQuestion(order) {
  if (!confirm(`确认删除第 ${order} 题？`)) return;
  try {
    await api(`/surveys/${editorState.surveyId}/questions/${order}`, { method: 'DELETE' });
    editorState.questions = editorState.questions.filter(x => x.order !== order);
    renderQuestionList();
    showToast('题目已删除', 'success');
  } catch (err) {
    showToast('删除失败: ' + err.message, 'error');
  }
}

// ================================================================
// FILL SURVEY
// ================================================================
let fillState = { survey: null, questions: [], submissionId: null, currentOrder: null, answers: {} };

async function initFillSurvey({ token } = {}) {
  try {
    const survey = await api(`/surveys/token/${token}`);
    fillState.survey = survey;

    const questions = await api(`/surveys/${survey.id}/questions`);
    fillState.questions = questions;
    fillState.answers = {};

    // Start submission
    const start = await api(`/surveys/${survey.id}/submit/start`, { method: 'POST' });
    fillState.submissionId = start.submission_id;
    fillState.currentOrder = start.next_order;

    renderFillHeader();
    renderFillQuestion();
  } catch (err) {
    // 401 — token expired or invalid; bounce to login
    if (String(err.message).toLowerCase().includes('not authenticated')) {
      clearAuth();
      const returnTo = encodeURIComponent(`index.html?token=${token}`);
      window.location.replace(`index.html?redirect=${returnTo}`);
      return;
    }
    document.getElementById('fill-header').innerHTML = `<p class="form-error">加载失败: ${err.message}</p>`;
  }
}

function renderFillHeader() {
  const s = fillState.survey;
  document.getElementById('fill-header').innerHTML = `
    <h2>${escHtml(s.title)}</h2>
    ${s.description ? `<p style="color:var(--text-muted)">${escHtml(s.description)}</p>` : ''}
  `;
}

function renderFillQuestion() {
  const errEl = document.getElementById('fill-error');
  errEl.classList.add('hidden');

  const q = fillState.questions.find(q => q.order === fillState.currentOrder);
  if (!q) {
    // All done
    finishFill();
    return;
  }

  const total = fillState.questions.length;
  const done  = fillState.questions.filter(x => x.order < fillState.currentOrder).length;
  const pct   = Math.round((done / total) * 100);
  document.getElementById('fill-progress-bar').style.width = pct + '%';

  const card = document.createElement('div');
  card.className = 'fill-card';
  card.innerHTML = `
    <div class="q-title">
      ${escHtml(q.title)}
      ${q.required ? '<span class="q-required-note"> * 必答</span>' : ''}
    </div>
    ${renderQuestionInput(q)}
    <div class="fill-nav">
      ${fillState.answers[q.order] !== undefined
        ? `<button class="btn secondary" id="btn-prev">← 上一题</button>`
        : '<span></span>'}
      <button class="btn primary" id="btn-next">${nextLabel(q)} →</button>
    </div>
  `;

  const container = document.getElementById('fill-question');
  container.innerHTML = '';
  container.appendChild(card);

  // Restore answer if exists
  if (fillState.answers[q.order] !== undefined) {
    restoreAnswer(q, fillState.answers[q.order]);
  }

  card.querySelector('#btn-next').addEventListener('click', () => submitCurrentAnswer(q));
  card.querySelector('#btn-prev')?.addEventListener('click', () => goToPrevQuestion(q));
}

function renderQuestionInput(q) {
  if (q.type === 'single') {
    return `<div class="options-list">
      ${(q.options || []).map((opt, i) => `
        <label class="option-item" data-value="${escHtml(opt)}">
          <input type="radio" name="q-opt" value="${escHtml(opt)}" ${i === 0 ? 'checked' : ''} />
          ${escHtml(opt)}
        </label>
      `).join('')}
    </div>`;
  }
  if (q.type === 'multi') {
    return `<div class="options-list">
      ${(q.options || []).map(opt => `
        <label class="option-item" data-value="${escHtml(opt)}">
          <input type="checkbox" name="q-opt" value="${escHtml(opt)}" />
          ${escHtml(opt)}
        </label>
      `).join('')}
    </div>`;
  }
  if (q.type === 'text') {
    return `<textarea id="fill-text" rows="4" placeholder="请输入...">${fillState.answers[q.order] || ''}</textarea>`;
  }
  if (q.type === 'number') {
    return `<input type="number" id="fill-number" placeholder="请输入数字" value="${fillState.answers[q.order] || ''}" />`;
  }
  return '';
}

function restoreAnswer(q, value) {
  if (q.type === 'single') {
    const labels = document.querySelectorAll('.option-item');
    labels.forEach(l => {
      l.classList.toggle('selected', l.dataset.value === value);
      const radio = l.querySelector('input');
      if (radio) radio.checked = l.dataset.value === value;
    });
  } else if (q.type === 'multi') {
    const vals = Array.isArray(value) ? value : [];
    document.querySelectorAll('.option-item').forEach(l => {
      const checked = vals.includes(l.dataset.value);
      l.classList.toggle('selected', checked);
      const cb = l.querySelector('input');
      if (cb) cb.checked = checked;
    });
  }
}

function nextLabel(q) {
  const rule = q.next_rule || {};
  if (rule.mode === 'default' && rule.fallback === 'end') return '提交';
  return '下一题';
}

async function submitCurrentAnswer(q) {
  const errEl = document.getElementById('fill-error');
  errEl.classList.add('hidden');

  let value;
  if (q.type === 'single') {
    const checked = document.querySelector('input[name="q-opt"]:checked');
    if (!checked && q.required) { errEl.textContent = '请选择一个选项'; errEl.classList.remove('hidden'); return; }
    value = checked ? checked.value : null;
  } else if (q.type === 'multi') {
    const checked = [...document.querySelectorAll('input[name="q-opt"]:checked')].map(el => el.value);
    if (!checked.length && q.required) { errEl.textContent = '请至少选择一个选项'; errEl.classList.remove('hidden'); return; }
    value = checked;
  } else if (q.type === 'text') {
    value = document.getElementById('fill-text').value.trim();
    if (!value && q.required) { errEl.textContent = '请输入内容'; errEl.classList.remove('hidden'); return; }
  } else if (q.type === 'number') {
    value = parseFloat(document.getElementById('fill-number').value);
    if (isNaN(value) && q.required) { errEl.textContent = '请输入数字'; errEl.classList.remove('hidden'); return; }
  }

  if (value === null || (Array.isArray(value) && !value.length)) value = undefined;
  fillState.answers[q.order] = value;

  try {
    const result = await api(`/surveys/${fillState.survey.id}/submit/${fillState.submissionId}/answer`, {
      method: 'POST',
      body: JSON.stringify({ question_order: q.order, value }),
    });

    if (result.is_end) {
      await finishFill();
    } else {
      fillState.currentOrder = result.next_order;
      renderFillQuestion();
    }
  } catch (err) {
    errEl.textContent = err.message;
    errEl.classList.remove('hidden');
  }
}

async function goToPrevQuestion(q) {
  const orders = fillState.questions.map(x => x.order).sort((a, b) => a - b);
  const idx = orders.indexOf(q.order);
  if (idx > 0) {
    fillState.currentOrder = orders[idx - 1];
    renderFillQuestion();
  }
}

async function finishFill() {
  try {
    await api(`/surveys/${fillState.survey.id}/submit/${fillState.submissionId}/finalize`, { method: 'POST' });
    document.getElementById('fill-progress-bar').style.width = '100%';
    document.getElementById('fill-question').innerHTML = `
      <div class="fill-card" style="text-align:center">
        <h3>✅ 提交成功！</h3>
        <p style="color:var(--text-muted);margin-top:8px">感谢您的填写</p>
      </div>
    `;
    document.getElementById('fill-error').classList.add('hidden');
  } catch (err) {
    // 401 mid-submission: re-login and let the user retry
    if (String(err.message).toLowerCase().includes('not authenticated')) {
      clearAuth();
      const returnTo = encodeURIComponent(`index.html?token=${fillState.survey.token}`);
      window.location.replace(`index.html?redirect=${returnTo}`);
      return;
    }
    const errEl = document.getElementById('fill-error');
    errEl.textContent = '提交失败: ' + err.message;
    errEl.classList.remove('hidden');
  }
}

// ================================================================
// STATISTICS
// ================================================================
async function renderStats({ surveyId, title }) {
  const el = document.getElementById('stats-content');
  el.innerHTML = '<p>加载中...</p>';

  try {
    const stats = await api(`/surveys/${surveyId}/statistics`);
    let html = `<h3>${escHtml(title)}</h3>`;
    html += `<p class="meta">总提交数: <strong>${stats.total_submissions}</strong> &nbsp;·&nbsp; ` +
            `<span class="status-badge ${stats.is_anonymous ? 'status-draft' : 'status-published'}">` +
            `${stats.is_anonymous ? '匿名收集' : '实名收集'}</span></p>`;

    // Respondents list
    if (stats.respondents?.length) {
      html += '<div class="stats-card"><h4>👥 填写人</h4>';
      html += '<table class="respondents-table" style="width:100%;border-collapse:collapse;font-size:.9rem">';
      html += '<thead><tr style="border-bottom:1px solid #e2e8f0;text-align:left">' +
              '<th style="padding:6px 4px">序号</th>' +
              '<th style="padding:6px 4px">用户名</th>' +
              '<th style="padding:6px 4px">提交时间</th>' +
              '</tr></thead><tbody>';
      stats.respondents.forEach((r, i) => {
        const who = r.username
          ? `<strong>${escHtml(r.username)}</strong>`
          : '<em style="color:var(--text-muted)">匿名</em>';
        const when = r.submitted_at ? new Date(r.submitted_at).toLocaleString('zh-CN') : '-';
        html += `<tr style="border-bottom:1px solid #f1f5f9">` +
                `<td style="padding:6px 4px;color:var(--text-muted)">${i + 1}</td>` +
                `<td style="padding:6px 4px">${who}</td>` +
                `<td style="padding:6px 4px;color:var(--text-muted);font-size:.85rem">${escHtml(when)}</td>` +
                `</tr>`;
      });
      html += '</tbody></table></div>';
    } else {
      html += '<div class="stats-card"><h4>👥 填写人</h4>' +
              '<p class="meta" style="margin:0">暂无提交</p></div>';
    }

    // Single choice
    if (stats.single_choice?.length) {
      html += '<div class="stats-card"><h4>📌 单选题</h4>';
      for (const q of stats.single_choice) {
        html += `<div style="margin-bottom:16px">
          <div class="stat-row"><strong>${escHtml(q.title)}</strong><span>${q.total} 人</span></div>`;
        for (const c of (q.counts || [])) {
          const pct = q.total ? Math.round(c.count / q.total * 100) : 0;
          html += `<div class="stat-row">
            <span>${escHtml(c.value)}</span>
            <span>${c.count} (${pct}%)</span>
          </div>
          <div class="stat-bar-wrap"><div class="stat-bar" style="width:${pct}%"></div></div>`;
        }
        html += '</div>';
      }
      html += '</div>';
    }

    // Multi choice
    if (stats.multi_choice?.length) {
      html += '<div class="stats-card"><h4>☑️ 多选题</h4>';
      for (const q of stats.multi_choice) {
        html += `<div style="margin-bottom:16px">
          <div class="stat-row"><strong>${escHtml(q.title)}</strong></div>`;
        const maxCount = Math.max(...(q.counts || []).map(c => c.count), 1);
        for (const c of (q.counts || [])) {
          const pct = Math.round(c.count / maxCount * 100);
          html += `<div class="stat-row">
            <span>${escHtml(c.value)}</span>
            <span>${c.count} 次</span>
          </div>
          <div class="stat-bar-wrap"><div class="stat-bar" style="width:${pct}%"></div></div>`;
        }
        html += '</div>';
      }
      html += '</div>';
    }

    // Number
    if (stats.number_stats?.length) {
      html += '<div class="stats-card"><h4>🔢 数字题</h4>';
      for (const q of stats.number_stats) {
        html += `<div class="stat-row"><strong>${escHtml(q.title)}</strong></div>
        <div class="stat-row">
          <span>平均</span><span>${q.avg?.toFixed(2) ?? '-'} (${q.n}人)</span>
        </div>
        <div class="stat-row"><span>范围</span><span>${q.min} ~ ${q.max}</span></div>`;
      }
      html += '</div>';
    }

    // Text
    if (stats.text_answers?.length) {
      html += '<div class="stats-card"><h4>📝 文本题</h4>';
      for (const q of stats.text_answers) {
        html += `<div style="margin-bottom:12px">
          <div class="stat-row"><strong>${escHtml(q.title)}</strong><span>${(q.values||[]).length} 条</span></div>`;
        for (const v of (q.values || []).slice(0, 5)) {
          html += `<div style="background:#f7f8fa;padding:6px 10px;border-radius:4px;margin-top:4px;font-size:0.85rem">${escHtml(String(v))}</div>`;
        }
        html += '</div>';
      }
      html += '</div>';
    }

    if (!stats.single_choice?.length && !stats.multi_choice?.length &&
        !stats.number_stats?.length && !stats.text_answers?.length) {
      html += '<p class="meta" style="margin-top:12px">暂无数据</p>';
    }

    el.innerHTML = html;
  } catch (err) {
    el.innerHTML = `<p class="form-error">加载失败: ${err.message}</p>`;
  }
}

// ================================================================
// SURVEY ACTIONS
// ================================================================
async function publishSurvey(surveyId) {
  if (!confirm('确认发布？发布后无法添加/删除题目。')) return;
  try {
    await api(`/surveys/${surveyId}/publish`, { method: 'POST' });
    showToast('发布成功', 'success');
    renderDashboard();
  } catch (err) {
    showToast('发布失败: ' + err.message, 'error');
  }
}

async function closeSurvey(surveyId) {
  if (!confirm('确认关闭？关闭后无法继续填写。')) return;
  try {
    await api(`/surveys/${surveyId}/close`, { method: 'POST' });
    showToast('已关闭', 'info');
    renderDashboard();
  } catch (err) {
    showToast('关闭失败: ' + err.message, 'error');
  }
}

async function deleteSurvey(surveyId) {
  if (!confirm('确认删除？此操作不可恢复，题目和提交记录也会一并删除。')) return;
  try {
    await api(`/surveys/${surveyId}`, { method: 'DELETE' });
    showToast('问卷已删除', 'success');
    renderDashboard();
  } catch (err) {
    showToast('删除失败: ' + err.message, 'error');
  }
}

function copyToken(token) {
  const url = `${window.location.origin}${window.location.pathname.replace(/[^/]*$/,'')}fill.html?token=${token}`;
  navigator.clipboard.writeText(url).then(() => showToast('链接已复制到剪贴板', 'success'))
    .catch(() => showToast('复制失败，请手动复制', 'error'));
}

// ================================================================
// UTILITIES
// ================================================================
function escHtml(str) {
  const d = document.createElement('div');
  d.textContent = str;
  return d.innerHTML;
}

function escAttr(str) {
  return (str || '').replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

function fmt(iso) {
  if (!iso) return '-';
  const d = new Date(iso);
  return `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())}`;
}

function pad(n) { return String(n).padStart(2, '0'); }

function statusText(s) {
  return { draft: '草稿', published: '已发布', closed: '已关闭' }[s] || s;
}

function typeLabel(t) {
  return { single: '单选', multi: '多选', text: '文本', number: '数字' }[t] || t;
}

function nextRuleLabel(rule) {
  if (!rule) return '默认下一题';
  if (rule.mode === 'default' && rule.fallback === 'end') return '结束';
  if (rule.mode === 'by_option') return '按选项跳转';
  return '默认下一题';
}

// ================================================================
// BOOT
// ================================================================
// Option item click — toggle selection
document.addEventListener('change', e => {
  if (e.target.name === 'q-opt') {
    const label = e.target.closest('.option-item');
    if (!label) return;
    if (e.target.type === 'radio') {
      document.querySelectorAll('.option-item').forEach(l => l.classList.remove('selected'));
      label.classList.add('selected');
    } else {
      label.classList.toggle('selected', e.target.checked);
    }
  }
});

// Check token in URL for public fill, or auth redirect.
//
// Filling out a survey always requires authentication (the API enforces
// it via the submit/* endpoints). So when the URL carries a `?token=`,
// we must bounce the user to the login screen first if no token is in
// localStorage, then come back after they authenticate.
const urlParams = new URLSearchParams(window.location.search);
const fillToken = urlParams.get('token');
const hasRedirect = urlParams.has('redirect');

if (fillToken) {
  if (getToken()) {
    showView('fill', { token: fillToken });
  } else {
    // Mirror fill.html's gate: stash the intended destination so
    // goAfterAuth() can send the user back here once they log in.
    // Drop our own `?token=` first so the page renders the auth form.
    const returnTo = encodeURIComponent(`index.html?token=${fillToken}`);
    const url = new URL(window.location.href);
    url.searchParams.delete('token');
    url.searchParams.set('redirect', returnTo);
    window.history.replaceState({}, '', url.toString());
    showView('auth');
  }
} else if (getToken() && !hasRedirect) {
  showView('dashboard');
} else {
  showView('auth');
}
