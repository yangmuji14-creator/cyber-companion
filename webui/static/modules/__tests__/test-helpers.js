import { vi } from "vitest";

export function installDom() {
  document.body.innerHTML = `
    <div id="messages"><div id="chat-welcome"></div></div>
    <textarea id="input"></textarea>
    <button id="btn-send"></button>
    <button id="btn-stop" hidden disabled></button>
    <div id="conn-status"></div>
    <div id="persona-name"></div>
    <div id="avatar">AI</div>
    <div id="toast" hidden></div>
    <button id="btn-voice"></button>
    <section id="voice-overlay" hidden></section>
    <span id="voice-timer"></span>
    <button id="voice-cancel"></button>
    <button id="voice-stop"></button>
    <button id="btn-diagnostics-run"></button>
    <div id="diagnostic-summary"></div>
    <div id="diagnostic-list"></div>
  `;
  globalThis.requestAnimationFrame = (callback) => {
    callback();
    return 1;
  };
}

export function sseResponse(reply = "测试回复") {
  const chunks = [new TextEncoder().encode(
    `event: done\ndata: ${JSON.stringify({ reply, level: 50 })}\n\n`,
  )];
  return {
    ok: true,
    status: 200,
    body: {
      getReader() {
        return {
          async read() {
            return chunks.length
              ? { done: false, value: chunks.shift() }
              : { done: true, value: undefined };
          },
        };
      },
    },
    async json() { return {}; },
  };
}

export async function settle() {
  await Promise.resolve();
  await Promise.resolve();
  await Promise.resolve();
}

export function installSuccessfulChatFetch(reply = "测试回复") {
  globalThis.fetch = vi.fn(async () => sseResponse(reply));
  return globalThis.fetch;
}
