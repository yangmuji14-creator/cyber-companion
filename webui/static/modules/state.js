/* ===== state.js — 全局状态与 DOM 引用单例 ===== */
// 模块加载时执行 dom 引用；script type="module" 默认 defer，DOM 已就绪。

export const $ = (sel) => document.querySelector(sel);
export const el = (tag, cls) => { const e = document.createElement(tag); if (cls) e.className = cls; return e; };

export const state = {
  schema: [],
  values: {},
  sending: false,
  personaName: "",
  avatar: "",
  currentPage: "chat",
  activeConversationId: null,  // T9: 当前激活会话 ID（null = legacy 模式）
  activeRequest: null,
  pendingImage: null,
  pendingSticker: null,
  activity: null,
};

export const dom = {
  messages: $("#messages"),
  input: $("#input"),
  send: $("#btn-send"),
  stop: $("#btn-stop"),
  connStatus: $("#conn-status"),
  personaName: $("#persona-name"),
  avatar: $("#avatar"),
  // settings
  form: $("#settings-form"),
  // pages + bottom nav (mobile)
  pageChat: $("#page-chat"),
  pageMemory: $("#page-memory"),
  pageSettings: $("#page-settings"),
  bottomNav: $(".bottom-nav"),
  navBtns: Array.from(document.querySelectorAll(".bottom-nav .nav-btn")),
  // sidebar nav (tablet/desktop)
  sidebarNavItems: Array.from(document.querySelectorAll(".sidebar-nav-item")),
  sidebarAvatar: $("#sidebar-avatar"),
  sidebarPersonaName: $("#sidebar-persona-name"),
  sidebarConnStatus: $("#sidebar-conn-status"),
  sidebarStatusDot: $("#sidebar-status-dot"),
  save: $("#btn-save"),
  saveStatus: $("#save-status"),
  // image
  btnImage: $("#btn-image"),
  fileImage: $("#file-image"),
  pendingImage: $("#pending-image"),
  pendingImagePreview: $("#pending-image-preview"),
  pendingImageName: $("#pending-image-name"),
  pendingImageRemove: $("#pending-image-remove"),
  pendingImageSend: $("#pending-image-send"),
  btnSticker: $("#btn-sticker"),
  stickerPicker: $("#sticker-picker"),
  // voice
  btnVoice: $("#btn-voice"),
  voiceOverlay: $("#voice-overlay"),
  voiceTimer: $("#voice-timer"),
  voiceCancel: $("#voice-cancel"),
  voiceStop: $("#voice-stop"),
  toast: $("#toast"),
  // T9: 会话侧栏
  convSidebar: $("#conv-sidebar"),
  convList: $("#conv-list"),
  convEmpty: $("#conv-empty"),
  convNewBtn: $("#conv-new-btn"),
  convToggle: $("#conv-toggle"),
  convBackdrop: $("#conv-backdrop"),
  convModal: $("#conv-modal"),
  convModalClose: $("#conv-modal-close"),
  convModalCancel: $("#conv-modal-cancel"),
  convModalSubmit: $("#conv-modal-submit"),
  convNewPersona: $("#conv-new-persona"),
};

const VALID_PAGES = ["chat", "contacts", "discover", "memory", "settings"];

