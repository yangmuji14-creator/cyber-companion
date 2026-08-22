/* ===== wechat-accounts.js — 微信账号管理（设置页子标签）
 * 由 settings-panel.js 在 "微信账号" tab 激活时动态 import + 调用 initWechatAccounts()。
 * 切换到其他 tab 时调用 destroyWechatAccounts() 停止轮询 + 关闭模态框。
 *
 * API 契约（T8 webui/server.py L1149-1437）：
 *   GET    /api/wechat/accounts                  → [{id, persona_id, persona_name, ...status}]
 *   POST   /api/wechat/accounts {id, persona_id, enabled?, auto_start?} → 200 | 400 | 409
 *   PATCH  /api/wechat/accounts/{id} {persona_id} → account role
 *   DELETE /api/wechat/accounts/{id}             → 200 | 404
 *   GET    /api/wechat/login/{id}/qrcode         → SSE (qrcode/status/done) | 404 | 409
 *   POST   /api/wechat/logout/{id}               → 200 | 404
 *   GET    /api/wechat/status/{id}               → {has_credentials, adapter_running} | 404
 *
 * SSE 事件格式（T8）：
 *   event: qrcode  data: {qr_url, qr_base64?}     // qr_base64 缺失时前端用 qr_url 文本兜底
 *   event: status   data: {status, message}       // status: scanning|confirmed|expired|failed
 *   event: done     data: {ok: true} | {ok: false, error}
 *   心跳: `: ping` 每 5s
 */
import { el } from './state.js';
import { toast, userFacingError } from './ui.js';

// ===== 模块状态 =====
let pollTimer = null;
let currentEventSource = null;
let qrCountdownTimer = null;
let qrModalEl = null;
let qrModalAccountId = "";

const POLL_INTERVAL_MS = 10000;
const QR_TIMEOUT_MS = 30000;

// ===== 工具 =====
function getContainer() {
  return document.querySelector('.settings-tab-content[data-tab="wechat_accounts"]');
}

function clearContainer(c) {
  while (c && c.firstChild) c.removeChild(c.firstChild);
}

// 状态映射：{has_credentials, adapter_running, session_expired} → {status, label, color}
// session-expired = 适配器检测到 token 过期（watchdog 触发），需重新扫码
// running = 适配器运行中；not-logged-in = 无凭证；offline = 有凭证但未运行
function mapAccountStatus(acc) {
  if (acc.session_expired) {
    return { status: "session-expired", label: "会话已过期", color: "#ef4444" };
  }
  if (acc.adapter_running) {
    return { status: "running", label: "运行中", color: "#22c55e" };
  }
  if (!acc.has_credentials) {
    return { status: "not-logged-in", label: "未登录", color: "#eab308" };
  }
  return { status: "offline", label: "离线", color: "#a1a1aa" };
}

// ===== 入口：tab 激活时调用 =====
export async function initWechatAccounts() {
  // 幂等：先清掉可能存在的旧 timer，再启动新的
  stopPolling();
  await refreshAccounts();
  startPolling();
}

export function destroyWechatAccounts() {
  stopPolling();
  closeQrModal();
}

function startPolling() {
  stopPolling();
  pollTimer = setInterval(refreshAccounts, POLL_INTERVAL_MS);
}

function stopPolling() {
  if (pollTimer) {
    clearInterval(pollTimer);
    pollTimer = null;
  }
}

