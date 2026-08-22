/* SSE chat transport with batching, cancellation and collapsed activity. */
import { state, dom } from "./state.js";
import { toast, scrollBottom, addBubble, autoResize, userFacingError } from "./ui.js";
import { appendVoiceBubble } from "./voice-bubble.js";

let pendingTexts = [];
let pendingTimer = null;
let pendingConversationId = null;
let pendingSticker = null;
let activeBubble = null;
let answerNode = null;
let activityDetails = null;

function debounceSeconds() {
  const value = Number(state.values?.debounce_seconds ?? 3);
  return Number.isFinite(value) ? Math.max(0, Math.min(15, value)) : 3;
}

function showStopButton(show) {
  if (dom.stop) {
    dom.stop.hidden = !show;
    dom.stop.disabled = !show;
  }
}

function clearPendingTimer() {
  if (pendingTimer !== null) clearTimeout(pendingTimer);
  pendingTimer = null;
}

export function sendMessage() {
  const content = dom.input.value.trim();
  if (state.pendingImage && !state.activeRequest && !state.sending) {
    dom.input.value = "";
    autoResize();
    import("./upload.js?v=4.3.11").then(({ sendPendingImage }) => sendPendingImage(content));
    return;
  }
  if (!content || state.activeRequest || (state.sending && pendingTexts.length === 0)) return;
  const conversationId = state.activeConversationId;
  if (pendingTexts.length === 0) pendingConversationId = conversationId;
  if (pendingConversationId !== conversationId) {
    cancelPendingSend(false);
    pendingConversationId = conversationId;
  }
  pendingTexts.push(content);
  if (state.pendingSticker) {
    pendingSticker = state.pendingSticker;
    state.pendingSticker = null;
    const bubble = addBubble("me", "", { html: true });
    const image = document.createElement("img");
    image.className = "sticker-image";
    image.src = pendingSticker.url;
    image.alt = pendingSticker.emotion || "表情包";
    const label = document.createElement("span");
    label.className = "sticker-label";
    label.textContent = content;
    bubble.append(image, label);
  } else {
    addBubble("me", content);
  }
  dom.input.value = "";
  autoResize();
  state.sending = true;
  dom.send.disabled = false;
  showStopButton(true);
  clearPendingTimer();
  pendingTimer = setTimeout(flushPendingMessages, debounceSeconds() * 1000);
  if (debounceSeconds() === 0) void flushPendingMessages();
}

export function cancelPendingSend(notify = true) {
  const hadPending = pendingTexts.length > 0;
  clearPendingTimer();
  pendingTexts = [];
  pendingConversationId = null;
  pendingSticker = null;
  if (hadPending && !state.activeRequest) {
    state.sending = false;
    showStopButton(false);
    if (notify) toast("已取消等待中的消息");
  }
}

export function stopMessageGeneration() {
  const hadPending = pendingTexts.length > 0;
  clearPendingTimer();
  pendingTexts = [];
  pendingConversationId = null;
  pendingSticker = null;
  if (state.activeRequest) {
    state.activeRequest.abort();
  } else if (hadPending) {
    state.sending = false;
    showStopButton(false);
    dom.send.disabled = false;
    dom.input.focus();
    toast("已取消等待中的消息");
  }
}