// 切换页面：隐藏所有 .page，显示 #page-{page}，同步激活态到
// .bottom-nav .nav-btn（手机端）和 .sidebar-nav-item（桌面端）。
// URL 不变，持久化到 localStorage。对当前页调用为 no-op（幂等）。
export async function switchPage(page) {
  if (!VALID_PAGES.includes(page)) return;
  if (state.currentPage === page) return; // idempotent no-op
  for (const p of VALID_PAGES) {
    const section = document.getElementById(`page-${p}`);
    if (section) {
      section.classList.remove("active");
      section.hidden = true;
    }
  }
  const target = document.getElementById(`page-${page}`);
  if (target) {
    target.classList.add("active");
    target.hidden = false;
  }
  // 手机端底栏 nav-btn
  for (const btn of dom.navBtns) {
    btn.classList.toggle("active", btn.dataset.page === page);
  }
  // 桌面端侧边栏 sidebar-nav-item
  for (const item of dom.sidebarNavItems) {
    item.classList.toggle("active", item.dataset.page === page);
  }
  state.currentPage = page;
  localStorage.setItem("cc-page", page);
  // 懒加载：contacts / discover / memory 各自独立模块，缺失时降级警告。
  // 用裸字符串变量拼接 `./${mod}.js`，Vite 可静态解析动态 import。
  let mod = "";
  let fnName = "";
  if (page === "contacts") { mod = "contacts-page"; fnName = "loadContactsPage"; }
  else if (page === "discover") { mod = "discover-page"; fnName = "loadDiscoverPage"; }
  else if (page === "memory") { mod = "memory-page"; fnName = "loadMemoryPage"; }
  if (mod) {
    try {
      const m = await import(`./${mod}.js`);
      if (m[fnName]) await m[fnName]();
    } catch (e) {
      console.warn(`${mod}.js not loaded yet:`, e.message);
    }
  }
}

export function getCurrentPage() {
  return state.currentPage || "chat";
}

/* ============================================================
   applyPersona — 应用 persona 详情到 state + DOM
   （从 main.js 移到 state.js，T9 conversation-sidebar.js 也需要调用）
   ============================================================ */
export function applyPersona(personaDetail) {
  const name = (personaDetail && personaDetail.name) || "";
  const initial = (name || "?").charAt(0);
  state.personaName = name;
  state.avatar = initial;
  if (dom.personaName) dom.personaName.textContent = name;
  if (dom.avatar) dom.avatar.textContent = initial;
}

/* ============================================================
   侧边栏自初始化（不依赖 main.js，避免扩大改动范围）
   - 侧边栏 nav 项点击 → switchPage
   - 侧边栏主题按钮 → 转发到顶栏主题按钮（main.js 已绑定 toggleTheme）
   - 顶栏 persona name/avatar → MutationObserver 镜像到侧边栏
   - 顶栏 conn-status → MutationObserver 镜像到侧边栏
   ============================================================ */
function bindSidebar() {
  // 侧边栏导航项点击
  for (const item of dom.sidebarNavItems) {
    if (item.dataset.bound === "1") continue;
    item.dataset.bound = "1";
    item.addEventListener("click", () => {
      switchPage(item.dataset.page).catch((e) => console.warn("sidebar switchPage failed:", e));
    });
  }

  // 侧边栏主题按钮 → 转发到顶栏主题按钮
  const topbarToggle = $("#toggle-theme");
  const sidebarToggle = $("#toggle-theme-sidebar");
  if (topbarToggle && sidebarToggle && sidebarToggle.dataset.bound !== "1") {
    sidebarToggle.dataset.bound = "1";
    sidebarToggle.addEventListener("click", () => topbarToggle.click());
  }

  // 镜像顶栏 persona name → 侧边栏
  if (dom.personaName && dom.sidebarPersonaName) {
    const mirrorName = () => { dom.sidebarPersonaName.textContent = dom.personaName.textContent; };
    mirrorName();
    new MutationObserver(mirrorName).observe(dom.personaName, { childList: true, characterData: true, subtree: true });
  }

  // 镜像顶栏 avatar → 侧边栏
  if (dom.avatar && dom.sidebarAvatar) {
    const mirrorAvatar = () => { dom.sidebarAvatar.textContent = dom.avatar.textContent; };
    mirrorAvatar();
    new MutationObserver(mirrorAvatar).observe(dom.avatar, { childList: true, characterData: true, subtree: true });
  }

  // 镜像顶栏连接状态 → 侧边栏
  if (dom.connStatus && dom.sidebarConnStatus && dom.sidebarStatusDot) {
    const mirrorStatus = () => {
      const txt = dom.connStatus.textContent || "";
      const isOnline = dom.connStatus.classList.contains("online");
      dom.sidebarConnStatus.textContent = txt;
      dom.sidebarStatusDot.classList.toggle("offline", !isOnline);
    };
    mirrorStatus();
    new MutationObserver(mirrorStatus).observe(dom.connStatus, { childList: true, characterData: true, subtree: true, attributes: true, attributeFilter: ["class"] });
  }
}

bindSidebar();
