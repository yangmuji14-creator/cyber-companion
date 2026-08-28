// ============================================================
// lib/chatStream.js — POST /api/chat 的 SSE 手写流解析 (零依赖)
//
// POST 不能用 EventSource, 必须 fetch + resp.body.getReader() 手写
// 解析 SSE。后端事件格式: `event: <name>\ndata: <json>\n\n`
//
// 用法:
//   const stream = chatStream({
//     body: {content, conversation_id, persona_id},
//     onToken, onPhase, onReasoning, onSticker, onDone, onError,
//     signal,
//   });
//   stream.abort()  // 组件卸载/换会话时中断
// ============================================================

const decoder = new TextDecoder();

/**
 * 启动一次流式聊天。
 * @param {object} opts
 *  - body: {content, conversation_id?, persona_id?}
 *  - onToken({token})        主渲染流
 *  - onPhase({name,label})
 *  - onReasoning({text})
 *  - onSticker({pack,emotion,filename,url})
 *  - onDone({reply,level,voice_url})
 *  - onError({error})
 *  - signal: 外部 AbortSignal (与内部 controller 合并中断)
 * @returns {{ signal: AbortSignal, abort: () => void }}
 */
export function chatStream(opts) {
  const {
    body,
    onToken,
    onPhase,
    onReasoning,
    onSticker,
    onDone,
    onError,
    signal,
  } = opts || {};

  const controller = new AbortController();
  const external = signal;
  let sawToken = false;
  let gotTerminal = false; // 收到 done 或 error

  const abort = () => controller.abort();
  if (external) {
    if (external.aborted) abort();
    else external.addEventListener('abort', abort, { once: true });
  }

  function dispatch(ev) {
    const d = ev.data || {};
    switch (ev.event) {
      case 'token':
        sawToken = true;
        onToken?.({ token: String(d.token ?? '') });
        break;
      case 'phase':
        onPhase?.({ name: d.name, label: d.label });
        break;
      case 'reasoning':
        onReasoning?.({ text: d.text ?? '' });
        break;
      case 'sticker':
        onSticker?.({
          pack: d.pack,
          emotion: d.emotion,
          filename: d.filename,
          url: d.url,
        });
        break;
      case 'done':
        gotTerminal = true;
        onDone?.({ reply: d.reply, level: d.level, voice_url: d.voice_url });
        break;
      case 'error':
        gotTerminal = true;
        onError?.({ error: d.error || '生成失败' });
        break;
      default:
        break;
    }
  }

  // 按空行切事件块, 解析后返回未消费的残余缓冲
  function feed(text) {
    let rest = text;
    let idx;
    while ((idx = rest.indexOf('\n\n')) !== -1) {
      const block = rest.slice(0, idx);
      rest = rest.slice(idx + 2);
      const ev = parseBlock(block);
      if (ev) dispatch(ev);
    }
    return rest;
  }

  (async () => {
    let res;
    try {
      res = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'content-type': 'application/json', accept: 'text/event-stream' },
        body: JSON.stringify(body || {}),
        signal: controller.signal,
      });
    } catch (e) {
      if (e.name === 'AbortError') return;
      onError?.({ error: '网络请求失败，请检查后端是否启动' });
      return;
    }

    if (!res.ok || !res.body) {
      let msg = `请求失败 (${res.status})`;
      try {
        const j = await res.json();
        if (j?.error) msg = j.error;
      } catch {
        /* ignore */
      }
      onError?.({ error: msg });
      return;
    }

    const reader = res.body.getReader();
    let buffer = '';

    try {
      for (;;) {
        const { value, done } = await reader.read();
        if (controller.signal.aborted) return;
        if (done) break;
        buffer = feed(buffer + decoder.decode(value, { stream: true }));
      }
      // 收尾: flush decoder + 残余缓冲（服务端无 done 直接断开时的兜底）
      buffer = feed(buffer + decoder.decode());
    } catch (e) {
      if (e.name === 'AbortError') return;
      onError?.({ error: '连接中断，回复不完整' });
    }
  })();

  return { signal: controller.signal, abort };
}

function parseBlock(block) {
  let eventName = 'message';
  const dataLines = [];
  for (const line of block.split('\n')) {
    if (line.startsWith('event:')) {
      eventName = line.slice('event:'.length).trim();
    } else if (line.startsWith('data:')) {
      dataLines.push(line.slice('data:'.length).trim());
    }
  }
  if (dataLines.length === 0) return null;
  const dataText = dataLines.join('\n');
  let data = null;
  try {
    data = JSON.parse(dataText);
  } catch {
    data = { raw: dataText };
  }
  return { event: eventName, data };
}
