/* ===== discover-page.js — 发现（朋友圈 moments）=====
 *
 * 对齐 PawzoChat 的“发现”分区：本地朋友圈动态墙。
 * - 渲染 GET /api/moments 的 feed
 * - 发布：右上角按钮打开发布面板（文案 + 可选作者：我 / 某个角色）
 * - 点赞 / 取消点赞、评论、删除
 *
 * 入口：loadDiscoverPage() — 由 state.js switchPage("discover") 懒加载调用。
 * 渲染安全：动态文本一律 textContent，不拼 innerHTML。
 */

import { $, el } from "./state.js";
import { toast, userFacingError } from "./ui.js";

let loaded = false;

function fmtTime(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return "";
  const diff = Date.now() - d.getTime();
  const min = Math.floor(diff / 60000);
  if (min < 1) return "刚刚";
  if (min < 60) return `${min}分钟前`;
  const hr = Math.floor(min / 60);
  if (hr < 24) return `${hr}小时前`;
  const day = Math.floor(hr / 24);
  if (day < 7) return `${day}天前`;
  return `${d.getMonth() + 1}/${d.getDate()}`;
}

async function apiJson(url, opts = {}) {
  const res = await fetch(url, {
    headers: opts.body ? { "Content-Type": "application/json" } : undefined,
    ...opts,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`);
  return data;
}

function renderFeed(moments) {
  const feed = $("#moments-feed");
  const empty = $("#moments-empty");
  const end = $("#moments-end");
  if (!feed) return;
  feed.innerHTML = "";

  if (!moments.length) {
    if (empty) empty.hidden = false;
    if (end) end.hidden = true;
    return;
  }
  if (empty) empty.hidden = true;
  if (end) end.hidden = false;

  for (const m of moments) {
    feed.appendChild(buildMomentCard(m));
  }
}

function buildMomentCard(m) {
  const card = el("div", "moment-card");
  card.dataset.id = m.id;

  const head = el("div", "moment-head");
  const avatar = el("div", "moment-avatar");
  avatar.textContent = (m.author_label || "?").charAt(0);
  head.appendChild(avatar);

  const meta = el("div", "moment-meta");
  const name = el("div", "moment-name");
  name.textContent = m.author_label || m.author || "未知";
  meta.appendChild(name);

  const time = el("div", "moment-time");
  time.textContent = fmtTime(m.timestamp);
  meta.appendChild(time);
  head.appendChild(meta);

  const delBtn = el("button", "moment-del");
  delBtn.type = "button";
  delBtn.textContent = "删除";
  delBtn.title = "删除这条动态";
  delBtn.addEventListener("click", () => removeMoment(m, card));
  head.appendChild(delBtn);
  card.appendChild(head);

  if (m.text) {
    const text = el("div", "moment-text");
    text.textContent = m.text;
    card.appendChild(text);
  }

  const actions = el("div", "moment-actions");
  const likeBtn = el("button", "moment-like");
  likeBtn.type = "button";
  likeBtn.textContent =
    m.likes && m.likes.some((l) => l.author === "user") ? "♥" : "♡";
  likeBtn.classList.toggle("on", m.likes && m.likes.some((l) => l.author === "user"));
  const likeCount = el("span", "moment-count");
  likeCount.textContent = (m.likes || []).length > 0 ? ` ${m.likes.length}` : "";
  likeBtn.appendChild(likeCount);
  likeBtn.addEventListener("click", () => toggleLike(m, likeBtn));
  actions.appendChild(likeBtn);

  const replyBtn = el("button", "moment-reply");
  replyBtn.type = "button";
  replyBtn.textContent = "评论";
  replyBtn.addEventListener("click", () => addReply(m));
  actions.appendChild(replyBtn);
  card.appendChild(actions);

  if (m.replies && m.replies.length) {
    const replies = el("div", "moment-replies");
    for (const r of m.replies) {
      const row = el("div", "moment-reply");
      const who = el("span", "moment-reply-who");
      who.textContent = r.reply_to_label
        ? `${r.author_label} 回复 ${r.reply_to_label}`
        : r.author_label;
      row.appendChild(who);
      const txt = el("span", "moment-reply-text");
      txt.textContent = `：${r.text}`;
      row.appendChild(txt);
      const t = el("span", "moment-reply-time");
      t.textContent = ` ${fmtTime(r.timestamp)}`;
      row.appendChild(t);
      replies.appendChild(row);
    }
    card.appendChild(replies);
  }

  return card;
}

async function reload() {
  try {
    const data = await apiJson("/api/moments");
    renderFeed(data.moments || []);
  } catch (e) {
    toast(userFacingError(e, "朋友圈加载失败"));
  }
}

async function toggleLike(m, btn) {
  try {
    const liked = btn.classList.contains("on");
    if (liked) {
      await apiJson(`/api/moments/${m.id}/like`, { method: "DELETE" });
    } else {
      await apiJson(`/api/moments/${m.id}/like`, { method: "POST" });
    }
    await reload();
  } catch (e) {
    toast(userFacingError(e, "操作失败"));
  }
}

async function addReply(m) {
  const text = prompt(`评论给 ${m.author_label || "TA"}:`);
  if (!text || !text.trim()) return;
  try {
    await apiJson(`/api/moments/${m.id}/replies`, {
      method: "POST",
      body: JSON.stringify({ text: text.trim() }),
    });
    await reload();
  } catch (e) {
    toast(userFacingError(e, "评论失败"));
  }
}

async function removeMoment(m, card) {
  if (!confirm("确定删除这条动态？")) return;
  try {
    await apiJson(`/api/moments/${m.id}`, { method: "DELETE" });
    card.remove();
    toast("已删除");
  } catch (e) {
    toast(userFacingError(e, "删除失败"));
  }
}

async function openPublish() {
  const text = prompt("此刻在想什么？");
  if (!text || !text.trim()) return;
  try {
    await apiJson("/api/moments", {
      method: "POST",
      body: JSON.stringify({ text: text.trim(), author: "user" }),
    });
    await reload();
    toast("已发布");
  } catch (e) {
    toast(userFacingError(e, "发布失败"));
  }
}

function bindPublish() {
  const btn = $("#moments-publish-btn");
  if (!btn) return;
  btn.addEventListener("click", openPublish);
}

export async function loadDiscoverPage() {
  if (loaded) return;
  loaded = true;
  bindPublish();
  await reload();
}
