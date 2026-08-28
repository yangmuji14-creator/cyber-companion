// ============================================================
// lib/api.js — fetch 封装 (基础, 阶段2)
//
// 阶段2 只保留后端健康测试等基础能力。业务接口 (chat/contacts/
// memory/settings 的增删改查) 在阶段3 补全。
// ============================================================

const JSON_HEADERS = { accept: 'application/json' };

async function request(resource, options = {}) {
  const res = await fetch(resource, {
    headers: { ...JSON_HEADERS, ...(options.headers || {}) },
    ...options,
  });
  const json = await res.json().catch(() => null);
  return { ok: res.ok, status: res.status, data: json };
}

// 后端健康检查: GET /api/health
export async function fetchHealth() {
  return request('/api/health');
}

// 统一便捷封装 (阶段3 业务接口扩展点)
export const api = {
  health: fetchHealth,
  // get:  (url) => request(url),
  // post: (url, body) => request(url, { method:'POST', body: JSON.stringify(body), headers:{'content-type':'application/json'} }),
  // put:  ...,
  // del:  ...,
};

export default api;
