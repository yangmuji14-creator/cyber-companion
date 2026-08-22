/* ===== upload.js - 图片上传与语音输入 ===== */
import { state, dom } from './state.js';
import { toast, scrollBottom, addBubble, userFacingError } from './ui.js';
import { sendMessage } from './chat-stream.js?v=4.3.11';

let mediaRecorder = null;
let speechRecognition = null;
let chunks = [];
let voiceTimer = null;
let voiceStart = 0;
let voiceCancelled = false;
let voiceResultHandled = false;

async function legacyUploadImage(file) {
  if (!file || state.sending) return;
  state.sending = true;
  dom.send.disabled = true;
  const url = URL.createObjectURL(file);
  const userBubble = addBubble("me", `<img src="${url}" alt="图片" />`, { html: true });
  const preview = userBubble.querySelector("img");
  if (preview) preview.addEventListener("load", () => URL.revokeObjectURL(url), { once: true });
  const aiBubble = addBubble("ai", "", { typing: true, html: true });
  aiBubble.innerHTML = '<span class="dots"><span></span><span></span><span></span></span>';

  const fd = new FormData();
  fd.append("image", file);
  fd.append("caption", "");
  if (state.activeConversationId) fd.append("conversation_id", state.activeConversationId);
  try {
    const resp = await fetch("/api/upload/image", { method: "POST", body: fd });
    const data = await resp.json();
    if (!resp.ok) throw new Error(data.error || `HTTP ${resp.status}`);
    aiBubble.classList.remove("typing");
    aiBubble.textContent = data.reply || "（没有回复）";
  } catch (e) {
    aiBubble.classList.remove("typing");
    const message = userFacingError(e, "图片暂时无法处理，请稍后重试");
    aiBubble.textContent = message;
    toast(message);
  } finally {
    state.sending = false;
    dom.send.disabled = false;
    scrollBottom();
  }
}

export function clearPendingImage() {
  if (state.pendingImage?.previewUrl) URL.revokeObjectURL(state.pendingImage.previewUrl);
  state.pendingImage = null;
  if (dom.pendingImage) dom.pendingImage.hidden = true;
  if (dom.pendingImagePreview) dom.pendingImagePreview.removeAttribute("src");
  if (dom.pendingImageName) dom.pendingImageName.textContent = "";
}

window.addEventListener("chat-cancel-pending", clearPendingImage);

export function uploadImage(file) {
  if (!file || state.sending) return;
  clearPendingImage();
  const previewUrl = URL.createObjectURL(file);
  state.pendingImage = { file, previewUrl };
  if (dom.pendingImagePreview) dom.pendingImagePreview.src = previewUrl;
  if (dom.pendingImageName) dom.pendingImageName.textContent = file.name || "图片";
  if (dom.pendingImage) dom.pendingImage.hidden = false;
  toast("图片已加入待发送区，可补充文字");
}

export async function sendPendingImage(caption = "") {
  const pending = state.pendingImage;
  if (!pending || state.sending) return false;
  state.sending = true;
  dom.send.disabled = true;
  const localUrl = pending.previewUrl;
  const userBubble = addBubble("me", "", { html: true });
  const image = document.createElement("img");
  image.src = localUrl;
  image.alt = "图片";
  userBubble.appendChild(image);
  if (caption) {
    const label = document.createElement("span");
    label.className = "image-caption";
    label.textContent = caption;
    userBubble.appendChild(label);
  }
  clearPendingImage();
  const aiBubble = addBubble("ai", "", { typing: true, html: true });
  aiBubble.innerHTML = '<span class="dots"><span></span><span></span><span></span></span>';
  const fd = new FormData();
  fd.append("image", pending.file);
  fd.append("caption", caption);
  if (state.activeConversationId) fd.append("conversation_id", state.activeConversationId);
  try {
    const resp = await fetch("/api/upload/image", { method: "POST", body: fd });
    const data = await resp.json();
    if (!resp.ok) throw new Error(data.error || `HTTP ${resp.status}`);
    aiBubble.classList.remove("typing");
    aiBubble.textContent = data.reply || "（没有收到回复）";
    return true;
  } catch (e) {
    aiBubble.classList.remove("typing");
    const message = userFacingError(e, "图片暂时无法处理，请稍后重试");
    aiBubble.textContent = message;
    toast(message);
    return false;
  } finally {
    state.sending = false;
    dom.send.disabled = false;
    scrollBottom();
  }
}

export async function startVoice() {
  if (state.sending) { toast("正在处理上一条消息"); return; }
  const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (Recognition) {
    startBrowserRecognition(Recognition);
    return;
  }
  await startRecorderFallback();
}

