'use strict';

// ================================================================
// BANK — 题库 / 可复用题目（需求变更）
// ---------------------------------------------------------------
// 对应《需求变更说明》的八条需求：
//   一 保存常用题目          → 新建题目 / 加入题库
//   二 分享给别人            → 共享面板（指定用户名 / 设为公开）
//   三 修改不影响已发布问卷  → 问卷里保存题目快照，修改题库只生成新版本
//   四 记录修改历史          → 版本历史面板（v1 → v2 → v3，可恢复）
//   五 不同版本同时存在      → 基于任一版本创建新版本
//   六 查看题目被哪些问卷使用 → 使用情况面板
//   七 建立题目库            → 题库标记 + 题库视图
//   八 单个题目的跨问卷统计  → 统计面板
// ================================================================

let bankState = {
  items: [],
  keyword: '',
  scope: 'all',
  onlyBank: false,
  editingId: null,   // 正在编辑（生成新版本）的题目 ID
  useTargetId: null, // 正在加入问卷的题目 ID
};

/** 题库版本内容缓存：{ versionId: { version, title, options, required, ... } } */
let bankVersionCache = {};

// ---------------------------------------------------------------
// 列表
// ---------------------------------------------------------------

async function renderBank() {
  const listEl = document.getElementById('bank-list');
  listEl.innerHTML = '<p class="meta">加载中...</p>';

  try {
    const params = new URLSearchParams({
      keyword: bankState.keyword,
      scope: bankState.scope,
      only_bank: String(bankState.onlyBank),
    });
    const items = await api(`/bank/questions?${params.toString()}`);
    bankState.items = items || [];

    if (!bankState.items.length) {
      listEl.innerHTML = '<p class="meta">暂无题目，点击右上角「＋ 新建题目」保存一个常用题目。</p>';
      return;
    }
    listEl.innerHTML = bankState.items.map(bankCardHtml).join('');
  } catch (err) {
    listEl.innerHTML = `<p class="form-error">加载失败: ${err.message}</p>`;
  }
}

function bankCardHtml(b) {
  const badges = [
    `<span class="status-badge status-draft">v${b.version}</span>`,
    `<span class="status-badge status-published">${typeLabel(b.type)}</span>`,
  ];
  if (b.in_bank) badges.push('<span class="status-badge status-published">题库</span>');
  if (b.visibility === 'public') badges.push('<span class="status-badge status-published">公开</span>');
  if (b.shared_with && b.shared_with.length) {
    badges.push(`<span class="status-badge status-closed">共享给 ${b.shared_with.length} 人</span>`);
  }
  if (!b.is_latest) badges.push('<span class="status-badge status-closed">非最新版本</span>');

  const owner = b.can_edit ? '我创建的' : `来自 ${b.owner_username || '他人'}`;

  const actions = [];
  actions.push(`<button class="btn secondary small" onclick="openBankDetail('${b.id}')">详情 / 统计</button>`);
  actions.push(`<button class="btn secondary small" onclick="openBankUseModal('${b.id}')">加入问卷</button>`);
  if (b.can_edit) {
    actions.push(`<button class="btn secondary small" onclick="openBankForm('${b.id}')">修改（生成新版本）</button>`);
    actions.push(`<button class="btn secondary small" onclick="toggleBankFlag('${b.id}', ${!b.in_bank})">${b.in_bank ? '移出题库' : '加入题库'}</button>`);
    actions.push(`<button class="btn danger small" onclick="deleteBankQuestion('${b.id}')">删除</button>`);
  } else {
    actions.push(`<button class="btn secondary small" onclick="forkBankQuestion('${b.id}')">复制到我的题库</button>`);
  }

  return `
    <div class="survey-card">
      <div class="info">
        <div class="title">${escHtml(b.title)}</div>
        <div class="meta">
          ${badges.join(' &nbsp;')}
          &nbsp;${owner}
          &nbsp;·&nbsp;被 ${b.usage_count} 个问卷题目引用
          ${b.tags && b.tags.length ? `&nbsp;·&nbsp;标签: ${b.tags.map(escHtml).join('、')}` : ''}
          ${b.derived_from_title ? `&nbsp;·&nbsp;派生自「${escHtml(b.derived_from_title)}」` : ''}
        </div>
        ${b.options ? `<div class="q-meta">选项: ${b.options.map(escHtml).join('、')}</div>` : ''}
        ${b.note ? `<div class="q-meta">说明: ${escHtml(b.note)}</div>` : ''}
      </div>
      <div class="actions">${actions.join('')}</div>
    </div>
  `;
}

