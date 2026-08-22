import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { settle } from "./test-helpers.js";

function response(payload) {
  return {
    ok: true,
    status: 200,
    async json() { return payload; },
  };
}

describe("account role and persona memory UI", () => {
  beforeEach(() => {
    vi.resetModules();
    document.body.innerHTML = '<div id="toast" hidden></div>';
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("updates the role assigned to a WeChat account", async () => {
    document.body.insertAdjacentHTML(
      "beforeend",
      '<section class="settings-tab-content" data-tab="wechat_accounts"></section>',
    );
    globalThis.fetch = vi.fn(async (url, options = {}) => {
      if (url === "/api/wechat/accounts" && !options.method) {
        return response([{ id: "acc1", persona_id: "role_a", has_credentials: false }]);
      }
      if (url === "/api/persona") {
        return response([
          { id: "role_a", name: "角色 A" },
          { id: "role_b", name: "角色 B" },
        ]);
      }
      if (url === "/api/wechat/accounts/acc1" && options.method === "PATCH") {
        return response({ ok: true, persona_id: "role_b" });
      }
      throw new Error(`unexpected request: ${url}`);
    });

    const module = await import("../wechat-accounts.js");
    await module.initWechatAccounts();
    const select = document.querySelector(".account-role select");
    expect(select.value).toBe("role_a");

    select.value = "role_b";
    select.dispatchEvent(new Event("change"));
    await settle();

    const patchCall = globalThis.fetch.mock.calls.find(([, options]) => options?.method === "PATCH");
    expect(patchCall[0]).toBe("/api/wechat/accounts/acc1");
    expect(JSON.parse(patchCall[1].body)).toEqual({ persona_id: "role_b" });
    module.destroyWechatAccounts();
  });

  it("keeps persona scope when opening the first-person diary", async () => {
    document.body.insertAdjacentHTML("beforeend", `
      <section id="page-chat" class="page active"></section>
      <section id="page-memory" class="page" hidden>
        <div class="memory-subtabs">
          <button class="memory-subtab" data-subtab="important"></button>
          <button class="memory-subtab" data-subtab="diary"></button>
        </div>
        <div id="memory-list-container"></div>
        <div id="memory-detail-container"></div>
      </section>
      <section id="page-settings" class="page" hidden></section>
    `);
    globalThis.fetch = vi.fn(async (url) => {
      if (String(url).startsWith("/api/life_summary")) {
        return response({ summaries: [], total: 0 });
      }
      if (String(url).startsWith("/api/memory")) {
        return response({ messages: [], total: 0 });
      }
      throw new Error(`unexpected request: ${url}`);
    });

    const module = await import("../memory-page.js");
    await module.openMemoryPage({ tab: "diary", personaId: "role_b" });

    const diaryCalls = globalThis.fetch.mock.calls
      .map(([url]) => String(url))
      .filter((url) => url.startsWith("/api/life_summary"));
    expect(diaryCalls.length).toBeGreaterThan(0);
    expect(diaryCalls.every((url) => url.includes("persona_id=role_b"))).toBe(true);
    expect(document.querySelector('[data-subtab="diary"]').classList.contains("active")).toBe(true);
  });
});
