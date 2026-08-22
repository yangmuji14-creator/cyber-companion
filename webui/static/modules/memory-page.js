/* ===== memory-page.js — 记忆页：重要度记忆 + 大脑日记 =====
 * 由 state.js switchPage("memory") 动态 import 调用 loadMemoryPage()。
 * 两个子标签：
 *   - 重要度记忆：GET /api/memory 分页 + level 过滤 + 详情 GET /api/memory/{id}
 *   - 大脑日记：GET /api/life_summary 列表 + 详情（数据已含全字段）
 * 所有用户内容用 textContent 渲染（防 XSS），绝不拼接 HTML 字符串。
 * 重要度记忆支持删除（DELETE /api/memory/{id}）；大脑日记为定期生成，不删。
 */
import { el, $, switchPage } from "./state.js";
import { toast, userFacingError } from "./ui.js";

// ===== 模块状态 =====
let handlersBound = false;
let currentSubtab = "important"; // "important" | "diary"
let currentOffset = 0;
let currentLevelFilter = 0; // 0 = 全部, 1-5 = 对应 level
let totalItems = 0;
let currentScope = { personaId: "", conversationId: "" };
const PAGE_SIZE = 20;

const listEl = $("#memory-list-container");
const detailEl = $("#memory-detail-container");

// ===== 工具函数 =====
function relativeTime(isoString) {
  if (!isoString) return "";
  const d = new Date(isoString);
  if (isNaN(d.getTime())) return String(isoString);
  const diff = Date.now() - d.getTime();
  const sec = Math.floor(diff / 1000);
  if (sec < 60) return "刚刚";
  const min = Math.floor(sec / 60);
  if (min < 60) return min + " 分钟前";
  const hr = Math.floor(min / 60);
  if (hr < 24) return hr + " 小时前";
  const day = Math.floor(hr / 24);
  if (day < 30) return day + " 天前";
  const month = Math.floor(day / 30);
  if (month < 12) return month + " 月前";
  return Math.floor(day / 365) + " 年前";
}

function truncate(s, n) {
  if (!s) return "";
  return s.length > n ? s.slice(0, n) + "…" : s;
}

function clearContainer(c) {
  while (c && c.firstChild) c.removeChild(c.firstChild);
}

function scopeQuery() {
  if (currentScope.conversationId) {
    return "conversation_id=" + encodeURIComponent(currentScope.conversationId);
  }
  if (currentScope.personaId) {
    return "persona_id=" + encodeURIComponent(currentScope.personaId);
  }
  return "";
}

function withScope(path) {
  const query = scopeQuery();
  if (!query) return path;
  return path + (path.includes("?") ? "&" : "?") + query;
}

function showList() {
  if (listEl) listEl.hidden = false;
  if (detailEl) detailEl.hidden = true;
}

function showDetail() {
  if (listEl) listEl.hidden = true;
  if (detailEl) detailEl.hidden = false;
}

// ===== 子标签 1：重要度记忆 =====
export async function loadMemoryList(offset = 0, levelFilter = 0) {
  if (!listEl) return;
  showList();
  listEl.textContent = "加载中…";
  currentOffset = offset;
  currentLevelFilter = levelFilter;
  const levelMin = levelFilter || 1;
  const levelMax = levelFilter || 5;
  const url = withScope("/api/memory?offset=" + offset + "&limit=" + PAGE_SIZE +
              "&level_min=" + levelMin + "&level_max=" + levelMax);
  try {
    const resp = await fetch(url);
    if (!resp.ok) throw new Error("HTTP " + resp.status);
    const data = await resp.json();
    totalItems = data.total || 0;
    renderMemoryList(data.messages || [], levelFilter);
  } catch (e) {
    listEl.textContent = "加载失败，请稍后重试";
  }
}

