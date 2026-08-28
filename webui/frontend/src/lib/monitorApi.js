// ============================================================
// lib/monitorApi.js — 系统监控子页专用后端接口封装
//
// 只消费两个现有只读端点, 不加任何后端新端点:
//   GET /api/health      -> { ok, models, mcp_servers, runtime:{ uptime_seconds, operations } }
//   GET /api/diagnostics -> { generated_at, overall, summary:{ok,warn,error}, checks:[...] }
// 返回统一 { ok, status, data } 结构 (与 settingsApi.js 的 req 一致)。
// 后端不可达时 ok=false 且不 throw, 由页面做可用性兜底。
// ============================================================

const JSON_HEADERS = { accept: 'application/json' };

async function req(resource) {
  try {
    const res = await fetch(resource, { headers: JSON_HEADERS });
    const data = await res.json().catch(() => null);
    return { ok: res.ok, status: res.status, data };
  } catch (err) {
    // 网络层失败 (后端不可达 / CORS / 断网), 不抛异常
    return { ok: false, status: null, data: null, error: String(err && err.message ? err.message : err) };
  }
}

export const monitorApi = {
  health: () => req('/api/health'),
  diagnostics: () => req('/api/diagnostics'),
};
