/* ===== main.js — 入口：事件绑定与启动 ===== */
import { state, dom, switchPage } from './state.js';
import { addBubble, checkHealth, autoResize, toggleTheme, toast, userFacingError } from './ui.js';
import { sendMessage, stopMessageGeneration } from './chat-stream.js?v=4.3.11';
import { loadSettings, saveSettings, loadPersonaEditor, loadModelSelect } from './settings-panel.js?v=4.3.3';
import { uploadImage, startVoice, stopVoice, clearPendingImage, sendPendingImage } from './upload.js?v=4.3.11';
import { bindStickers, loadStickers } from './stickers.js?v=4.3.11';
import { loadConversationSidebar } from './conversation-sidebar.js';
import { initBootstrap } from './bootstrap.js?v=4.3.2';
import { initDiagnostics } from './diagnostics.js';

function bind() {
  dom.send.addEventListener("click", sendMessage);
  dom.stop?.addEventListener("click", stopMessageGeneration);
  dom.input.addEventListener("input", autoResize);
  dom.input.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendMessage(); }
    if (e.key === "Escape" && state.activeRequest) {
      e.preventDefault();
      stopMessageGeneration();
    }
  });

  dom.save.addEventListener("click", saveSettings);

  // 底部导航 tab 切换
  dom.navBtns.forEach((btn) => {
    btn.addEventListener("click", () => switchPage(btn.dataset.page).catch((e) => console.warn("switchPage failed:", e)));
  });

  dom.btnImage.addEventListener("click", () => dom.fileImage.click());
  dom.fileImage.addEventListener("change", (e) => {
    if (e.target.files[0]) uploadImage(e.target.files[0]);
    e.target.value = "";
  });
  dom.pendingImageRemove?.addEventListener("click", clearPendingImage);
  dom.pendingImageSend?.addEventListener("click", () => sendPendingImage(dom.input.value.trim()));
  bindStickers();
  void loadStickers();

  dom.btnVoice.addEventListener("click", startVoice);
  dom.voiceStop.addEventListener("click", () => stopVoice(false));
  dom.voiceCancel.addEventListener("click", () => stopVoice(true));

  document.getElementById("toggle-theme").addEventListener("click", toggleTheme);

  bindDataTools();
  initDiagnostics();

}