// ===== 列表渲染 =====
async function refreshAccounts() {
  const container = getContainer();
  if (!container) return;
  // 轮询期间若用户正在填写添加表单，不要覆盖整个容器（避免输入丢失）
  const addForm = document.getElementById('wechat-add-form');
  const isAdding = addForm && !addForm.hidden;
  if (isAdding) return;
  // QR 模态框打开中不刷新列表（避免打断用户扫码；session_expired 检测在 modal 关闭后下一轮触发）
  if (qrModalEl) return;
  try {
    const [accountResp, personaResp] = await Promise.all([
      fetch('/api/wechat/accounts'),
      fetch('/api/persona'),
    ]);
    if (!accountResp.ok || !personaResp.ok) throw new Error('账号或角色列表加载失败');
    const [accounts, personas] = await Promise.all([
      accountResp.json(), personaResp.json(),
    ]);
    renderAccountsList(container, accounts, personas);
    // 自动为 session_expired 账号弹 QR 重登模态框（避免重复弹：qrModalAccountId 已是本账号则跳过）
    for (const acc of accounts) {
      if (acc.session_expired && qrModalAccountId !== acc.id) {
        openQrModal(acc.id, { expired: true });
        toast('微信 ' + acc.id + ' 会话已过期，请重新扫码');
        break; // 一次只弹一个 modal
      }
    }
  } catch (e) {
    renderError(container, '加载账号失败：' + e.message);
  }
}

function renderAccountsList(container, accounts, personas) {
  clearContainer(container);

  // 顶部：标题 + 添加按钮
  const header = el('div', 'wechat-accounts-header');
  const title = el('h3', 'wechat-accounts-title');
  title.textContent = '微信账号';
  header.appendChild(title);
  const addBtn = el('button', 'primary-btn wechat-add-btn');
  addBtn.textContent = '+ 添加微信号';
  addBtn.addEventListener('click', showAddForm);
  header.appendChild(addBtn);
  container.appendChild(header);

  // 添加表单（默认隐藏）
  const addForm = el('div', 'wechat-add-form');
  addForm.hidden = true;
  addForm.id = 'wechat-add-form';
  const input = el('input');
  input.type = 'text';
  input.placeholder = 'acc1';
  input.maxLength = 32;
  input.id = 'wechat-new-id';
  const hint = el('div', 'wechat-add-hint');
  hint.textContent = '3-32 位字母数字下划线连字符';
  const roleLabel = el('label', 'wechat-role-field');
  const roleText = el('span');
  roleText.textContent = '这个账号使用的角色';
  const roleSelect = el('select');
  roleSelect.id = 'wechat-new-persona';
  fillPersonaSelect(roleSelect, personas, '');
  roleLabel.append(roleText, roleSelect);
  const btnRow = el('div', 'wechat-add-buttons');
  const submitBtn = el('button', 'primary-btn');
  submitBtn.textContent = '添加';
  submitBtn.addEventListener('click', submitAddForm);
  const cancelBtn = el('button', 'ghost-btn');
  cancelBtn.textContent = '取消';
  cancelBtn.addEventListener('click', hideAddForm);
  btnRow.appendChild(submitBtn);
  btnRow.appendChild(cancelBtn);
  addForm.appendChild(input);
  addForm.appendChild(hint);
  addForm.appendChild(roleLabel);
  addForm.appendChild(btnRow);
  container.appendChild(addForm);

  // 账号卡片列表
  if (!accounts || accounts.length === 0) {
    const empty = el('div', 'wechat-accounts-empty');
    empty.textContent = '暂无微信账号，点击上方"添加微信号"创建';
    container.appendChild(empty);
    return;
  }

  const list = el('div', 'wechat-account-list');
  for (const acc of accounts) {
    list.appendChild(renderAccountCard(acc, personas));
  }
  container.appendChild(list);
}

function fillPersonaSelect(select, personas, selectedId) {
  select.replaceChildren();
  for (const persona of (personas || [])) {
    const option = el('option');
    option.value = persona.id;
    option.textContent = persona.name || persona.id;
    option.selected = persona.id === selectedId;
    select.appendChild(option);
  }
}

