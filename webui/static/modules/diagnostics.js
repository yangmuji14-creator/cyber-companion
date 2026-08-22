/* ===== diagnostics.js - 本地诊断中心 ===== */
import { toast, userFacingError } from './ui.js';

const STATUS_META = {
  ok: { symbol: "✓", label: "正常" },
  warn: { symbol: "!", label: "需注意" },
  error: { symbol: "×", label: "异常" },
};

export function renderDiagnosticReport(summary, list, report) {
  const counts = report?.summary || {};
  const overall = report?.overall in STATUS_META ? report.overall : "warn";
  const headline = overall === "ok"
    ? "所有检查均正常"
    : overall === "error"
      ? `发现 ${counts.error || 0} 项需要处理`
      : `检查完成，${counts.warn || 0} 项建议关注`;
  summary.className = `diagnostic-summary ${overall}`;
  summary.textContent = headline;
  list.replaceChildren();

  for (const check of report?.checks || []) {
    const status = check.status in STATUS_META ? check.status : "warn";
    const meta = STATUS_META[status];
    const row = document.createElement("article");
    row.className = `diagnostic-item ${status}`;
    const icon = document.createElement("span");
    icon.className = "diagnostic-icon";
    icon.textContent = meta.symbol;
    icon.setAttribute("aria-label", meta.label);
    const copy = document.createElement("div");
    const title = document.createElement("strong");
    title.textContent = check.label || "检查项";
    const message = document.createElement("p");
    message.textContent = check.message || "";
    copy.append(title, message);
    row.append(icon, copy);
    list.appendChild(row);
  }
}

export function initDiagnostics() {
  const runButton = document.getElementById("btn-diagnostics-run");
  const summary = document.getElementById("diagnostic-summary");
  const list = document.getElementById("diagnostic-list");
  const metrics = document.getElementById("runtime-metrics");
  if (!runButton || !summary || !list || runButton.dataset.bound === "1") return;
  runButton.dataset.bound = "1";
  runButton.addEventListener("click", async () => {
    runButton.disabled = true;
    summary.className = "diagnostic-summary running";
    summary.textContent = "正在检查本机状态…";
    try {
      const response = await fetch("/api/diagnostics", { cache: "no-store" });
      const report = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(report.error || `HTTP ${response.status}`);
      renderDiagnosticReport(summary, list, report);
      if (metrics) await renderRuntimeMetrics(metrics);
    } catch (error) {
      const message = userFacingError(error, "诊断暂时无法完成，请查看启动日志");
      summary.className = "diagnostic-summary error";
      summary.textContent = message;
      toast(message);
    } finally {
      runButton.disabled = false;
    }
  });
}

async function renderRuntimeMetrics(target) {
  try {
    const response = await fetch("/api/health", { cache: "no-store" });
    const health = await response.json();
    const operations = health.runtime?.operations || {};
    const values = Object.values(operations);
    const llm = operations["llm.stream"] || operations["llm.chat"] || {};
    const hit = values.reduce((sum, item) => sum + (item.cached_tokens || item.cache_read_input_tokens || 0), 0);
    const prompts = values.reduce((sum, item) => sum + (item.prompt_tokens || 0), 0);
    target.replaceChildren();
    const title = document.createElement("strong");
    title.textContent = "运行耗时与缓存";
    const detail = document.createElement("span");
    detail.textContent = `缓存命中率 ${prompts ? `${(hit / prompts * 100).toFixed(1)}%` : "暂无数据"} · 首 token ${llm.avg_ttft_ms != null ? `${llm.avg_ttft_ms.toFixed(0)} ms` : "暂无数据"} · 平均响应 ${llm.avg_ms != null ? `${llm.avg_ms.toFixed(0)} ms` : "暂无数据"}`;
    target.append(title, detail);
  } catch (_) {
    target.textContent = "运行指标暂不可用";
  }
}
