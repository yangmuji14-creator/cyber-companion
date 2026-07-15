/* ===== 赛博伴侣 Web UI 客户端 ===== */
"use strict";

const $ = (sel) => document.querySelector(sel);
const el = (tag, cls) => { const e = document.createElement(tag); if (cls) e.className = cls; return e; };

const state = {
  schema: [],
  values: {},
  sending: false,
  personaName: "赛博伴侣",
  avatar: "🌸",
};

const dom = {
  messages: $("#messages"),
  input: $("#input"),
  send: $("#btn-send"),
  connStatus: $("#conn-status"),
  personaName: $("#persona-name"),
  avatar: $("#avatar"),
  // settings
  openSettings: $("#open-settings"),
  closeSettings: $("#close-settings"),
  drawer: $("#drawer"),
  scrim: $("#drawer-scrim"),
  form: $("#settings-form"),
  save: $("#btn-save"),
  saveStatus: $("#save-status"),
  // image
  btnImage: $("#btn-image"),
  fileImage: $("#file-image"),
  // voice
  btnVoice: $("#btn-voice"),
  voiceOverlay: $("#voice-overlay"),
  voiceTimer: $("#voice-timer"),
  voiceCancel: $("#voice-cancel"),
  voiceStop: $("#voice-stop"),
  toast: $("#toast"),
};

/* ---------- 工具 ---------- */
let toastTimer = null;
function toast(msg) {
  dom.toast.textContent = msg;
  dom.toast.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { dom.toast.hidden = true; }, 2600);
}

function scrollBottom() {
  requestAnimationFrame(() => { dom.messages.scrollTop = dom.messages.scrollHeight; });
}

function addBubble(role, text, opts = {}) {
  const row = el("div", `row ${role}`);
  const av = el("div", "bubble-avatar");
  av.textContent = role === "me" ? "🙂" : state.avatar;
  const bubble = el("div", "bubble");
  if (opts.html) bubble.innerHTML = text;
  else bubble.textContent = text;
  if (opts.typing) bubble.classList.add("typing");
  row.appendChild(av);
  row.appendChild(bubble);
  dom.messages.appendChild(row);
  scrollBottom();
  return bubble;
}

/* ---------- 对话（SSE 流式） ---------- */
async function sendMessage() {
  const content = dom.input.value.trim();
  if (!content || state.sending) return;

  state.sending = true;
  dom.send.disabled = true;
  addBubble("me", content);
  dom.input.value = "";
  autoResize();

  // typing 占位
  const aiBubble = addBubble("ai", "", { typing: true, html: true });
  aiBubble.innerHTML = '<span class="dots"><span></span><span></span><span></span></span>';

  let acc = "";
  let started = false;

  try {
    const resp = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ content }),
    });
    if (!resp.ok || !resp.body) {
      const err = await resp.json().catch(() => ({}));
      throw new Error(err.error || `HTTP ${resp.status}`);
    }

    const reader = resp.body.getReader();
    const decoder = new TextDecoder("utf-8");
    let buffer = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      // 解析 SSE：以空行分隔的事件块
      const blocks = buffer.split("\n\n");
      buffer = blocks.pop();  // 末尾残块留待下轮
      for (const block of blocks) {
        const ev = parseSSE(block);
        if (!ev) continue;
        if (ev.event === "token") {
          if (!started) { aiBubble.classList.remove("typing"); aiBubble.textContent = ""; started = true; }
          acc += ev.data.token || "";
          aiBubble.textContent = acc;
          scrollBottom();
        } else if (ev.event === "done") {
          if (!started) { aiBubble.classList.remove("typing"); aiBubble.textContent = ev.data.reply || acc; }
        } else if (ev.event === "error") {
          throw new Error(ev.data.error || "服务出错");
        }
      }
    }
    if (!started && !acc) {
      aiBubble.classList.remove("typing");
      aiBubble.textContent = "（没有收到回复）";
    }
  } catch (e) {
    aiBubble.classList.remove("typing");
    aiBubble.textContent = "消息发送失败：" + e.message;
    toast("发送失败：" + e.message);
  } finally {
    state.sending = false;
    dom.send.disabled = false;
    dom.input.focus();
  }
}

function parseSSE(block) {
  let event = "message", data = "";
  for (const line of block.split("\n")) {
    if (line.startsWith("event:")) event = line.slice(6).trim();
    else if (line.startsWith("data:")) data += line.slice(5).trim();
  }
  if (!data) return null;
  try { return { event, data: JSON.parse(data) }; }
  catch { return null; }
}