function renderAccountCard(acc, personas) {
  const st = mapAccountStatus(acc);
  const card = el('div', 'wechat-account-card');

  const info = el('div', 'account-info');
  const dot = el('span', 'account-status-dot');
  dot.dataset.status = st.status;
  dot.style.backgroundColor = st.color;
  const idSpan = el('span', 'account-id');
  idSpan.textContent = acc.id;
  const statusText = el('span', 'account-status-text');
  statusText.textContent = st.label;
  info.appendChild(dot);
  info.appendChild(idSpan);
  info.appendChild(statusText);
  card.appendChild(info);

  const role = el('label', 'account-role');
  const roleLabel = el('span');
  roleLabel.textContent = '使用角色';
  const roleSelect = el('select');
  roleSelect.setAttribute('aria-label', `${acc.id} 使用的角色`);
  fillPersonaSelect(roleSelect, personas, acc.persona_id);
  roleSelect.dataset.savedValue = acc.persona_id || '';
  roleSelect.addEventListener('change', () => updateAccountPersona(
    acc.id, roleSelect.value, roleSelect,
  ));
  role.append(roleLabel, roleSelect);
  card.appendChild(role);

  const actions = el('div', 'account-actions');
  const loginBtn = el('button', 'ghost-btn btn-login');
  loginBtn.textContent = '登录';
  loginBtn.addEventListener('click', () => openQrModal(acc.id));
  const logoutBtn = el('button', 'ghost-btn btn-logout');
  logoutBtn.textContent = '退出';
  logoutBtn.hidden = !acc.has_credentials;
  logoutBtn.addEventListener('click', () => logoutAccount(acc.id));
  const deleteBtn = el('button', 'delete-btn btn-delete');
  deleteBtn.textContent = '删除';
  deleteBtn.addEventListener('click', () => deleteAccount(acc.id));
  actions.appendChild(loginBtn);
  actions.appendChild(logoutBtn);
  actions.appendChild(deleteBtn);
  card.appendChild(actions);

  return card;
}

async function updateAccountPersona(accountId, personaId, select) {
  const previous = select.dataset.savedValue || '';
  select.disabled = true;
  try {
    const response = await fetch('/api/wechat/accounts/' + encodeURIComponent(accountId), {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ persona_id: personaId }),
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(payload.error || 'HTTP ' + response.status);
    select.dataset.savedValue = personaId;
    toast('账号角色已更新');
  } catch (error) {
    if (previous) select.value = previous;
    toast(userFacingError(error, '角色更新失败，请稍后重试'));
  } finally {
    select.disabled = false;
  }
}

function renderError(container, msg) {
  clearContainer(container);
  const err = el('div', 'wechat-accounts-empty');
  err.textContent = msg;
  container.appendChild(err);
}

// ===== 添加账号 =====
function showAddForm() {
  const form = document.getElementById('wechat-add-form');
  if (form) {
    form.hidden = false;
    const input = document.getElementById('wechat-new-id');
    if (input) input.focus();
  }
}

function hideAddForm() {
  const form = document.getElementById('wechat-add-form');
  if (form) {
    form.hidden = true;
    const input = document.getElementById('wechat-new-id');
    if (input) input.value = '';
  }
}

async function submitAddForm() {
  const input = document.getElementById('wechat-new-id');
  if (!input) return;
  const accId = input.value.trim();
  if (!accId) {
    toast('请输入账号 ID');
    return;
  }
  const personaSelect = document.getElementById('wechat-new-persona');
  const personaId = personaSelect ? personaSelect.value : '';
  if (!personaId) {
    toast('请先选择角色');
    return;
  }
  try {
    const resp = await fetch('/api/wechat/accounts', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        id: accId, persona_id: personaId, enabled: true, auto_start: false,
      }),
    });
    if (resp.status === 409) {
      toast('账号 ID 已存在');
      return;
    }
    if (resp.status === 400) {
      const data = await resp.json().catch(() => ({}));
      toast(data.error || '账号 ID 不合法');
      return;
    }
    if (!resp.ok) throw new Error('HTTP ' + resp.status);
    toast('账号已添加');
    hideAddForm();
    await refreshAccounts();
  } catch (e) {
    toast(userFacingError(e, '添加账号失败，请稍后重试'));
  }
}

