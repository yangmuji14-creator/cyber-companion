/* ===== settings-panel.js — 设置面板：6 分类标签页 + 加载/渲染/收集/保存 ===== */
import { state, dom, el, $, switchPage } from './state.js';
import { toast, userFacingError } from './ui.js';

/* ===== 6 分类标签页配置 ===== */
const SETTINGS_TABS = [
  { name: "persona", label: "人设设定" },
  { name: "model", label: "模型设置" },
  { name: "proactive", label: "主动消息" },
  { name: "style", label: "回复风格" },
  { name: "pace", label: "对话节奏" },
  { name: "advanced", label: "高级" },
  { name: "wechat_accounts", label: "微信账号" },
  { name: "mcp", label: "MCP 扩展" },
  { name: "plugins", label: "插件管理" },
  { name: "auto-moments", label: "朋友圈自动发布" },
  { name: "voice-providers", label: "语音服务商" },
  { name: "data", label: "数据与应用" },
];
// schema 驱动的 4 个 tab（人设/模型不走 schema）
const SCHEMA_TAB_NAMES = ["style", "pace", "proactive", "advanced"];
// schema section → tab 映射；智能开关 3 字段合并入"高级"tab
const SECTION_TO_TAB = {
  "回复风格": "style",
  "对话节奏": "pace",
  "主动消息时段": "proactive",
  "高级": "advanced",
  "智能开关": "advanced",
};

let currentSettingsTab = "";
let personaEditorLoaded = false;
let modelConfigLoaded = false;
let settingsPageObserverAttached = false;

function getTabContent(tabName) {
  return document.querySelector(`.settings-tab-content[data-tab="${tabName}"]`);
}

function getCurrentSettingsTab() {
  return currentSettingsTab;
}

/* ===== 加载入口 ===== */
export async function loadSettings() {
  try {
    const [schemaRes, valRes] = await Promise.all([
      fetch("/api/schema").then((r) => r.json()),
      fetch("/api/settings").then((r) => r.json()),
    ]);
    state.schema = schemaRes.schema || [];
    state.values = valRes.values || {};
    renderSettingsTabs();
    renderSettings();
    showSettingsHome(); // 默认回到卡片主页（PawzoChat 式），而非直接进入人设 tab
  } catch (e) {
    toast(userFacingError(e, "暂时无法加载设置"));
  }
  // 自接线：main.js 也可显式调用，函数内含幂等保护
  bindResetButton();
  loadModelSelect();
  hookSettingsPageVisibility();
  ensurePersonaEditorLoaded();
}

/* ===== 标签页结构渲染（幂等，仅创建一次容器） ===== */
function renderSettingsTabs() {
  const nav = document.querySelector(".settings-tabs");
  if (nav) {
    nav.replaceChildren();
    for (const tab of SETTINGS_TABS) {
      const btn = el("button", "settings-tab");
      btn.dataset.tab = tab.name;
      btn.textContent = tab.label;
      btn.addEventListener("click", () => switchSettingsTab(tab.name));
      nav.appendChild(btn);
    }
  }
  const content = document.getElementById("settings-content");
  if (!content) return;
  for (const tab of SETTINGS_TABS) {
    if (getTabContent(tab.name)) continue; // 已创建，跳过
    const div = el("div", "settings-tab-content");
    div.dataset.tab = tab.name;
    div.id = tab.name === "model" ? "model-config-container" : `tab-content-${tab.name}`;
    div.hidden = true;
    content.appendChild(div);
  }
  // 把 #persona-editor-section 移入人设设定 tab 内容容器（选择"移动"而非"就地渲染"，
  // 复用既有 renderPersonaForm 逻辑，避免重写）
  const personaTab = getTabContent("persona");
  const personaSection = document.getElementById("persona-editor-section");
  if (personaTab && personaSection && personaSection.parentElement !== personaTab) {
    personaTab.appendChild(personaSection);
  }
  if (personaSection) personaSection.hidden = false; // 由外层 tab-content 控制显隐
  const dataTab = getTabContent("data");
  const dataTools = document.querySelector(".settings-utility");
  if (dataTab && dataTools && dataTools.parentElement !== dataTab) {
    dataTab.appendChild(dataTools);
  }
  ensureSettingsHome(content);
}

/* ===== 卡片分组主页（PawzoChat 式） =====
 * 主页 = 个人资料卡 + 分组卡片，点击进入对应子页（现有 tab-content）。
 * #settings-home 常驻 #settings-content 首位，进入任意子页时隐藏。
 */
function ensureSettingsHome(content) {
  let home = document.getElementById("settings-home");
  if (!home) {
    home = el("div", "settings-home");
    home.id = "settings-home";
    content.prepend(home);
  }
  if (home.dataset.built === "1") return;
  home.dataset.built = "1";

  // 个人资料卡 → 人设设定
  const profile = el("button", "settings-profile-card");
  profile.type = "button";
  profile.addEventListener("click", () => switchSettingsTab("persona"));
  const avatar = el("div", "settings-profile-avatar");
  avatar.id = "settings-home-avatar";
  avatar.textContent = (state.personaName || "?").charAt(0);
  profile.appendChild(avatar);
  const pinfo = el("div", "settings-profile-info");
  const pname = el("div", "settings-profile-name");
  pname.id = "settings-home-name";
  pname.textContent = state.personaName || "人设";
  pinfo.appendChild(pname);
  const psub = el("div", "settings-profile-sub");
  psub.textContent = "人设设定";
  pinfo.appendChild(psub);
  profile.appendChild(pinfo);
  profile.appendChild(el("span", "row-arrow"));
  home.appendChild(profile);

  // 分组卡片
  const groups = [
    {
      title: "账号与服务",
      rows: [
        { tab: "wechat_accounts", icon: "📱", label: "微信账号", value: "扫码登录/管理" },
        { tab: "model", icon: "⚙️", label: "模型设置", value: "对话服务商" },
        { tab: "mcp", icon: "🧩", label: "MCP 扩展", value: "连接更多工具" },
        { tab: "plugins", icon: "🧰", label: "插件管理", value: "内置 / MCP 工具" },
        { tab: "voice-providers", icon: "🎙️", label: "语音服务商", value: "AI 语音回复" },
      ],
    },
    {
      title: "对话与风格",
      rows: [
        { tab: "style", icon: "✏️", label: "回复风格", value: "" },
        { tab: "pace", icon: "🕐", label: "对话节奏", value: "" },
        { tab: "proactive", icon: "🔔", label: "主动消息", value: "" },
        { tab: "auto-moments", icon: "📸", label: "朋友圈自动发布", value: "AI 定时动态" },
      ],
    },
    {
      title: "系统与数据",
      rows: [
        { tab: "advanced", icon: "🧰", label: "高级设置", value: "" },
        { tab: "data", icon: "💾", label: "数据与应用", value: "备份 / 恢复 / 诊断" },
      ],
    },
  ];

  for (const g of groups) {
    const card = el("div", "settings-card");
    const cardTitle = el("div", "settings-card-title");
    cardTitle.textContent = g.title;
    card.appendChild(cardTitle);
    for (const row of g.rows) {
      const btn = el("button", "card-row");
      btn.type = "button";
      btn.addEventListener("click", () => switchSettingsTab(row.tab));
      const icon = el("div", "card-row-icon");
      icon.textContent = row.icon;
      btn.appendChild(icon);
      const span = el("span", "card-row-label");
      span.textContent = row.label;
      btn.appendChild(span);
      if (row.value) {
        const val = el("span", "card-row-value");
        val.textContent = row.value;
        btn.appendChild(val);
      }
      btn.appendChild(el("span", "row-arrow"));
      card.appendChild(btn);
    }
    home.appendChild(card);
  }
}

/* ===== 标签页切换 ===== */
function switchSettingsTab(tabName) {
  const prevTab = currentSettingsTab;
  currentSettingsTab = tabName;
  document.querySelectorAll(".settings-tab").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.tab === tabName);
  });
  const home = document.getElementById("settings-home");
  if (home) home.hidden = true;
  document.querySelectorAll(".settings-tab-content").forEach((content) => {
    const isActive = content.dataset.tab === tabName;
    content.hidden = !isActive;
    content.classList.toggle("active", isActive);
  });
  const foot = document.querySelector(".settings-foot");
  if (foot) foot.hidden = !SCHEMA_TAB_NAMES.includes(tabName);
  ensureSubpageBack(tabName);
  // 切离微信账号 tab → 停止轮询 + 关闭 QR 模态框
  if (prevTab === "wechat_accounts" && tabName !== "wechat_accounts") {
    destroyWechatAccountsModule();
  }
  if (tabName === "persona") ensurePersonaEditorLoaded();
  if (tabName === "model") ensureModelConfigLoaded();
  if (tabName === "wechat_accounts") ensureWechatAccountsLoaded();
  if (tabName === "mcp") ensureMcpLoaded();
  if (tabName === "plugins") ensurePluginsLoaded();
  if (tabName === "auto-moments") ensureAutoMomentsLoaded();
  if (tabName === "voice-providers") ensureVoiceProvidersLoaded();
}

/* ===== 返回卡片主页 ===== */
export function showSettingsHome() {
  currentSettingsTab = "";
  document.querySelectorAll(".settings-tab").forEach((btn) => {
    btn.classList.toggle("active", false);
  });
  document.querySelectorAll(".settings-tab-content").forEach((content) => {
    content.hidden = true;
    content.classList.remove("active");
  });
  const foot = document.querySelector(".settings-foot");
  if (foot) foot.hidden = true;
  const home = document.getElementById("settings-home");
  if (home) home.hidden = false;
  // 保留 persona 懒加载继续可用
  const back = document.querySelector(".settings-back");
  if (back) back.remove();
}