// ---------------------------------------------------------------
// 工具栏
// ---------------------------------------------------------------

document.getElementById('btn-bank-back').addEventListener('click', () => showView('dashboard'));
document.getElementById('btn-bank-new').addEventListener('click', () => openBankForm(null));

let bankSearchTimer;
document.getElementById('bank-search').addEventListener('input', e => {
  bankState.keyword = e.target.value.trim();
  clearTimeout(bankSearchTimer);
  bankSearchTimer = setTimeout(renderBank, 300);
});

document.getElementById('bank-scope').addEventListener('change', e => {
  bankState.scope = e.target.value;
  renderBank();
});

document.getElementById('bank-only').addEventListener('change', e => {
  bankState.onlyBank = e.target.checked;
  renderBank();
});

// ---------------------------------------------------------------
// 新建 / 修改题目
// ---------------------------------------------------------------

function openBankForm(questionId) {
  bankState.editingId = questionId || null;

  const form = document.getElementById('form-bank-question');
  form.reset();

  document.getElementById('bank-q-type').disabled = false;
  document.getElementById('bank-modal-title').textContent = questionId ? '修改题目（生成新版本）' : '新建题目';
  document.getElementById('bank-modal-submit').textContent = questionId ? '生成新版本' : '保存到题库';
  document.getElementById('bank-q-note').value = '';

  if (questionId) {
    const b = bankState.items.find(x => x.id === questionId);
    if (b) fillBankForm(b);
  }

  syncBankOptionsBox();
  document.getElementById('bank-modal').classList.remove('hidden');
}

function fillBankForm(b) {
  document.getElementById('bank-q-type').value = b.type;
  document.getElementById('bank-q-type').disabled = true; // 题型不可变，跨版本保持一致
  document.getElementById('bank-q-title').value = b.title;
  document.getElementById('bank-q-required').checked = !!b.required;
  document.getElementById('bank-q-options').value = (b.options || []).join('\n');
  document.getElementById('bank-q-tags').value = (b.tags || []).join(', ');
  document.getElementById('bank-q-visibility').value = b.visibility || 'private';
  document.getElementById('bank-q-in-bank').checked = !!b.in_bank;
}

function syncBankOptionsBox() {
  const type = document.getElementById('bank-q-type').value;
  document.getElementById('bank-q-options-box').classList.toggle('hidden', type === 'text' || type === 'number');
}

document.getElementById('bank-q-type').addEventListener('change', syncBankOptionsBox);

function closeBankForm() {
  document.getElementById('bank-modal').classList.add('hidden');
  bankState.editingId = null;
}

document.getElementById('bank-modal-close').addEventListener('click', closeBankForm);
document.getElementById('bank-modal-cancel').addEventListener('click', closeBankForm);
document.getElementById('bank-modal-backdrop').addEventListener('click', closeBankForm);

document.getElementById('form-bank-question').addEventListener('submit', async e => {
  e.preventDefault();

  const type = document.getElementById('bank-q-type').value;
  const title = document.getElementById('bank-q-title').value.trim();
  const required = document.getElementById('bank-q-required').checked;
  const tags = document.getElementById('bank-q-tags').value
    .split(',').map(t => t.trim()).filter(Boolean);
  const visibility = document.getElementById('bank-q-visibility').value;
  const in_bank = document.getElementById('bank-q-in-bank').checked;
  const note = document.getElementById('bank-q-note').value.trim();

  let options = null;
  if (type === 'single' || type === 'multi') {
    const raw = document.getElementById('bank-q-options').value.trim();
    if (!raw) { showToast('请填写选项', 'error'); return; }
    options = raw.split('\n').map(o => o.trim()).filter(Boolean);
  }

  const payload = { title, required, options, tags, visibility, in_bank, note };
  if (!bankState.editingId) payload.type = type;

  try {
    if (bankState.editingId) {
      await api(`/bank/questions/${bankState.editingId}`, {
        method: 'PUT',
        body: JSON.stringify(payload),
      });
      showToast('已生成新版本，旧问卷保持不变', 'success');
    } else {
      await api('/bank/questions', {
        method: 'POST',
        body: JSON.stringify({ ...payload, type }),
      });
      showToast('题目已保存到题库', 'success');
    }
    closeBankForm();
    renderBank();
  } catch (err) {
    showToast('保存失败: ' + err.message, 'error');
  }
});

