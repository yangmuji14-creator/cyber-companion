// ============================================================
// lib/format.js — 时间/日期格式化小工具 (仅三页共用)
// ============================================================

// 输入后端常见时间串 (ISO 或 'YYYY-MM-DD HH:MM:SS') -> 相对/友好时间
export function friendlyTime(input) {
  if (!input) return '';
  let ts;
  const d = new Date(input);
  ts = Number.isNaN(d.getTime()) ? null : d.getTime();
  if (ts == null) {
    // 退化: 尝试把 'YYYY-MM-DD HH:MM' 手动解析
    const m = /(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2})?/.exec(String(input));
    if (m) ts = new Date(+m[1], +m[2] - 1, +m[3], +(m[4] || 0), +(m[5] || 0)).getTime();
    else return String(input);
  }

  const now = Date.now();
  const diff = Math.max(0, now - ts);
  const min = 60 * 1000;
  const hour = 60 * min;
  const day = 24 * hour;

  if (diff < min) return '刚刚';
  if (diff < hour) return `${Math.floor(diff / min)} 分钟前`;
  if (diff < day) return `${Math.floor(diff / hour)} 小时前`;
  if (diff < 7 * day) return `${Math.floor(diff / day)} 天前`;

  const dt = new Date(ts);
  const pad = (n) => String(n).padStart(2, '0');
  return `${dt.getFullYear()}-${pad(dt.getMonth() + 1)}-${pad(dt.getDate())} ${pad(dt.getHours())}:${pad(dt.getMinutes())}`;
}

// 纯日期 YYYY-MM-DD
export function dateOnly(input) {
  if (!input) return '';
  const d = new Date(input);
  if (Number.isNaN(d.getTime())) return String(input);
  const pad = (n) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}
