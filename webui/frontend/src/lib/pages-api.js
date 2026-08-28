// ============================================================
// lib/pages-api.js — 通讯录/发现/记忆 三页共用的 fetch 封装 (独立, 不改 api.js)
// 仅服务这三个页面，不涉及聊天/设置。
// ============================================================

// 通用 JSON 请求: 返回 { ok, status, data }
export async function request(url, { method = 'GET', body, headers } = {}) {
  const opts = { method, headers: { accept: 'application/json', ...(headers || {}) } };
  if (body !== undefined) {
    opts.headers['content-type'] = 'application/json';
    opts.body = JSON.stringify(body);
  }
  const res = await fetch(url, opts);
  const data = await res.json().catch(() => null);
  return { ok: res.ok, status: res.status, data };
}

export async function get(url) {
  return request(url);
}

export async function post(url, body) {
  return request(url, { method: 'POST', body });
}

export async function del(url) {
  return request(url, { method: 'DELETE' });
}

// multipart 文件上传 (头像)
export async function postFile(url, file, field = 'file') {
  const fd = new FormData();
  fd.append(field, file);
  const res = await fetch(url, { method: 'POST', body: fd });
  const data = await res.json().catch(() => null);
  return { ok: res.ok, status: res.status, data };
}