/* 在每个子页顶部注入「返回主页」小条（幂等） */
function ensureSubpageBack(tabName) {
  const tab = getTabContent(tabName);
  if (!tab) return;
  if (tab.querySelector(".settings-back")) return;
  const bar = el("div", "settings-back");
  bar.textContent = "← 返回设置";
  bar.addEventListener("click", showSettingsHome);
  tab.prepend(bar);
}

/* ===== MCP 扩展子页懒加载：tab 激活时 import + 渲染到其内容容器 ===== */
let mcpRendered = false;

async function ensureMcpLoaded() {
  try {
    const mod = await import("./mcp-page.js");
    if (mod.renderMcpPage) {
      await mod.renderMcpPage();
      mcpRendered = true;
    }
  } catch (e) {
    console.warn("mcp-page load failed:", e);
  }
}

/* ===== 插件管理 / 朋友圈自动发布 / 语音识别 子页懒加载 ===== */
async function ensurePluginsLoaded() {
  try {
    const mod = await import("./plugins-page.js");
    if (mod.renderPluginsPage) await mod.renderPluginsPage();
  } catch (e) {
    console.warn("plugins-page load failed:", e);
  }
}

async function ensureAutoMomentsLoaded() {
  try {
    const mod = await import("./auto-moments-page.js");
    if (mod.renderAutoMomentsPage) await mod.renderAutoMomentsPage();
  } catch (e) {
    console.warn("auto-moments-page load failed:", e);
  }
}

async function ensureVoiceProvidersLoaded() {
  try {
    const mod = await import("./voice-providers-page.js");
    if (mod.renderVoiceProvidersPage) await mod.renderVoiceProvidersPage();
  } catch (e) {
    console.warn("voice-providers-page load failed:", e);
  }
}

/* ===== 人设编辑器懒加载：仅在设置页可见且人设 tab 激活时加载 ===== */
function ensurePersonaEditorLoaded() {
  if (personaEditorLoaded) return;
  const settingsPage = document.getElementById("page-settings");
  if (!settingsPage || settingsPage.hidden) return;
  if (getCurrentSettingsTab() !== "persona") return;
  personaEditorLoaded = true;
  loadPersonaEditor();
}

// 监听 #page-settings 的 hidden 属性变化，设置页首次可见时触发人设懒加载
function hookSettingsPageVisibility() {
  if (settingsPageObserverAttached) return;
  const settingsPage = document.getElementById("page-settings");
  if (!settingsPage) return;
  settingsPageObserverAttached = true;
  const observer = new MutationObserver(ensurePersonaEditorLoaded);
  observer.observe(settingsPage, { attributes: true, attributeFilter: ["hidden"] });
}

/* ===== 微信账号 tab 懒加载：tab 激活时 import + init，切走时 destroy ===== */
let wechatAccountsModule = null;

async function ensureWechatAccountsLoaded() {
  try {
    if (!wechatAccountsModule) {
      wechatAccountsModule = await import("./wechat-accounts.js");
    }
    if (wechatAccountsModule.initWechatAccounts) {
      await wechatAccountsModule.initWechatAccounts();
    }
  } catch (e) {
    console.warn("wechat-accounts load failed:", e);
  }
}

function destroyWechatAccountsModule() {
  if (wechatAccountsModule && wechatAccountsModule.destroyWechatAccounts) {
    wechatAccountsModule.destroyWechatAccounts();
  }
}

/* ===== Schema 字段渲染（按 tab 分组，复用 renderField） ===== */
export function renderSettings() {
  // 清空 4 个 schema tab 内容容器
  for (const name of SCHEMA_TAB_NAMES) {
    const container = getTabContent(name);
    if (container) container.replaceChildren();
  }
  // 按 tab → section → fields 三级分组
  const tabSections = {}; // tab -> { section -> [fields] }
  for (const f of state.schema) {
    const tab = SECTION_TO_TAB[f.section];
    if (!tab) continue;
    if (!tabSections[tab]) tabSections[tab] = {};
    if (!tabSections[tab][f.section]) tabSections[tab][f.section] = [];
    tabSections[tab][f.section].push(f);
  }
  for (const tab of SCHEMA_TAB_NAMES) {
    const container = getTabContent(tab);
    if (!container) continue;
    const sections = tabSections[tab] || {};
    for (const sec of Object.keys(sections)) {
      const wrap = el("div", "set-section");
      if (sec === "高级") wrap.classList.add("collapsed");
      const h = el("h3"); h.textContent = sec;
      h.addEventListener("click", () => wrap.classList.toggle("collapsed"));
      wrap.appendChild(h);
      if (sec === "高级") {
        const warn = el("p", "section-warn");
        warn.textContent = "如果不懂请保持默认，错误配置可能影响对话质量";
        wrap.appendChild(warn);
      }
      for (const f of sections[sec]) wrap.appendChild(renderField(f));
      container.appendChild(wrap);
    }
  }
}

export function renderField(f) {
  const field = el("div", "field");
  const val = state.values[f.key];
  if (f.type === "bool") {
    const head = el("div", "field-head");
    const label = el("span", "field-label");
    label.textContent = f.label;
    if (f.live === false) { const b = el("span", "restart-badge"); b.textContent = "需重启"; label.appendChild(b); }
    const sw = el("label", "switch");
    const cb = el("input"); cb.type = "checkbox"; cb.checked = !!val; cb.dataset.key = f.key;
    const sl = el("span", "slider");
    sw.appendChild(cb); sw.appendChild(sl);
    head.appendChild(label); head.appendChild(sw);
    field.appendChild(head);
  } else {
    const head = el("div", "field-head");
    const label = el("span", "field-label");
    label.textContent = f.label;
    if (f.live === false) { const b = el("span", "restart-badge"); b.textContent = "需重启"; label.appendChild(b); }
    const valSpan = el("span", "field-val");
    valSpan.textContent = fmt(val, f);
    head.appendChild(label); head.appendChild(valSpan);
    field.appendChild(head);
    const range = el("input"); range.type = "range";
    range.min = f.min; range.max = f.max; range.step = f.step || 1;
    range.value = val; range.dataset.key = f.key; range.dataset.type = f.type;
    range.addEventListener("input", () => { valSpan.textContent = fmt(range.value, f); });
    field.appendChild(range);
  }
  if (f.hint) { const hint = el("div", "field-hint"); hint.textContent = f.hint; field.appendChild(hint); }
  return field;
}

export function fmt(v, f) {
  if (f.type === "float") return Number(v).toFixed(2);
  return String(v);
}

/* ===== 收集与保存（扫描 4 个 schema tab，不含人设/模型） ===== */
export function collectSettings() {
  const out = {};
  for (const name of SCHEMA_TAB_NAMES) {
    const container = getTabContent(name);
    if (!container) continue;
    container.querySelectorAll("input[data-key]").forEach((inp) => {
      const key = inp.dataset.key;
      if (inp.type === "checkbox") out[key] = inp.checked;
      else out[key] = inp.dataset.type === "int" ? parseInt(inp.value, 10) : parseFloat(inp.value);
    });
  }
  return out;
}

export async function saveSettings() {
  const values = collectSettings();
  dom.save.disabled = true;
  dom.saveStatus.className = "save-status"; dom.saveStatus.textContent = "保存中…";
  try {
    const resp = await fetch("/api/settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ values }),
    });
    const data = await resp.json();
    if (!resp.ok) throw new Error(data.error || `HTTP ${resp.status}`);
    state.values = data.values || values;
    dom.saveStatus.className = "save-status ok"; dom.saveStatus.textContent = "已保存并生效";
    setTimeout(() => { dom.saveStatus.textContent = ""; }, 2500);
  } catch (e) {
    dom.saveStatus.className = "save-status err";
    dom.saveStatus.textContent = "保存失败：" + e.message;
  } finally {
    dom.save.disabled = false;
  }
}

/* ===== 恢复默认（仅当前 schema 标签页的字段） ===== */
export function bindResetButton() {
  const btn = $("#btn-reset");
  if (!btn || btn.dataset.bound === "1") return;
  btn.dataset.bound = "1";
  btn.addEventListener("click", async () => {
    if (!state.schema || !state.schema.length) return;
    const currentTab = getCurrentSettingsTab();
    if (!SCHEMA_TAB_NAMES.includes(currentTab)) {
      toast("当前标签页无可恢复的默认设置");
      return;
    }
    const container = getTabContent(currentTab);
    if (!container) return;
    for (const f of state.schema) {
      if (SECTION_TO_TAB[f.section] !== currentTab) continue;
      const inp = container.querySelector(`input[data-key="${f.key}"]`);
      if (!inp) continue;
      if (inp.type === "checkbox") {
        inp.checked = !!f.default;
      } else {
        inp.value = f.default;
        inp.dispatchEvent(new Event("input"));
      }
    }
    await saveSettings();
    toast("已恢复当前标签页默认设置并保存");
  });
}

