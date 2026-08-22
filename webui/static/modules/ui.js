/* ===== ui.js — UI 工具：toast / 滚动 / 气泡 / 健康检查 / 输入框自适应 / 长按菜单 ===== */
import { state, dom, el } from './state.js';

let toastTimer = null;
export function toast(msg) {
  dom.toast.textContent = msg;
  dom.toast.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { dom.toast.hidden = true; }, 2600);
}

export function scrollBottom() {
  requestAnimationFrame(() => { dom.messages.scrollTop = dom.messages.scrollHeight; });
}

let msgMenuTimer = null;

export function hideMsgMenu() {
  const menu = document.getElementById("msg-menu");
  if (menu) menu.hidden = true;
}

export function showMsgMenu(bubbleEl, clientX, clientY) {
  const menu = document.getElementById("msg-menu");
  if (!menu) return;
  menu.hidden = false;
  menu.style.left = `${Math.min(clientX, window.innerWidth - 140)}px`;
  menu.style.top = `${Math.min(clientY, window.innerHeight - 100)}px`;

  const items = menu.querySelectorAll(".msg-menu-item");
  items.forEach((item) => {
    item.onclick = () => {
      const action = item.dataset.action;
      if (action === "copy") {
        navigator.clipboard.writeText(bubbleEl.textContent || "");
        toast("已复制");
      } else if (action === "regen") {
        regenLastMessage();
      }
      hideMsgMenu();
    };
  });
}

async function regenLastMessage() {
  try {
    const query = state.activeConversationId
      ? `?conversation_id=${encodeURIComponent(state.activeConversationId)}`
      : "";
    const delResp = await fetch(`/api/history/last${query}`, { method: "DELETE" });
    if (!delResp.ok) throw new Error(`删除失败 HTTP ${delResp.status}`);

    const messages = document.getElementById("messages");
    const userBubbles = messages.querySelectorAll(".row.me .bubble");
    const lastUserBubble = userBubbles[userBubbles.length - 1];
    if (!lastUserBubble) {
      toast("没有可重新生成的消息");
      return;
    }
    const userText = lastUserBubble.textContent || "";

    const allRows = messages.querySelectorAll(".row");
    if (allRows.length >= 2) {
      allRows[allRows.length - 1].remove(); // ai
      allRows[allRows.length - 2].remove(); // user
    }

    // dynamic import 避免与 chat-stream.js 循环依赖
    const { sendMessage } = await import('./chat-stream.js?v=4.3.11');
    const input = document.getElementById("input");
    input.value = userText;
    await sendMessage();
  } catch (e) {
    toast(userFacingError(e, "重新生成失败，请稍后重试"));
  }
}

export function addBubble(role, text, opts = {}) {
  document.getElementById("chat-welcome")?.remove();
  const row = el("div", `row ${role}`);
  const av = el("div", "bubble-avatar");
  av.textContent = role === "me" ? "🙂" : state.avatar;
  const bubble = el("div", "bubble");
  if (opts.html) bubble.innerHTML = text;
  else bubble.textContent = text;
  if (opts.sticker?.url) {
    const image = document.createElement("img");
    image.className = "sticker-image";
    image.src = opts.sticker.url;
    image.alt = opts.sticker.emotion || "表情包";
    bubble.appendChild(image);
  }
  if (opts.typing) bubble.classList.add("typing");
  row.appendChild(av);
  row.appendChild(bubble);
  dom.messages.appendChild(row);
  scrollBottom();

  // 长按菜单（touch 长按 600ms / mouse 右键 contextmenu）
  bubble.addEventListener("touchstart", (e) => {
    msgMenuTimer = setTimeout(() => {
      const touch = e.touches[0];
      showMsgMenu(bubble, touch.clientX, touch.clientY);
    }, 600);
  }, { passive: true });
  bubble.addEventListener("touchmove", () => { clearTimeout(msgMenuTimer); }, { passive: true });
  bubble.addEventListener("touchend", () => { clearTimeout(msgMenuTimer); }, { passive: true });
  bubble.addEventListener("contextmenu", (e) => {
    e.preventDefault();
    showMsgMenu(bubble, e.clientX, e.clientY);
  });

  return bubble;
}

export function userFacingError(error, fallback = "暂时无法完成操作") {
  if (error?.name === "AbortError") return "已停止生成";
  const message = String(error?.message || "").toLowerCase();
  if (message.includes("api key") || message.includes("unauthorized")) return "模型配置需要检查";
  if (message.includes("timeout") || message.includes("network") || message.includes("connection")) return "网络暂时不可用，请稍后重试";
  if (message.includes("http 5")) return "服务暂时忙碌，请稍后重试";
  return fallback;
}

export function autoResize() {
  dom.input.style.height = "auto";
  dom.input.style.height = Math.min(dom.input.scrollHeight, 120) + "px";
}

export async function checkHealth() {
  try {
    const r = await fetch("/api/settings");
    if (r.ok) { dom.connStatus.textContent = "在线"; dom.connStatus.classList.add("online"); return; }
  } catch {}
  dom.connStatus.textContent = "离线"; dom.connStatus.classList.remove("online");
}

export function toggleTheme() {
  const html = document.documentElement;
  const current = html.dataset.theme || "light";
  const next = current === "light" ? "dark" : "light";
  html.dataset.theme = next;
  localStorage.setItem("cc-theme", next);
}
