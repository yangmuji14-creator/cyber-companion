import { beforeEach, afterEach, describe, expect, it, vi } from "vitest";
import { installDom, installSuccessfulChatFetch, settle } from "./test-helpers.js";

describe("Web voice input", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.resetModules();
    installDom();
  });

  afterEach(() => {
    vi.useRealTimers();
    delete window.SpeechRecognition;
    delete window.webkitSpeechRecognition;
    delete globalThis.fetch;
  });

  it("feeds browser speech recognition into the normal text batching path", async () => {
    const fetchMock = installSuccessfulChatFetch("听到了");
    class Recognition {
      static instance = null;
      constructor() { Recognition.instance = this; }
      start() { this.onstart?.(); }
      stop() { this.onend?.(); }
      abort() { this.onerror?.({ error: "aborted" }); this.onend?.(); }
    }
    window.SpeechRecognition = Recognition;
    const { state } = await import("../state.js");
    const { startVoice } = await import("../upload.js");
    state.values = { debounce_seconds: 0 };

    await startVoice();
    Recognition.instance.onresult({ results: [{ 0: { transcript: "语音内容" } }] });
    Recognition.instance.onend();
    await vi.runAllTimersAsync();
    await settle();

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const request = JSON.parse(fetchMock.mock.calls[0][1].body);
    expect(request.content).toBe("语音内容");
    expect(document.querySelector(".row.me .bubble").textContent).toBe("语音内容");
  });
});