function bindDataTools() {
  const backup = document.getElementById("btn-backup");
  const restore = document.getElementById("btn-restore");
  const restoreFile = document.getElementById("restore-file");
  const restoreCard = document.getElementById("restore-card");
  const restoreTitle = document.getElementById("restore-title");
  const restoreDetail = document.getElementById("restore-detail");
  const restoreCancel = document.getElementById("btn-restore-cancel");
  const restoreConfirm = document.getElementById("btn-restore-confirm");
  const about = document.getElementById("btn-about");
  const aboutCard = document.getElementById("about-card");
  let selectedRestoreFile = null;

  backup?.addEventListener("click", async () => {
    backup.disabled = true;
    try {
      const response = await fetch("/api/backup", { method: "POST" });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const url = URL.createObjectURL(await response.blob());
      const link = document.createElement("a");
      link.href = url;
      link.download = "mu-backup.zip";
      link.click();
      URL.revokeObjectURL(url);
      toast("备份已导出");
    } catch (e) {
      toast(userFacingError(e, "备份创建失败，请稍后重试"));
    } finally {
      backup.disabled = false;
    }
  });

  const showPendingRestore = (restoreInfo) => {
    if (!restoreCard || !restoreInfo) return;
    const count = restoreInfo.manifest?.included?.length || 0;
    restoreTitle.textContent = "恢复任务已安排";
    restoreDetail.textContent = `下次重新启动应用时恢复 ${count} 项数据。当前数据会先自动备份。`;
    restoreConfirm.hidden = true;
    restoreCancel.hidden = true;
    restoreCard.hidden = false;
  };

  restore?.addEventListener("click", () => restoreFile?.click());
  restoreFile?.addEventListener("change", async () => {
    const file = restoreFile.files?.[0];
    if (!file) return;
    restore.disabled = true;
    const form = new FormData();
    form.append("backup", file);
    try {
      const response = await fetch("/api/backup/inspect", { method: "POST", body: form });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || `HTTP ${response.status}`);
      selectedRestoreFile = file;
      const count = data.manifest?.included?.length || 0;
      const created = data.manifest?.created_at
        ? new Date(data.manifest.created_at).toLocaleString()
        : "未知时间";
      restoreTitle.textContent = file.name;
      restoreDetail.textContent = `备份时间 ${created}，包含 ${count} 项数据。恢复将在下次启动前完成。`;
      restoreConfirm.hidden = false;
      restoreCancel.hidden = false;
      restoreCard.hidden = false;
    } catch (e) {
      selectedRestoreFile = null;
      restoreCard.hidden = true;
      toast(userFacingError(e, "这个备份无法使用，请选择由本应用导出的备份"));
    } finally {
      restore.disabled = false;
      restoreFile.value = "";
    }
  });

  restoreCancel?.addEventListener("click", () => {
    selectedRestoreFile = null;
    restoreCard.hidden = true;
  });

  restoreConfirm?.addEventListener("click", async () => {
    if (!selectedRestoreFile) return;
    restoreConfirm.disabled = true;
    const form = new FormData();
    form.append("backup", selectedRestoreFile);
    try {
      const response = await fetch("/api/restore", { method: "POST", body: form });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || `HTTP ${response.status}`);
      selectedRestoreFile = null;
      showPendingRestore(data.restore);
      toast("恢复已安排，请重新启动应用");
    } catch (e) {
      toast(userFacingError(e, "恢复安排失败，请稍后重试"));
    } finally {
      restoreConfirm.disabled = false;
    }
  });

  fetch("/api/restore/status")
    .then((response) => response.ok ? response.json() : null)
    .then((data) => { if (data?.pending) showPendingRestore(data.restore); })
    .catch(() => {});

  about?.addEventListener("click", async () => {
    if (!aboutCard) return;
    if (!aboutCard.hidden) { aboutCard.hidden = true; return; }
    try {
      const response = await fetch("/api/about");
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const info = await response.json();
      aboutCard.replaceChildren();
      const title = document.createElement("strong");
      title.textContent = `${info.name} ${info.version}`;
      const detail = document.createElement("p");
      detail.textContent = `${info.license} License · ${info.storage}`;
      const tagline = document.createElement("blockquote");
      tagline.className = "about-tagline";
      tagline.textContent = info.tagline || "";
      const privacy = document.createElement("p");
      privacy.textContent = info.privacy;
      aboutCard.append(title, tagline, detail, privacy);
      aboutCard.hidden = false;
    } catch (e) {
      toast(userFacingError(e, "暂时无法读取应用信息"));
    }
  });
}

async function init() {
  const savedTheme = localStorage.getItem("cc-theme") || "light";
  document.documentElement.dataset.theme = savedTheme;
  bind();
  loadSettings();
  checkHealth();
  await initBootstrap();

  // 恢复上次停留的页面（URL 不变，localStorage 持久化）
  const savedPage = localStorage.getItem("cc-page");
  if (["chat", "contacts", "discover", "memory", "settings"].includes(savedPage)) {
    switchPage(savedPage).catch((e) => console.warn("restore page failed:", e));
  }

  // T9: 加载会话侧栏 + 历史 + persona（替代原 inline fetch）
  // loadConversationSidebar 内部：
  //   1. GET /api/conversations → 渲染侧栏列表
  //   2. 恢复 localStorage("cc-conv") → 如有则 switchConversation
  //   3. 否则走 legacy：GET /api/history + GET /api/persona → applyPersona + 渲染气泡
  try {
    await loadConversationSidebar();
  } catch (e) {
    console.error("conversation sidebar load failed:", e);
    toast(userFacingError(e, "暂时无法加载会话"));
  }
}
document.addEventListener("DOMContentLoaded", init);
