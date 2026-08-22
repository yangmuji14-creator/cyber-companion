import { beforeEach, afterEach, describe, expect, it, vi } from "vitest";
import { installDom, installSuccessfulChatFetch, settle } from "./test-helpers.js";

describe("Web chat batching", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.resetModules();
    installDom();
  });

  afterEach(() => {
    vi.useRealTimers();
    delete globalThis.fetch;
  });

  it("merges consecutive messages into one request after the quiet window", async () => {
    const fetchMock = installSuccessfulChatFetch("合并完成");
    const { state, dom } = await import("../state.js");
    const { sendMessage } = await import("../chat-stream.js");
    state.values = { debounce_seconds: 3 };
    state.activeConversationId = "conversation-a";

    dom.input.value = "第一句";
    sendMessage();
    dom.input.value = "第二句";
    sendMessage();

    expect(document.querySelectorAll(".row.me")).toHaveLength(2);
    await vi.advanceTimersByTimeAsync(2999);
    expect(fetchMock).not.toHaveBeenCalled();
    await vi.advanceTimersByTimeAsync(1);
    await settle();

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const request = JSON.parse(fetchMock.mock.calls[0][1].body);
    expect(request).toEqual({
      content: "第一句\n第二句",
      conversation_id: "conversation-a",
    });
    expect(document.querySelector(".row.ai .bubble").textContent).toBe("合并完成");
  });

  it("stops a batch while it is still waiting", async () => {
    const fetchMock = installSuccessfulChatFetch();
    const { state, dom } = await import("../state.js");
    const { sendMessage, stopMessageGeneration } = await import("../chat-stream.js");
    state.values = { debounce_seconds: 3 };

    dom.input.value = "不要发送";
    sendMessage();
    stopMessageGeneration();
    await vi.advanceTimersByTimeAsync(3000);

    expect(fetchMock).not.toHaveBeenCalled();
    expect(state.sending).toBe(false);
    expect(dom.stop.hidden).toBe(true);
  });

  it("cancels the old batch when the conversation changes", async () => {
    const fetchMock = installSuccessfulChatFetch();
    const { state, dom } = await import("../state.js");
    const { sendMessage } = await import("../chat-stream.js");
    state.values = { debounce_seconds: 3 };
    state.activeConversationId = "old";

    dom.input.value = "旧会话消息";
    sendMessage();
    window.dispatchEvent(new Event("chat-cancel-pending"));
    state.activeConversationId = "new";
    await vi.advanceTimersByTimeAsync(3000);

    expect(fetchMock).not.toHaveBeenCalled();
    expect(state.sending).toBe(false);
  });

  it("keeps reasoning and tool activity collapsed while answer tokens stream", async () => {
    const payload = [
      `event: phase\ndata: ${JSON.stringify({ name: "thinking", label: "正在思考" })}\n\n`,
      `event: reasoning\ndata: ${JSON.stringify({ text: "分析上下文" })}\n\n`,
      `event: token\ndata: ${JSON.stringify({ token: "流式回答" })}\n\n`,
      `event: done\ndata: ${JSON.stringify({ reply: "流式回答", level: 50 })}\n\n`,
    ].join("");
    const chunks = [new TextEncoder().encode(payload)];
    globalThis.fetch = vi.fn(async () => ({
      ok: true,
      status: 200,
      body: { getReader: () => ({ read: async () => chunks.length
        ? { done: false, value: chunks.shift() }
        : { done: true } }) },
      json: async () => ({}),
    }));
    const { state, dom } = await import("../state.js");
    const { sendMessage } = await import("../chat-stream.js");
    state.values = { debounce_seconds: 0 };
    dom.input.value = "测试流式状态";
    sendMessage();
    await vi.runAllTimersAsync();
    await settle();

    expect(document.querySelector(".answer-text").textContent).toBe("流式回答");
    const activity = document.querySelector(".activity-details");
    expect(activity.open).toBe(false);
    expect(activity.textContent).toContain("分析上下文");
    expect(activity.classList.contains("activity-running")).toBe(false);
  });
});