/* ===== 模型 select（顶栏快捷切换，原任务 12） ===== */
export async function loadModelSelect() {
  const select = $("#model-select");
  if (!select) return;
  const bindChange = select.dataset.bound !== "1";
  if (bindChange) select.dataset.bound = "1";
  try {
    const data = await fetch("/api/model").then((r) => r.json());
    select.replaceChildren();
    const list = data.available || [];
    for (const m of list) {
      const id = typeof m === "string" ? m : (m.id || m.name);
      const name = typeof m === "string" ? m : (m.name || m.id);
      const opt = el("option");
      opt.value = id;
      opt.textContent = name;
      if (id === data.current) opt.selected = true;
      select.appendChild(opt);
    }
    if (bindChange) {
      select.addEventListener("change", async () => {
        try {
          const resp = await fetch("/api/model", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ model: select.value }),
          });
          const d = await resp.json().catch(() => ({}));
          if (!resp.ok) throw new Error(d.error || `HTTP ${resp.status}`);
          toast(`模型已切换为 ${select.value}，下次启动生效`);
        } catch (e) {
          toast(userFacingError(e, "模型切换失败，请稍后重试"));
        }
      });
    }
    select.removeAttribute("hidden");
  } catch (e) {
    toast(userFacingError(e, "暂时无法加载模型列表"));
  }
}

/* ===== 模型供应商配置（T6：列表 + 切换默认 + 删除 + 新增供应商） ===== */
function ensureModelConfigLoaded() {
  if (modelConfigLoaded) return;
  modelConfigLoaded = true;
  renderModelConfig();
}

async function renderModelConfig() {
  const container = document.getElementById("model-config-container");
  if (!container) return;
  container.replaceChildren();

  let data;
  try {
    const resp = await fetch("/api/model");
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    data = await resp.json();
  } catch (e) {
    const p = el("p");
    p.textContent = "模型列表加载失败：" + e.message;
    container.appendChild(p);
    return;
  }

  const current = data.current || "";
  const available = data.available || [];

  const heading = el("div", "model-config-heading");
  const headingTitle = el("h2");
  headingTitle.textContent = "模型设置";
  const headingCopy = el("p");
  headingCopy.textContent = "主模型负责对话；如果它不支持图片，可以在下方配置一个独立视觉模型。";
  heading.append(headingTitle, headingCopy);
  container.appendChild(heading);

  // 模型列表：每行一个 .model-item（默认项加 .default 类 + "(默认)" 后缀）
  const list = el("div", "model-list");
  for (const key of available) {
    const isDefault = key === current;
    const item = el("div", "model-item");
    if (isDefault) item.classList.add("default");

    const info = el("div", "model-item-info");
    const keyDiv = el("div", "model-item-key");
    keyDiv.textContent = isDefault ? `${key} (默认)` : key;
    info.appendChild(keyDiv);
    // /api/model 仅返回 key，不暴露完整配置；不新增后端接口，meta 留空
    const meta = el("div", "model-item-meta");
    info.appendChild(meta);
    item.appendChild(info);

    const actions = el("div", "model-item-actions");

    // 设为默认（已为默认时禁用）—— POST /api/model 写 settings.json，下次启动生效
    const setBtn = el("button");
    setBtn.type = "button";
    setBtn.textContent = "设为默认";
    setBtn.disabled = isDefault;
    setBtn.addEventListener("click", async () => {
      setBtn.disabled = true;
      try {
        const resp = await fetch("/api/model", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ model: key }),
        });
        const d = await resp.json().catch(() => ({}));
        if (!resp.ok) throw new Error(d.error || `HTTP ${resp.status}`);
        toast("下次启动生效");
        await renderModelConfig();
      } catch (err) {
        toast(err.message);
        setBtn.disabled = isDefault;
      }
    });
    actions.appendChild(setBtn);

    // 删除 —— confirm 弹窗确认，DELETE /api/model/{key}（最后一个供应商禁止删除）
    const delBtn = el("button");
    delBtn.type = "button";
    delBtn.textContent = "删除";
    delBtn.addEventListener("click", async () => {
      if (!confirm(`确认删除供应商 ${key}？`)) return;
      delBtn.disabled = true;
      try {
        const resp = await fetch(`/api/model/${encodeURIComponent(key)}`, {
          method: "DELETE",
        });
        const d = await resp.json().catch(() => ({}));
        if (!resp.ok) throw new Error(d.error || `HTTP ${resp.status}`);
        await renderModelConfig();
      } catch (err) {
        toast(err.message);
        delBtn.disabled = false;
      }
    });
    actions.appendChild(delBtn);

    item.appendChild(actions);
    list.appendChild(item);
  }
  container.appendChild(list);

  await renderVisionSettings(container);

  // 新增供应商表单：POST /api/model/provider
  const form = el("form", "model-form");

  const createField = (labelText, name, inpType, opts = {}) => {
    const wrap = el("div");
    const label = el("label");
    label.textContent = labelText;
    const inp = el("input");
    inp.type = inpType;
    inp.name = name;
    if (opts.required) inp.required = true;
    if (opts.placeholder) inp.placeholder = opts.placeholder;
    if (opts.value !== undefined) inp.value = opts.value;
    if (opts.min !== undefined) inp.min = opts.min;
    if (opts.max !== undefined) inp.max = opts.max;
    if (opts.step !== undefined) inp.step = opts.step;
    wrap.appendChild(label);
    wrap.appendChild(inp);
    if (opts.hint) {
      const hint = el("small", "field-hint");
      hint.textContent = opts.hint;
      hint.style.display = "block";
      hint.style.fontSize = "12px";
      hint.style.color = "var(--text-muted, #888)";
      hint.style.marginTop = "2px";
      wrap.appendChild(hint);
    }
    form.appendChild(wrap);
    return inp;
  };

  const keyInput = createField("供应商名", "key", "text", {
    required: true,
    hint: "settings.json 中的唯一键，如 openai / my-deepseek",
  });

  // Provider 选项中英文映射 — key 来自 core/llm/registry.py env_key_map
  const PROVIDER_LABELS = {
    openai: "OpenAI (GPT 系列)",
    deepseek: "DeepSeek (深度求索)",
    gemini: "Google Gemini (谷歌)",
    qwen: "通义千问 Qwen (阿里)",
    kimi: "Kimi (月之暗面)",
    zhipu: "智谱 GLM (Zhipu)",
    mimo: "小米 MiMo",
    doubao: "豆包 Doubao (字节跳动)",
    baichuan: "百川 Baichuan",
    minimax: "MiniMax",
    stepfun: "阶跃星辰 StepFun",
    moonshot: "Moonshot (月之暗面)",
  };

  // Provider 类型 — 对齐后端 registry PROVIDER_MAP / env_key_map 的 key
  // createField 只建 <input>，select 手动构建同结构
  const providerWrap = el("div");
  const providerLabel = el("label");
  providerLabel.textContent = "模型供应商";
  const providerSelect = el("select");
  providerSelect.name = "provider";
  providerSelect.required = true;
  for (const [p, label] of Object.entries(PROVIDER_LABELS)) {
    const opt = el("option");
    opt.value = p;
    opt.textContent = label;
    if (p === "openai") opt.selected = true;
    providerSelect.appendChild(opt);
  }
  // 自定义 provider 选项 — 后端 PROVIDER_MAP.get(provider, OpenAICompatibleLLM) 兜底
  const customOpt = el("option");
  customOpt.value = "custom";
  customOpt.textContent = "自定义 (手动填写)";
  providerSelect.appendChild(customOpt);
  const providerHint = el("small", "field-hint");
  providerHint.textContent = "选择服务商；选「自定义」可手动填写 provider 名";
  providerHint.style.display = "block";
  providerHint.style.fontSize = "12px";
  providerHint.style.color = "var(--text-muted, #888)";
  providerHint.style.marginTop = "2px";
  providerWrap.appendChild(providerLabel);
  providerWrap.appendChild(providerSelect);
  providerWrap.appendChild(providerHint);
  form.appendChild(providerWrap);

  // 自定义 provider 名 — 仅在选「自定义」时显示
  const customProviderWrap = el("div");
  customProviderWrap.style.display = "none";
  const customProviderLabel = el("label");
  customProviderLabel.textContent = "自定义 Provider 名";
  const customProviderInput = el("input");
  customProviderInput.type = "text";
  customProviderInput.name = "custom_provider_name";
  customProviderInput.placeholder = "my-provider";
  const customProviderHint = el("small", "field-hint");
  customProviderHint.textContent = "英文标识，用于内部注册（任意字符串，后端按 OpenAI 兼容调用）";
  customProviderHint.style.display = "block";
  customProviderHint.style.fontSize = "12px";
  customProviderHint.style.color = "var(--text-muted, #888)";
  customProviderHint.style.marginTop = "2px";
  customProviderWrap.appendChild(customProviderLabel);
  customProviderWrap.appendChild(customProviderInput);
  customProviderWrap.appendChild(customProviderHint);
  form.appendChild(customProviderWrap);

  const modelInput = createField("模型名称", "model_name", "text", {
    required: true,
    hint: "API 实际调用的模型 ID，如 gpt-4o-mini / claude-3-5-sonnet",
  });
  // API Key — type="password" 防肩窥（spec 要求，不存 localStorage）
  const apiKeyInput = createField("API 密钥", "api_key", "password", {
    required: true,
    hint: "从服务商官网获取；加载时优先从环境变量读取",
  });
  const apiBaseInput = createField("API 地址", "base_url", "text", {
    required: true,
    placeholder: "https://api.openai.com/v1",
    hint: "通常以 /v1 结尾，如 https://api.openai.com/v1",
  });
  // apiBaseHint 用于自定义切换时更新文案
  const apiBaseHint = apiBaseInput.parentElement.querySelector(".field-hint");
  const tempInput = createField("生成温度", "temperature", "number", {
    value: "1.0",
    min: 0,
    max: 2,
    step: 0.1,
    hint: "0=精确, 1=创意, 默认 1.0",
  });

  // provider 切换：显示/隐藏自定义 provider 名输入框，更新 base_url hint
  providerSelect.addEventListener("change", () => {
    const isCustom = providerSelect.value === "custom";
    customProviderWrap.style.display = isCustom ? "block" : "none";
    customProviderInput.required = isCustom;
    if (apiBaseHint) {
      apiBaseHint.textContent = isCustom
        ? "必填：填入 API 地址，如 https://api.example.com/v1"
        : "通常以 /v1 结尾，如 https://api.openai.com/v1";
    }
  });

  // 拉取模型列表：通过本地后端转发，API Key 不会暴露给浏览器跨域请求。
  let modelSelect = null; // 拉取成功后指向 <select>，否则 null（仍用 modelInput）
  const modelWrap = modelInput.parentElement;
  const fetchRow = el("div");
  fetchRow.style.marginTop = "4px";
  const fetchBtn = el("button", "ghost-btn");
  fetchBtn.type = "button";
  fetchBtn.textContent = "拉取模型";
  fetchBtn.title = "根据 API 地址和密钥自动获取可用模型列表";
  fetchBtn.style.fontSize = "12px";
  fetchRow.appendChild(fetchBtn);
  modelWrap.appendChild(fetchRow);

  const fetchModels = async () => {
    const api_base = apiBaseInput.value.trim().replace(/\/$/, "");
    const api_key = apiKeyInput.value.trim();
    if (!api_base || !api_key) {
      toast("请先填写 API Base 和 API Key");
      return;
    }
    fetchBtn.disabled = true;
    const prevText = fetchBtn.textContent;
    fetchBtn.textContent = "拉取中…";
    try {
      const resp = await fetch("/api/model/discover", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ base_url: api_base, api_key }),
      });
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) throw new Error(data.message || `HTTP ${resp.status}`);
      const ids = data.models || [];
      if (!ids.length) throw new Error("返回的模型列表为空");
      const sel = el("select");
      sel.name = "model_name";
      sel.required = true;
      sel.style.width = "100%";
      const ph = el("option");
      ph.value = "";
      ph.textContent = "请选择模型";
      ph.disabled = true;
      ph.selected = true;
      sel.appendChild(ph);
      for (const id of ids) {
        const opt = el("option");
        opt.value = id;
        opt.textContent = id;
        sel.appendChild(opt);
      }
      if (modelSelect) {
        modelSelect.replaceWith(sel);
      } else {
        modelInput.replaceWith(sel);
      }
      modelSelect = sel;
      fetchBtn.textContent = "重新拉取";
      toast(`已拉取 ${ids.length} 个模型`);
    } catch (err) {
      const isNetworkOrCors = err instanceof TypeError;
      toast(
        isNetworkOrCors
          ? "拉取失败：可能被跨域拦截或网络错误，请手填模型名"
          : "拉取模型失败：" + err.message
      );
      fetchBtn.textContent = prevText;
    } finally {
      fetchBtn.disabled = false;
    }
  };
  fetchBtn.addEventListener("click", fetchModels);

  const submitBtn = el("button");
  submitBtn.type = "submit";
  submitBtn.textContent = "新增";
  form.appendChild(submitBtn);

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const key = keyInput.value.trim();
    // 选「自定义」时，provider 取用户输入的自定义名；否则取下拉框值
    const isCustomProvider = providerSelect.value === "custom";
    const provider = isCustomProvider
      ? customProviderInput.value.trim()
      : providerSelect.value.trim();
    const model = (modelSelect ? modelSelect.value : modelInput.value).trim();
    const api_key = apiKeyInput.value.trim();
    const api_base = apiBaseInput.value.trim();
    if (!key || !provider || !model || !api_key || !api_base) {
      toast(isCustomProvider && !provider ? "请填写自定义 Provider 名" : "请填写所有必填字段");
      return;
    }
    const tempVal = parseFloat(tempInput.value);
    const temperature = isNaN(tempVal) ? 1.0 : tempVal;
    submitBtn.disabled = true;
    try {
      const resp = await fetch("/api/model/provider", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          key,
          provider,
          model_name: model,
          base_url: api_base,
          api_key,
          temperature,
        }),
      });
      const d = await resp.json().catch(() => ({}));
      if (!resp.ok) throw new Error(d.error || `HTTP ${resp.status}`);
      toast(`已添加 ${key}`);
      form.reset();
      tempInput.value = "1.0";
      // form.reset() 不触发 change 事件，手动重置自定义 provider 输入框可见性
      customProviderWrap.style.display = "none";
      customProviderInput.required = false;
      await renderModelConfig();
    } catch (err) {
      toast(err.message);
    } finally {
      submitBtn.disabled = false;
    }
  });

  const addDetails = el("details", "model-add-details");
  const addSummary = el("summary");
  addSummary.textContent = "添加模型服务";
  addDetails.append(addSummary, form);
  container.appendChild(addDetails);
}

