/* ===== contacts-page.js — 通讯录（人设花名册）=====
 *
 * 对齐 PawzoChat 的“通讯录”分区：这里展示的是与你相伴的角色（persona / 人设），
 * 而不是真实微信联系人。数据来自 GET /api/persona（{id,name,avatar}）。
 * 支持：查看头像/名字 → 一键“去聊天”（ensureWebConversation）。
 *
 * 入口：loadContactsPage() — 由 state.js switchPage("contacts") 懒加载调用。
 * 渲染安全：动态文本用 textContent，不拼 innerHTML。
 */

import { dom, $, el } from "./state.js";
import { toast, userFacingError } from "./ui.js";

let loaded = false;
let bound = false;

function avatarEl(persona) {
  const wrap = el("div", "contact-avatar");
  if (persona.avatar) {
    const img = document.createElement("img");
    img.src = persona.avatar;
    img.alt = persona.name || "";
    img.loading = "lazy";
    wrap.appendChild(img);
  } else {
    wrap.textContent = (persona.name || "?").charAt(0);
  }
  return wrap;
}

async function goChat(persona) {
  // 创建/切换到该 persona 的网页会话，然后切回聊天页
  try {
    const mod = await import("./conversation-sidebar.js");
    if (!mod.ensureWebConversation) throw new Error("conversation-sidebar unavailable");
    await mod.ensureWebConversation(persona.id);
    const { switchPage } = await import("./state.js");
    await switchPage("chat");
  } catch (e) {
    console.warn("contacts goChat failed:", e);
    toast(userFacingError(e, "暂时无法开始对话"));
  }
}

export async function loadContactsPage() {
  bindOnce();
  const listEl = $("#contacts-list");
  const emptyEl = $("#contacts-empty");
  if (!listEl || loaded) return;

  loaded = true;
  let personas = [];
  try {
    const res = await fetch("/api/persona");
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    personas = await res.json();
  } catch (e) {
    console.warn("load contacts failed:", e);
    toast(userFacingError(e, "通讯录加载失败"));
  }

  listEl.innerHTML = "";
  if (!Array.isArray(personas) || personas.length === 0) {
    if (emptyEl) emptyEl.hidden = false;
    return;
  }
  if (emptyEl) emptyEl.hidden = true;

  for (const p of personas) {
    const item = el("div", "contact-item");
    item.appendChild(avatarEl(p));

    const info = el("div", "contact-info");
    const name = el("div", "contact-name");
    name.textContent = p.name || p.id || "未命名";
    info.appendChild(name);
    item.appendChild(info);

    const btn = el("button", "contact-chat-btn");
    btn.type = "button";
    btn.textContent = "发消息";
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      goChat(p).catch((err) => console.warn(err));
    });
    item.appendChild(btn);

    // 点击整行也可去聊天
    item.addEventListener("click", () => {
      goChat(p).catch((err) => console.warn(err));
    });

    listEl.appendChild(item);
  }
}

function bindOnce() {
  if (bound) return;
  bound = true;
  // 预留：未来可在此绑定刷新等
  const toolbar = $(".page-toolbar");
  void toolbar;
}
