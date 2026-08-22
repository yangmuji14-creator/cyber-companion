/* ===== conversation-sidebar.js (T9) — 会话侧栏 + 历史聚合 =====
 *
 * 职责：
 *   1. 渲染会话列表（GET /api/conversations）
 *   2. 切换会话 → 重新拉历史 + persona（GET /api/history?conversation_id=X）
 *   3. 新建网页角色对话（POST /api/conversations）
 *   4. 手机端 hamburger 抽屉
 *   5. 无激活会话时走 legacy 模式（GET /api/history + GET /api/persona）
 *
 * 入口：loadConversationSidebar() — 由 main.js init() 调用
 *
 * 渲染安全：所有动态文本用 textContent，不拼 innerHTML（XSS 防护）
 */

import { state, dom, $, el, applyPersona } from './state.js';
import { addBubble, toast, scrollBottom, userFacingError } from './ui.js';

// ── 模块状态 ──
let handlersBound = false;
let currentConversations = []; // 最近一次拉取的会话列表

// ── 平台图标 ──
const PLATFORM_ICON = {
  wechat: { emoji: "💬", cls: "wechat", label: "微信" },
  web:    { emoji: "🌐", cls: "web",    label: "网页" },
  cli:    { emoji: "💻", cls: "cli",    label: "CLI" },
  api:    { emoji: "🔌", cls: "cli",    label: "API" },
};

function platformIcon(platform) {
  return PLATFORM_ICON[platform] || PLATFORM_ICON.web;
}

// ── 时间格式化（相对时间） ──
function relativeTime(isoStr) {
  if (!isoStr) return "";
  const d = new Date(isoStr);
  if (isNaN(d.getTime())) return "";
  const now = Date.now();
  const diff = now - d.getTime();
  const min = Math.floor(diff / 60000);
  if (min < 1) return "刚刚";
  if (min < 60) return `${min}分钟前`;
  const hr = Math.floor(min / 60);
  if (hr < 24) return `${hr}小时前`;
  const day = Math.floor(hr / 24);
  if (day < 7) return `${day}天前`;
  return `${d.getMonth() + 1}/${d.getDate()}`;
}

// ── 清空消息区（保留 day-divider） ──
function clearMessages() {
  if (!dom.messages) return;
  // 保留第一个 .day-divider，移除其余子节点
  const children = Array.from(dom.messages.children);
  for (const c of children) {
    if (!c.classList.contains("day-divider")) {
      dom.messages.removeChild(c);
    }
  }
}

// ── 渲染历史消息气泡 ──
function renderHistoryBubbles(messages) {
  clearMessages();
  if (messages && messages.length > 0) {
    for (const m of messages) {
      const role = m.role === "user" ? "me" : "ai";
      addBubble(role, m.content, { sticker: m.sticker });
    }
    scrollBottom();
  }
}

// ── 渲染会话列表 ──
function renderConvList(conversations) {
  currentConversations = conversations || [];
  if (!dom.convList) return;

  // 清空列表（保留 conv-empty 模板）
  const empty = dom.convEmpty;
  dom.convList.innerHTML = "";
  if (empty) dom.convList.appendChild(empty);

  if (currentConversations.length === 0) {
    if (empty) empty.style.display = "";
    return;
  }
  if (empty) empty.style.display = "none";

  for (const conv of currentConversations) {
    const item = el("div", "conv-item");
    item.dataset.conversationId = conv.conversation_id;
    if (conv.conversation_id === state.activeConversationId) {
      item.classList.add("active");
    }

    // 平台图标
    const iconInfo = platformIcon(conv.platform);
    const icon = el("div", `conv-item-icon ${iconInfo.cls}`);
    icon.textContent = iconInfo.emoji;
    item.appendChild(icon);

    // 主体：名称 + 元信息
    const body = el("div", "conv-item-body");
    const name = el("div", "conv-item-name");
    // title 优先（用户自定义备注名）；空则回退 persona name → persona_id → contact_id
    name.textContent = conv.title || conv.persona_name || conv.persona_id || conv.contact_id || "未命名";
    body.appendChild(name);

    const meta = el("div", "conv-item-meta");
    const metaLeft = el("span");
    metaLeft.textContent = conv.platform === "wechat"
      ? `${iconInfo.label}账号 · ${conv.account_id || "默认"}`
      : `${iconInfo.label}对话`;
    meta.appendChild(metaLeft);
    body.appendChild(meta);
    item.appendChild(body);

    // 时间
    const time = el("div", "conv-item-time");
    time.textContent = relativeTime(conv.updated_at || conv.created_at);
    item.appendChild(time);

    // ⋯ 菜单按钮（hover 显示，移动端常显）
    const menuBtn = el("button", "conv-item-menu-btn");
    menuBtn.type = "button";
    menuBtn.setAttribute("aria-label", "更多操作");
    menuBtn.textContent = "⋯";
    item.appendChild(menuBtn);

    // 下拉菜单（绝对定位，默认隐藏）
    const menu = buildConvMenu(conv);
    item.appendChild(menu);

    // 菜单按钮点击：阻止冒泡（不触发 conv 切换），切换菜单显隐
    menuBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      const isOpen = !menu.hidden;
      closeAllConvMenus();
      if (!isOpen) menu.hidden = false;
    });

    // 点击切换
    item.addEventListener("click", () => {
      switchConversation(conv.conversation_id).catch((e) => {
        console.warn("switchConversation failed:", e);
        toast(userFacingError(e, "切换会话失败，请稍后重试"));
      });
    });

    dom.convList.appendChild(item);
  }
}