async function renderVisionSettings(container) {
  const section = el("section", "vision-settings");
  const heading = el("div", "vision-settings-heading");
  const title = el("h3");
  title.textContent = "图片识别模型";
  const copy = el("p");
  copy.textContent = "主模型支持图片时会直接使用主模型；只有文本模型才会调用这里配置的视觉模型。";
  heading.append(title, copy);
  section.appendChild(heading);

  let data = {};
  try {
    const response = await fetch("/api/vision/config");
    data = response.ok ? await response.json() : {};
  } catch (_) {
    data = {};
  }

  const status = el("p", "vision-status");
  const mainName = data.main_model || "当前主模型";
  if (data.main_is_multimodal) {
    const strong = document.createElement("strong");
    strong.textContent = "当前主模型支持图片";
    status.append(strong, document.createTextNode(`（${mainName}），图片会直接发送给它。`));
  } else {
    status.textContent = `当前主模型 ${mainName} 不支持图片，需要配置独立视觉模型。`;
  }
  section.appendChild(status);

  const form = el("form", "vision-settings-form");
  const field = (labelText, type, value, placeholder, full = false) => {
    const label = el("label");
    if (full) label.classList.add("full");
    const text = document.createElement("span");
    text.textContent = labelText;
    const input = document.createElement("input");
    input.type = type;
    input.value = value || "";
    if (placeholder) input.placeholder = placeholder;
    label.append(text, input);
    form.appendChild(label);
    return input;
  };
  const provider = field("服务商标识", "text", data.provider || "openai", "openai / qwen / 自定义");
  const model = field("视觉模型 ID", "text", data.model_name || "", "例如 gpt-4o-mini 或 qwen-vl-max");
  model.setAttribute("list", "vision-model-options");
  const datalist = document.createElement("datalist");
  datalist.id = "vision-model-options";
  form.appendChild(datalist);
  const base = field("API 地址", "url", data.base_url || "", "https://api.openai.com/v1", true);
  const key = field("API 密钥", "password", "", data.has_api_key ? "已配置，留空保持不变" : "粘贴视觉模型 API 密钥", true);
  const keyHint = el("small", "vision-field-hint");
  keyHint.textContent = "密钥只保存在本机配置文件，不会回传到模型列表。";
  key.parentElement.appendChild(keyHint);

  const actions = el("div", "vision-form-actions");
  const discover = el("button", "ghost-btn");
  discover.type = "button";
  discover.textContent = "拉取模型";
  const save = el("button", "primary-btn");
  save.type = "submit";
  save.textContent = "保存视觉模型";
  const result = el("span", "vision-form-result");
  actions.append(discover, save, result);
  form.appendChild(actions);
  section.appendChild(form);
  container.appendChild(section);

  discover.addEventListener("click", async () => {
    if (!base.value.trim() || !key.value.trim()) {
      result.textContent = data.has_api_key ? "API 密钥已保存，留空时无法重新拉取模型。" : "请先填写 API 地址和 API 密钥。";
      result.className = "vision-form-result error";
      return;
    }
    discover.disabled = true;
    result.textContent = "正在拉取模型…";
    result.className = "vision-form-result";
    try {
      const response = await fetch("/api/model/discover", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ base_url: base.value.trim(), api_key: key.value.trim() }),
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(payload.message || "拉取模型失败");
      datalist.replaceChildren();
      for (const id of payload.models || []) {
        const option = document.createElement("option");
        option.value = id;
        datalist.appendChild(option);
      }
      result.textContent = payload.message || "模型列表已更新";
      result.className = "vision-form-result success";
    } catch (error) {
      result.textContent = error.message || "拉取模型失败";
      result.className = "vision-form-result error";
    } finally {
      discover.disabled = false;
    }
  });

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    save.disabled = true;
    result.textContent = "正在保存…";
    result.className = "vision-form-result";
    try {
      const response = await fetch("/api/vision/config", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ provider: provider.value.trim(), model_name: model.value.trim(), base_url: base.value.trim(), api_key: key.value.trim() }),
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(payload.error || "保存失败");
      result.textContent = "已保存，文本主模型下次图片消息会使用它。";
      result.className = "vision-form-result success";
      if (payload.has_api_key) { key.value = ""; data.has_api_key = true; }
    } catch (error) {
      result.textContent = error.message || "保存失败";
      result.className = "vision-form-result error";
    } finally {
      save.disabled = false;
    }
  });
}

