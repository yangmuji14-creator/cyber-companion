/* ===== plugins-page.js — 插件管理子页（工具目录，只读）=====
 *
 * 列出当前可用工具：内置工具（core/tools/builtin）+ MCP 工具。
 * 只读目录：展示名称、来源、描述、参数。运行时不做启用/禁用（当前 ToolRegistry
 * 不支持 per-tool 开关，跨协议的工具过滤属于更大改动，此处保持只读、如实展示）。
 *
 * 后端端点：GET /api/plugins
 * 渲染安全：动态文本一律 textContent，防止 XSS。
 * 入口：renderPluginsPage(container)
 */

import { el } from "./state.js";
import { toast, userFacingError } from "./ui.js";

const CONTAINER_SEL = "#tab-content-plugins";

async function apiJson(url) {
  const res = await fetch(url);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`);
  return data;
}

function paramNames(parameters) {
  if (!parameters || !parameters.properties) return [];
  const req = new Set((parameters.required || []));
  return Object.keys(parameters.properties).map((k) => (req.has(k) ? `${k}*` : k));
}

function buildToolCard(t) {
  const card = el("div", "plug-card");
  card.dataset.source = t.source || "builtin";

  const head = el("div", "plug-card-head");
  const badge = el("span", `plug-badge ${t.source === "mcp" ? "mcp" : ""}`);
  badge.textContent = t.source === "mcp" ? (t.server || "MCP") : "内置";
  head.appendChild(badge);
  const name = el("div", "plug-card-name");
  name.textContent = t.name || "未命名";
  head.appendChild(name);
  card.appendChild(head);

  const desc = el("div", "plug-card-desc");
  desc.textContent = t.description || "（无描述）";
  card.appendChild(desc);

  const params = paramNames(t.parameters);
  if (params.length) {
    const row = el("div", "plug-card-params");
    row.textContent = `参数：${params.join("、")}`;
    card.appendChild(row);
  }

  return card;
}

async function refresh(target) {
  try {
    const data = await apiJson("/api/plugins");
    const plugins = data.plugins || [];
    target.innerHTML = "";

    const title = el("h3", "plug-title");
    title.textContent = "插件 / 工具";
    target.appendChild(title);

    const meta = el("div", "plug-meta");
    meta.textContent = `共 ${plugins.length} 个工具 · 内置 ${data.builtin_count || 0} · MCP ${data.mcp_count || 0}`;
    target.appendChild(meta);

    const mcpStatus = data.mcp_status;
    if (mcpStatus) {
      const status = el("div", "plug-mcp-status");
      status.textContent =
        typeof mcpStatus === "object" && mcpStatus.connected !== undefined
          ? `MCP 连接：${mcpStatus.connected}`
          : "MCP 状态：见 MCP 扩展页";
      target.appendChild(status);
    }

    if (!plugins.length) {
      const empty = el("div", "plug-empty");
      empty.textContent = "暂无可用工具。";
      target.appendChild(empty);
      return;
    }

    // 分组展示：内置在前，MCP 在后
    const grouped = [
      ["内置工具", plugins.filter((p) => p.source !== "mcp")],
      ["MCP 工具", plugins.filter((p) => p.source === "mcp")],
    ];
    for (const [label, list] of grouped) {
      if (!list.length) continue;
      const section = el("div", "plug-group");
      const h = el("div", "plug-group-title");
      h.textContent = `${label}（${list.length}）`;
      section.appendChild(h);
      const grid = el("div", "plug-grid");
      for (const t of list) grid.appendChild(buildToolCard(t));
      section.appendChild(grid);
      target.appendChild(section);
    }

    const note = el("p", "plug-note");
    note.textContent = "当前为只读目录，工具的启用/禁用与执行在对话管道中按需调用。";
    target.appendChild(note);
  } catch (e) {
    target.innerHTML = "";
    const err = el("div", "plug-error");
    err.textContent = userFacingError(e, "插件列表加载失败");
    target.appendChild(err);
  }
}

/** 渲染插件子页到指定容器；若无容器则尝试 #tab-content-plugins。 */
export async function renderPluginsPage(container = null) {
  const target = container || document.querySelector(CONTAINER_SEL);
  if (!target) return;
  await refresh(target);
}