/* ---------- 输入框自适应高度 ---------- */
function autoResize() {
  dom.input.style.height = "auto";
  dom.input.style.height = Math.min(dom.input.scrollHeight, 120) + "px";
}

/* ---------- 设置面板 ---------- */
async function loadSettings() {
  try {
    const [schemaRes, valRes] = await Promise.all([
      fetch("/api/schema").then((r) => r.json()),
      fetch("/api/settings").then((r) => r.json()),
    ]);
    state.schema = schemaRes.schema || [];
    state.values = valRes.values || {};
    renderSettings();
  } catch (e) {
    toast("设置加载失败：" + e.message);
  }
}

function renderSettings() {
  dom.form.innerHTML = "";
  // 按 section 分组，保持 schema 顺序
  const sections = [];
  const map = {};
  for (const f of state.schema) {
    if (!map[f.section]) { map[f.section] = []; sections.push(f.section); }
    map[f.section].push(f);
  }

  for (const sec of sections) {
    const wrap = el("div", "set-section");
    const h = el("h3"); h.textContent = sec; wrap.appendChild(h);
    for (const f of map[sec]) wrap.appendChild(renderField(f));
    dom.form.appendChild(wrap);
  }
}

function renderField(f) {
  const field = el("div", "field");
  const val = state.values[f.key];

  if (f.type === "bool") {
    const head = el("div", "field-head");
    const label = el("span", "field-label");
    label.textContent = f.live === false ? f.label + " ★" : f.label;
    const sw = el("label", "switch");
    const cb = el("input"); cb.type = "checkbox"; cb.checked = !!val; cb.dataset.key = f.key;
    const sl = el("span", "slider");
    sw.appendChild(cb); sw.appendChild(sl);
    head.appendChild(label); head.appendChild(sw);
    field.appendChild(head);
  } else {
    const head = el("div", "field-head");
    const label = el("span", "field-label");
    label.textContent = f.live === false ? f.label + " ★" : f.label;
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

function fmt(v, f) {
  if (f.type === "float") return Number(v).toFixed(2);
  return String(v);
}

function collectSettings() {
  const out = {};
  dom.form.querySelectorAll("input[data-key]").forEach((inp) => {
    const key = inp.dataset.key;
    if (inp.type === "checkbox") out[key] = inp.checked;
    else out[key] = inp.dataset.type === "int" ? parseInt(inp.value, 10) : parseFloat(inp.value);
  });
  return out;
}

async function saveSettings() {
  const values = collectSettings();
  dom.save.disabled = true;
  dom.saveStatus.className = "save-status";
  dom.saveStatus.textContent = "保存中…";
  try {
    const resp = await fetch("/api/settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ values }),
    });
    const data = await resp.json();
    if (!resp.ok) throw new Error(data.error || `HTTP ${resp.status}`);
    state.values = data.values || values;
    dom.saveStatus.className = "save-status ok";
    dom.saveStatus.textContent = "已保存并生效";
    setTimeout(() => { dom.saveStatus.textContent = ""; }, 2500);
  } catch (e) {
    dom.saveStatus.className = "save-status err";
    dom.saveStatus.textContent = "保存失败：" + e.message;
  } finally {
    dom.save.disabled = false;
  }
}

function openDrawer() { dom.drawer.classList.add("open"); dom.drawer.setAttribute("aria-hidden", "false"); dom.scrim.hidden = false; }
function closeDrawer() { dom.drawer.classList.remove("open"); dom.drawer.setAttribute("aria-hidden", "true"); dom.scrim.hidden = true; }

/* ---------- 图片上传 ---------- */
async function uploadImage(file) {
  if (!file) return;
  const url = URL.createObjectURL(file);
  addBubble("me", `<img src="${url}" alt="图片" />`, { html: true });
  const aiBubble = addBubble("ai", "", { typing: true, html: true });
  aiBubble.innerHTML = '<span class="dots"><span></span><span></span><span></span></span>';

  const fd = new FormData();
  fd.append("image", file);
  fd.append("caption", "");
  try {
    const resp = await fetch("/api/upload/image", { method: "POST", body: fd });
    const data = await resp.json();
    if (!resp.ok) throw new Error(data.error || `HTTP ${resp.status}`);
    aiBubble.classList.remove("typing");
    aiBubble.textContent = data.reply || "（没有回复）";
  } catch (e) {
    aiBubble.classList.remove("typing");
    aiBubble.textContent = "图片处理失败：" + e.message;
    toast(e.message);
  }
  scrollBottom();
}

/* ---------- 语音录制 ---------- */
let mediaRecorder = null, chunks = [], voiceTimer = null, voiceStart = 0, voiceCancelled = false;

async function startVoice() {
  if (!navigator.mediaDevices || !window.MediaRecorder) { toast("当前浏览器不支持录音"); return; }
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    chunks = []; voiceCancelled = false;
    mediaRecorder = new MediaRecorder(stream);
    mediaRecorder.ondataavailable = (e) => { if (e.data.size) chunks.push(e.data); };
    mediaRecorder.onstop = () => {
      stream.getTracks().forEach((t) => t.stop());
      if (!voiceCancelled) sendVoice(new Blob(chunks, { type: "audio/webm" }));
    };
    mediaRecorder.start();
    voiceStart = Date.now();
    dom.voiceOverlay.hidden = false;
    updateVoiceTimer();
    voiceTimer = setInterval(updateVoiceTimer, 250);
  } catch (e) {
    toast("无法访问麦克风");
  }
}
function updateVoiceTimer() {
  const s = Math.floor((Date.now() - voiceStart) / 1000);
  dom.voiceTimer.textContent = `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}
function stopVoice(cancel) {
  voiceCancelled = cancel;
  clearInterval(voiceTimer);
  dom.voiceOverlay.hidden = true;
  if (mediaRecorder && mediaRecorder.state !== "inactive") mediaRecorder.stop();
}
async function sendVoice(blob) {
  const aiBubble = addBubble("ai", "", { typing: true, html: true });
  aiBubble.innerHTML = '<span class="dots"><span></span><span></span><span></span></span>';
  const fd = new FormData();
  fd.append("audio", blob, "voice.webm");
  try {
    const resp = await fetch("/api/upload/voice", { method: "POST", body: fd });
    const data = await resp.json();
    if (!resp.ok) {
      if (data.need_asr) throw new Error("语音转写未配置，请改用文字");
      throw new Error(data.error || `HTTP ${resp.status}`);
    }
    // 回填用户语音转写
    if (data.transcript) {
      const row = el("div", "row me");
      const av = el("div", "bubble-avatar"); av.textContent = "🙂";
      const b = el("div", "bubble"); b.textContent = "🎤 " + data.transcript;
      row.appendChild(av); row.appendChild(b);
      dom.messages.insertBefore(row, aiBubble.parentElement);
    }
    aiBubble.classList.remove("typing");
    aiBubble.textContent = data.reply || "（没有回复）";
  } catch (e) {
    aiBubble.classList.remove("typing");
    aiBubble.textContent = "语音处理失败：" + e.message;
    toast(e.message);
  }
  scrollBottom();
}

/* ---------- 连接状态 ---------- */
async function checkHealth() {
  try {
    const r = await fetch("/api/settings");
    if (r.ok) { dom.connStatus.textContent = "在线"; dom.connStatus.classList.add("online"); return; }
  } catch {}
  dom.connStatus.textContent = "离线"; dom.connStatus.classList.remove("online");
}

/* ---------- 事件绑定 ---------- */
function bind() {
  dom.send.addEventListener("click", sendMessage);
  dom.input.addEventListener("input", autoResize);
  dom.input.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendMessage(); }
  });

  dom.openSettings.addEventListener("click", openDrawer);
  dom.closeSettings.addEventListener("click", closeDrawer);
  dom.scrim.addEventListener("click", closeDrawer);
  dom.save.addEventListener("click", saveSettings);

  dom.btnImage.addEventListener("click", () => dom.fileImage.click());
  dom.fileImage.addEventListener("change", (e) => {
    if (e.target.files[0]) uploadImage(e.target.files[0]);
    e.target.value = "";
  });

  dom.btnVoice.addEventListener("click", startVoice);
  dom.voiceStop.addEventListener("click", () => stopVoice(false));
  dom.voiceCancel.addEventListener("click", () => stopVoice(true));
}

/* ---------- 启动 ---------- */
function init() {
  bind();
  loadSettings();
  checkHealth();
  addBubble("ai", "嗨，我在呢～想聊点什么都可以 🌸");
}
document.addEventListener("DOMContentLoaded", init);