/* ===== Persona 编辑器（原任务 11） ===== */
let currentPersonaId = "girlfriend_001";
// T10: 缓存当前人设完整对象（含 avatar 字段），供头像区/侧边栏同步使用
let currentPersonaDetail = null;
// 多人设：当前聊天激活的 persona（由 persona-changed 事件同步）。
// currentPersonaId 是"编辑器正在编辑的 persona"，可与 activePersonaId 不同
// （用户点列表卡片编辑他人设时 currentPersonaId 变，activePersonaId 不变）。
let activePersonaId = "girlfriend_001";

const PERSONA_FIELDS = [
  { key: "id", type: "readonly", label: "ID" },
  { key: "name", type: "text", label: "名字" },
  { key: "age", type: "text", label: "年龄" },
  { key: "gender", type: "text", label: "性别" },
  { key: "birthday", type: "text", label: "生日" },
  { key: "hometown", type: "text", label: "家乡" },
  { key: "occupation", type: "text", label: "职业" },
  { key: "daily_routine", type: "text", label: "日常作息" },
  { key: "appearance", type: "text", label: "外貌" },
  { key: "personality", type: "list", label: "性格特征" },
  { key: "mbti", type: "text", label: "MBTI" },
  { key: "hobbies", type: "json", label: "爱好（JSON）" },
  { key: "music_taste", type: "text", label: "音乐品味" },
  { key: "movie_taste", type: "text", label: "电影品味" },
  { key: "food_preferences", type: "text", label: "饮食偏好" },
  { key: "catchphrases", type: "list", label: "口癖" },
  { key: "filler_words", type: "list", label: "语气词" },
  { key: "emoji_habits", type: "text", label: "表情习惯" },
  { key: "speech_rhythm", type: "text", label: "说话节奏" },
  { key: "nickname_for_user", type: "text", label: "对你的昵称" },
  { key: "happy_expression", type: "text", label: "开心时" },
  { key: "sad_expression", type: "text", label: "难过时" },
  { key: "angry_expression", type: "text", label: "生气时" },
  { key: "jealous_expression", type: "text", label: "嫉妒时" },
  { key: "shy_expression", type: "text", label: "害羞时" },
  { key: "initiative_level", type: "select", label: "主动性", options: ["低", "中", "高"] },
  { key: "clinginess", type: "select", label: "粘人程度", options: ["低", "中", "高"] },
  { key: "jealous_tendency", type: "select", label: "嫉妒倾向", options: ["低", "中", "高"] },
  { key: "conflict_style", type: "text", label: "冲突风格" },
  { key: "affection_style", type: "text", label: "表达爱意方式" },
  { key: "pet_names", type: "list", label: "对你的称呼" },
  { key: "favorite_topics", type: "list", label: "喜欢的话题" },
  { key: "avoided_topics", type: "list", label: "回避的话题" },
  { key: "question_tendency", type: "text", label: "提问倾向" },
  { key: "background", type: "textarea", label: "背景故事" },
  { key: "relationship_level", type: "range", label: "关系等级", min: 0, max: 100 },
];

/* ===== 人设字段 5 分组（前 4 组渲染为 fieldset.settings-section；
   第 5 组"高级"由 #persona-advanced-form 在 <details> 中渲染） ===== */
const PERSONA_SECTIONS = [
  { title: "基本信息", keys: ["id", "name", "age", "gender", "birthday", "hometown", "occupation"] },
  { title: "外貌性格", keys: ["appearance", "personality", "mbti", "daily_routine", "hobbies", "music_taste", "movie_taste", "food_preferences", "catchphrases", "filler_words", "emoji_habits", "speech_rhythm"] },
  { title: "情绪反应", keys: ["happy_expression", "sad_expression", "angry_expression", "jealous_expression", "shy_expression"] },
  { title: "关系互动", keys: ["nickname_for_user", "initiative_level", "clinginess", "jealous_tendency", "conflict_style", "affection_style", "pet_names", "favorite_topics", "avoided_topics", "question_tendency", "background", "relationship_level"] },
];

const PERSONA_ADVANCED_FIELDS = [
  { key: "hard_rules", type: "list", label: "硬性规则（每行一条）" },
  { key: "example_dialogs", type: "json", label: "示例对话（JSON）", big: true },
  { key: "identity_anchor", type: "json", label: "身份锚点（JSON）" },
  { key: "speaking_style", type: "json", label: "说话风格（JSON）" },
  { key: "emotional_patterns", type: "json", label: "情绪模式（JSON）" },
  { key: "relationship_behavior", type: "json", label: "关系行为（JSON）" },
  { key: "core_memories", type: "list", label: "核心记忆（每行一条）" },
  { key: "legacy_speaking_style", type: "text", label: "遗留说话风格" },
  { key: "values", type: "list", label: "价值观（每行一条）" },
  { key: "taboos", type: "list", label: "禁忌（每行一条）" },
  { key: "important_moments", type: "list", label: "重要时刻（每行一条）" },
  { key: "how_we_met", type: "text", label: "相识经历" },
  { key: "first_impression", type: "text", label: "第一印象" },
];

const PERSONA_CORE_FIELDS = [
  { key: "system_prompt", type: "textarea", label: "系统提示词", big: true,
    hint: "整体行为规则：它应该怎样回应、遵守什么边界。适合放稳定原则。" },
  { key: "output_examples", type: "textarea", label: "输出示例", big: true,
    hint: "常用语和表达方式示范。可以写多组“对方说 / 你说”，帮助它学会语气。" },
  { key: "persona_prompt", type: "textarea", label: "人设提示词", big: true,
    hint: "角色小传：名字、性格、关系、兴趣和生活背景。这里回答“它是谁”。" },
];

window.addEventListener("persona-changed", (e) => {
  if (!e.detail || !e.detail.id) return;
  currentPersonaId = e.detail.id;
  activePersonaId = e.detail.id;
  if (personaEditorLoaded) {
    // 已加载则重新拉取新人设（loadPersonaEditor 内部会同步侧边栏头像）
    loadPersonaEditor();
  } else {
    // T10: 设置页未加载时，仍轻量同步侧边栏头像
    syncSidebarAvatar(e.detail.id);
  }
});

export async function loadPersonaEditor(personaId) {
  // 多人设：传 personaId 则切换编辑目标（不改变聊天激活人设）
  if (personaId) currentPersonaId = personaId;
  ensurePersonaListBar();
  try {
    const [basicRes, advRes, listRes] = await Promise.all([
      fetch(`/api/persona/${currentPersonaId}`).then((r) => r.json()),
      fetch(`/api/persona/${currentPersonaId}/advanced`).then((r) => r.json()),
      fetch(`/api/persona`).then((r) => r.json()), // T10: list 含 avatar，detail 不含
    ]);
    // T10: detail endpoint 不返回 avatar 字段，从 list 补充
    const entry = (listRes || []).find((p) => p.id === currentPersonaId);
    if (entry) basicRes.avatar = entry.avatar || "";
    currentPersonaDetail = basicRes; // T10: 缓存供头像区/侧边栏使用
    renderPersonaList(listRes); // 多人设：刷新人设卡片列表（高亮当前编辑项 + 当前激活项）
    renderPersonaForm($("#persona-core-form"), { ...basicRes, ...advRes }, PERSONA_CORE_FIELDS);
    renderPersonaForm($("#persona-form"), basicRes, PERSONA_FIELDS);
    renderPersonaForm($("#persona-advanced-form"), advRes, PERSONA_ADVANCED_FIELDS);
    renderAvatarZone($("#persona-form"), basicRes); // T10: 人设表单顶部插入头像上传区
    updateSidebarAvatar(basicRes.avatar, basicRes.name); // T10: 同步侧边栏头像
    renderEditorHeader();
    await renderPersonaMemoryOverview();
    const btnSave = $("#btn-save-persona");
    if (btnSave && btnSave.dataset.bound !== "1") {
      btnSave.dataset.bound = "1";
      btnSave.addEventListener("click", savePersona);
    }
  } catch (e) {
    toast(userFacingError(e, "暂时无法加载人设"));
  }
}

/* ============================================================
   多人设：人设列表栏 + 新建/删除/设为当前
   - ensurePersonaListBar: 幂等注入列表栏 HTML 到人设 tab 顶部
   - renderPersonaList: 渲染人设卡片（头像 + 名称 + 描述预览 + 当前徽章）
   - openNewPersonaDialog / closeNewPersonaDialog / submitNewPersona
   - setCurrentPersonaActive: "设为当前"按钮 → applyPersona + dispatch persona-changed
   - deleteCurrentPersona: "删除人设"按钮 → 确认 + DELETE + 刷新列表
   - renderEditorHeader: 幂等注入编辑器顶部/底部按钮
   ============================================================ */
function ensurePersonaListBar() {
  const personaTab = getTabContent("persona");
  if (!personaTab) return;
  if ($("#persona-list-bar")) return; // 已注入
  const bar = el("div", "persona-list-bar");
  bar.id = "persona-list-bar";

  const btnNew = el("button", "primary-btn btn-new-persona");
  btnNew.type = "button";
  btnNew.textContent = "+ 新建人设";
  btnNew.addEventListener("click", openNewPersonaDialog);

  const cards = el("div", "persona-cards");
  cards.id = "persona-cards";

  bar.appendChild(btnNew);
  bar.appendChild(cards);

  // 插入到 persona-editor-section 之前（列表在上，编辑器在下）
  const editorSection = $("#persona-editor-section");
  if (editorSection) {
    personaTab.insertBefore(bar, editorSection);
  } else {
    personaTab.appendChild(bar);
  }
}