function renderMemoryList(messages, levelFilter) {
  clearContainer(listEl);

  // 过滤栏：全部 + ★1-★5
  const filterBar = el("div", "memory-filter");
  const filters = [
    { label: "全部", val: 0 },
    { label: "★1", val: 1 },
    { label: "★2", val: 2 },
    { label: "★3", val: 3 },
    { label: "★4", val: 4 },
    { label: "★5", val: 5 },
  ];
  for (const f of filters) {
    const btn = el("button");
    btn.textContent = f.label;
    if (f.val === levelFilter) btn.classList.add("active");
    btn.addEventListener("click", () => loadMemoryList(0, f.val));
    filterBar.appendChild(btn);
  }
  listEl.appendChild(filterBar);

  if (messages.length === 0) {
    const empty = el("div");
    empty.textContent = "暂无记忆";
    empty.style.padding = "24px";
    empty.style.color = "var(--ink-faint)";
    empty.style.textAlign = "center";
    listEl.appendChild(empty);
    renderPagination();
    return;
  }

  for (const m of messages) {
    const item = el("div", "memory-item");
    item.dataset.memoryId = m.id;

    const content = el("div", "memory-item-content");
    content.textContent = truncate(m.content, 60);
    item.appendChild(content);

    const meta = el("div", "memory-item-meta");
    const lvl = el("span"); lvl.textContent = "★" + m.level;
    const cat = el("span"); cat.textContent = m.category || "";
    const time = el("span"); time.textContent = relativeTime(m.created_at);
    meta.appendChild(lvl);
    meta.appendChild(cat);
    meta.appendChild(time);
    item.appendChild(meta);

    item.addEventListener("click", () => loadMemoryDetail(m.id));
    listEl.appendChild(item);
  }

  renderPagination();
}

function renderPagination() {
  const totalPages = Math.max(1, Math.ceil(totalItems / PAGE_SIZE));
  const currentPage = Math.floor(currentOffset / PAGE_SIZE) + 1;

  const pagination = el("div", "memory-pagination");

  const prevBtn = el("button", "ghost-btn");
  prevBtn.textContent = "上一页";
  prevBtn.disabled = currentOffset === 0;
  prevBtn.addEventListener("click", () => {
    if (currentOffset > 0) loadMemoryList(currentOffset - PAGE_SIZE, currentLevelFilter);
  });
  pagination.appendChild(prevBtn);

  const info = el("span");
  info.textContent = "第 " + currentPage + " 页 / 共 " + totalPages + " 页";
  pagination.appendChild(info);

  const nextBtn = el("button", "ghost-btn");
  nextBtn.textContent = "下一页";
  nextBtn.disabled = currentOffset + PAGE_SIZE >= totalItems;
  nextBtn.addEventListener("click", () => {
    if (currentOffset + PAGE_SIZE < totalItems) loadMemoryList(currentOffset + PAGE_SIZE, currentLevelFilter);
  });
  pagination.appendChild(nextBtn);

  listEl.appendChild(pagination);
}

async function loadMemoryDetail(id) {
  if (!detailEl) return;
  showDetail();
  clearContainer(detailEl);
  detailEl.textContent = "加载中…";
  try {
    const resp = await fetch(withScope("/api/memory/" + encodeURIComponent(id)));
    if (!resp.ok) throw new Error("HTTP " + resp.status);
    const m = await resp.json();
    renderMemoryDetail(m);
  } catch (e) {
    clearContainer(detailEl);
    detailEl.textContent = "加载失败，请稍后重试";
  }
}