// ---------------------------------------------------------------
// 详情：版本历史 / 使用情况 / 跨问卷统计 / 共享
// ---------------------------------------------------------------

async function openBankDetail(questionId) {
  const body = document.getElementById('bank-detail-body');
  body.innerHTML = '<p class="meta">加载中...</p>';
  document.getElementById('bank-detail-modal').classList.remove('hidden');

  const b = bankState.items.find(x => x.id === questionId);
  document.getElementById('bank-detail-title').textContent = b ? b.title : '题目详情';

  try {
    const [history, usage, stats] = await Promise.all([
      api(`/bank/questions/${questionId}/versions`),
      api(`/bank/questions/${questionId}/usage`),
      api(`/bank/questions/${questionId}/statistics`),
    ]);

    let html = '';

    // —— 概览 ——
    html += `<div class="stats-card">
      <div class="stat-row"><span>当前版本</span><span>v${b ? b.version : '?'}${b && b.is_latest ? '（最新）' : ''}</span></div>
      <div class="stat-row"><span>可见性</span><span>${b && b.visibility === 'public' ? '公开' : '仅自己可见'}</span></div>
      ${b && b.shared_with && b.shared_with.length
        ? `<div class="stat-row"><span>共享给</span><span>${b.shared_with.map(escHtml).join('、')}</span></div>`
        : ''}
      <div class="stat-row"><span>被引用</span><span>${usage.total} 个问卷题目</span></div>
    </div>`;

    // —— 共享面板 ——
    if (b && b.can_edit) {
      html += `
      <div class="stats-card">
        <h4>🔗 共享</h4>
        <div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center">
          <input id="bank-share-users" type="text" placeholder="用户名（多个用逗号分隔）" style="flex:1;min-width:180px" />
          <button class="btn secondary small" id="bank-share-add">共享</button>
          <button class="btn secondary small" id="bank-share-public">${b.visibility === 'public' ? '取消公开' : '设为公开'}</button>
        </div>
        <p class="meta" style="margin:6px 0 0 0;font-size:.8rem">共享后对方可以在自己的问卷里使用这道题，且仍然可以继续使用同一个题目。</p>
      </div>`;
    }

    // —— 版本历史 ——
    html += `<div class="stats-card">
      <h4>🕘 版本历史</h4>
      <table style="width:100%;border-collapse:collapse;font-size:.9rem">
        <thead><tr style="border-bottom:1px solid #e2e8f0;text-align:left">
          <th style="padding:6px 4px">版本</th><th style="padding:6px 4px">题干</th>
          <th style="padding:6px 4px">来源</th><th style="padding:6px 4px">说明</th>
          <th style="padding:6px 4px">被引用</th><th style="padding:6px 4px"></th>
        </tr></thead><tbody>`;
    for (const v of history.versions) {
      const from = v.parent_version ? `v${v.parent_version}「${v.parent_title || ''}」` : '原始版本';
      html += `<tr style="border-bottom:1px solid #f1f5f9">
        <td style="padding:6px 4px">v${v.version}${v.is_current ? ' <span class="status-badge status-published">当前</span>' : ''}${v.is_latest ? ' <span class="status-badge status-draft">最新</span>' : ''}</td>
        <td style="padding:6px 4px">${escHtml(v.title)}</td>
        <td style="padding:6px 4px;color:var(--text-muted)">${escHtml(from)}</td>
        <td style="padding:6px 4px;color:var(--text-muted)">${escHtml(v.note || '-')}</td>
        <td style="padding:6px 4px">${v.usage_count}</td>
        <td style="padding:6px 4px;text-align:right">
          ${b && b.can_edit && !v.is_current
            ? `<button class="btn secondary small" onclick="restoreBankVersion('${questionId}', '${v.id}')">恢复此版本</button>`
            : ''}
        </td>
      </tr>`;
    }
    html += '</tbody></table></div>';

    // —— 使用情况 ——
    html += `<div class="stats-card">
      <h4>📋 使用情况（需求六）</h4>`;
    if (usage.items.length) {
      html += '<table style="width:100%;border-collapse:collapse;font-size:.9rem"><tbody>';
      for (const u of usage.items) {
        html += `<tr style="border-bottom:1px solid #f1f5f9">
          <td style="padding:6px 4px">${escHtml(u.survey_title)}</td>
          <td style="padding:6px 4px;color:var(--text-muted)">第 ${u.order} 题</td>
          <td style="padding:6px 4px;color:var(--text-muted)">${statusText(u.survey_status)}</td>
          <td style="padding:6px 4px;color:var(--text-muted)">v${u.version ?? '-'}${u.is_current_version ? '（当前版本）' : ''}</td>
        </tr>`;
      }
      html += '</tbody></table>';
    } else {
      html += '<p class="meta" style="margin:0">还没有问卷使用这道题。</p>';
    }
    html += '</div>';

    // —— 跨问卷统计 ——
    html += `<div class="stats-card">
      <h4>📊 跨问卷统计（需求八）</h4>
      <div class="stat-row"><span>覆盖问卷</span><span>${stats.survey_count} 个</span></div>
      <div class="stat-row"><span>题目实例</span><span>${stats.question_count} 个</span></div>
      <div class="stat-row"><span>回答总数</span><span>${stats.total_answers}</span></div>`;

    if (stats.type === 'single' || stats.type === 'multi') {
      for (const c of stats.counts) {
        const pct = stats.total_answers ? Math.round(c.count / stats.total_answers * 100) : 0;
        html += `<div class="stat-row"><span>${escHtml(String(c.value))}</span><span>${c.count} (${pct}%)</span></div>
                 <div class="stat-bar-wrap"><div class="stat-bar" style="width:${pct}%"></div></div>`;
      }
    } else if (stats.type === 'number') {
      html += `<div class="stat-row"><span>平均</span><span>${stats.avg?.toFixed(2) ?? '-'}（${stats.n} 人）</span></div>
               <div class="stat-row"><span>范围</span><span>${stats.min ?? '-'} ~ ${stats.max ?? '-'}</span></div>`;
    } else if (stats.values && stats.values.length) {
      for (const v of stats.values.slice(0, 10)) {
        html += `<div style="background:#f7f8fa;padding:6px 10px;border-radius:4px;margin-top:4px;font-size:.85rem">${escHtml(String(v))}</div>`;
      }
    }

    if (stats.by_survey && stats.by_survey.length) {
      html += '<h4 style="margin-top:12px">按问卷</h4>';
      for (const s of stats.by_survey) {
        html += `<div class="stat-row"><span>${escHtml(s.title)}</span><span>${s.count}</span></div>`;
      }
    }
    if (stats.by_version && stats.by_version.length) {
      html += '<h4 style="margin-top:12px">按版本</h4>';
      for (const v of stats.by_version) {
        html += `<div class="stat-row"><span>v${v.version ?? '-'} ${escHtml(v.title || '')}</span><span>${v.count}</span></div>`;
      }
    }
    html += '</div>';

    body.innerHTML = html;

    // 共享按钮
    document.getElementById('bank-share-add')?.addEventListener('click', async () => {
      const raw = document.getElementById('bank-share-users').value.trim();
      if (!raw) { showToast('请输入用户名', 'error'); return; }
      const usernames = raw.split(',').map(s => s.trim()).filter(Boolean);
      try {
        await api(`/bank/questions/${questionId}/share`, {
          method: 'POST',
          body: JSON.stringify({ add_usernames: usernames }),
        });
        showToast('已共享', 'success');
        await renderBank();
        openBankDetail(questionId);
      } catch (err) {
        showToast('共享失败: ' + err.message, 'error');
      }
    });

    document.getElementById('bank-share-public')?.addEventListener('click', async () => {
      const next = b && b.visibility === 'public' ? 'private' : 'public';
      try {
        await api(`/bank/questions/${questionId}/share`, {
          method: 'POST',
          body: JSON.stringify({ visibility: next }),
        });
        showToast(next === 'public' ? '已设为公开' : '已取消公开', 'success');
        await renderBank();
        openBankDetail(questionId);
      } catch (err) {
        showToast('操作失败: ' + err.message, 'error');
      }
    });
  } catch (err) {
    body.innerHTML = `<p class="form-error">加载失败: ${err.message}</p>`;
  }
}