function renderPersonaList(personas) {
  const container = $("#persona-cards");
  if (!container) return;
  container.replaceChildren();
  const list = Array.isArray(personas) ? personas : [];
  for (const p of list) {
    const card = el("div", "persona-card");
    if (p.id === currentPersonaId) card.classList.add("editing");
    if (p.id === activePersonaId) card.classList.add("active");
    card.dataset.id = p.id;

    // 头像（32px）：有 avatar 用 img，否则首字
    const avatar = el("div", "persona-card-avatar");
    if (p.avatar) {
      const img = el("img");
      img.src = p.avatar;
      img.alt = p.name || "";
      avatar.appendChild(img);
    } else {
      avatar.textContent = (p.name || "?").charAt(0);
    }

    const info = el("div", "persona-card-info");
    const name = el("div", "persona-card-name");
    name.textContent = p.name || p.id;
    info.appendChild(name);
    // 描述预览：list endpoint 只返回 id+name+avatar，无描述字段；
    // 显示 id 作为副文本帮助区分同名 persona。
    const sub = el("div", "persona-card-sub");
    sub.textContent = p.id;
    info.appendChild(sub);

    if (p.id === activePersonaId) {
      const badge = el("span", "persona-card-badge");
      badge.textContent = "当前";
      info.appendChild(badge);
    }

    card.appendChild(avatar);
    card.appendChild(info);

    card.addEventListener("click", () => {
      if (p.id === currentPersonaId) return; // 已在编辑，不重载
      loadPersonaEditor(p.id);
    });
    container.appendChild(card);
  }
}

function renderEditorHeader() {
  const editor = $("#persona-editor");
  if (!editor) return;

  // 顶部"设为当前"按钮（幂等：已存在则更新状态）
  let header = $("#persona-editor-header");
  if (!header) {
    header = el("div", "persona-editor-header");
    header.id = "persona-editor-header";
    editor.insertBefore(header, editor.firstChild);
  }
  header.replaceChildren();
  const isActive = currentPersonaId === activePersonaId;
  if (isActive) {
    const status = el("span", "persona-active-status");
    status.textContent = "当前对话角色";
    header.appendChild(status);
  }
  const btn = el("button", "ghost-btn btn-set-active");
  btn.type = "button";
  btn.textContent = isActive ? "返回对话" : "与这个角色聊天";
  btn.addEventListener("click", setCurrentPersonaActive);
  header.appendChild(btn);

  // 底部"删除人设"按钮（幂等：已存在则更新状态）
  const btnSave = $("#btn-save-persona");
  if (!btnSave) return;
  let footer = $("#persona-editor-footer");
  if (!footer) {
    footer = el("div", "persona-editor-footer");
    footer.id = "persona-editor-footer";
    btnSave.parentNode.insertBefore(footer, btnSave.nextSibling);
  }
  footer.replaceChildren();
  const isDefault = currentPersonaId === "girlfriend_001"; // DEFAULT_PERSONA_ID
  if (isDefault) {
    const note = el("span", "persona-delete-note");
    note.textContent = "默认人设不可删除";
    footer.appendChild(note);
  } else {
    const btnDel = el("button", "ghost-btn btn-delete-persona");
    btnDel.type = "button";
    btnDel.textContent = "删除此人设";
    btnDel.addEventListener("click", deleteCurrentPersona);
    footer.appendChild(btnDel);
  }
}

async function setCurrentPersonaActive() {
  const btn = $(".btn-set-active");
  if (btn) btn.disabled = true;
  try {
    const sidebar = await import("./conversation-sidebar.js");
    await sidebar.ensureWebConversation(currentPersonaId);
    activePersonaId = currentPersonaId;
    await switchPage("chat");
  } catch (e) {
    toast(userFacingError(e, "暂时无法开始这个角色的对话"));
  } finally {
    if (btn) btn.disabled = false;
  }
}

async function renderPersonaMemoryOverview() {
  const editor = $("#persona-editor");
  const coreForm = $("#persona-core-form");
  if (!editor || !coreForm) return;
  let section = $("#persona-memory-overview");
  if (!section) {
    section = el("section", "persona-memory-overview");
    section.id = "persona-memory-overview";
    editor.insertBefore(section, coreForm);
  }
  section.replaceChildren();
  section.setAttribute("aria-busy", "true");

  const personaId = currentPersonaId;
  const useActiveConversation = (
    personaId === activePersonaId && Boolean(state.activeConversationId)
  );
  const scope = useActiveConversation
    ? "conversation_id=" + encodeURIComponent(state.activeConversationId)
    : "persona_id=" + encodeURIComponent(personaId);

  try {
    const [memoryResp, diaryResp] = await Promise.all([
      fetch(`/api/memory?offset=0&limit=1&level_min=1&level_max=5&${scope}`),
      fetch(`/api/life_summary?limit=1&${scope}`),
    ]);
    if (!memoryResp.ok || !diaryResp.ok) throw new Error("memory overview unavailable");
    const [memoryData, diaryData] = await Promise.all([
      memoryResp.json(), diaryResp.json(),
    ]);
    if (personaId !== currentPersonaId) return;

    const heading = el("div", "persona-memory-heading");
    const headingCopy = el("div");
    const kicker = el("span", "persona-memory-kicker");
    kicker.textContent = "记忆与内心";
    const title = el("h3");
    title.textContent = "她记得的，也会成为她生活的一部分";
    headingCopy.append(kicker, title);
    const stats = el("div", "persona-memory-stats");
    const memoryStat = el("span");
    memoryStat.textContent = `${memoryData.total || 0} 条记忆`;
    const diaryStat = el("span");
    diaryStat.textContent = `${diaryData.total || 0} 篇心事`;
    stats.append(memoryStat, diaryStat);
    heading.append(headingCopy, stats);

    const latest = (diaryData.summaries || [])[0];
    const diary = el("div", "persona-diary-preview");
    const diaryLabel = el("span");
    diaryLabel.textContent = "心事日记";
    const prose = el("p");
    prose.textContent = latest?.summary
      ? latest.summary
      : "还没有写下心事。等共同经历慢慢积累，她会在这里留下属于自己的第一人称日记。";
    diary.append(diaryLabel, prose);

    const actions = el("div", "persona-memory-actions");
    const openDiary = el("button", "primary-btn");
    openDiary.type = "button";
    openDiary.textContent = "读她的心事";
    const openMemory = el("button", "ghost-btn");
    openMemory.type = "button";
    openMemory.textContent = "看她记得的事";
    const open = async (tab) => {
      const memoryPage = await import("./memory-page.js");
      await memoryPage.openMemoryPage({
        tab,
        personaId,
        conversationId: useActiveConversation ? state.activeConversationId : "",
      });
    };
    openDiary.addEventListener("click", () => open("diary"));
    openMemory.addEventListener("click", () => open("important"));
    actions.append(openDiary, openMemory);
    section.replaceChildren(heading, diary, actions);
  } catch (error) {
    const message = el("p", "persona-memory-unavailable");
    message.textContent = "记忆暂时无法读取，人设编辑不受影响。";
    section.replaceChildren(message);
  } finally {
    section.setAttribute("aria-busy", "false");
  }
}

async function deleteCurrentPersona() {
  if (currentPersonaId === activePersonaId) {
    toast("请先切换到其他人设再删除");
    return;
  }
  const name = (currentPersonaDetail && currentPersonaDetail.name) || currentPersonaId;
  if (!confirm(`确定删除人设「${name}」？此操作不可撤销。`)) return;
  const btn = $(".btn-delete-persona");
  if (btn) btn.disabled = true;
  try {
    const resp = await fetch(`/api/persona/${currentPersonaId}`, { method: "DELETE" });
    const d = await resp.json().catch(() => ({}));
    if (!resp.ok) throw new Error(d.error || `HTTP ${resp.status}`);
    toast("人设已删除");
    // 删除后：切换到激活人设（一定还存在）并刷新列表
    await loadPersonaEditor(activePersonaId);
  } catch (e) {
    toast(userFacingError(e, "删除人设失败，请稍后重试"));
  } finally {
    if (btn) btn.disabled = false;
  }
}