function renderMemoryDetail(m) {
  clearContainer(detailEl);

  const backBtn = el("button", "ghost-btn");
  backBtn.textContent = "← 返回列表";
  backBtn.addEventListener("click", () => { showList(); });
  detailEl.appendChild(backBtn);

  const wrap = el("div", "memory-detail");

  const h = el("h4");
  h.textContent = truncate(m.content, 40);
  wrap.appendChild(h);

  const meta = el("div", "memory-detail-meta");
  const parts = [];
  parts.push("★" + m.level);
  if (m.category) parts.push(m.category);
  if (m.created_at) parts.push("创建: " + m.created_at);
  if (m.last_accessed) parts.push("最近访问: " + relativeTime(m.last_accessed));
  if (typeof m.access_count === "number") parts.push("访问 " + m.access_count + " 次");
  if (m.source) parts.push("来源: " + m.source);
  if (typeof m.confidence === "number") parts.push("置信度: " + m.confidence);
  if (typeof m.forget_score === "number") parts.push("遗忘分: " + m.forget_score);
  if (m.archived) parts.push("已归档");
  if (m.superseded_by) parts.push("被替代: " + m.superseded_by);
  meta.textContent = parts.join(" · ");
  wrap.appendChild(meta);

  const contentPara = el("div");
  contentPara.textContent = m.content;
  contentPara.style.whiteSpace = "pre-wrap";
  contentPara.style.marginBottom = "12px";
  wrap.appendChild(contentPara);

  if (Array.isArray(m.tags) && m.tags.length > 0) {
    const tagsWrap = el("div", "memory-detail-tags");
    for (const t of m.tags) {
      const tag = el("span", "tag");
      tag.textContent = t;
      tagsWrap.appendChild(tag);
    }
    wrap.appendChild(tagsWrap);
  }

  if (Array.isArray(m.related_memory_ids) && m.related_memory_ids.length > 0) {
    const relWrap = el("div");
    relWrap.style.marginTop = "12px";
    const relLabel = el("div");
    relLabel.textContent = "关联记忆：";
    relLabel.style.fontSize = "12px";
    relLabel.style.color = "var(--ink-faint)";
    relWrap.appendChild(relLabel);
    for (const rid of m.related_memory_ids) {
      const ridEl = el("span", "tag");
      ridEl.textContent = rid;
      relWrap.appendChild(ridEl);
    }
    wrap.appendChild(relWrap);
  }

  // 删除按钮：危险操作，需二次确认。加载中禁用防重复点击。
  const delBtn = el("button", "memory-delete-btn");
  delBtn.type = "button";
  delBtn.textContent = "删除";
  delBtn.addEventListener("click", async () => {
    if (!confirm("确定删除这条记忆？此操作不可撤销")) return;
    delBtn.disabled = true;
    const originalText = delBtn.textContent;
    delBtn.textContent = "删除中…";
    try {
      const resp = await fetch(withScope("/api/memory/" + encodeURIComponent(m.id)), {
        method: "DELETE",
      });
      if (!resp.ok) {
        const err = await resp.json().catch(() => ({}));
        throw new Error(err.error || "HTTP " + resp.status);
      }
      toast("记忆已删除");
      await loadMemoryList(currentOffset, currentLevelFilter);
    } catch (e) {
      toast(userFacingError(e, "删除记忆失败，请稍后重试"));
      delBtn.disabled = false;
      delBtn.textContent = originalText;
    }
  });
  wrap.appendChild(delBtn);

  detailEl.appendChild(wrap);
}

// ===== 子标签 2：大脑日记 =====
export async function loadLifeSummaryList() {
  if (!listEl) return;
  showList();
  listEl.textContent = "加载中…";
  try {
    const resp = await fetch(withScope("/api/life_summary?limit=20"));
    if (!resp.ok) throw new Error("HTTP " + resp.status);
    const data = await resp.json();
    renderSummaryList(data.summaries || []);
  } catch (e) {
    listEl.textContent = "加载失败，请稍后重试";
  }
}

function renderSummaryList(summaries) {
  clearContainer(listEl);

  if (summaries.length === 0) {
    const empty = el("div");
    empty.textContent = "还没有写下心事";
    empty.style.padding = "24px";
    empty.style.color = "var(--ink-faint)";
    empty.style.textAlign = "center";
    listEl.appendChild(empty);
    return;
  }

  for (const s of summaries) {
    const item = el("div", "memory-item");
    item.classList.add("diary-entry");
    item.dataset.summaryId = s.id;

    const content = el("div", "memory-item-content");
    content.textContent = truncate((s.summary || "").replace(/\s+/g, " "), 96);
    item.appendChild(content);

    const meta = el("div", "memory-item-meta");
    const type = el("span"); type.textContent = summaryTypeLabel(s.summary_type);
    const count = el("span"); count.textContent = (s.message_count || 0) + " 条消息";
    const time = el("span"); time.textContent = relativeTime(s.created_at);
    meta.appendChild(type);
    meta.appendChild(count);
    meta.appendChild(time);
    item.appendChild(meta);

    item.addEventListener("click", () => renderSummaryDetail(s));
    listEl.appendChild(item);
  }
}