function closeBankDetail() {
  document.getElementById('bank-detail-modal').classList.add('hidden');
}

document.getElementById('bank-detail-close').addEventListener('click', closeBankDetail);
document.getElementById('bank-detail-close-2').addEventListener('click', closeBankDetail);
document.getElementById('bank-detail-backdrop').addEventListener('click', closeBankDetail);

// ---------------------------------------------------------------
// 版本操作
// ---------------------------------------------------------------

async function restoreBankVersion(questionId, targetId) {
  if (!confirm('恢复该历史版本？将基于它生成一个新版本，旧版本仍会保留。')) return;
  try {
    await api(`/bank/questions/${questionId}/versions/${targetId}/restore`, { method: 'POST' });
    showToast('已恢复为新版本', 'success');
    await renderBank();
    openBankDetail(questionId);
  } catch (err) {
    showToast('恢复失败: ' + err.message, 'error');
  }
}

async function forkBankQuestion(questionId) {
  try {
    await api(`/bank/questions/${questionId}/fork`, { method: 'POST' });
    showToast('已复制到我的题库', 'success');
    renderBank();
  } catch (err) {
    showToast('复制失败: ' + err.message, 'error');
  }
}

async function toggleBankFlag(questionId, inBank) {
  try {
    await api(`/bank/questions/${questionId}/bank`, {
      method: 'POST',
      body: JSON.stringify({ in_bank: inBank }),
    });
    showToast(inBank ? '已加入题库' : '已移出题库', 'success');
    renderBank();
  } catch (err) {
    showToast('操作失败: ' + err.message, 'error');
  }
}

