/* ===== voice-tts.test.js — 语音回复气泡 + 语音服务商子页 ===== */
import { describe, it, expect, beforeEach, beforeAll, vi } from "vitest";

beforeAll(() => {
  // jsdom 无原生 audio：polyfill play/pause 为可控 promise
  if (typeof HTMLMediaElement !== "undefined") {
    HTMLMediaElement.prototype.play = vi.fn(() => Promise.resolve());
    HTMLMediaElement.prototype.pause = vi.fn(() => {});
    HTMLMediaElement.prototype.load = vi.fn(() => {});
  }
  Object.defineProperty(HTMLMediaElement.prototype, "duration", {
    get: () => 3,
    set: () => {},
  });
});

async function installDom() {
  document.body.innerHTML = `
    <div id="container"></div>
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

describe("voice-bubble", () => {
  let el;
  beforeEach(async () => {
    await installDom();
    el = await import("../voice-bubble.js");
  });

  it("renders a playable voice bubble with audio element", () => {
    const container = document.getElementById("container");
    el.appendVoiceBubble(container, "/api/audio/x/1.mp3");
    const bubble = container.querySelector(".voice-bubble");
    expect(bubble).toBeTruthy();
    expect(bubble.querySelector(".voice-play").textContent).toBe("▶");
    expect(bubble.querySelector(".voice-waves").children.length).toBeGreaterThan(3);
    const audio = bubble.querySelector("audio");
    expect(audio.src).toContain("/api/audio/x/1.mp3");
    expect(bubble.dataset.playing).toBe("0");
  });

  it("click toggles play/pause via audio", async () => {
    const container = document.getElementById("container");
    el.appendVoiceBubble(container, "/api/audio/x/1.mp3");
    const bubble = container.querySelector(".voice-bubble");
    bubble.click();
    await Promise.resolve();
    expect(bubble.dataset.playing).toBe("1");
    expect(HTMLMediaElement.prototype.play).toHaveBeenCalled();
    bubble.click();
    expect(HTMLMediaElement.prototype.pause).toHaveBeenCalled();
    expect(bubble.dataset.playing).toBe("0");
  });
});

describe("voice-providers-page", () => {
  let mod;
  beforeEach(async () => {
    await installDom();
    mockFetch({
      "GET /api/voice-providers": {
        providers: [
          { name: "mytts", type: "openai", model: "tts-1", voice: "nova", enabled: true, has_api_key: true },
        ],
        active: "mytts",
      },
    });
    mod = await import("../voice-providers-page.js");
  });

  it("lists providers from the endpoint", async () => {
    await mod.renderVoiceProvidersPage(document.getElementById("container"));
    const container = document.getElementById("container");
    expect(container.querySelector(".vp2-title").textContent).toContain("语音服务商");
    expect(container.querySelector(".vp2-pname").textContent).toBe("mytts");
    const row = container.querySelector(".vp2-prow");
    expect(row.querySelector(".vp2-pstate").textContent).toContain("启用中");
    // 行内应有 测试/试听/编辑/删除 按钮
    const buttons = row.querySelectorAll("button");
    const labels = Array.from(buttons).map((b) => b.textContent);
    expect(labels).toContain("测试");
    expect(labels).toContain("试听");
    expect(labels).toContain("编辑");
    expect(labels).toContain("删除");
  });
});