function summaryTypeLabel(type) {
  const labels = {
    diary: "心事日记",
    periodic: "阶段记录",
    milestone: "重要时刻",
    initial: "最初印象",
  };
  return labels[type] || "大脑日记";
}

function renderSummaryDetail(s) {
  if (!detailEl) return;
  showDetail();
  clearContainer(detailEl);

  const backBtn = el("button", "ghost-btn");
  backBtn.textContent = "← 返回列表";
  backBtn.addEventListener("click", () => { showList(); });
  detailEl.appendChild(backBtn);

  const wrap = el("div", "memory-detail");

  const h = el("h4");
  h.textContent = summaryTypeLabel(s.summary_type);
  wrap.appendChild(h);

  const meta = el("div", "memory-detail-meta");
  const parts = [];
  if (s.created_at) parts.push("写于 " + s.created_at);
  if (typeof s.message_count === "number") parts.push(s.message_count + " 条消息");
  meta.textContent = parts.join(" · ");
  wrap.appendChild(meta);

  if (s.summary) {
    const p = el("div", "diary-prose");
    p.textContent = s.summary;
    p.style.whiteSpace = "pre-wrap";
    p.style.marginBottom = "12px";
    wrap.appendChild(p);
  }

  if (s.recent_status) {
    const label = el("div");
    label.textContent = "那段时间";
    label.style.fontSize = "12px";
    label.style.color = "var(--ink-faint)";
    label.style.marginTop = "8px";
    wrap.appendChild(label);
    const p = el("div");
    p.textContent = s.recent_status;
    p.style.whiteSpace = "pre-wrap";
    wrap.appendChild(p);
  }

  if (Array.isArray(s.key_events) && s.key_events.length > 0) {
    const label = el("div");
    label.textContent = "关键事件：";
    label.style.fontSize = "12px";
    label.style.color = "var(--ink-faint)";
    label.style.marginTop = "12px";
    wrap.appendChild(label);
    const ul = el("ul");
    for (const ev of s.key_events) {
      const li = el("li");
      li.textContent = ev;
      ul.appendChild(li);
    }
    wrap.appendChild(ul);
  }

  if (s.emotional_trends) {
    const label = el("div");
    label.textContent = "情绪底色";
    label.style.fontSize = "12px";
    label.style.color = "var(--ink-faint)";
    label.style.marginTop = "12px";
    wrap.appendChild(label);
    const p = el("div");
    p.textContent = typeof s.emotional_trends === "string"
      ? s.emotional_trends
      : JSON.stringify(s.emotional_trends);
    p.style.whiteSpace = "pre-wrap";
    wrap.appendChild(p);
  }

  detailEl.appendChild(wrap);
}

// ===== 子标签切换 =====
function setSubtab(name) {
  currentSubtab = name;
  document.querySelectorAll(".memory-subtab").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.subtab === name);
  });
}

function bindHandlers() {
  if (handlersBound) return;
  handlersBound = true;
  document.querySelectorAll(".memory-subtab").forEach((btn) => {
    btn.addEventListener("click", () => {
      const name = btn.dataset.subtab;
      if (name === "important") {
        setSubtab("important");
        loadMemoryList(0, currentLevelFilter);
      } else if (name === "diary") {
        setSubtab("diary");
        loadLifeSummaryList();
      }
    });
  });
}

// ===== 入口：由 state.js switchPage("memory") 调用 =====
export async function loadMemoryPage() {
  if (!listEl || !detailEl) return;
  // T4 CSS 未给 #memory-detail-container 设 flex/overflow，长内容会被裁切。
  // 此处补 inline style 保证详情可滚动（不修改 style.css）。
  detailEl.style.flex = "1";
  detailEl.style.overflowY = "auto";
  bindHandlers();
  showList();
  if (currentSubtab === "diary") {
    await loadLifeSummaryList();
  } else {
    await loadMemoryList(0, currentLevelFilter);
  }
}

export async function openMemoryPage({ tab = "important", personaId = "", conversationId = "" } = {}) {
  currentScope = {
    personaId: String(personaId || ""),
    conversationId: String(conversationId || ""),
  };
  setSubtab(tab === "diary" ? "diary" : "important");
  await switchPage("memory");
  await loadMemoryPage();
}