async function flushPendingMessages() {
  clearPendingTimer();
  if (!pendingTexts.length || state.activeRequest) return;
  const content = pendingTexts.join("\n");
  const conversationId = pendingConversationId;
  const sticker = pendingSticker;
  pendingTexts = [];
  pendingConversationId = null;
  pendingSticker = null;

  activeBubble = addBubble("ai", "", { typing: true, html: true });
  answerNode = document.createElement("span");
  answerNode.className = "answer-text";
  activityDetails = document.createElement("details");
  activityDetails.className = "activity-details";
  activityDetails.hidden = true;
  const summary = document.createElement("summary");
  summary.textContent = "正在处理";
  const body = document.createElement("div");
  body.className = "activity-body";
  activityDetails.append(summary, body);
  activeBubble.replaceChildren(answerNode);

  let acc = "";
  let started = false;
  const controller = new AbortController();
  state.activeRequest = controller;
  dom.send.disabled = true;
  showStopButton(true);
  try {
    const resp = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        content,
        conversation_id: conversationId,
        ...(sticker ? { sticker } : {}),
      }),
      signal: controller.signal,
    });
    if (!resp.ok || !resp.body) {
      const error = await resp.json().catch(() => ({}));
      throw new Error(error.error || `HTTP ${resp.status}`);
    }
    const reader = resp.body.getReader();
    const decoder = new TextDecoder("utf-8");
    let buffer = "";
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const blocks = buffer.split("\n\n");
      buffer = blocks.pop();
      for (const block of blocks) {
        const ev = parseSSE(block);
        if (!ev) continue;
        if (ev.event === "token") {
          if (!started) {
            activeBubble.classList.remove("typing");
            answerNode.textContent = "";
            started = true;
          }
          acc += ev.data.token || "";
          answerNode.textContent = acc;
          scrollBottom();
        } else if (["phase", "reasoning", "tool_start", "tool_end"].includes(ev.event)) {
          renderActivity(ev.event, ev.data || {});
        } else if (ev.event === "sticker" && ev.data?.url) {
          const image = document.createElement("img");
          image.className = "sticker-image";
          image.src = ev.data.url;
          image.alt = ev.data.emotion || "表情包";
          activeBubble.appendChild(image);
        } else if (ev.event === "done") {
          if (!started) {
            activeBubble.classList.remove("typing");
            answerNode.textContent = ev.data.reply || acc;
            started = true;
          }
          if (ev.data.voice_url) {
            appendVoiceBubble(activeBubble, ev.data.voice_url);
          }
          finishActivity();
        } else if (ev.event === "error") {
          throw new Error(ev.data.error || "服务暂时不可用");
        }
      }
    }
    if (!started && !acc) {
      activeBubble.classList.remove("typing");
      answerNode.textContent = "（没有收到回复）";
    }
  } catch (error) {
    activeBubble.classList.remove("typing");
    const message = error.name === "AbortError"
      ? "已停止生成"
      : userFacingError(error, "暂时无法发送消息，请稍后重试");
    answerNode.textContent = message;
    if (error.name === "AbortError") toast(message);
    else toast(message);
  } finally {
    if (state.activeRequest === controller) state.activeRequest = null;
    activeBubble = null;
    answerNode = null;
    activityDetails = null;
    state.sending = false;
    dom.send.disabled = false;
    showStopButton(false);
    dom.input.focus();
  }
}

function renderActivity(event, data) {
  if (!activityDetails) return;
  if (!activityDetails.parentElement) activeBubble?.appendChild(activityDetails);
  activityDetails.hidden = false;
  activityDetails.classList.toggle("activity-running", event !== "tool_end");
  const activityBody = activityDetails.querySelector(".activity-body");
  const previous = activityBody?.lastElementChild;
  if (event === "reasoning" && previous?.classList.contains("reasoning")) {
    previous.textContent += data.text || "";
    return;
  }
  const row = document.createElement("div");
  row.className = `activity-row ${event}`;
  row.textContent = event === "reasoning"
    ? (data.text || "正在思考")
    : event === "tool_start"
      ? `调用工具：${data.name || "工具"}`
      : event === "tool_end"
        ? `${data.name || "工具"} · ${data.success ? "已完成" : "未完成"}`
        : (data.label || "正在处理");
  activityBody?.appendChild(row);
  const summary = activityDetails.querySelector("summary");
  if (summary) summary.textContent = event === "tool_end" ? "已完成" : (data.label || "正在处理");
}

function finishActivity() {
  if (!activityDetails) return;
  activityDetails.classList.remove("activity-running");
  const summary = activityDetails.querySelector("summary");
  if (summary) summary.textContent = "处理记录";
}

window.addEventListener("chat-cancel-pending", () => cancelPendingSend(false));

function parseSSE(block) {
  let event = "message";
  let data = "";
  for (const line of block.split("\n")) {
    if (line.startsWith("event:")) event = line.slice(6).trim();
    else if (line.startsWith("data:")) data += line.slice(5).trim();
  }
  if (!data) return null;
  try { return { event, data: JSON.parse(data) }; } catch { return null; }
}