// ===== 退出登录 =====
async function logoutAccount(accId) {
  if (!confirm('确定退出登录？')) return;
  try {
    const resp = await fetch('/api/wechat/logout/' + encodeURIComponent(accId), { method: 'POST' });
    if (resp.status === 404) {
      toast('账号不存在');
    } else if (!resp.ok) {
      throw new Error('HTTP ' + resp.status);
    } else {
      toast('已退出');
    }
    await refreshAccounts();
  } catch (e) {
    toast(userFacingError(e, '退出登录失败，请稍后重试'));
  }
}

// ===== 删除账号 =====
async function deleteAccount(accId) {
  if (!confirm('确定删除账号 ' + accId + '？此操作会清除登录凭证')) return;
  try {
    const resp = await fetch('/api/wechat/accounts/' + encodeURIComponent(accId), { method: 'DELETE' });
    if (resp.status === 404) {
      toast('账号不存在');
    } else if (!resp.ok) {
      throw new Error('HTTP ' + resp.status);
    } else {
      toast('账号已删除');
    }
    await refreshAccounts();
  } catch (e) {
    toast(userFacingError(e, '删除账号失败，请稍后重试'));
  }
}

// ===== QR 登录模态框 =====
function openQrModal(accountId, opts) {
  opts = opts || {};
  closeQrModal(); // 清理可能存在的旧 modal
  qrModalAccountId = accountId;
  qrModalEl = buildQrModal(accountId, opts);
  document.body.appendChild(qrModalEl);
  startQrStream(accountId);
}

function buildQrModal(accountId, opts) {
  opts = opts || {};
  const overlay = el('div', 'qr-modal-overlay');
  overlay.id = 'qr-modal';

  const card = el('div', 'qr-modal-card');

  const closeBtn = el('button', 'qr-modal-close');
  closeBtn.textContent = '×';
  closeBtn.setAttribute('aria-label', '关闭');
  closeBtn.addEventListener('click', closeQrModal);

  const title = el('h3', 'qr-modal-title');
  // session_expired 触发的重登 → 标题改为"会话已过期，请重新扫码"
  title.textContent = opts.expired
    ? '会话已过期，请重新扫码 - ' + accountId
    : '微信登录 - ' + accountId;

  const display = el('div', 'qr-display');
  display.id = 'qr-display';
  const loading = el('div', 'qr-loading');
  loading.textContent = '正在获取二维码...';
  display.appendChild(loading);

  const status = el('div', 'qr-status');
  status.id = 'qr-status';
  status.textContent = '等待扫码';

  const timer = el('div', 'qr-timer');
  timer.id = 'qr-timer';
  timer.textContent = (QR_TIMEOUT_MS / 1000) + 's';

  card.appendChild(closeBtn);
  card.appendChild(title);
  card.appendChild(display);
  card.appendChild(status);
  card.appendChild(timer);
  overlay.appendChild(card);

  // 点击遮罩关闭
  overlay.addEventListener('click', (e) => {
    if (e.target === overlay) closeQrModal();
  });

  return overlay;
}

