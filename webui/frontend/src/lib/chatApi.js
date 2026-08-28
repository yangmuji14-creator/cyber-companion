// ============================================================
// lib/chatApi.js — 聊天页专属后端 API 封装 (ChatPage 业务契约)
//
// 只服务聊天页 (会话/历史/人设/贴纸/上传)。字段名严格对齐
// webui/server.py 的 /api/* 契约, 一个都不能错。
// 所有请求经 Vite dev proxy (/api -> 127.0.0.1:8000) 或后端
// add_static 直出 (build 产物)。不修改全局 lib/api.js 结构。
// ============================================================

const JSON_HEADERS = { accept: 'application/json', 'content-type': 'application/json' };

async function request(resource, options = {}) {
  const res = await fetch(resource, {
    headers: { ...JSON_HEADERS, ...(options.headers || {}) },
    ...options,
  });
  let data = null;
  try {
    data = await res.json();
  } catch {
    data = null;
  }
  if (!res.ok) {
    const msg = (data && data.error) || `请求失败 (${res.status})`;
    const err = new Error(msg);
    err.status = res.status;
    err.data = data;
    throw err;
  }
  return data;
}

// ---- 会话 (Conversations) ----

// GET /api/conversations -> 裸数组
export async function listConversations() {
  return request('/api/conversations');
}

// POST /api/conversations body {platform, persona_id} -> 单条 binding
export async function createConversation({ platform = 'web', persona_id }) {
  return request('/api/conversations', {
    method: 'POST',
    body: JSON.stringify({ platform, persona_id }),
  });
}

// PATCH /api/conversations/{id} body {persona_id?, title?} -> 单条 binding
export async function updateConversation(id, { persona_id, title } = {}) {
  const body = {};
  if (persona_id) body.persona_id = persona_id;
  if (title !== undefined) body.title = title;
  return request(`/api/conversations/${encodeURIComponent(id)}`, {
    method: 'PATCH',
    body: JSON.stringify(body),
  });
}

// DELETE /api/conversations/{id} -> {ok:true}
export async function deleteConversation(id) {
  return request(`/api/conversations/${encodeURIComponent(id)}`, { method: 'DELETE' });
}

// ---- 消息历史 ----

// GET /api/history?conversation_id={id} -> {messages:[{role,content,timestamp,sticker?}]}
export async function fetchHistory(conversation_id) {
  const q = new URLSearchParams({ conversation_id });
  const data = await request(`/api/history?${q.toString()}`);
  return Array.isArray(data?.messages) ? data.messages : [];
}

// ---- 人设 ----

// GET /api/persona -> 裸数组 [{id,name,avatar}]
export async function listPersonas() {
  return request('/api/persona');
}

// ---- 贴纸 ----

// GET /api/stickers -> {stickers:[{pack,emotion,images:[...]}]}
export async function listStickers() {
  const data = await request('/api/stickers');
  return Array.isArray(data?.stickers) ? data.stickers : [];
}

// ---- 多模态上传 (multipart) ----

// POST /api/upload/image 字段 image(+caption/conversation_id) -> {reply}
export async function uploadImage(file, { caption = '', conversation_id } = {}) {
  const form = new FormData();
  form.append('image', file);
  if (caption) form.append('caption', caption);
  if (conversation_id) form.append('conversation_id', conversation_id);
  return request('/api/upload/image', { method: 'POST', body: form });
}

// POST /api/upload/voice 字段 audio(+conversation_id) -> {transcript, reply}
export async function uploadVoice(file, { conversation_id } = {}) {
  const form = new FormData();
  form.append('audio', file);
  if (conversation_id) form.append('conversation_id', conversation_id);
  return request('/api/upload/voice', { method: 'POST', body: form });
}