async function deleteBankQuestion(questionId) {
  if (!confirm('确认删除这道题？已经被问卷使用的题目无法删除。')) return;
  try {
    await api(`/bank/questions/${questionId}`, { method: 'DELETE' });
    showToast('题目已删除', 'success');
    renderBank();
  } catch (err) {
    showToast('删除失败: ' + err.message, 'error');
  }
}

// ---------------------------------------------------------------
// 从题库选题（问卷编辑器内）
// ---------------------------------------------------------------

async function openBankPicker() {
  const listEl = document.getElementById('bank-picker-list');
  listEl.innerHTML = '<p class="meta">加载中...</p>';
  document.getElementById('bank-picker-modal').classList.remove('hidden');
  await loadBankPickerList();
}

async function loadBankPickerList() {
  const listEl = document.getElementById('bank-picker-list');
  const keyword = document.getElementById('bank-picker-search').value.trim();
  try {
    const params = new URLSearchParams({ keyword, scope: 'all' });
    const items = await api(`/bank/questions?${params.toString()}`);
    if (!items.length) {
      listEl.innerHTML = '<p class="meta">没有可用的题库题目。</p>';
      return;
    }
    listEl.innerHTML = items.map(b => `
      <div class="question-item" style="cursor:pointer" onclick="useBankQuestionInSurvey('${b.id}')">
        <div class="q-header">
          <span class="q-title">${escHtml(b.title)}</span>
          <span class="q-type">${typeLabel(b.type)} · v${b.version}</span>
        </div>
        ${b.options ? `<div class="q-meta">选项: ${b.options.map(escHtml).join('、')}</div>` : ''}
        <div class="q-meta">${b.can_edit ? '我创建的' : `来自 ${b.owner_username || '他人'}`}${b.tags && b.tags.length ? ' · ' + b.tags.map(escHtml).join('、') : ''}</div>
      </div>
    `).join('');
  } catch (err) {
    listEl.innerHTML = `<p class="form-error">加载失败: ${err.message}</p>`;
  }
}

function closeBankPicker() {
  document.getElementById('bank-picker-modal').classList.add('hidden');
}

document.getElementById('bank-picker-close').addEventListener('click', closeBankPicker);
document.getElementById('bank-picker-cancel').addEventListener('click', closeBankPicker);
document.getElementById('bank-picker-backdrop').addEventListener('click', closeBankPicker);

let pickerTimer;
document.getElementById('bank-picker-search').addEventListener('input', () => {
  clearTimeout(pickerTimer);
  pickerTimer = setTimeout(loadBankPickerList, 300);
});

async function useBankQuestionInSurvey(questionId) {
  if (!editorState.surveyId) { showToast('请先保存问卷基本信息', 'error'); return; }
  try {
    const q = await api(`/surveys/${editorState.surveyId}/questions`, {
      method: 'POST',
      body: JSON.stringify({ bank_question_id: questionId }),
    });
    editorState.questions.push(q);
    renderQuestionList();
    closeBankPicker();
    showToast('已从题库添加题目', 'success');
  } catch (err) {
    showToast('添加失败: ' + err.message, 'error');
  }
}

