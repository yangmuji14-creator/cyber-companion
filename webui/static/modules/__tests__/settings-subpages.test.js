/* ===== settings-subpages.test.js — 插件 / 朋友圈自动发布子页 ===== */
import { describe, it, expect, beforeEach, vi } from "vitest";

async function installDom() {
  document.body.innerHTML = `
    <div id="tab-content-plugins" class="settings-tab-content" data-tab="plugins"></div>
    <div id="tab-content-auto-moments" class="settings-tab-content" data-tab="auto-moments"></div>
    <div id="toast" hidden></div>
  `;
}

function mockFetch(routes) {
  globalThis.fetch = vi.fn(async (url, opts = {}) => {
    const method = (opts.method || "GET").toUpperCase();
    const key = `${method} ${url}`;
    const hit = routes[key] || routes[url];
    if (!hit) return { ok: false, status: 404, async json() { return { error: "not found" }; } };
    if (typeof hit === "function") return hit(opts);
    return { ok: true, status: 200, async json() { return hit; } };
  });
}

describe("plugins-page", () => {
  let mod;
  beforeEach(async () => {
    await installDom();
    mockFetch({
      "GET /api/plugins": {
        plugins: [
          { source: "builtin", name: "clock", description: "查时间", parameters: { type: "object", properties: {}, required: [] } },
          { source: "mcp", name: "search", description: "搜索", server: "web" },
        ],
        builtin_count: 1,
        mcp_count: 1,
        mcp_status: { connected: 0 },
      },
    });
    mod = await import("../plugins-page.js");
  });

  it("renders builtin + mcp tool cards", async () => {
    await mod.renderPluginsPage();
    const container = document.getElementById("tab-content-plugins");
    expect(container.querySelector(".plug-title").textContent).toContain("插件");
    const names = Array.from(container.querySelectorAll(".plug-card-name")).map((n) => n.textContent);
    expect(names).toContain("clock");
    expect(names).toContain("search");
    const badges = Array.from(container.querySelectorAll(".plug-badge")).map((b) => b.textContent);
    expect(badges).toContain("内置");
    expect(badges.some((b) => b === "web" || b === "MCP")).toBe(true);
  });
});

describe("auto-moments-page", () => {
  let mod;
  beforeEach(async () => {
    await installDom();
    mockFetch({
      "GET /api/moments/auto/config": {
        config: { enabled: false, interval_minutes: 180, persona_id: "", active_start: 8, active_end: 22 },
        personas: [{ id: "test_001", name: "小慕" }],
      },
    });
    mod = await import("../auto-moments-page.js");
  });

  it("renders config and persona options", async () => {
    await mod.renderAutoMomentsPage();
    const container = document.getElementById("tab-content-auto-moments");
    expect(container.querySelector(".am-title").textContent).toContain("朋友圈");
    const personaSelect = container.querySelector("select");
    const labels = Array.from(personaSelect.options).map((o) => o.textContent);
    expect(labels).toContain("小慕");
    const interval = container.querySelector('input[type="number"]');
    expect(interval.value).toBe("180");
  });

  it("saves config via PUT with selected persona", async () => {
    let putBody = null;
    mockFetch({
      "GET /api/moments/auto/config": {
        config: { enabled: false, interval_minutes: 180, persona_id: "", active_start: 8, active_end: 22 },
        personas: [{ id: "test_001", name: "小慕" }],
      },
      "PUT /api/moments/auto/config": (opts) => {
        putBody = JSON.parse(opts.body);
        return { ok: true, status: 200, async json() { return { ok: true, config: putBody }; } };
      },
    });
    await mod.renderAutoMomentsPage();
    const container = document.getElementById("tab-content-auto-moments");
    // enable + pick persona + set interval
    container.querySelector(".am-check input").click();
    const personaSelect = container.querySelector("select");
    personaSelect.value = "test_001";
    const interval = container.querySelector('input[type="number"]');
    interval.value = "60";
    container.querySelector(".primary-btn").click();
    await Promise.resolve(); await Promise.resolve();
    expect(putBody.enabled).toBe(true);
    expect(putBody.persona_id).toBe("test_001");
    expect(putBody.interval_minutes).toBe(60);
  });
});