function openNewPersonaDialog() {
  closeNewPersonaDialog(); // 幂等：先清理旧实例
  const overlay = el("div", "persona-modal-overlay");
  overlay.id = "persona-new-modal";
  overlay.addEventListener("click", (e) => {
    if (e.target === overlay) closeNewPersonaDialog();
  });

  const card = el("div", "persona-modal-card");

  const closeBtn = el("button", "persona-modal-close");
  closeBtn.type = "button";
  closeBtn.textContent = "×";
  closeBtn.setAttribute("aria-label", "关闭");
  closeBtn.addEventListener("click", closeNewPersonaDialog);

  const title = el("h3", "persona-modal-title");
  title.textContent = "新建人设";

  const form = el("form", "persona-modal-form");
  form.id = "persona-new-form";

  const idField = el("div", "persona-field");
  const idLabel = el("label", "persona-field-label");
  idLabel.textContent = "人设 ID";
  const idInput = el("input");
  idInput.type = "text";
  idInput.name = "id";
  idInput.placeholder = "gf001";
  idInput.required = true;
  idInput.pattern = "[A-Za-z0-9_]+";
  const idHint = el("span", "persona-field-hint");
  idHint.textContent = "英文/数字/下划线，唯一标识，创建后不可改";
  idField.appendChild(idLabel);
  idField.appendChild(idInput);
  idField.appendChild(idHint);

  const nameField = el("div", "persona-field");
  const nameLabel = el("label", "persona-field-label");
  nameLabel.textContent = "人设名称";
  const nameInput = el("input");
  nameInput.type = "text";
  nameInput.name = "name";
  nameInput.placeholder = "小雨";
  nameInput.required = true;
  nameField.appendChild(nameLabel);
  nameField.appendChild(nameInput);

  const descField = el("div", "persona-field");
  const descLabel = el("label", "persona-field-label");
  descLabel.textContent = "基础描述（可选）";
  const descInput = el("textarea");
  descInput.name = "description";
  descInput.placeholder = "一句话介绍这个人设…";
  descField.appendChild(descLabel);
  descField.appendChild(descInput);

  const actions = el("div", "persona-modal-actions");
  const btnCancel = el("button", "ghost-btn");
  btnCancel.type = "button";
  btnCancel.textContent = "取消";
  btnCancel.addEventListener("click", closeNewPersonaDialog);
  const btnSubmit = el("button", "primary-btn");
  btnSubmit.type = "submit";
  btnSubmit.textContent = "创建";
  btnSubmit.id = "btn-submit-new-persona";
  actions.appendChild(btnCancel);
  actions.appendChild(btnSubmit);

  form.appendChild(idField);
  form.appendChild(nameField);
  form.appendChild(descField);
  form.appendChild(actions);
  form.addEventListener("submit", (e) => {
    e.preventDefault();
    submitNewPersona({
      id: idInput.value.trim(),
      name: nameInput.value.trim(),
      description: descInput.value.trim(),
    }, btnSubmit);
  });

  card.appendChild(closeBtn);
  card.appendChild(title);
  card.appendChild(form);
  overlay.appendChild(card);
  document.body.appendChild(overlay);
  idInput.focus();
}

function closeNewPersonaDialog() {
  const modal = $("#persona-new-modal");
  if (modal) modal.remove();
}

async function submitNewPersona({ id, name, description }, btn) {
  if (!id || !name) {
    toast("人设 ID 和名称必填");
    return;
  }
  if (!/^[A-Za-z0-9_]+$/.test(id)) {
    toast("人设 ID 只能含英文/数字/下划线");
    return;
  }
  if (btn) btn.disabled = true;
  try {
    const resp = await fetch("/api/persona", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id, name, description }),
    });
    const d = await resp.json().catch(() => ({}));
    if (!resp.ok) throw new Error(d.error || `HTTP ${resp.status}`);
    closeNewPersonaDialog();
    toast("人设已创建");
    // 选中新人设进入编辑（不自动设为当前聊天人设，用户手动点"设为当前"）
    await loadPersonaEditor(id);
  } catch (e) {
    toast(userFacingError(e, "创建人设失败，请稍后重试"));
  } finally {
    if (btn) btn.disabled = false;
  }
}

function renderPersonaForm(form, values, metaList) {
  if (!form) return;
  form.replaceChildren();
  const vals = values || {};
  const keys = Object.keys(vals);
  const rendered = new Set();

  // 主表单（#persona-form）按 5 分组渲染为 fieldset.settings-section；
  // 高级表单（#persona-advanced-form）保持扁平列表（外层 <details> 已是卡片）
  const useSections = form.id === "persona-form";
  const isCore = form.id === "persona-core-form";

  if (useSections) {
    // 按 section 分组渲染 fieldset
    for (const sec of PERSONA_SECTIONS) {
      const sectionFields = [];
      for (const meta of metaList) {
        if (!sec.keys.includes(meta.key)) continue;
        if (meta.type === "readonly") {
          if (vals[meta.key] !== undefined && vals[meta.key] !== null) {
            sectionFields.push(meta);
            rendered.add(meta.key);
          }
        } else if (keys.includes(meta.key)) {
          sectionFields.push(meta);
          rendered.add(meta.key);
        }
      }
      if (sectionFields.length === 0) continue;
      const fieldset = el("fieldset", "settings-section");
      const legend = el("legend");
      legend.textContent = sec.title;
      fieldset.appendChild(legend);
      for (const meta of sectionFields) {
        fieldset.appendChild(renderPersonaField(meta, vals[meta.key]));
      }
      form.appendChild(fieldset);
    }
  } else {
    // 高级表单：扁平渲染（外层 <details> 提供折叠卡片）
    for (const meta of metaList) {
      if (meta.type === "readonly") {
        if (vals[meta.key] !== undefined && vals[meta.key] !== null) {
          form.appendChild(renderPersonaField(meta, vals[meta.key]));
          rendered.add(meta.key);
        }
      } else if (keys.includes(meta.key)) {
        form.appendChild(renderPersonaField(meta, vals[meta.key]));
        rendered.add(meta.key);
      }
    }
  }

  // 未知字段兜底：数组→list/json，对象→json，其他→text
  if (isCore) return;
  for (const k of keys) {
    if (rendered.has(k)) continue;
    if (PERSONA_CORE_FIELDS.some((meta) => meta.key === k)) continue;
    // avatar 由 renderAvatarZone 单独管理（上传/删除端点），不走文本字段；
    // 否则会被 collectPersonaFields 收集后发给 update_persona，后端因 avatar
    // 不在 USER_FIELDS ∪ ADVANCED_FIELDS 而拒绝整个保存（T10 回归）。
    if (k === "avatar") continue;
    const v = vals[k];
    let fallbackType = "text";
    if (Array.isArray(v)) fallbackType = (v.length > 0 && typeof v[0] === "object" && v[0] !== null) ? "json" : "list";
    else if (v !== null && typeof v === "object") fallbackType = "json";
    form.appendChild(renderPersonaField({ key: k, type: fallbackType, label: k }, v));
  }
}

function renderPersonaField(meta, val) {
  const field = el("div", "persona-field");
  const label = el("label", "persona-field-label");
  label.textContent = meta.label || meta.key;
  const controlId = `persona-${meta.key}`;
  label.htmlFor = controlId;
  field.appendChild(label);
  const t = meta.type;
  if (t === "readonly") {
    const inp = el("input"); inp.type = "text"; inp.id = controlId; inp.value = val || ""; inp.readOnly = true;
    inp.dataset.key = meta.key; field.appendChild(inp);
  } else if (t === "text") {
    const inp = el("input"); inp.type = "text"; inp.id = controlId; inp.value = val || "";
    inp.dataset.key = meta.key; field.appendChild(inp);
  } else if (t === "list") {
    const ta = el("textarea"); ta.id = controlId; ta.value = Array.isArray(val) ? val.join("\n") : (val || "");
    ta.dataset.key = meta.key; ta.dataset.type = "list"; field.appendChild(ta);
  } else if (t === "json") {
    const ta = el("textarea"); ta.id = controlId;
    ta.value = (val !== null && val !== undefined) ? JSON.stringify(val, null, 2) : "";
    ta.dataset.key = meta.key; ta.dataset.type = "json";
    if (meta.big) ta.style.minHeight = "120px";
    field.appendChild(ta);
  } else if (t === "textarea") {
    const ta = el("textarea"); ta.id = controlId; ta.value = val || "";
    ta.dataset.key = meta.key;
    if (meta.big) ta.style.minHeight = "120px";
    field.appendChild(ta);
  } else if (t === "range") {
    const row = el("div"); row.style.display = "flex"; row.style.alignItems = "center";
    const inp = el("input"); inp.type = "range"; inp.id = controlId; inp.min = meta.min != null ? meta.min : 0; inp.max = meta.max != null ? meta.max : 100;
    inp.value = val != null ? val : 0; inp.dataset.key = meta.key;
    const vs = el("span", "persona-field-val"); vs.textContent = String(inp.value);
    inp.addEventListener("input", () => { vs.textContent = inp.value; });
    row.appendChild(inp); row.appendChild(vs); field.appendChild(row);
  } else if (t === "select") {
    const sel = el("select"); sel.id = controlId; sel.dataset.key = meta.key;
    for (const opt of (meta.options || [])) {
      const o = el("option"); o.value = opt; o.textContent = opt;
      if (opt === val) o.selected = true;
      sel.appendChild(o);
    }
    field.appendChild(sel);
  }
  if (meta.hint) {
    const hint = el("small", "persona-field-hint");
    hint.textContent = meta.hint;
    field.appendChild(hint);
  }
  return field;
}

export function collectPersonaFields(formId) {
  const fields = {};
  const selector = formId
    ? `#${formId} [data-key]`
    : "#persona-core-form [data-key], #persona-form [data-key], #persona-advanced-form [data-key]";
  document.querySelectorAll(selector).forEach((node) => {
    const key = node.dataset.key;
    if (node.readOnly) return; // 跳过 id 等只读字段
    if (node.tagName === "TEXTAREA" && node.dataset.type === "list") {
      fields[key] = node.value.split("\n").map((s) => s.trim()).filter((s) => s.length > 0);
    } else if (node.tagName === "TEXTAREA" && node.dataset.type === "json") {
      const trimmed = node.value.trim();
      if (!trimmed) { fields[key] = []; }
      else { try { fields[key] = JSON.parse(trimmed); } catch { fields[key] = trimmed; } }
    } else if (node.tagName === "SELECT") {
      fields[key] = node.value;
    } else if (node.type === "range") {
      fields[key] = parseInt(node.value, 10);
    } else {
      fields[key] = node.value;
    }
  });
  return { fields };
}