document.getElementById('btn-pick-from-bank').addEventListener('click', openBankPicker);

// ---------------------------------------------------------------
// 把题库题目加入指定问卷（题库页面）
// ---------------------------------------------------------------

async function openBankUseModal(questionId) {
  bankState.useTargetId = questionId;
  const sel = document.getElementById('bank-use-survey');
  sel.innerHTML = '<option value="">加载中...</option>';
  document.getElementById('bank-use-modal').classList.remove('hidden');
  try {
    const data = await api('/surveys/');
    const surveys = data.items || [];
    if (!surveys.length) {
      sel.innerHTML = '<option value="">（还没有问卷，请先创建一个）</option>';
      return;
    }
    sel.innerHTML = surveys.map(s => `<option value="${s.id}">${escHtml(s.title)}（${statusText(s.status)}）</option>`).join('');
  } catch (err) {
    sel.innerHTML = `<option value="">加载失败: ${err.message}</option>`;
  }
}

function closeBankUseModal() {
  document.getElementById('bank-use-modal').classList.add('hidden');
  bankState.useTargetId = null;
}

document.getElementById('bank-use-close').addEventListener('click', closeBankUseModal);
document.getElementById('bank-use-cancel').addEventListener('click', closeBankUseModal);
document.getElementById('bank-use-backdrop').addEventListener('click', closeBankUseModal);

document.getElementById('bank-use-confirm').addEventListener('click', async () => {
  const surveyId = document.getElementById('bank-use-survey').value;
  if (!surveyId) { showToast('请选择问卷', 'error'); return; }
  try {
    await api(`/surveys/${surveyId}/questions`, {
      method: 'POST',
      body: JSON.stringify({ bank_question_id: bankState.useTargetId }),
    });
    closeBankUseModal();
    showToast('已加入问卷', 'success');
    // 刷新题库列表，让"被 N 个问卷题目引用"即时更新
    await renderBank();
  } catch (err) {
    showToast('添加失败: ' + err.message, 'error');
  }
});

// ---------------------------------------------------------------
// 题目编辑弹窗：切换题库版本
// ---------------------------------------------------------------

/**
 * 若问卷题目来自题库，弹出可选版本列表。
 * 返回所选版本 ID（未变化则返回 null）。
 */
async function loadBankVersionsForQuestion(q) {
  const box = document.getElementById('edit-q-bank-box');
  const sel = document.getElementById('edit-q-bank-version');
  if (!q.bank_ref || !q.bank_ref.root_id) {
    box.classList.add('hidden');
    sel.innerHTML = '';
    bankVersionCache = {};
    return;
  }
  try {
    const history = await api(`/bank/questions/${q.bank_ref.version_id}/versions`);
    // 缓存各版本内容：切换版本时用来回填编辑表单
    bankVersionCache = {};
    for (const v of history.versions) bankVersionCache[v.id] = v;
    sel.innerHTML = history.versions
      .map(v => `<option value="${v.id}"${v.id === q.bank_ref.version_id ? ' selected' : ''}>v${v.version} — ${escHtml(v.title)}</option>`)
      .join('');
    box.classList.remove('hidden');
  } catch (err) {
    box.classList.add('hidden');
  }
}

/**
 * 切换题库版本时，把该版本的内容回填到编辑表单，
 * 否则会出现"来源标成 v1、内容还是 v2"的错位（需求五）。
 */
function applyBankVersionToEditForm() {
  const sel = document.getElementById('edit-q-bank-version');
  const v = bankVersionCache[sel.value];
  if (!v) return;
  if (v.type !== 'single' && v.type !== 'multi') return;   // 题型不同则不覆盖选项
  document.getElementById('edit-q-title').value = v.title;
  document.getElementById('edit-q-options').value = (v.options || []).join('\n');
  document.getElementById('edit-q-required').checked = !!v.required;
}

document.getElementById('edit-q-bank-version').addEventListener('change', applyBankVersionToEditForm);

/** 取当前选中的版本 ID（若与原版本相同则返回 null）。 */
function selectedBankVersionId(q) {
  const sel = document.getElementById('edit-q-bank-version');
  if (!sel.value || !q.bank_ref) return null;
  return sel.value === q.bank_ref.version_id ? null : sel.value;
}
