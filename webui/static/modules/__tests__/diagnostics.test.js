import { beforeEach, describe, expect, it, vi } from "vitest";
import { installDom } from "./test-helpers.js";

describe("Diagnostics UI", () => {
  beforeEach(() => {
    vi.resetModules();
    installDom();
  });

  it("renders a concise summary and individual statuses", async () => {
    const { renderDiagnosticReport } = await import("../diagnostics.js");
    const summary = document.getElementById("diagnostic-summary");
    const list = document.getElementById("diagnostic-list");

    renderDiagnosticReport(summary, list, {
      overall: "warn",
      summary: { ok: 1, warn: 1, error: 0 },
      checks: [
        { id: "database", label: "本地数据库", status: "ok", message: "完整性正常" },
        { id: "vision", label: "图片识别", status: "warn", message: "需要配置视觉模型" },
      ],
    });

    expect(summary.textContent).toContain("1 项建议关注");
    expect(summary.classList.contains("warn")).toBe(true);
    expect(list.querySelectorAll(".diagnostic-item")).toHaveLength(2);
    expect(list.textContent).toContain("需要配置视觉模型");
  });
});