function startQrStream(accountId) {
  let qrcodeReceived = false;
  let doneReceived = false;
  let timeLeft = QR_TIMEOUT_MS / 1000;

  // 倒计时
  const timerEl = document.getElementById('qr-timer');
  qrCountdownTimer = setInterval(() => {
    timeLeft -= 1;
    if (timerEl) timerEl.textContent = Math.max(0, timeLeft) + 's';
    if (timeLeft <= 0) {
      stopQrCountdown();
      if (!doneReceived) {
        showQrTimeout();
        closeEventSource();
      }
    }
  }, 1000);

  const url = '/api/wechat/login/' + encodeURIComponent(accountId) + '/qrcode';
  const es = new EventSource(url);
  currentEventSource = es;

  es.addEventListener('qrcode', (e) => {
    qrcodeReceived = true;
    try {
      const data = JSON.parse(e.data);
      renderQr(data);
    } catch (err) {
      showQrError('二维码数据解析失败');
    }
  });

  es.addEventListener('status', (e) => {
    try {
      const data = JSON.parse(e.data);
      updateQrStatus(data.status, data.message);
    } catch (err) {
      // 忽略解析错误
    }
  });

  es.addEventListener('done', (e) => {
    doneReceived = true;
    stopQrCountdown();
    try {
      const data = JSON.parse(e.data);
      if (data.ok) {
        toast('登录成功');
        closeQrModal();
        refreshAccounts();
      } else if (isSdkMissingError(data.error)) {
        // SDK 缺失：专用 HTML 提示 + 安装指引（安全：消息为静态字符串，无 XSS 风险）
        showQrErrorHtml(
          '⚠️ 微信 SDK 未安装<br><br>' +
          '请联系管理员运行 <code>python install.py</code> 安装微信 SDK，安装后重启服务器。'
        );
      } else {
        showQrError(formatLoginError(data.error));
      }
    } catch (err) {
      showQrError('登录响应解析失败');
    }
    closeEventSource();
  });

  es.onerror = () => {
    // EventSource 遇到错误（404/409 返回非 SSE 响应，或连接断开）
    // 必须手动 close 防止自动重连
    es.close();
    currentEventSource = null;
    stopQrCountdown();
    if (!doneReceived) {
      if (!qrcodeReceived) {
        showQrError('无法获取二维码（账号可能未配置或已有登录进行中）');
      } else if (!doneReceived) {
        showQrError('连接已断开，请重试');
      }
    }
  };
}

// 检测错误字符串是否表示微信 SDK 未安装
function isSdkMissingError(errorStr) {
  if (!errorStr || typeof errorStr !== 'string') return false;
  const lower = errorStr.toLowerCase();
  return (
    lower.includes('weixin_ilink') ||
    lower.includes('importerror') ||
    lower.includes('no module named') ||
    lower.includes('modulenotfounderror')
  );
}

// 格式化登录错误：SDK 缺失 → 友好提示 + 安装指引；其他 → 原始错误
function formatLoginError(error) {
  if (!error) return '登录失败';
  if (isSdkMissingError(error)) {
    return '微信 SDK 未安装，请联系管理员运行 python install.py 安装';
  }
  return error;
}

function closeEventSource() {
  if (currentEventSource) {
    currentEventSource.close();
    currentEventSource = null;
  }
}

function stopQrCountdown() {
  if (qrCountdownTimer) {
    clearInterval(qrCountdownTimer);
    qrCountdownTimer = null;
  }
}

function renderQr(data) {
  const display = document.getElementById('qr-display');
  if (!display) return;
  clearContainer(display);
  if (data.qr_base64) {
    // 后端已生成 base64 二维码图片（qrcode Python 库已安装）
    const img = el('img', 'qr-image');
    img.src = data.qr_base64;
    img.alt = '微信登录二维码';
    display.appendChild(img);
  } else if (data.qr_url && typeof window.QRious === 'function') {
    // 后端 qrcode 库未安装 → 前端用 QRious 渲染 qr_url 为二维码
    try {
      const qr = new window.QRious({
        value: data.qr_url,
        size: 220,
        level: 'M',
        background: '#ffffff',
        foreground: '#000000',
      });
      const img = el('img', 'qr-image');
      img.src = qr.toDataURL();
      img.alt = '微信登录二维码';
      display.appendChild(img);
    } catch (err) {
      // QRious 渲染失败 → 回退为文本链接
      showQrUrlFallback(display, data.qr_url);
    }
  } else if (data.qr_url) {
    // QRious CDN 加载失败 → 文本链接兜底（用户可手动复制到手机浏览器扫码）
    showQrUrlFallback(display, data.qr_url);
  } else {
    showQrError('二维码数据为空');
  }
}

