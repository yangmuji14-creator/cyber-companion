// ============================================================
// lib/settingsApi.js — 设置页专用后端接口封装
//
// 独立于 src/lib/api.js 的全局结构, 仅设置页使用。
// 所有请求返回 { ok, status, data } 统一结构 (与 api.js 的 request 一致)。
// 字段名严格对后端契约, 一个都不能错。
// ============================================================

const JSON_HEADERS = { accept: 'application/json' };

async function req(resource, options = {}) {
  const res = await fetch(resource, {
    headers: { ...JSON_HEADERS, ...(options.headers || {}) },
    ...options,
  });
  const data = await res.json().catch(() => null);
  return { ok: res.ok, status: res.status, data };
}

// 拼 body 的统一封装
function jsonBody(body) {
  return {
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(body),
  };
}

// 文件下载辅助: 后端返回 zip 字节, 触发浏览器下载
async function download(resource, method = 'GET', body = null) {
  const res = await fetch(resource, {
    method,
    headers: body ? { 'content-type': 'application/json' } : {},
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) {
    const text = await res.text().catch(() => `HTTP ${res.status}`);
    return { ok: false, status: res.status, data: text };
  }
  const blob = await res.blob();
  // 从 Content-Disposition 或 URL 推断文件名
  const cd = res.headers.get('content-disposition') || '';
  const m = cd.match(/filename\*?=(?:UTF-8''|")?([^";]+)/i);
  let filename = (m ? m[1] : resource.split('/').pop() || 'download') + '.zip';
  filename = decodeURIComponent(filename).replace(/"/g, '');
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
  return { ok: true, status: res.status, data: { filename } };
}

// ---- 模型 ----
export const modelApi = {
  get: () => req('/api/model'),
  set: (model) => req('/api/model', { method: 'POST', ...jsonBody({ model }) }),
  addProvider: (body) => req('/api/model/provider', { method: 'POST', ...jsonBody(body) }),
  remove: (key) => req(`/api/model/${encodeURIComponent(key)}`, { method: 'DELETE' }),
  discover: (base_url, api_key) =>
    req('/api/model/discover', { method: 'POST', ...jsonBody({ base_url, api_key }) }),
};

// ---- 内置服务商预设 (bootstrap catalog) ----
// GET /api/bootstrap/providers → { providers:[{key,label,description,base_url,default_model,env_key,provider}] }
// POST /api/bootstrap/test → { ok, ... } (仅支持 catalog 预设做连通性测试)
export const bootstrapApi = {
  providers: () => req('/api/bootstrap/providers'),
  test: (body) => req('/api/bootstrap/test', { method: 'POST', ...jsonBody(body) }),
};

// ---- 视觉模型 ----
export const visionApi = {
  get: () => req('/api/vision/config'),
  set: (body) => req('/api/vision/config', { method: 'POST', ...jsonBody(body) }),
};

// ---- 通用设置 (schema 驱动) ----
export const settingsApi = {
  schema: () => req('/api/schema'),
  get: () => req('/api/settings'),
  save: (values) => req('/api/settings', { method: 'POST', ...jsonBody({ values }) }),
};

// ---- 微信账号 ----
export const wechatApi = {
  list: () => req('/api/wechat/accounts'),
  add: (body) => req('/api/wechat/accounts', { method: 'POST', ...jsonBody(body) }),
  edit: (id, body) => req(`/api/wechat/accounts/${encodeURIComponent(id)}`, { method: 'PATCH', ...jsonBody(body) }),
  remove: (id) => req(`/api/wechat/accounts/${encodeURIComponent(id)}`, { method: 'DELETE' }),
  logout: (account_id) =>
    req(`/api/wechat/logout/${encodeURIComponent(account_id)}`, { method: 'POST' }),
  qrcodeUrl: (id) => `/api/wechat/login/${encodeURIComponent(id)}/qrcode`,
};

// ---- MCP ----
export const mcpApi = {
  list: () => req('/api/mcp/servers'),
  add: (body) => req('/api/mcp/servers', { method: 'POST', ...jsonBody(body) }),
  edit: (name, body) => req(`/api/mcp/servers/${encodeURIComponent(name)}`, { method: 'PUT', ...jsonBody(body) }),
  remove: (name) => req(`/api/mcp/servers/${encodeURIComponent(name)}`, { method: 'DELETE' }),
  action: (name, action) =>
    req(`/api/mcp/servers/${encodeURIComponent(name)}/${action}`, { method: 'POST' }),
  tools: (name) => req(`/api/mcp/servers/${encodeURIComponent(name)}/tools`),
};

// ---- 插件 ----
export const pluginsApi = {
  list: () => req('/api/plugins'),
};

// ---- 朋友圈自动发布 ----
export const momentsApi = {
  config: () => req('/api/moments/auto/config'),
  save: (body) => req('/api/moments/auto/config', { method: 'PUT', ...jsonBody(body) }),
  publish: () => req('/api/moments/auto/publish', { method: 'POST' }),
};

// ---- 语音服务商 (TTS) ----
export const voiceApi = {
  list: () => req('/api/voice-providers'),
  add: (body) => req('/api/voice-providers', { method: 'POST', ...jsonBody(body) }),
  edit: (name, body) => req(`/api/voice-providers/${encodeURIComponent(name)}`, { method: 'PUT', ...jsonBody(body) }),
  remove: (name) => req(`/api/voice-providers/${encodeURIComponent(name)}`, { method: 'DELETE' }),
  test: (name) => req(`/api/voice-providers/${encodeURIComponent(name)}/test`, { method: 'POST' }),
  synthesizeUrl: (text, voice) => {
    const p = new URLSearchParams();
    if (text) p.set('text', text);
    if (voice) p.set('voice', voice);
    return `/api/audio/synthesize?${p.toString()}`;
  },
};

// ---- 诊断 / 备份 / 恢复 / 关于 ----
export const diagApi = {
  report: () => req('/api/diagnostics'),
  export: () => download('/api/diagnostics/export'),
  backup: () => download('/api/backup'),
  restore: (file) => {
    const fd = new FormData();
    fd.append('backup', file);
    return fetch('/api/restore', { method: 'POST', body: fd })
      .then((res) => res.json().catch(() => null).then((data) => ({ ok: res.ok, status: res.status, data })));
  },
  about: () => req('/api/about'),
};

export { download };
