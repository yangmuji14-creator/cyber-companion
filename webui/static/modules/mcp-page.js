/* ===== mcp-page.js — MCP 扩展配置子页 =====
 *
 * 把项目已有的 MCP 能力（core/tools/mcp_manager，配置在 CONFIG_DIR/mcp_servers.json）
 * 完整暴露到 Web 设置：
 *  - server 列表（名/命令/连接状态/工具数）
 *  - 新增/编辑（富表单：命令、多行参数、环境变量、工作目录、超时、自动重连、启停）
 *  - 测试连接 / 逐 server 连接 / 刷新工具 / 查看工具列表 / 删除
 *  - JSON 导入（stdio 服务器，Claude Desktop 风格）
 *
 * 后端端点：
 *  - GET/POST/PUT/DELETE /api/mcp/servers
 *  - POST /api/mcp/connect、POST /api/mcp/servers/{name}/test
 *  - POST /api/mcp/servers/{name}/connect|disconnect|refresh
 *  - GET /api/mcp/servers/{name}/tools
 *
 * 渲染安全：动态文本一律 textContent，防止 XSS。
 * 入口：renderMcpPage(container)
 */

import { el } from "./state.js";
import { toast, userFacingError } from "./ui.js";

const CONTAINER_SEL = "#mcp-container, #tab-content-mcp";