function showQrUrlFallback(display, qrUrl) {
  const hint = el('div', 'qr-url-hint');
  hint.textContent = '请手动扫码（或复制链接到手机浏览器打开）：';
  const link = el('a', 'qr-url-link');
  link.href = qrUrl;
  link.target = '_blank';
  link.rel = 'noopener noreferrer';
  link.textContent = qrUrl;
  display.appendChild(hint);
  display.appendChild(link);
}

function updateQrStatus(status, message) {
  const statusEl = document.getElementById('qr-status');
  if (!statusEl) return;
  const textMap = {
    scanning: '已扫码，请在手机上确认',
    confirmed: '登录成功',
    expired: '二维码已过期',
    failed: '登录失败',
  };
  statusEl.textContent = message || textMap[status] || status;
  statusEl.dataset.status = status;
}

function showQrError(msg) {
  const display = document.getElementById('qr-display');
  if (display) {
    clearContainer(display);
    const err = el('div', 'qr-error');
    err.textContent = msg;
    display.appendChild(err);
  }
  const statusEl = document.getElementById('qr-status');
  if (statusEl) {
    statusEl.textContent = msg;
    statusEl.dataset.status = 'failed';
  }
  addRetryButton();
}

// SDK 缺失专用：用 innerHTML 渲染 HTML 提示（含 <br> / <code>）。
// 仅用于静态 SDK 缺失消息，不接受用户输入，无 XSS 风险。
function showQrErrorHtml(htmlMsg) {
  const display = document.getElementById('qr-display');
  if (display) {
    clearContainer(display);
    const err = el('div', 'qr-error qr-error-sdk');
    err.innerHTML = htmlMsg;
    display.appendChild(err);
  }
  const statusEl = document.getElementById('qr-status');
  if (statusEl) {
    statusEl.textContent = '微信 SDK 未安装';
    statusEl.dataset.status = 'failed';
  }
  addRetryButton();
}

function showQrTimeout() {
  const display = document.getElementById('qr-display');
  if (display) {
    clearContainer(display);
    const err = el('div', 'qr-error');
    err.textContent = '登录超时';
    display.appendChild(err);
  }
  const statusEl = document.getElementById('qr-status');
  if (statusEl) {
    statusEl.textContent = '登录超时';
    statusEl.dataset.status = 'failed';
  }
  addRetryButton();
}

function addRetryButton() {
  const card = document.querySelector('.qr-modal-card');
  if (!card) return;
  // 移除可能存在的旧重试按钮
  const oldRetry = card.querySelector('.qr-retry-btn');
  if (oldRetry) oldRetry.remove();
  const retry = el('button', 'primary-btn qr-retry-btn');
  retry.textContent = '重试';
  retry.addEventListener('click', () => {
    if (!qrModalAccountId) return;
    // 重置 modal 内容
    const display = document.getElementById('qr-display');
    if (display) {
      clearContainer(display);
      const loading = el('div', 'qr-loading');
      loading.textContent = '正在获取二维码...';
      display.appendChild(loading);
    }
    const statusEl = document.getElementById('qr-status');
    if (statusEl) {
      statusEl.textContent = '等待扫码';
      delete statusEl.dataset.status;
    }
    const timerEl = document.getElementById('qr-timer');
    if (timerEl) timerEl.textContent = (QR_TIMEOUT_MS / 1000) + 's';
    retry.remove();
    startQrStream(qrModalAccountId);
  });
  card.appendChild(retry);
}

function closeQrModal() {
  closeEventSource();
  stopQrCountdown();
  if (qrModalEl && qrModalEl.parentNode) {
    qrModalEl.parentNode.removeChild(qrModalEl);
  }
  qrModalEl = null;
}
