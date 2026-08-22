/* ===== voice-providers-page.js — 语音服务商设置子页（TTS）=====
 *
 * 配置 Web 面板「AI 语音回复」的 TTS 服务商：
 *  - 列表（名称/类型/模型/音色 + 启用态）
 *  - 新增 / 编辑（name / type / base_url / model / voice / api_key）
 *  - 测试连接（POST /test）
 *  - 试听（GET /api/audio/synthesize?text=...&voice=...）
 *  - 删除
 *
 * 后端端点：
 *  - GET/POST /api/voice-providers
 *  - PUT/DELETE /api/voice-providers/{name}
 *  - POST /api/voice-providers/{name}/test
 *  - GET /api/audio/synthesize
 * 渲染安全：动态文本一律 textContent，防止 XSS。
 * 入口：renderVoiceProvidersPage(container)
 */

import { el } from "./state.js";
import { toast, userFacingError } from "./ui.js";
import { appendVoiceBubble } from "./voice-bubble.js";

const CONTAINER_SEL = "#tab-content-voice-providers, #voice-providers-container";
const OPENAI_VOICES = ["alloy", "echo", "fable", "onyx", "nova", "shimmer"];

async function apiJson(url, opts = {}) {
  const res = await fetch(url, {
    headers: opts.body ? { "Content-Type": "application/json" } : undefined,
    ...opts,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`);
  return data;
}

function wrapField(labelText) {
  const wrap = el("label", "vp2-field");
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

function fieldPassword(labelText, value = "") {
  const wrap = wrapField(labelText);
  const input = document.createElement("input");
  input.type = "password";
  input.value = value;
  input.placeholder = "sk-…（编辑时留空保留原值）";
  wrap.appendChild(input);
  return wrap;
}

function voiceSelect(value) {
  const wrap = wrapField("默认音色");
  const select = document.createElement("select");
  for (const v of OPENAI_VOICES) {
    const opt = document.createElement("option");
    opt.value = v;
    opt.textContent = v;
    if (v === value || (!value && v === "alloy")) opt.selected = true;
    select.appendChild(opt);
  }
  wrap.appendChild(select);
  return wrap;
}

function buildProviderRow(container, p, activeName) {
  const row = el("div", "vp2-prow");
  const info = el("div", "vp2-pinfo");
  const name = el("div", "vp2-pname");
  name.textContent = p.name || "未命名";
  info.appendChild(name);
  const meta = el("div", "vp2-pmeta");
  meta.textContent = `${p.type} · ${p.model} · 音色 ${p.voice}${p.has_api_key ? "" : "（未设 Key）"}`;
  info.appendChild(meta);
  row.appendChild(info);

  const st = el("div", `vp2-pstate ${activeName === p.name ? "active" : ""}`);
  st.textContent = activeName === p.name ? "启用中" : (p.enabled ? "已启用" : "未启用");
  row.appendChild(st);

  const btns = el("div", "vp2-pbtns");
  const test = el("button", "ghost-btn small");
  test.type = "button";
  test.textContent = "测试";
  test.addEventListener("click", () => testProvider(container, p));
  btns.appendChild(test);

  const audition = el("button", "ghost-btn small");
  audition.type = "button";
  audition.textContent = "试听";
  audition.addEventListener("click", () => auditionProvider(row, p));
  btns.appendChild(audition);

  const edit = el("button", "ghost-btn small");
  edit.type = "button";
  edit.textContent = "编辑";
  edit.addEventListener("click", () => openEditor(container, p));
  btns.appendChild(edit);

  const del = el("button", "ghost-btn small danger");
  del.type = "button";
  del.textContent = "删除";
  del.addEventListener("click", () => removeProvider(container, p));
  btns.appendChild(del);

  row.appendChild(btns);
  return row;
}

async function refresh(container) {
  try {
    const data = await apiJson("/api/voice-providers");
    const providers = data.providers || [];
    const active = data.active;
    container.innerHTML = "";

    const head = el("div", "vp2-toolbar");
    const title = el("h3", "vp2-title");
    title.textContent = "语音服务商（TTS）";
    head.appendChild(title);
    const actions = el("div", "vp2-toolbar-actions");
    const addBtn = el("button", "primary-btn");
    addBtn.type = "button";
    addBtn.textContent = "新增服务商";
    addBtn.addEventListener("click", () => openEditor(container, null));
    actions.appendChild(addBtn);
    head.appendChild(actions);
    container.appendChild(head);

    const desc = el("p", "vp2-desc");
    desc.textContent = "AI 在回复中用 [语音] 标记把文字合成语音发给你。配置 OpenAI 兼容 TTS（/v1/audio/speech）。";
    container.appendChild(desc);

    if (!providers.length) {
      const empty = el("div", "vp2-empty");
      empty.textContent = "还没有语音服务商，点「新增服务商」添加（建议填 OpenAI 兼容 /v1/audio/speech 服务）。";
      container.appendChild(empty);
      return;
    }

    const list = el("div", "vp2-list");
    for (const p of providers) list.appendChild(buildProviderRow(container, p, active));
    container.appendChild(list);
  } catch (e) {
    container.innerHTML = "";
    const err = el("div", "vp2-empty");
    err.textContent = userFacingError(e, "语音服务商加载失败");
    container.appendChild(err);
  }
}

async function testProvider(container, p) {
  try {
    const data = await apiJson(`/api/voice-providers/${encodeURIComponent(p.name)}/test`, { method: "POST" });
    toast(data.ok ? "连接成功，可正常合成" : `连接失败：${data.error || ""}`);
  } catch (e) {
    const msg = userFacingError(e, "测试失败");
    toast(`${msg}${e.message && e.message.includes("已") ? "" : `：${e.message || ""}`}`);
  }
}

async function auditionProvider(row, p) {
  try {
    const url = `/api/audio/synthesize?text=${encodeURIComponent("你好，我是慕。")}&voice=${encodeURIComponent(p.voice)}`;
    const resp = await fetch(url);
    if (!resp.ok) {
      const data = await resp.json().catch(() => ({}));
      throw new Error(data.error || `HTTP ${resp.status}`);
    }
    const blob = await resp.blob();
    const objectUrl = URL.createObjectURL(blob);
    appendVoiceBubble(row, objectUrl);
    toast("合成成功，可试听");
  } catch (e) {
    toast(userFacingError(e, "试听失败"));
  }
}

async function removeProvider(container, p) {
  if (!confirm(`删除语音服务商「${p.name}」？`)) return;
  try {
    await apiJson(`/api/voice-providers/${encodeURIComponent(p.name)}`, { method: "DELETE" });
    await refresh(container);
    toast("已删除");
  } catch (e) {
    toast(userFacingError(e, "删除失败"));
  }
}

function openEditor(container, existing) {
  container.innerHTML = "";
  const card = el("div", "vp2-editor");
  const title = el("h3", "vp2-title");
  title.textContent = existing ? `编辑服务商：${existing.name}` : "新增语音服务商";
  card.appendChild(title);

  const nameInput = fieldInput("服务商名称", existing ? existing.name : "", "如 my-tts");
  const typeInput = fieldInput("类型", existing ? existing.type : "openai", "openai");
  const baseInput = fieldInput("Base URL", existing ? existing.base_url : "https://api.openai.com", "如 https://api.openai.com");
  const modelInput = fieldInput("模型", existing ? existing.model : "tts-1", "如 tts-1 / gpt-4o-mini-tts");
  const voice = voiceSelect(existing ? existing.voice : "alloy");
  const keyInput = fieldPassword("API Key", existing && existing.has_api_key ? "************" : "");

  card.appendChild(nameInput);
  card.appendChild(typeInput);
  card.appendChild(baseInput);
  card.appendChild(modelInput);
  card.appendChild(voice);
  card.appendChild(keyInput);

  const btns = el("div", "vp2-editor-btns");
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
    const apiKey = keyInput.querySelector("input").value.trim();
    if (!name) { toast("请填写服务商名称"); return; }
    const body = {
      name,
      type: typeInput.querySelector("input").value.trim() || "openai",
      base_url: baseInput.querySelector("input").value.trim(),
      model: modelInput.querySelector("input").value.trim() || "tts-1",
      voice: voice.querySelector("select").value,
    };
    // 编辑时若 Key 是占位符（未改动），不发回，后端保留原值
    if (apiKey && apiKey !== "************") body.api_key = apiKey;
    try {
      const url = existing
        ? `/api/voice-providers/${encodeURIComponent(existing.name)}`
        : "/api/voice-providers";
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

/** 渲染语音服务商子页到指定容器；若无容器则尝试 #tab-content-voice-providers。 */
export async function renderVoiceProvidersPage(container = null) {
  const target = container || document.querySelector(CONTAINER_SEL);
  if (!target) return;
  await refresh(target);
}