function startBrowserRecognition(Recognition) {
  voiceCancelled = false;
  voiceResultHandled = false;
  speechRecognition = new Recognition();
  speechRecognition.lang = "zh-CN";
  speechRecognition.continuous = false;
  speechRecognition.interimResults = false;
  speechRecognition.maxAlternatives = 1;

  speechRecognition.onstart = showVoiceOverlay;
  speechRecognition.onresult = (event) => {
    if (voiceCancelled) return;
    const transcript = Array.from(event.results)
      .map((result) => result[0]?.transcript || "")
      .join("")
      .trim();
    if (!transcript) return;
    voiceResultHandled = true;
    dom.input.value = transcript;
    dom.input.dispatchEvent(new Event("input", { bubbles: true }));
    sendMessage();
  };
  speechRecognition.onerror = (event) => {
    if (voiceCancelled || event.error === "aborted") return;
    voiceResultHandled = true;
    const messages = {
      "not-allowed": "麦克风权限被拒绝，请在浏览器地址栏允许麦克风",
      "service-not-allowed": "浏览器语音服务不可用，请检查系统语音权限",
      "audio-capture": "没有检测到可用的麦克风",
      "network": "语音识别服务连接失败，请检查网络后重试",
      "no-speech": "没有听到清晰的语音，请靠近麦克风重试",
    };
    toast(messages[event.error] || "语音识别失败，请稍后重试");
  };
  speechRecognition.onend = () => {
    hideVoiceOverlay();
    speechRecognition = null;
    if (!voiceCancelled && !voiceResultHandled) toast("没有听清，请再说一次");
  };

  try {
    speechRecognition.start();
  } catch (_) {
    speechRecognition = null;
    toast("语音识别暂时无法启动，请稍后重试");
  }
}

async function startRecorderFallback() {
  if (!navigator.mediaDevices || !window.MediaRecorder) {
    toast("当前浏览器不支持语音输入");
    return;
  }
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    chunks = [];
    voiceCancelled = false;
    mediaRecorder = new MediaRecorder(stream);
    mediaRecorder.ondataavailable = (event) => {
      if (event.data.size) chunks.push(event.data);
    };
    mediaRecorder.onstop = () => {
      stream.getTracks().forEach((track) => track.stop());
      if (!voiceCancelled) void sendVoice(new Blob(chunks, { type: mediaRecorder.mimeType || "audio/webm" }));
      mediaRecorder = null;
    };
    mediaRecorder.start();
    showVoiceOverlay();
  } catch (error) {
    const denied = error?.name === "NotAllowedError" || error?.name === "SecurityError";
    toast(denied ? "麦克风权限被拒绝，请在浏览器地址栏允许麦克风" : "无法访问麦克风，请检查系统输入设备");
  }
}

function showVoiceOverlay() {
  voiceStart = Date.now();
  dom.voiceOverlay.hidden = false;
  updateVoiceTimer();
  clearInterval(voiceTimer);
  voiceTimer = setInterval(updateVoiceTimer, 250);
}

function hideVoiceOverlay() {
  clearInterval(voiceTimer);
  voiceTimer = null;
  dom.voiceOverlay.hidden = true;
}

export function updateVoiceTimer() {
  const seconds = Math.floor((Date.now() - voiceStart) / 1000);
  dom.voiceTimer.textContent = `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
}

export function stopVoice(cancel) {
  voiceCancelled = cancel;
  hideVoiceOverlay();
  if (speechRecognition) {
    try {
      if (cancel) speechRecognition.abort();
      else speechRecognition.stop();
    } catch (_) {}
    return;
  }
  if (mediaRecorder && mediaRecorder.state !== "inactive") mediaRecorder.stop();
}

async function sendVoice(blob) {
  if (state.sending) return;
  state.sending = true;
  dom.send.disabled = true;
  const aiBubble = addBubble("ai", "", { typing: true, html: true });
  aiBubble.innerHTML = '<span class="dots"><span></span><span></span><span></span></span>';
  const fd = new FormData();
  fd.append("audio", blob, "voice.webm");
  if (state.activeConversationId) fd.append("conversation_id", state.activeConversationId);
  try {
    const resp = await fetch("/api/upload/voice", { method: "POST", body: fd });
    const data = await resp.json();
    if (!resp.ok) {
      if (data.need_asr) throw new Error("本地语音转写组件未安装，请使用支持语音识别的浏览器或文字输入");
      throw new Error(data.error || `HTTP ${resp.status}`);
    }
    if (data.transcript) {
      const row = addBubble("me", `🎤 ${data.transcript}`);
      const rowElement = row.parentElement;
      dom.messages.insertBefore(rowElement, aiBubble.parentElement);
    }
    aiBubble.classList.remove("typing");
    aiBubble.textContent = data.reply || "（没有回复）";
  } catch (e) {
    aiBubble.classList.remove("typing");
    const message = userFacingError(e, e.message || "语音暂时无法处理，请稍后重试");
    aiBubble.textContent = message;
    toast(message);
  } finally {
    state.sending = false;
    dom.send.disabled = false;
    scrollBottom();
  }
}