// ── 构建对话菜单（重命名 / 删除） ──
function buildConvMenu(conv) {
  const menu = el("div", "conv-item-menu");
  menu.hidden = true;
  populateMainMenu(menu, conv);
  return menu;
}

// 用主菜单项（重命名/删除）填充 menu
function populateMainMenu(menu, conv) {
  clearMenuItems(menu);

  const renameItem = el("div", "conv-item-menu-item");
  renameItem.textContent = "重命名";
  renameItem.addEventListener("click", (e) => {
    e.stopPropagation();
    menu.hidden = true;
    startRename(conv);
  });
  menu.appendChild(renameItem);

  const deleteItem = el("div", "conv-item-menu-item danger");
  deleteItem.textContent = "删除";
  deleteItem.addEventListener("click", (e) => {
    e.stopPropagation();
    menu.hidden = true;
    deleteConversation(conv);
  });
  menu.appendChild(deleteItem);
}

// ── 关闭所有打开的对话菜单 ──
function closeAllConvMenus() {
  if (!dom.convList) return;
  for (const m of dom.convList.querySelectorAll(".conv-item-menu")) {
    m.hidden = true;
  }
}

// ── 重命名：把 name 替换为 input ──
function startRename(conv) {
  if (!dom.convList) return;
  const item = dom.convList.querySelector(
    `.conv-item[data-conversation-id="${cssEscape(conv.conversation_id)}"]`
  );
  if (!item) return;
  const nameEl = item.querySelector(".conv-item-name");
  if (!nameEl) return;

  // 避免重复创建 input
  if (item.querySelector(".conv-item-rename-input")) return;

  // 隐藏 name，插入 input
  nameEl.style.display = "none";
  const input = el("input", "conv-item-rename-input");
  input.type = "text";
  input.value = conv.title || "";
  input.placeholder = conv.persona_name || conv.persona_id || "备注名（空则显示人设名）";
  input.maxLength = 50;
  nameEl.parentNode.insertBefore(input, nameEl.nextSibling);
  input.focus();
  input.select();

  let committed = false;
  const submit = async () => {
    if (committed) return;
    committed = true;
    const newTitle = input.value.trim();
    // 无变化 → 直接取消
    if (newTitle === (conv.title || "")) {
      restoreName();
      return;
    }
    try {
      const resp = await fetch(`/api/conversations/${encodeURIComponent(conv.conversation_id)}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title: newTitle }),
      });
      if (!resp.ok) {
        const err = await resp.json().catch(() => ({}));
        throw new Error(err.error || `HTTP ${resp.status}`);
      }
      await refreshConvList();
      toast(newTitle ? "已重命名" : "已清除备注名");
    } catch (e) {
      toast(userFacingError(e, "重命名失败，请稍后重试"));
      restoreName();
    }
  };

  const restoreName = () => {
    input.remove();
    nameEl.style.display = "";
  };

  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      submit();
    } else if (e.key === "Escape") {
      e.preventDefault();
      restoreName();
    }
  });
  input.addEventListener("blur", () => {
    // 失焦提交（如未提交过）
    submit();
  });
  // 阻止 input 点击冒泡到 conv-item（避免误触发切换）
  input.addEventListener("click", (e) => e.stopPropagation());
}

function clearMenuItems(menu) {
  while (menu.firstChild) menu.removeChild(menu.firstChild);
}

// ── 删除对话 ──
async function deleteConversation(conv) {
  const ok = confirm("确定删除此对话？关联的聊天记录将一并清除");
  if (!ok) return;
  try {
    const resp = await fetch(`/api/conversations/${encodeURIComponent(conv.conversation_id)}`, {
      method: "DELETE",
    });
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({}));
      throw new Error(err.error || `HTTP ${resp.status}`);
    }
    const wasActive = conv.conversation_id === state.activeConversationId;
    await refreshConvList();
    if (wasActive) {
      // 删的是当前对话 → 切到列表第一个，或清空走 legacy
      if (currentConversations.length > 0) {
        await switchConversation(currentConversations[0].conversation_id);
      } else {
        state.activeConversationId = null;
        localStorage.removeItem("cc-conv");
        clearMessages();
      }
    }
    toast("对话已删除");
  } catch (e) {
    toast(userFacingError(e, "删除失败，请稍后重试"));
  }
}

// ── CSS 转义（防 conversation_id 含特殊字符破坏 selector） ──
function cssEscape(s) {
  if (typeof CSS !== "undefined" && CSS.escape) return CSS.escape(s);
  // 兜底：转义非字母数字
  return String(s).replace(/[^a-zA-Z0-9_-]/g, "\\$&");
}

// ── 更新侧栏激活态 ──
function updateActiveItem() {
  if (!dom.convList) return;
  for (const item of dom.convList.querySelectorAll(".conv-item")) {
    item.classList.toggle(
      "active",
      item.dataset.conversationId === state.activeConversationId
    );
  }
}

// ── 切换会话 ──
export async function switchConversation(conversationId) {
  if (!conversationId) return;
  // 幂等：相同会话不重复加载（但首次设置仍需执行）
  const isFirstSet = state.activeConversationId === null;
  if (!isFirstSet && state.activeConversationId === conversationId) return;

  // Cancel a quiet-window batch before changing the binding. Otherwise its
  // eventual request could be sent into the newly selected conversation.
  window.dispatchEvent(new Event("chat-cancel-pending"));
  state.activeConversationId = conversationId;
  localStorage.setItem("cc-conv", conversationId);
  updateActiveItem();
  closeDrawer();

  // 拉历史
  let messages = [];
  try {
    const resp = await fetch(`/api/history?conversation_id=${encodeURIComponent(conversationId)}`);
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({}));
      throw new Error(err.error || `HTTP ${resp.status}`);
    }
    const data = await resp.json();
    messages = data.messages || [];
  } catch (e) {
    toast(userFacingError(e, "暂时无法加载聊天记录"));
    return;
  }

  // 拉 conversation 详情 → persona_id → persona 详情
  try {
    const convResp = await fetch(`/api/conversations/${encodeURIComponent(conversationId)}`);
    if (convResp.ok) {
      const convDetail = await convResp.json();
      if (convDetail.persona_id) {
        const personaResp = await fetch(`/api/persona/${convDetail.persona_id}`);
        if (personaResp.ok) {
          const personaDetail = await personaResp.json();
          applyPersona(personaDetail);
          window.dispatchEvent(new CustomEvent("persona-changed", {
            detail: { id: convDetail.persona_id },
          }));
        }
      }
    }
  } catch (e) {
    console.warn("load conversation/persona detail failed:", e);
  }

  // 渲染气泡
  renderHistoryBubbles(messages);
  if (messages.length === 0) {
    addBubble("ai", `切换到新会话了～想聊点什么都可以`);
  }
}

// ── Legacy 模式：无激活会话时加载历史 + persona ──
async function loadLegacyHistoryAndPersona() {
  const [histRes, personaListRes] = await Promise.all([
    fetch("/api/history").then((r) => r.json()),
    fetch("/api/persona").then((r) => r.json()),
  ]);

  // 先应用 persona（更新 state.avatar），再渲染历史气泡
  if (personaListRes[0]) {
    try {
      const personaDetail = await fetch(`/api/persona/${personaListRes[0].id}`).then((r) => r.json());
      applyPersona(personaDetail);
    } catch (e) {
      console.error("persona detail load failed:", e);
    }
  }

  if (histRes.messages && histRes.messages.length > 0) {
    for (const m of histRes.messages) {
      const role = m.role === "user" ? "me" : "ai";
      addBubble(role, m.content, { sticker: m.sticker });
    }
    scrollBottom();
  } else {
    const personaName = (personaListRes[0] && personaListRes[0].name) || "伴侣";
    addBubble("ai", `嗨，我是 ${personaName}～想聊点什么都可以`);
  }
}

// ── 手机端抽屉控制 ──
function openDrawer() {
  if (dom.convSidebar) dom.convSidebar.classList.add("open");
  if (dom.convBackdrop) {
    dom.convBackdrop.hidden = false;
    // 强制 reflow 后加 show 类，触发 fade 动画
    void dom.convBackdrop.offsetWidth;
    dom.convBackdrop.classList.add("show");
  }
}

function closeDrawer() {
  if (dom.convSidebar) dom.convSidebar.classList.remove("open");
  if (dom.convBackdrop) {
    dom.convBackdrop.classList.remove("show");
    dom.convBackdrop.hidden = true;
  }
}

// ── 新建对话 modal ──
async function openNewConvModal() {
  if (!dom.convModal) return;
  dom.convModal.hidden = false;

  // 加载 persona 列表
  try {
    const resp = await fetch("/api/persona");
    if (resp.ok) {
      const personas = await resp.json();
      if (dom.convNewPersona) {
        dom.convNewPersona.innerHTML = "";
        for (const p of personas) {
          const opt = el("option");
          opt.value = p.id;
          opt.textContent = p.name || p.id;
          dom.convNewPersona.appendChild(opt);
        }
      }
    }
  } catch (e) {
    console.warn("load personas for modal failed:", e);
  }

}

function closeNewConvModal() {
  if (dom.convModal) dom.convModal.hidden = true;
}

async function submitNewConv() {
  const personaId = dom.convNewPersona ? dom.convNewPersona.value : "";

  if (!personaId) {
    toast("请选择人设");
    return;
  }

  try {
    const resp = await fetch("/api/conversations", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        platform: "web",
        account_id: "",
        contact_id: "",
        persona_id: personaId,
      }),
    });
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({}));
      throw new Error(err.error || `HTTP ${resp.status}`);
    }
    const data = await resp.json();
    closeNewConvModal();
    // 重新加载会话列表
    await refreshConvList();
    // 切换到新会话
    await switchConversation(data.conversation_id);
    toast("新会话已创建");
  } catch (e) {
    toast(userFacingError(e, "创建会话失败，请稍后重试"));
  }
}

// ── 刷新会话列表 ──
async function refreshConvList() {
  try {
    const resp = await fetch("/api/conversations");
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const data = await resp.json();
    renderConvList(data);
  } catch (e) {
    console.warn("refreshConvList failed:", e);
  }
}

export async function ensureWebConversation(personaId) {
  await refreshConvList();
  let conversation = currentConversations.find((item) => (
    item.platform === "web" && item.persona_id === personaId
  ));
  if (!conversation) {
    const response = await fetch("/api/conversations", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        platform: "web", account_id: "", contact_id: "", persona_id: personaId,
      }),
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(payload.error || `HTTP ${response.status}`);
    conversation = payload;
    await refreshConvList();
  }
  state.activeConversationId = null;
  await switchConversation(conversation.conversation_id);
  return conversation;
}

// ── 事件绑定（幂等） ──
function bindHandlers() {
  if (handlersBound) return;
  handlersBound = true;

  // hamburger 抽屉切换（手机端）
  if (dom.convToggle) {
    dom.convToggle.addEventListener("click", openDrawer);
  }
  if (dom.convBackdrop) {
    dom.convBackdrop.addEventListener("click", closeDrawer);
  }

  // 新建对话按钮
  if (dom.convNewBtn) {
    dom.convNewBtn.addEventListener("click", openNewConvModal);
  }

  // modal 关闭/取消
  if (dom.convModalClose) {
    dom.convModalClose.addEventListener("click", closeNewConvModal);
  }
  if (dom.convModalCancel) {
    dom.convModalCancel.addEventListener("click", closeNewConvModal);
  }

  // modal 提交
  if (dom.convModalSubmit) {
    dom.convModalSubmit.addEventListener("click", submitNewConv);
  }

  // ESC 关闭 modal
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      if (dom.convModal && !dom.convModal.hidden) closeNewConvModal();
      if (dom.convSidebar && dom.convSidebar.classList.contains("open")) closeDrawer();
      closeAllConvMenus();
    }
  });

  // 点击对话菜单外部 → 关闭所有菜单
  document.addEventListener("click", (e) => {
    if (!dom.convList) return;
    // 点在菜单按钮或菜单内 → 不关闭（按钮自身 handler 已处理切换）
    const target = e.target;
    if (target instanceof Element && target.closest(".conv-item-menu-btn")) return;
    if (target instanceof Element && target.closest(".conv-item-menu")) return;
    closeAllConvMenus();
  });
}

// ── 入口：加载会话侧栏 + 历史 + persona ──
export async function loadConversationSidebar() {
  bindHandlers();

  // 拉取会话列表
  await refreshConvList();

  // 恢复上次激活的会话
  const savedConv = localStorage.getItem("cc-conv");
  if (savedConv) {
    // 验证 savedConv 仍在列表中
    const exists = currentConversations.some((c) => c.conversation_id === savedConv);
    if (exists) {
      await switchConversation(savedConv);
      return;
    }
    // savedConv 不在列表中（可能已删除）→ 清理 + 走 legacy
    localStorage.removeItem("cc-conv");
  }

  // Legacy 模式：无激活会话
  state.activeConversationId = null;
  await loadLegacyHistoryAndPersona();
}