async function apiJson(url, opts = {}) {
  const res = await fetch(url, {
    headers: opts.body ? { "Content-Type": "application/json" } : undefined,
    ...opts,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`);
  return data;
}

async function loadServers() {
  const data = await apiJson("/api/mcp/servers");
  return data.servers || [];
}

function stateLabel(s) {
  if (s._connected) return `已连接 · ${s._tools} 个工具`;
  if (s._state === "error") return "连接失败";
  return "未连接";
}

function renderList(container, servers) {
  container.innerHTML = "";

  const head = el("div", "mcp-toolbar");
  const title = el("h3", "mcp-title");
  title.textContent = "MCP 扩展";
  head.appendChild(title);

  const actions = el("div", "mcp-toolbar-actions");
  const importBtn = el("button", "ghost-btn");
  importBtn.type = "button";
  importBtn.textContent = "JSON 导入";
  importBtn.addEventListener("click", () => openJsonImport(container));
  actions.appendChild(importBtn);

  const connectBtn = el("button", "ghost-btn");
  connectBtn.type = "button";
  connectBtn.textContent = "重连全部";
  connectBtn.addEventListener("click", reconnectAll);
  actions.appendChild(connectBtn);

  const addBtn = el("button", "primary-btn");
  addBtn.type = "button";
  addBtn.textContent = "新增服务";
  addBtn.addEventListener("click", () => openEditor(container, null));
  actions.appendChild(addBtn);
  head.appendChild(actions);
  container.appendChild(head);

  if (!servers.length) {
    const empty = el("div", "mcp-empty");
    empty.textContent = "还没有 MCP 服务，点「新增服务」或「JSON 导入」添加。";
    container.appendChild(empty);
    return;
  }

  const list = el("div", "mcp-list");
  for (const s of servers) {
    list.appendChild(buildServerRow(container, s));
  }
  container.appendChild(list);
}

function buildServerRow(container, s) {
  const row = el("div", "mcp-server");
  const info = el("div", "mcp-server-info");
  const name = el("div", "mcp-server-name");
  name.textContent = s.name || "未命名";
  info.appendChild(name);

  const meta = el("div", "mcp-server-meta");
  const cmd = el("span", "mcp-server-cmd");
  cmd.textContent = `${s.command || ""} ${(s.args || []).join(" ")}`.trim() || "stdio 服务";
  meta.appendChild(cmd);
  info.appendChild(meta);
  row.appendChild(info);

  const state = el("div", `mcp-server-state ${s._connected ? "on" : ""}`);
  state.textContent = stateLabel(s);
  row.appendChild(state);

  const btnGroup = el("div", "mcp-server-btns");

  // 查看工具
  const tools = el("button", "ghost-btn small");
  tools.type = "button";
  tools.textContent = "工具";
  tools.title = "查看该服务的工具";
  tools.addEventListener("click", () => showTools(container, s));
  btnGroup.appendChild(tools);

  // 测试连接
  const test = el("button", "ghost-btn small");
  test.type = "button";
  test.textContent = "测试";
  test.title = "测试连接";
  test.addEventListener("click", () => testConnection(container, s));
  btnGroup.appendChild(test);

  // 连接/断开
  const conn = el("button", "ghost-btn small");
  conn.type = "button";
  conn.textContent = s._connected ? "断开" : "连接";
  conn.addEventListener("click", () => toggleConnection(container, s, !!s._connected));
  btnGroup.appendChild(conn);

  // 刷新工具
  const rf = el("button", "ghost-btn small");
  rf.type = "button";
  rf.textContent = "刷新";
  rf.title = "刷新工具发现";
  rf.addEventListener("click", () => refreshServer(container, s));
  btnGroup.appendChild(rf);

  const edit = el("button", "ghost-btn small");
  edit.type = "button";
  edit.textContent = "编辑";
  edit.addEventListener("click", () => openEditor(container, s));
  btnGroup.appendChild(edit);

  const del = el("button", "ghost-btn small danger");
  del.type = "button";
  del.textContent = "删除";
  del.addEventListener("click", () => removeServer(container, s));
  btnGroup.appendChild(del);

  row.appendChild(btnGroup);
  return row;
}

async function refresh(container) {
  try {
    const servers = await loadServers();
    renderList(container, servers);
  } catch (e) {
    toast(userFacingError(e, "MCP 加载失败"));
  }
}

async function reconnectAll() {
  try {
    const data = await apiJson("/api/mcp/connect", { method: "POST" });
    toast(`已连接 ${data.connected} 个 MCP 服务`);
  } catch (e) {
    toast(userFacingError(e, "重连失败"));
  }
}

async function removeServer(container, s) {
  if (!confirm(`删除 MCP 服务「${s.name}」？`)) return;
  try {
    await apiJson(`/api/mcp/servers/${encodeURIComponent(s.name)}`, { method: "DELETE" });
    await refresh(container);
    toast("已删除");
  } catch (e) {
    toast(userFacingError(e, "删除失败"));
  }
}

async function testConnection(container, s) {
  try {
    const data = await apiJson(`/api/mcp/servers/${encodeURIComponent(s.name)}/test`, { method: "POST" });
    toast(data.ok ? `连接成功 · ${data.tools} 个工具` : `连接失败：${data.error || ""}`);
    await refresh(container);
  } catch (e) {
    toast(userFacingError(e, "测试失败"));
  }
}

async function toggleConnection(container, s, isConnected) {
  try {
    const url = `/api/mcp/servers/${encodeURIComponent(s.name)}/${isConnected ? "disconnect" : "connect"}`;
    await apiJson(url, { method: "POST" });
    await refresh(container);
    toast(isConnected ? "已断开" : "已连接");
  } catch (e) {
    toast(userFacingError(e, "操作失败"));
  }
}

async function refreshServer(container, s) {
  try {
    const data = await apiJson(`/api/mcp/servers/${encodeURIComponent(s.name)}/refresh`, { method: "POST" });
    toast(`已刷新 · ${data.tools} 个工具`);
    await refresh(container);
  } catch (e) {
    toast(userFacingError(e, "刷新失败"));
  }
}

async function showTools(container, s) {
  try {
    const data = await apiJson(`/api/mcp/servers/${encodeURIComponent(s.name)}/tools`);
    const tools = data.tools || [];
    if (!tools.length) {
      toast("该服务暂无可列出工具（可能未连接）");
      return;
    }
    const names = tools.map((t) => t.name).join("\n");
    alert(`「${s.name}」工具列表：\n\n${names}`);
  } catch (e) {
    toast(userFacingError(e, "读取工具失败"));
  }
}

/* ===== 富表单 ===== */

function wrapField(labelText) {
  const wrap = el("label", "mcp-field");
  const span = el("span");
  span.textContent = labelText;
  wrap.appendChild(span);
  return wrap;
}

function fieldInput(labelText, value = "", placeholder = "") {
  const wrap = wrapField(labelText);
  const input = document.createElement("input");
  input.type = "text";
  input.value = value;
  input.placeholder = placeholder;
  wrap.appendChild(input);
  return wrap;
}

function fieldTextarea(labelText, value = "", placeholder = "") {
  const wrap = wrapField(labelText);
  const ta = document.createElement("textarea");
  ta.rows = 3;
  ta.value = value;
  ta.placeholder = placeholder;
  wrap.appendChild(ta);
  return wrap;
}

function fieldCheckbox(labelText, checked) {
  const wrap = el("label", "mcp-check");
  const input = document.createElement("input");
  input.type = "checkbox";
  input.checked = !!checked;
  const span = el("span");
  span.textContent = labelText;
  wrap.appendChild(input);
  wrap.appendChild(span);
  return wrap;
}

const ENV_META = "_envKeys";

function envEditor(existing) {
  const card = el("div", "mcp-env-editor");
  const head = el("div", "mcp-env-head");
  const lbl = el("span", "mcp-env-label");
  lbl.textContent = "环境变量";
  head.appendChild(lbl);
  const addBtn = el("button", "ghost-btn small");
  addBtn.type = "button";
  addBtn.textContent = "+ 添加";
  addBtn.addEventListener("click", () => addEnvRow(card));
  head.appendChild(addBtn);
  card.appendChild(head);

  card[ENV_META] = card[ENV_META] ?? {};
  const keys = Object.keys((existing && existing.env) || {});
  if (keys.length === 0) {
    addEnvRow(card);
  } else {
    for (const k of keys) {
      addEnvRow(card, k, existing.env[k]);
    }
  }
  return card;
}

function addEnvRow(card, key = "", value = "") {
  const row = el("div", "env-row");
  const k = document.createElement("input");
  k.className = "env-key";
  k.placeholder = "KEY";
  k.value = key;
  const v = document.createElement("input");
  v.className = "env-val";
  v.type = "password";
  v.placeholder = "VALUE";
  v.value = value;
  const rm = el("button", "ghost-btn small danger");
  rm.type = "button";
  rm.textContent = "✕";
  rm.addEventListener("click", () => row.remove());
  row.appendChild(k);
  row.appendChild(v);
  row.appendChild(rm);
  card.appendChild(row);
}

function collectEnv(card) {
  const env = {};
  if (!card) return env;
  for (const row of card.querySelectorAll(".env-row")) {
    const key = row.querySelector(".env-key").value.trim();
    const val = row.querySelector(".env-val").value;
    if (key) env[key] = val;
  }
  return env;
}

function openEditor(container, existing) {
  container.innerHTML = "";
  const card = el("div", "mcp-editor");

  const title = el("h3", "mcp-title");
  title.textContent = existing ? `编辑服务：${existing.name}` : "新增 MCP 服务";
  card.appendChild(title);

  const nameInput = fieldInput("服务名", existing ? existing.name : "", "如 my-server");
  const cmdInput = fieldInput("启动命令", existing ? existing.command : "", "如 npx / python");
  const argsInput = fieldTextarea(
    "参数（每行一个）",
    existing ? (existing.args || []).join("\n") : "",
    "-y\npkg-name"
  );
  const cwdInput = fieldInput("工作目录（可选）", existing ? (existing.cwd || "") : "", "留空则用项目资源目录");
  const timeoutInput = fieldInput(
    "工具超时（秒）",
    existing && existing.operation_timeout ? String(existing.operation_timeout) : "",
    "默认 60"
  );
  const autoReconnect = fieldCheckbox("自动重连", existing ? existing.auto_reconnect !== false : true);

  const envCard = envEditor(existing);

  card.appendChild(nameInput);
  card.appendChild(cmdInput);
  card.appendChild(argsInput);
  card.appendChild(cwdInput);
  card.appendChild(timeoutInput);
  card.appendChild(autoReconnect);
  card.appendChild(envCard);

  // 测试连接（编辑已有服务时）
  if (existing) {
    const testBtn = el("button", "ghost-btn");
    testBtn.type = "button";
    testBtn.textContent = "测试连接";
    testBtn.addEventListener("click", () => testConnection(container, existing));
    card.appendChild(testBtn);
  }

  const btns = el("div", "mcp-editor-btns");
  const cancel = el("button", "ghost-btn");
  cancel.type = "button";
  cancel.textContent = "取消";
  cancel.addEventListener("click", () => refresh(container));
  btns.appendChild(cancel);

  const save = el("button", "primary-btn");
  save.type = "button";
  save.textContent = "保存";
  save.addEventListener("click", async () => {
    const name = nameInput.querySelector("input").value.trim();
    const command = cmdInput.querySelector("input").value.trim();
    const args = argsInput.querySelector("textarea").value
      .split(/\n/)
      .map((s) => s.trim())
      .filter(Boolean);
    const cwd = cwdInput.querySelector("input").value.trim();
    const timeoutRaw = timeoutInput.querySelector("input").value.trim();
    const operation_timeout = timeoutRaw ? Number(timeoutRaw) : undefined;
    const autoRec = autoReconnect.querySelector("input").checked;
    const env = collectEnv(envCard);

    if (!name || !command) {
      toast("请填写服务名和启动命令");
      return;
    }

    const body = {
      name,
      command,
      args,
      cwd,
      auto_reconnect: autoRec,
      enabled: existing ? existing.enabled !== false : true,
    };
    if (operation_timeout && operation_timeout > 0) body.operation_timeout = operation_timeout;
    if (Object.keys(env).length) body.env = env;
    else body.env = {};

    try {
      const url = existing
        ? `/api/mcp/servers/${encodeURIComponent(existing.name)}`
        : "/api/mcp/servers";
      await apiJson(url, { method: existing ? "PUT" : "POST", body: JSON.stringify(body) });
      await refresh(container);
      toast("已保存");
    } catch (e) {
      toast(userFacingError(e, "保存失败"));
    }
  });
  btns.appendChild(save);
  card.appendChild(btns);

  container.appendChild(card);
}

/* ===== JSON 导入（stdio 服务器，Claude Desktop 风格） ===== */

function openJsonImport(container) {
  container.innerHTML = "";
  const card = el("div", "mcp-editor");
  const title = el("h3", "mcp-title");
  title.textContent = "JSON 导入 MCP 服务";
  card.appendChild(title);
  const hint = el("p", "mcp-import-hint");
  hint.textContent = "支持 Claude Desktop 风格：{ \"服务名\": { \"command\": ..., \"args\": [...] } }";
  card.appendChild(hint);
  const ta = document.createElement("textarea");
  ta.className = "mcp-json-area";
  ta.rows = 10;
  ta.placeholder = '{\n  "example": {\n    "command": "npx",\n    "args": ["-y", "pkg"]\n  }\n}';
  card.appendChild(ta);

  const btns = el("div", "mcp-editor-btns");
  const cancel = el("button", "ghost-btn");
  cancel.type = "button";
  cancel.textContent = "返回";
  cancel.addEventListener("click", () => refresh(container));
  btns.appendChild(cancel);
  const save = el("button", "primary-btn");
  save.type = "button";
  save.textContent = "导入";
  save.addEventListener("click", async () => {
    let parsed;
    try {
      parsed = JSON.parse(ta.value || "{}");
    } catch {
      toast("JSON 解析失败");
      return;
    }
    let entries;
    if (Array.isArray(parsed)) {
      entries = parsed;
    } else if (parsed.servers) {
      entries = parsed.servers;
    } else {
      entries = Object.entries(parsed).map(([name, cfg]) => ({ name, ...cfg }));
    }
    if (!entries.length) { toast("没有可导入的服务"); return; }
    let okCount = 0;
    for (const e of entries) {
      if (!e.name || !e.command) continue;
      try {
        await apiJson("/api/mcp/servers", {
          method: "POST",
          body: JSON.stringify({ name: e.name, command: e.command, args: e.args || [], env: e.env || {} }),
        });
        okCount += 1;
      } catch { /* duplicate/other */ }
    }
    toast(okCount ? `已导入 ${okCount} 个服务` : "没有成功导入（可能都已存在）");
    await refresh(container);
  });
  btns.appendChild(save);
  card.appendChild(btns);
  container.appendChild(card);
}

/** 渲染 MCP 子页到指定容器；若无容器则尝试 #mcp-container。 */
export async function renderMcpPage(container = null) {
  const target = container || document.querySelector(CONTAINER_SEL);
  if (!target) return;
  await refresh(target);
}