async function savePersona() {
  const btn = $("#btn-save-persona");
  if (btn) btn.disabled = true;
  try {
    const body = collectPersonaFields();
    const resp = await fetch(`/api/persona/${currentPersonaId}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const d = await resp.json().catch(() => ({}));
    if (!resp.ok) throw new Error(d.error || `HTTP ${resp.status}`);
    toast("人设已保存");
    // 多人设：刷新人设卡片列表（名称可能已变）
    try {
      const listRes = await fetch("/api/persona").then((r) => r.json());
      renderPersonaList(listRes);
    } catch (_) { /* 列表刷新失败不影响保存成功提示 */ }
  } catch (e) {
    toast(userFacingError(e, "保存人设失败，请稍后重试"));
  } finally {
    if (btn) btn.disabled = false;
  }
}

/* ============================================================
   T10: 人设头像上传区（人设编辑器顶部）
   - 圆形预览（80px）：有 avatar 显示 <img>，否则显示名字首字
   - 上传按钮 + 隐藏 file input + 删除链接（仅 avatar 存在时显示）
   - 客户端校验：<2MB、png/jpg/webp
   - POST /api/persona/{id}/avatar (multipart, field "file")
   - DELETE /api/persona/{id}/avatar
   - 上传/删除成功后同步 #sidebar-avatar
   ============================================================ */
const AVATAR_ALLOWED_MIME = ["image/png", "image/jpeg", "image/webp"];
const AVATAR_MAX_SIZE = 2 * 1024 * 1024; // 2MB

function renderAvatarZone(form, persona) {
  if (!form) return;
  const zone = el("div", "avatar-upload-zone");

  const preview = el("div", "avatar-preview");
  preview.id = "avatar-preview";
  renderAvatarPreview(preview, persona);

  const actions = el("div", "avatar-actions");
  const btnUpload = el("button", "ghost-btn");
  btnUpload.type = "button";
  btnUpload.id = "btn-upload-avatar";
  btnUpload.textContent = "上传头像";
  const fileInput = el("input");
  fileInput.type = "file";
  fileInput.id = "avatar-file-input";
  fileInput.accept = AVATAR_ALLOWED_MIME.join(",");
  fileInput.hidden = true;
  const btnDelete = el("a", "delete-link");
  btnDelete.href = "#";
  btnDelete.id = "btn-delete-avatar";
  btnDelete.textContent = "删除";
  btnDelete.hidden = !persona.avatar;
  actions.appendChild(btnUpload);
  actions.appendChild(fileInput);
  actions.appendChild(btnDelete);

  zone.appendChild(preview);
  zone.appendChild(actions);
  // 头像区置于表单顶部（名字字段之上）
  form.insertBefore(zone, form.firstChild);

  bindAvatarZone({ btnUpload, fileInput, btnDelete, preview });
}

function renderAvatarPreview(previewEl, persona) {
  if (!previewEl) return;
  previewEl.replaceChildren();
  const avatar = (persona && persona.avatar) || "";
  const name = (persona && persona.name) || "";
  if (avatar) {
    const img = el("img", "avatar-img");
    img.src = avatar;
    img.alt = name || "头像";
    previewEl.appendChild(img);
    previewEl.classList.remove("is-placeholder");
  } else {
    const ph = el("span", "avatar-placeholder");
    ph.textContent = (name || "?").charAt(0);
    previewEl.appendChild(ph);
    previewEl.classList.add("is-placeholder");
  }
}

function bindAvatarZone({ btnUpload, fileInput, btnDelete, preview }) {
  // 幂等绑定：每次 renderAvatarZone 重建节点，dataset.bound 防重复
  btnUpload.addEventListener("click", () => fileInput.click());
  fileInput.addEventListener("change", async (e) => {
    const file = e.target.files && e.target.files[0];
    if (!file) return;
    // 客户端校验
    if (!AVATAR_ALLOWED_MIME.includes(file.type)) {
      toast("仅支持 PNG/JPG/WebP");
      fileInput.value = "";
      return;
    }
    if (file.size > AVATAR_MAX_SIZE) {
      toast("文件过大，最大 2MB");
      fileInput.value = "";
      return;
    }
    await uploadAvatar(file, btnUpload, btnDelete, preview);
    fileInput.value = ""; // 重置以便重复上传同名文件
  });
  btnDelete.addEventListener("click", async (e) => {
    e.preventDefault();
    if (!confirm("确定删除头像？")) return;
    await deleteAvatar(btnUpload, btnDelete, preview);
  });
}

async function uploadAvatar(file, btnUpload, btnDelete, preview) {
  const originalText = btnUpload.textContent;
  btnUpload.disabled = true;
  btnUpload.textContent = "上传中…";
  try {
    const fd = new FormData();
    fd.append("file", file);
    const resp = await fetch(`/api/persona/${currentPersonaId}/avatar`, {
      method: "POST",
      body: fd,
    });
    const d = await resp.json().catch(() => ({}));
    if (!resp.ok) throw new Error(d.error || `HTTP ${resp.status}`);
    // 更新缓存 + 预览 + 删除链接 + 侧边栏
    if (currentPersonaDetail) currentPersonaDetail.avatar = d.avatar_url;
    renderAvatarPreview(preview, {
      avatar: d.avatar_url,
      name: (currentPersonaDetail && currentPersonaDetail.name) || "",
    });
    btnDelete.hidden = false;
    updateSidebarAvatar(
      d.avatar_url,
      (currentPersonaDetail && currentPersonaDetail.name) || "",
    );
    toast("头像更新成功");
  } catch (e) {
    toast(userFacingError(e, "头像上传失败，请检查图片后重试"));
  } finally {
    btnUpload.disabled = false;
    btnUpload.textContent = originalText;
  }
}

async function deleteAvatar(btnUpload, btnDelete, preview) {
  btnUpload.disabled = true;
  try {
    const resp = await fetch(`/api/persona/${currentPersonaId}/avatar`, {
      method: "DELETE",
    });
    const d = await resp.json().catch(() => ({}));
    if (!resp.ok) throw new Error(d.error || `HTTP ${resp.status}`);
    if (currentPersonaDetail) currentPersonaDetail.avatar = "";
    renderAvatarPreview(preview, {
      avatar: "",
      name: (currentPersonaDetail && currentPersonaDetail.name) || "",
    });
    btnDelete.hidden = true;
    updateSidebarAvatar(
      "",
      (currentPersonaDetail && currentPersonaDetail.name) || "",
    );
    toast("头像已删除");
  } catch (e) {
    toast(userFacingError(e, "头像删除失败，请稍后重试"));
  } finally {
    btnUpload.disabled = false;
  }
}

/* ===== T10: 侧边栏头像同步 =====
   #sidebar-avatar 由 state.js 的 MutationObserver 镜像顶栏 #avatar 文本。
   人设切换时 applyPersona 先设顶栏 textContent → 观察者微任务先执行清空侧边栏；
   随后 loadPersonaEditor 的 fetch 解析后调用本函数覆盖为 <img>，时序安全。
   上传/删除后直接调用本函数，无需经过观察者。 */
function updateSidebarAvatar(avatarUrl, name) {
  const sidebarAvatar = $("#sidebar-avatar");
  if (!sidebarAvatar) return;
  if (avatarUrl) {
    sidebarAvatar.replaceChildren();
    const img = el("img", "avatar-img");
    img.src = avatarUrl;
    img.alt = name || "头像";
    sidebarAvatar.appendChild(img);
  } else {
    sidebarAvatar.textContent = (name || "?").charAt(0);
  }
}

async function syncSidebarAvatar(personaId) {
  try {
    // T10: detail endpoint 不含 avatar，用 list endpoint 获取 {id, name, avatar}
    const list = await fetch(`/api/persona`).then((r) => r.json());
    const p = (list || []).find((x) => x.id === personaId);
    if (p) {
      if (currentPersonaDetail) {
        currentPersonaDetail.avatar = p.avatar || "";
        currentPersonaDetail.name = p.name || "";
      } else {
        currentPersonaDetail = { avatar: p.avatar || "", name: p.name || "" };
      }
      updateSidebarAvatar(p.avatar, p.name);
    }
  } catch (e) {
    console.warn("sidebar avatar sync failed:", e);
  }
}

/* ===== T10: 顶栏 #avatar 变化时重新同步侧边栏头像 =====
   背景：state.js 的 MutationObserver 会将顶栏 #avatar 文本镜像到 #sidebar-avatar。
   人设切换/初始加载时 applyPersona 设顶栏 textContent → state.js 观察者先执行（先注册）
   将侧边栏设为首字；本观察者后执行（后注册），根据 currentPersonaDetail.avatar
   覆盖为 <img>。观察者注册顺序由模块加载顺序保证（state.js 先于 settings-panel.js）。 */
function hookSidebarAvatarSync() {
  const topbarAvatar = $("#avatar");
  if (!topbarAvatar || topbarAvatar.dataset.t10Bound === "1") return;
  topbarAvatar.dataset.t10Bound = "1";
  const reapply = () => {
    if (!currentPersonaDetail) return; // loadPersonaEditor 未跑过，交给 state.js 镜像
    updateSidebarAvatar(currentPersonaDetail.avatar, currentPersonaDetail.name);
  };
  new MutationObserver(reapply).observe(topbarAvatar, {
    childList: true,
    characterData: true,
    subtree: true,
  });
}
hookSidebarAvatarSync();
