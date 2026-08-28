<script>
  // ChatPage.svelte — 聊天页（完整业务逻辑）
  // Svelte 5 runes。消费后端 /api/* 契约 (见 lib/chatApi.js), SSE 流式见 lib/chatStream.js。  // 只改本文件 + 自己的 lib 模块; 不动后端/全局结构/其它页面。
  import {
    listConversations,
    createConversation,
    updateConversation,
    deleteConversation,
    fetchHistory,
    listPersonas,
    listStickers,
    uploadImage,
    uploadVoice,
  } from '../lib/chatApi.js';
  import { chatStream } from '../lib/chatStream.js';
  import { monitorApi } from '../lib/monitorApi.js';
  import { navigate } from '../lib/router.js';
  import { confirmDialog, promptDialog } from '../lib/dialog.svelte.js';
  import ConfigNotice from '../components/ConfigNotice.svelte';

  // 后端将配置缺失/出错"包装成 done 事件的友好文案，命中即渲染为配置提示卡片而非普通气泡。
  const CONFIG_ERROR_TEXTS = [
    '我还没配置好模型呢',
    'API key 好像有问题',
    '模型太忙了',
    '网络有点慢',
    '网络好像断了',
    '出了点小问题',
    '我找不到我的人设了',
  ];
  function isConfigErrorText(reply) {
    const t = String(reply ?? '');
    if (!t) return false;
    return CONFIG_ERROR_TEXTS.some((k) => t.includes(k));
  }

  // ---------- 后端数据 (会话/人设/贴纸) ----------
  let conversations = $state([]);
  let personas = $state([]);
  let stickerGroups = $state([]); // [{pack,emotion,images:[]}]

  // ---------- 界面状态 ----------
  let activeConvId = $state(null);
  let messages = $state([]); // [{role,content,timestamp,sticker?,voice_url?,streaming?}]
  let loadingHistory = $state(false);

  let input = $state('');
  let sending = $state(false);
  let phase = $state(null); // {name,label}
  let reasoning = $state(''); // 思考面板缓存
  let thinkingOpen = $state(false);

  let error = $state(null); // toast
  let toastTimer = null;

  // 模型/服务商配置就绪状态 null=检测中, true=已就绪(models>0), false=未配置(Key 无效
  let modelReady = $state(null);
  let modelChecking = $state(false);

  let showStickerPanel = $state(false);
  let showImagePanel = $state(false);
  let pickedImage = $state(null); // {file, url}
  let imageCaption = $state('');
  let uploading = $state(false);

  let recording = $state(false);
  let recorder = null;
  let recordChunks = [];

  // 会话抽屉 (移动端
  let listOpen = $state(false);
  let isMobile = $state(false);

  // 最近一次流式stream 句柄 (换会话时发新消息/卸载时 abort)
  let agentStream = null;
  let unmountAbort = new AbortController();

  // 滚动锚点
  let messagesEl = $state(null);
  let bottomEl = $state(null);

  // ---------- 派生 ----------
  let activeConv = $derived(
    activeConvId ? conversations.find((c) => c.conversation_id === activeConvId) ?? null : null,
  );
  let canSend = $derived(!sending && !uploading && input.trim().length > 0);
  let personaOfActive = $derived(activeConv?.persona_id ?? null);
  let activePersona = $derived(personas.find((p) => p.id === personaOfActive) ?? null);

  // ---------- 生命周期 ----------
  $effect(() => {
    const mq = window.matchMedia('(max-width: 767px)');
    const apply = () => (isMobile = mq.matches);
    apply();
    mq.addEventListener('change', apply);
    return () => mq.removeEventListener('change', apply);
  });

  $effect(() => {
    // 装载基础数据 + 检测模型配置
    let alive = true;
    loadAll();
    checkModelHealth();
    return () => {
      alive = false;
      unmountAbort.abort();
    };
    async function loadAll() {
      const results = await Promise.allSettled([listConversations(), listPersonas(), listStickers()]);
      if (!alive) return;
      const [convR, personaR, stickerR] = results;
      if (convR.status === 'fulfilled') conversations = convR.value;
      if (personaR.status === 'fulfilled') personas = personaR.value;
      if (stickerR.status === 'fulfilled') stickerGroups = stickerR.value;
    }
  });

  // 新消息 -> 滚到底部
  $effect(() => {
    if (!messagesEl || !bottomEl) return;
    const n = messages.length;
    const s = sending;
    if (n > 0 || s) bottomEl.scrollIntoView({ behavior: 'smooth', block: 'end' });
  });

  // ---------- 会话操作 ----------
  async function selectConversation(id) {
    if (id === activeConvId && messages.length > 0) return;
    abortStream();
    activeConvId = id;
    reasoning = '';
    phase = null;
    thinkingOpen = false;
    if (isMobile) listOpen = false;
    messages = [];
    loadingHistory = true;
    try {
      messages = await fetchHistory(id);
    } catch (e) {
      showError(e.message);
    } finally {
      loadingHistory = false;
    }
  }

  async function startWithPersona(persona_id) {
    // 复用已存在的同人设 web 会话, 否则新建
    const existing = conversations.find(
      (c) => c.persona_id === persona_id && c.platform === 'web',
    );
    if (existing) {
      showToast('已打开该会话');
      await selectConversation(existing.conversation_id);
      return;
    }
    try {
      const conv = await createConversation({ platform: 'web', persona_id });
      const fresh = await listConversations();
      conversations = fresh;
      await selectConversation(conv.conversation_id);
    } catch (e) {
      showError(e.message);
    }
  }

  async function newEmptyConversation() {
    // 新建会话：若有默认人设（或第一个人设）就打开其会话；后端按人设约束一个仅一个会话
    if (personas.length === 0) {
      showError('还没有可用的人设，请先在通讯录创建');
      return;
    }
    const persona = personas.find((p) => p.is_default) ?? personas[0];
    await startWithPersona(persona.id);
  }

  async function renameConversation(conv) {
    const title = await promptDialog('输入新的会话备注名（留空清除）', { title: '重命名会话', defaultValue: conv.title || '' });
    if (title === null) return;
    try {
      const updated = await updateConversation(conv.conversation_id, { title });
      conversations = conversations.map((c) =>
        c.conversation_id === updated.conversation_id ? updated : c,
      );
    } catch (e) {
      showError(e.message);
    }
  }

  async function removeConversation(conv) {
    const ok = await confirmDialog(`确定删除会话「${displayName(conv)}」？其历史消息也会清除。`, { title: '删除会话', danger: true });
    if (!ok) return;
    try {
      await deleteConversation(conv.conversation_id);
      conversations = conversations.filter((c) => c.conversation_id !== conv.conversation_id);
      if (activeConvId === conv.conversation_id) {
        abortStream();
        activeConvId = null;
        messages = [];
      }
    } catch (e) {
      showError(e.message);
    }
  }

  // ---------- 发送（SSE 流式） ----------
  function send() {
    const text = input.trim();
    if (!text || sending || uploading) return;
    // 主动守卫: 模型未配置时拦截发送，引导去配置
    if (modelReady !== true) {
      showError('请先配置对话模型，AI 才能回复');
      return;
    }
    pushUserMessage(text);
    input = '';
    reasoning = '';
    thinkingOpen = false;
    streamChat({ content: text });
  }

  function pushUserMessage(content, sticker) {
    messages = [
      ...messages,
      { role: 'user', content, timestamp: nowISO(), ...(sticker ? { sticker } : {}) },
    ];
  }

  function streamChat({ content, sticker } = {}) {
    if (!activeConvId) {
      // 无会话时自动建一个会话（用 body persona_id; 这里用默认）
      showError('请先选择一个会话');
      return;
    }
    abortStream();
    sending = true;
    phase = { name: 'context', label: '整理上下文' };

    // 先占用 assistant 气泡 (流式填充)
    messages = [...messages, { role: 'assistant', content: '', streaming: true, timestamp: nowISO() }];

    const body = { content, conversation_id: activeConvId };
    if (personaOfActive) body.persona_id = personaOfActive;
    if (sticker) body.sticker = sticker;

    const currentLen = messages.length;

    agentStream = chatStream({
      body,
      signal: unmountAbort.signal,
      onToken: ({ token }) => {
        messages = messages.map((m, i) => {
          if (i === currentLen - 1 && m.streaming) return { ...m, content: m.content + token };
          return m;
        });
      },
      onPhase: ({ name, label }) => {
        phase = { name, label };
      },
      onReasoning: ({ text }) => {
        reasoning += text;
        thinkingOpen = true;
      },
      onSticker: (stk) => {
        messages = messages.map((m, i) =>
          i === currentLen - 1 && m.streaming ? { ...m, sticker: stk } : m,
        );
      },
      onDone: ({ reply, voice_url }) => {
        const isConfig = isConfigErrorText(reply);
        messages = messages.map((m, i) => {
          if (i === currentLen - 1 && m.streaming) {
            return {
              ...m,
              content: reply ?? '',
              streaming: false,
              configError: isConfig || undefined,
              ...(voice_url ? { voice_url } : {}),
            };
          }
          return m;
        });
        finishStreaming();
        // 收到真实回复说明模型链路已通，顺带刷新一次配置状态
        if (!isConfig && modelReady !== true) checkModelHealth();
      },
      onError: ({ error: emsg }) => {
        messages = messages.map((m, i) =>
          i === currentLen - 1 && m.streaming ? { ...m, content: m.content || '', streaming: false } : m,
        );
        finishStreaming();
        showError(emsg);
      },
    });
  }

  function finishStreaming() {
    sending = false;
    phase = null;
    agentStream = null;
  }

  function abortStream() {
    if (agentStream) {
      agentStream.abort();
      agentStream = null;
    }
  }

  // ---------- 图片上传 ----------
  function pickImageFile(ev) {
    const f = ev.target.files?.[0];
    if (!f) return;
    const url = URL.createObjectURL(f);
    pickedImage = { file: f, url };
    imageCaption = '';
    showImagePanel = true;
    ev.target.value = '';
  }

  async function sendImage() {
    if (!pickedImage) return;
    if (!activeConvId) {
      showError('请先选择一个会话');
      return;
    }
    const file = pickedImage.file;
    const url = pickedImage.url;
    uploading = true;
    try {
      const { reply } = await uploadImage(file, {
        caption: imageCaption,
        conversation_id: activeConvId,
      });
      pushUserMessage('[发送了一张图片]' + (imageCaption ? ` ${imageCaption}` : ''));
      messages = [...messages, { role: 'assistant', content: reply ?? '', timestamp: nowISO() }];
    } catch (e) {
      showError(e.message);
    } finally {
      uploading = false;
      pickedImage = null;
      showImagePanel = false;
      imageCaption = '';
      if (url) URL.revokeObjectURL(url);
    }
  }

  // ---------- 语音上传 (MediaRecorder -> webm) ----------
  async function toggleRecord() {
    if (recording) {
      stopRecord();
      return;
    }
    if (!navigator.mediaDevices?.getUserMedia) {
      showError('当前浏览器不支持录音');
      return;
    }
    try {
      const streamRef = await navigator.mediaDevices.getUserMedia({ audio: true });
      recorder = new MediaRecorder(streamRef);
      recordChunks = [];
      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) recordChunks.push(e.data);
      };
      recorder.onstop = () => {
        streamRef.getTracks().forEach((t) => t.stop());
        const blob = new Blob(recordChunks, { type: 'audio/webm' });
        uploadRecorded(blob);
      };
      recorder.start();
      recording = true;
    } catch (e) {
      showError('无法访问麦克风：' + e.message);
    }
  }

  function stopRecord() {
    try {
      recorder?.stop();
    } catch {
      /* ignore */
    }
    recorder = null;
    recording = false;
  }

  async function uploadRecorded(blob) {
    if (!activeConvId) {
      showError('请先选择一个会话');
      return;
    }
    uploading = true;
    try {
      const file = new File([blob], `voice-${Date.now()}.webm`, { type: 'audio/webm' });
      const { transcript, reply } = await uploadVoice(file, { conversation_id: activeConvId });
      if (transcript) pushUserMessage(transcript);
      if (reply !== undefined)
        messages = [...messages, { role: 'assistant', content: reply ?? '', timestamp: nowISO() }];
    } catch (e) {
      showError(e.message);
    } finally {
      uploading = false;
    }
  }

  // ---------- 贴纸 ----------
  async function sendSticker(group, filename) {
    const sticker = {
      pack: group.pack,
      emotion: group.emotion,
      filename,
      url: stickerUrl(group.pack, group.emotion, filename),
    };
    if (!activeConvId) {
      showError('请先选择一个会话');
      return;
    }
    pushUserMessage('[表情]', sticker);
    showStickerPanel = false;
    streamChat({ content: `[表情:${group.emotion}]`, sticker: { pack: group.pack, emotion: group.emotion, filename } });
  }

  // ---------- 工具 ----------
  function nowISO() {
    return new Date().toISOString();
  }
  function formatTime(ts) {
    if (!ts) return '';
    const d = new Date(ts);
    if (Number.isNaN(d.getTime())) return '';
    const hh = String(d.getHours()).padStart(2, '0');
    const mm = String(d.getMinutes()).padStart(2, '0');
    return `${hh}:${mm}`;
  }
  function displayName(conv) {
    return conv.title || conv.persona_name || '未命名会话';
  }
  function stickerUrl(pack, emotion, filename) {
    return `/api/stickers/file/${encodeURIComponent(pack)}/${encodeURIComponent(emotion)}/${encodeURIComponent(filename)}`;
  }
  function initialOf(name) {
    return (name || '?').trim().slice(0, 1).toUpperCase();
  }
  function showError(msg) {
    error = msg;
    if (toastTimer) clearTimeout(toastTimer);
    toastTimer = setTimeout(() => (error = null), 4000);
  }

  // 中性轻提示（复用 toast 展示位，非错误样式）
  function showToast(msg) {
    error = msg;
    if (toastTimer) clearTimeout(toastTimer);
    toastTimer = setTimeout(() => (error = null), 2500);
  }

  // 主动守卫: 通过 /api/health 检测模型是否已配置 (models===0 => 未配置( Key 无效)
  async function checkModelHealth() {
    modelChecking = true;
    const r = await monitorApi.health();
    modelChecking = false;
    // health 权威信号: models 为后端实际成功加载的模型实例数 ===0 即未配置(Key 无效
    const models = r && r.data ? Number(r.data.models) : 0;
    modelReady = r.ok === true && models > 0;
  }

  // 去模型设置子页（如 banner / 配置卡按钮
  function gotoModelSettings() {
    navigate('settings/model');
  }
  function stopEvent(e) {
    e.stopPropagation();
  }

  // 会话行上右键/点按菜单 (零依赖 以定位弹层替代原生 prompt)
  let menuOpen = $state(null); // { conv, x, y }

  function rowMenu(e, conv) {
    stopEvent(e);
    // 用按钮位置定位菜单，避免溢出边界
    const rect = e.currentTarget.getBoundingClientRect();
    menuOpen = { conv, x: rect.right, y: rect.bottom + 4 };
  }

  function closeMenu() {
    menuOpen = null;
  }

  function menuRename(conv) {
    closeMenu();
    renameConversation(conv);
  }

  function menuDelete(conv) {
    closeMenu();
    removeConversation(conv);
  }

  // 点击菜单外部关闭
  $effect(() => {
    if (!menuOpen) return;
    const onDoc = (e) => {
      if (!e.target.closest('.convs-menu, .row-menu')) closeMenu();
    };
    const onScroll = () => closeMenu();
    document.addEventListener('pointerdown', onDoc);
    window.addEventListener('scroll', onScroll, true);
    window.addEventListener('resize', onScroll);
    return () => {
      document.removeEventListener('pointerdown', onDoc);
      window.removeEventListener('scroll', onScroll, true);
      window.removeEventListener('resize', onScroll);
    };
  });


  async function renameConversationWithText(conv, title) {
    try {
      const updated = await updateConversation(conv.conversation_id, { title });
      conversations = conversations.map((c) =>
        c.conversation_id === updated.conversation_id ? updated : c,
      );
    } catch (e) {
      showError(e.message);
    }
  }

  // 首次进入: 自动选中第一个会话(如有)
  $effect(() => {
    if (!loadingHistory && activeConvId === null && conversations.length > 0 && messages.length === 0) {
      selectConversation(conversations[0].conversation_id);
    }
  });
</script>

<div class="chat-page">
  {#snippet recheckButton()}
    <button class="config-recheck" type="button" onclick={checkModelHealth} disabled={modelChecking} title="重新检测">
      {modelChecking ? '检测中…' : '重新检测'}
    </button>
  {/snippet}

  {#if isMobile}
    <header class="mobile-head">
      <button class="icon-btn" onclick={() => (listOpen = true)} aria-label="会话列表" title="会话列表">
        <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M3 6h18M3 12h18M3 18h18"/></svg>
      </button>
      <span class="head-title">{activeConv ? displayName(activeConv) : '聊天'}</span>
      <button
        class="icon-btn" onclick={() => { if (activeConvId) renameConversation(activeConv); }}
        aria-label="重命名" title="重命名" disabled={!activeConvId}
      >
        <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17 3a2.85 2.83 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5Z"/></svg>
      </button>
    </header>
  {/if}

  <div class="chat-body">
    {#if !isMobile}
      <aside class="conv-panel">
        <div class="panel-head">
          <span class="panel-title">会话</span>
          <button class="add-btn" onclick={() => newEmptyConversation()} title="新建会话">
            <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M12 5v14M5 12h14"/></svg>
          </button>
        </div>
        <div class="conv-list">
          {#each conversations as conv}
            <button
              class="conv-row {conv.conversation_id === activeConvId ? 'is-active' : ''}"
              onclick={() => selectConversation(conv.conversation_id)}
            >
              <span class="conv-dot">{initialOf(displayName(conv))}</span>
              <span class="conv-meta">
                <span class="conv-name">{displayName(conv)}</span>
                <span class="conv-sub">{conv.platform === 'web' ? 'Web' : conv.platform}</span>
              </span>
              <span class="row-menu" onclick={(e) => rowMenu(e, conv)} role="button" tabindex="-1" title="操作" onkeydown={(e) => e.key === 'Enter' && rowMenu(e, conv)}>
                <svg viewBox="0 0 24 24" width="18" height="18" fill="currentColor"><circle cx="5" cy="12" r="1.6"/><circle cx="12" cy="12" r="1.6"/><circle cx="19" cy="12" r="1.6"/></svg>
              </span>
            </button>
          {/each}
          {#if conversations.length === 0}
            <div class="conv-empty">暂无会话</div>
          {/if}
        </div>

        <div class="panel-divider"></div>

        <div class="persona-panel">
          <span class="panel-title">人设</span>
          <div class="persona-row" role="listbox">
            {#each personas as p}
              <button class="persona-chip" title={p.name} onclick={() => startWithPersona(p.id)}>
                {#if p.avatar}
                  <img class="chip-avatar" src={p.avatar} alt={p.name} loading="lazy" />
                {:else}
                  <span class="chip-avatar chip-fallback">{initialOf(p.name)}</span>
                {/if}
                <span class="chip-name">{p.name}</span>
              </button>
            {/each}
          </div>
        </div>
      </aside>
    {/if}

    <section class="chat-stage">
      <!-- 消息列表 -->
      <div class="msgs" class:empty={!loadingHistory && messages.length === 0} bind:this={messagesEl}>
        {#if loadingHistory}
          <div class="center-hint">加载中…</div>
        {:else if messages.length === 0}
          <div class="welcome">
            <div class="welcome-mark" aria-hidden="true">
              <span class="brand-dot"></span>
            </div>
            <h2 class="welcome-title">{activeConv ? displayName(activeConv) : '聊天'}</h2>
            <p class="welcome-desc">
              {#if activeConv}
                和 {displayName(activeConv)} 打个招呼吧。可以发文字、图片或语音，也可以从左侧选择人设开启新对话。              {:else}
                选择一个会话或从"人设"开始对话。              {/if}
            </p>
            {#if personas.length > 0 && !activeConv}
              <div class="welcome-personas">
                {#each personas as p}
                  <button class="welcome-chip" onclick={() => startWithPersona(p.id)}>
                    {#if p.avatar}
                      <img class="chip-avatar" src={p.avatar} alt={p.name} />
                    {:else}
                      <span class="chip-avatar chip-fallback">{initialOf(p.name)}</span>
                    {/if}
                    <span>{p.name}</span>
                  </button>
                {/each}
              </div>
            {/if}
          </div>
        {:else}
          {#each messages as m, i (i)}
            {@const isUser = m.role === 'user'}
            {@const isStreaming = m.streaming === true}
            <div class="bubble-row {isUser ? 'self' : 'friend'}">
              {#if !isUser && !isStreaming}
                <span class="av">{initialOf(activePersona?.name ?? activeConv?.persona_name ?? 'AI')}</span>
              {/if}
              <div class="bubble-col">
                {#if m.sticker}
                  <div class="sticker-bubble">
                    <img class="sticker-img" src={m.sticker.url || stickerUrl(m.sticker.pack, m.sticker.emotion, m.sticker.filename)} alt="贴纸" loading="lazy" />
                  </div>
                {/if}
                {#if m.configError && !isUser && !isStreaming}
                  <ConfigNotice
                    variant="card"
                    tone="warning"
                    icon="key"
                    title="模型配置待处理"
                    text={m.content}
                    actionLabel="去设置配置"
                    onAction={gotoModelSettings}
                  />
                {:else if m.content}
                  <div class="bubble {isUser ? 'bubble-user' : 'bubble-ai'} {isStreaming ? 'is-streaming' : ''}">
                    <div class="bubble-text">{m.content}{#if isStreaming}<span class="caret"></span>{/if}</div>
                  </div>
                {/if}
                {#if m.voice_url}
                  <audio class="voice-player" controls preload="none" src={m.voice_url}></audio>
                {/if}
                <span class="bubble-time">{formatTime(m.timestamp)}</span>
              </div>
            </div>
          {/each}
          {#if reasoning}
            <details class="reasoning" open={thinkingOpen}>
              <summary>思考过程</summary>
              <div class="reasoning-body">{reasoning}</div>
            </details>
          {/if}
        {/if}
        <div bind:this={bottomEl} class="scroll-anchor"></div>
      </div>

      <!-- 输入区 -->
      <div class="input-area">
        {#if modelReady !== true}
          <div class="config-banner">
            <ConfigNotice
              variant="banner"
              tone="warning"
              icon={modelReady === null ? 'alert' : 'key'}
              title={modelReady === null ? '正在检测模型配置…' : '尚未配置对话模型'}
              text={modelReady === null
                ? '正在确认对话模型是否就绪…'
                : '对话模型尚未配置或 API Key 无效，AI 无法回复。请先配置后再发送。'}
              actionLabel={modelReady === null ? '' : '去设置配置'}
              onAction={modelReady === null ? null : gotoModelSettings}
              checking={modelReady === null}
              foot={recheckButton}
            />
          </div>
        {/if}

        {#if phase}
          <div class="phase-bar"><span class="phase-dot"></span>{phase.label}</div>
        {/if}

        {#if showStickerPanel}
          <div class="panel sheet">
            <div class="sheet-head">
              <span>贴纸</span>
              <button class="icon-btn" onclick={() => (showStickerPanel = false)} aria-label="关闭">
                <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M18 6 6 18M6 6l12 12"/></svg>
              </button>
            </div>
            <div class="sticker-grid">
              {#each stickerGroups as g}
                {#each g.images as fname}
                  <button class="sticker-item" onclick={() => sendSticker(g, fname)} title={`${g.pack}/${g.emotion}`}>
                    <img src={stickerUrl(g.pack, g.emotion, fname)} alt={`${g.emotion}`} loading="lazy" />
                  </button>
                {/each}
              {/each}
              {#if stickerGroups.length === 0}
                <div class="center-hint">暂无贴纸</div>
              {/if}
            </div>
          </div>
        {/if}

        {#if showImagePanel && pickedImage}
          <div class="panel sheet">
            <div class="sheet-head"><span>发送图片</span></div>
            <div class="image-preview-wrap">
              <img class="image-preview" src={pickedImage.url} alt="预览" />
              <button class="icon-btn remove" onclick={() => { if (pickedImage?.url) URL.revokeObjectURL(pickedImage.url); pickedImage = null; showImagePanel = false; imageCaption = ''; }} aria-label="移除">
                <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M18 6 6 18M6 6l12 12"/></svg>
              </button>
            </div>
            <div class="caption-row">
              <input class="caption-input" bind:value={imageCaption} placeholder="补充说明（可选）" maxlength="200" />
              <button class="send-small" onclick={sendImage} disabled={uploading} title="发送图片">
                {uploading ? '发送中…' : '发送'}
              </button>
            </div>
          </div>
        {/if}

        <div class="composer">
          <label class="act-btn" title="图片">
            <input type="file" accept="image/*" hidden onchange={pickImageFile} />
            <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/><path d="m21 15-5-5L5 21"/></svg>
          </label>

          <button class="act-btn" title="语音" onclick={toggleRecord} class:recording={recording}>
            {#if recording}
              <span class="rec-dot"></span>
            {:else}
              <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Z"/><path d="M19 10v2a7 7 0 0 1-14 0v-2"/><line x1="12" y1="19" x2="12" y2="22"/></svg>
            {/if}
          </button>

          <button class="act-btn" title="贴纸" onclick={() => { showStickerPanel = !showStickerPanel; showImagePanel = false; }}>
            <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12a9 9 0 1 1-9-9"/><path d="M21 12h-6a3 3 0 0 0-3 3v6"/><circle cx="9" cy="10" r="0.5"/><circle cx="14" cy="8" r="0.5"/></svg>
          </button>

          <input
            class="text-input"
            bind:value={input}
            placeholder={recording ? '录音中…松开结束' : '输入消息…'}
            onkeydown={(e) => { if (e.key === 'Enter' && canSend) send(); }}
            disabled={sending || uploading}
          />

          {#if sending || uploading}
            <button class="send-btn disabled" disabled title="正在生成">
              <span class="thinking-dot"></span>
            </button>
          {:else}
            <button class="send-btn {canSend ? 'active' : ''}" onclick={() => { if (canSend) send(); }} disabled={!canSend} title="发送">
              <svg viewBox="0 0 24 24" width="22" height="22" fill="currentColor"><path d="M3.4 20.4l17-8.4-17-8.4L8 12l-4.6 8.4z"/></svg>
            </button>
          {/if}
        </div>
      </div>
    </section>
  </div>

  {#if isMobile && listOpen}
    <div class="drawer-mask" role="button" tabindex="-1" aria-label="关闭会话列表" onclick={() => (listOpen = false)} onkeydown={(e) => e.key === 'Enter' && (listOpen = false)}></div>
    <aside class="drawer">
      <div class="panel-head">
        <span class="panel-title">会话</span>
        <button class="icon-btn" onclick={() => { startWithPersona(personas[0]?.id) }} title="新建会话" disabled={!personas.length}>
          <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M12 5v14M5 12h14"/></svg>
        </button>
      </div>
      <div class="conv-list">
        {#each conversations as conv}
          <button
            class="conv-row {conv.conversation_id === activeConvId ? 'is-active' : ''}"
            onclick={() => selectConversation(conv.conversation_id)}
          >
            <span class="conv-dot">{initialOf(displayName(conv))}</span>
            <span class="conv-meta">
              <span class="conv-name">{displayName(conv)}</span>
              <span class="conv-sub">{conv.platform === 'web' ? 'Web' : conv.platform}</span>
            </span>
            <span class="row-menu" onclick={(e) => rowMenu(e, conv)} role="button" tabindex="-1" onkeydown={(e) => e.key === 'Enter' && rowMenu(e, conv)}>
              <svg viewBox="0 0 24 24" width="18" height="18" fill="currentColor"><circle cx="5" cy="12" r="1.6"/><circle cx="12" cy="12" r="1.6"/><circle cx="19" cy="12" r="1.6"/></svg>
            </span>
          </button>
        {/each}
        {#if conversations.length === 0}
          <div class="conv-empty">暂无会话</div>
        {/if}
      </div>
      <div class="panel-divider"></div>
      <span class="panel-title">人设</span>
      <div class="persona-row">
        {#each personas as p}
          <button class="persona-chip" title={p.name} onclick={() => startWithPersona(p.id)}>
            {#if p.avatar}
              <img class="chip-avatar" src={p.avatar} alt={p.name} loading="lazy" />
            {:else}
              <span class="chip-avatar chip-fallback">{initialOf(p.name)}</span>
            {/if}
            <span class="chip-name">{p.name}</span>
          </button>
        {/each}
      </div>
    </aside>
  {/if}

  {#if error}
    <div class="toast" role="alert">{error}<button class="icon-btn" onclick={() => (error = null)} aria-label="关闭"><svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M18 6 6 18M6 6l12 12"/></svg></button></div>
  {/if}

  {#if menuOpen}
    <div class="convs-menu" style="left:{menuOpen.x}px;top:{menuOpen.y}px" role="menu" aria-label="会话操作">
      <button class="convs-menu-item" type="button" role="menuitem" onclick={() => menuRename(menuOpen.conv)}>
        <span class="convs-menu-ico" aria-hidden="true">{@html `<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17 3a2.828 2.828 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5Z"/></svg>`}</span>
        重命名      </button>
      <button class="convs-menu-item danger" type="button" role="menuitem" onclick={() => menuDelete(menuOpen.conv)}>
        <span class="convs-menu-ico" aria-hidden="true">{@html `<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 6h18M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/></svg>`}</span>
        删除会话
      </button>
    </div>
  {/if}
</div>

<style>
  .chat-page {
    height: 100%;
    min-height: 0;
    display: flex;
    flex-direction: column;
    background: var(--bg);
    position: relative;
    overflow: hidden;
  }

  .mobile-head {
    flex: none;
    display: flex;
    align-items: center;
    gap: var(--space-2);
    height: 48px;
    padding: 0 var(--space-3);
    background: var(--topbar-bg);
    border-bottom: 1px solid var(--topbar-border);
  }
  .head-title {
    flex: 1;
    font-weight: 600;
    font-size: var(--text-base);
    color: var(--text-1);
    text-align: center;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .icon-btn {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 36px;
    height: 36px;
    border: none;
    border-radius: var(--radius-full);
    background: transparent;
    color: var(--text-2);
    cursor: pointer;
    transition: background var(--transition), color var(--transition);
  }
  .icon-btn:hover:not(:disabled) {
    background: var(--row-hover);
    color: var(--text-1);
  }
  .icon-btn:disabled {
    opacity: 0.4;
    cursor: not-allowed;
  }

  .chat-body {
    flex: 1;
    min-height: 0;
    display: flex;
    position: relative;
  }

  /* ---- 会话侧栏 (桌面) ---- */
  .conv-panel {
    flex: none;
    width: 240px;
    border-right: 1px solid var(--border);
    background: var(--surface);
    display: flex;
    flex-direction: column;
    min-height: 0;
    padding: var(--space-3);
    gap: var(--space-2);
  }
  .panel-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
  }
  .panel-title {
    font-size: var(--text-xs);
    font-weight: 600;
    letter-spacing: 0.4px;
    text-transform: uppercase;
    color: var(--text-3);
  }
  .add-btn {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 30px;
    height: 30px;
    border: none;
    border-radius: var(--radius-full);
    background: var(--accent);
    color: var(--on-accent);
    cursor: pointer;
    transition: background var(--transition), transform var(--transition);
  }
  .add-btn:hover {
    background: var(--accent-strong);
  }
  .add-btn:active {
    transform: scale(0.94);
  }

  .conv-list {
    display: flex;
    flex-direction: column;
    gap: 2px;
    overflow-y: auto;
    min-height: 0;
    flex: 1;
  }
  .conv-row {
    display: flex;
    align-items: center;
    gap: var(--space-3);
    width: 100%;
    padding: var(--space-2) var(--space-2);
    border: none;
    border-radius: var(--radius);
    background: transparent;
    color: var(--text-1);
    text-align: left;
    cursor: pointer;
    transition: background var(--transition);
    position: relative;
  }
  .conv-row:hover {
    background: var(--row-hover);
  }
  .conv-row.is-active {
    background: var(--tint);
  }
  .conv-dot {
    flex: none;
    width: 36px;
    height: 36px;
    border-radius: var(--radius-full);
    background: var(--accent-soft);
    color: var(--accent-strong);
    display: inline-flex;
    align-items: center;
    justify-content: center;
    font-weight: 600;
    font-size: var(--text-base);
  }
  .conv-meta {
    flex: 1;
    min-width: 0;
    display: flex;
    flex-direction: column;
  }
  .conv-name {
    font-weight: 500;
    font-size: var(--text-sm);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .conv-sub {
    font-size: var(--text-xs);
    color: var(--text-3);
  }
  .row-menu {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 28px;
    height: 28px;
    border-radius: var(--radius-full);
    color: var(--text-3);
    cursor: pointer;
    opacity: 0;
    transition: opacity var(--transition), background var(--transition);
  }
  .conv-row:hover .row-menu,
  .conv-row.is-active .row-menu {
    opacity: 1;
  }
  .row-menu:hover {
    background: var(--row-active);
    color: var(--text-1);
  }
  /* 会话行上下拉菜单 */
  .convs-menu {
    position: fixed;
    z-index: 200;
    min-width: 150px;
    padding: var(--space-1);
    background: var(--surface);
    border: 1px solid var(--card-border);
    border-radius: var(--card-radius);
    box-shadow: var(--shadow-lg);
    display: flex;
    flex-direction: column;
    animation: convs-pop .14s ease-out;
  }
  @keyframes convs-pop {
    from { opacity: 0; transform: translateY(-4px) scale(.98); }
    to { opacity: 1; transform: none; }
  }
  .convs-menu-item {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    padding: var(--space-2) var(--space-3);
    border: none;
    border-radius: var(--radius-sm);
    background: transparent;
    color: var(--text-1);
    font-size: var(--text-sm);
    text-align: left;
    cursor: pointer;
    transition: background var(--transition), color var(--transition);
  }
  .convs-menu-item:hover { background: var(--row-hover); }
  .convs-menu-item.danger { color: var(--error); }
  .convs-menu-item.danger:hover { background: color-mix(in srgb, var(--error) 12%, transparent); }
  .convs-menu-ico { display: inline-flex; }
  .conv-empty {
    padding: var(--space-5);
    text-align: center;
    font-size: var(--text-sm);
    color: var(--text-3);
  }
  .panel-divider {
    border-top: 1px solid var(--border);
    margin: var(--space-2) 0;
  }
  .persona-panel {
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
  }
  .persona-row {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-2);
  }
  .persona-chip,
  .welcome-chip {
    display: inline-flex;
    align-items: center;
    gap: var(--space-2);
    padding: var(--space-1) var(--space-2) var(--space-1) var(--space-1);
    border: 1px solid var(--border);
    border-radius: var(--radius-full);
    background: var(--surface);
    color: var(--text-1);
    font-size: var(--text-xs);
    cursor: pointer;
    transition: border-color var(--transition), background var(--transition), transform var(--transition);
  }
  .persona-chip:hover,
  .welcome-chip:hover {
    border-color: var(--accent);
    background: var(--tint);
  }
  .persona-chip:active,
  .welcome-chip:active {
    transform: scale(0.96);
  }
  .chip-avatar {
    width: 22px;
    height: 22px;
    border-radius: var(--radius-full);
    object-fit: cover;
    background: var(--surface-2);
  }
  .chip-fallback {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    font-weight: 600;
    color: var(--accent-strong);
    background: var(--accent-soft);
  }
  .chip-name {
    max-width: 90px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  /* ---- 聊天主区 ---- */
  .chat-stage {
    flex: 1;
    min-width: 0;
    min-height: 0;
    display: flex;
    flex-direction: column;
    position: relative;
  }
  .msgs {
    flex: 1;
    min-height: 0;
    overflow-y: auto;
    overflow-x: hidden;
    padding: var(--space-4);
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
    -webkit-overflow-scrolling: touch;
  }
  /* 空会话：让欢迎区在容器中真正居中（比 margin:auto 在滚动容器里更可靠） */
  .msgs.empty {
    justify-content: center;
    align-items: center;
  }
  .msgs.empty .scroll-anchor {
    display: none;
  }
  .scroll-anchor {
    height: 1px;
    flex: none;
  }
  .center-hint {
    text-align: center;
    padding: var(--space-6);
    color: var(--text-3);
    font-size: var(--text-sm);
  }

  /* 欢迎区 */
  .welcome {
    margin: 0;
    width: 100%;
    max-width: 360px;
    text-align: center;
    padding: var(--space-6);
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: var(--space-3);
  }
  .welcome-mark {
    width: 72px;
    height: 72px;
    border-radius: var(--radius-xl);
    background: var(--tint);
    display: flex;
    align-items: center;
    justify-content: center;
    box-shadow: var(--shadow);
  }
  .brand-dot {
    width: 30px;
    height: 30px;
    border-radius: var(--radius-full);
    background: var(--accent);
    box-shadow: 0 0 0 8px var(--accent-soft);
  }
  .welcome-title {
    margin: 0;
    font-size: var(--text-xl);
    font-weight: 700;
    color: var(--text-1);
  }
  .welcome-desc {
    margin: 0;
    font-size: var(--text-sm);
    color: var(--text-2);
    line-height: var(--leading-normal);
  }
  .welcome-personas {
    display: flex;
    flex-wrap: wrap;
    justify-content: center;
    gap: var(--space-2);
    margin-top: var(--space-2);
  }

  /* 气泡 */
  .bubble-row {
    display: flex;
    align-items: flex-start;
    gap: var(--space-2);
    max-width: min(var(--chat-msg-maxw), 78%);
  }
  .bubble-row.self {
    align-self: flex-end;
    flex-direction: row-reverse;
  }
  .bubble-row.friend {
    align-self: flex-start;
  }
  .av {
    flex: none;
    width: 32px;
    height: 32px;
    border-radius: var(--radius-full);
    background: var(--accent-soft);
    color: var(--accent-strong);
    display: inline-flex;
    align-items: center;
    justify-content: center;
    font-weight: 600;
    font-size: var(--text-xs);
  }
  .bubble-col {
    display: flex;
    flex-direction: column;
    gap: 4px;
    min-width: 0;
  }
  .bubble {
    padding: var(--space-2) var(--space-3);
    border-radius: var(--bubble-radius-lg);
    line-height: var(--leading-snug);
    word-break: break-word;
    white-space: pre-wrap;
  }
  .bubble-user {
    background: var(--bubble-self-bg);
    color: var(--bubble-self-text);
    border-bottom-right-radius: var(--bubble-radius-sm);
  }
  .bubble-ai {
    background: var(--bubble-friend-bg);
    color: var(--bubble-friend-text);
    border: 1px solid var(--bubble-border);
    border-bottom-left-radius: var(--bubble-radius-sm);
    border-left: 3px solid var(--accent);
  }
  .bubble-text {
    font-size: var(--text-base);
  }
  .caret {
    display: inline-block;
    width: 2px;
    height: 1em;
    margin-left: 2px;
    vertical-align: text-bottom;
    background: currentColor;
    opacity: 0.7;
    animation: caret-blink 1s steps(1) infinite;
  }
  @keyframes caret-blink {
    50% { opacity: 0; }
  }
  .bubble-time {
    font-size: var(--text-xs);
    color: var(--bubble-time);
    padding: 0 2px;
  }
  .self .bubble-time {
    text-align: right;
  }
  .sticker-bubble {
    max-width: 150px;
  }
  .sticker-img {
    width: 100%;
    max-width: 150px;
    border-radius: var(--radius-sm);
  }
  .voice-player {
    max-width: 260px;
    height: 34px;
  }

  /* 思考面板 */
  .reasoning {
    align-self: flex-start;
    max-width: min(var(--chat-msg-maxw), 78%);
    font-size: var(--text-xs);
    color: var(--text-3);
    background: color-mix(in srgb, var(--surface-2) 60%, transparent);
    border-left: 3px solid var(--border-strong);
    border-radius: var(--radius-sm);
    padding: var(--space-2) var(--space-3);
    margin-top: var(--space-1);
  }
  .reasoning summary {
    cursor: pointer;
    font-weight: 600;
    user-select: none;
  }
  .reasoning-body {
    margin-top: var(--space-2);
    white-space: pre-wrap;
    line-height: var(--leading-normal);
  }

  /* 输入区 */
  .input-area {
    flex: none;
    border-top: 1px solid var(--border);
    background: var(--surface);
    position: relative;
    padding-bottom: env(safe-area-inset-bottom);
  }
  /* 配置守卫 banner (模型未配置时显示在输入框上方) */
  .config-banner {
    padding: var(--space-2) var(--space-3);
    border-bottom: 1px solid var(--border);
    background: color-mix(in srgb, var(--warning-soft) 70%, transparent);
  }
  .config-recheck {
    flex: none;
    height: var(--btn-h-sm);
    padding: 0 var(--space-2);
    border: 1px solid var(--border-strong);
    border-radius: var(--btn-radius);
    background: transparent;
    color: var(--text-2);
    font-size: var(--text-xs);
    white-space: nowrap;
    cursor: pointer;
    transition: background var(--transition), color var(--transition), border-color var(--transition);
  }
  .config-recheck:hover:not(:disabled) {
    background: var(--tint);
    border-color: var(--accent);
    color: var(--text-1);
  }
  .config-recheck:disabled {
    opacity: 0.6;
    cursor: not-allowed;
  }
  .phase-bar {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    padding: var(--space-2) var(--space-4);
    font-size: var(--text-xs);
    color: var(--text-2);
    border-bottom: 1px solid var(--border);
    background: color-mix(in srgb, var(--tint) 40%, transparent);
  }
  .phase-dot {
    width: 8px;
    height: 8px;
    border-radius: var(--radius-full);
    background: var(--accent);
    animation: boot-pulse 1.2s var(--ease-in-out) infinite;
  }
  @keyframes boot-pulse {
    0%, 100% { opacity: 0.3; transform: scale(0.8); }
    50% { opacity: 1; transform: scale(1.1); }
  }

  .panel.sheet {
    border-bottom: 1px solid var(--border);
    background: var(--surface-2);
    padding: var(--space-3);
    max-height: 240px;
    overflow-y: auto;
  }
  .sheet-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: var(--space-2);
    font-weight: 600;
    font-size: var(--text-sm);
    color: var(--text-1);
  }
  .sticker-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(56px, 1fr));
    gap: var(--space-2);
  }
  .sticker-item {
    border: none;
    background: transparent;
    cursor: pointer;
    padding: 0;
    border-radius: var(--radius-sm);
    transition: transform var(--transition), background var(--transition);
  }
  .sticker-item:hover {
    transform: scale(1.08);
    background: var(--tint);
  }
  .sticker-item img {
    width: 100%;
    aspect-ratio: 1;
    object-fit: contain;
  }
  .image-preview-wrap {
    position: relative;
    max-width: 200px;
    margin: 0 auto;
  }
  .image-preview {
    width: 100%;
    border-radius: var(--radius);
    border: 1px solid var(--border);
    background: var(--surface);
  }
  .remove {
    position: absolute;
    top: var(--space-1);
    right: var(--space-1);
    background: var(--overlay);
    color: #fff;
  }
  .caption-row {
    display: flex;
    gap: var(--space-2);
    margin-top: var(--space-2);
  }
  .caption-input {
    flex: 1;
    height: 38px;
    padding: 0 var(--space-3);
    border: 1px solid var(--input-border);
    border-radius: var(--input-radius);
    background: var(--input-bg);
    color: var(--input-text);
    font-size: var(--text-sm);
  }
  .caption-input:focus {
    outline: none;
    border-color: var(--input-focus-border);
    box-shadow: var(--focus-ring);
  }
  .send-small {
    height: 38px;
    padding: 0 var(--space-4);
    border: none;
    border-radius: var(--input-radius);
    background: var(--accent);
    color: var(--on-accent);
    font-weight: 600;
    cursor: pointer;
    transition: background var(--transition);
  }
  .send-small:hover:not(:disabled) {
    background: var(--accent-strong);
  }
  .send-small:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  .composer {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    padding: var(--space-2) var(--space-3);
  }
  .act-btn {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 38px;
    height: 38px;
    flex: none;
    border: none;
    border-radius: var(--radius-full);
    background: transparent;
    color: var(--text-2);
    cursor: pointer;
    transition: background var(--transition), color var(--transition);
  }
  .act-btn:hover {
    background: var(--row-hover);
    color: var(--text-1);
  }
  .act-btn.recording {
    background: var(--error);
    color: #fff;
  }
  .rec-dot {
    width: 16px;
    height: 16px;
    border-radius: var(--radius-full);
    background: #fff;
    animation: caret-blink 1s steps(1) infinite;
  }
  .text-input {
    flex: 1;
    min-width: 0;
    height: 40px;
    padding: 0 var(--space-4);
    border: 1px solid var(--input-border);
    border-radius: var(--input-radius);
    background: var(--input-bg);
    color: var(--input-text);
    font-size: var(--text-base);
    transition: border-color var(--transition), box-shadow var(--transition);
  }
  .text-input:focus {
    outline: none;
    border-color: var(--input-focus-border);
    box-shadow: var(--focus-ring);
  }
  .text-input::placeholder {
    color: var(--input-placeholder);
  }
  .send-btn {
    flex: none;
    width: 40px;
    height: 40px;
    border: none;
    border-radius: var(--radius-full);
    background: var(--surface-3);
    color: var(--text-3);
    cursor: not-allowed;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    transition: background var(--transition), color var(--transition), transform var(--transition), box-shadow var(--transition);
  }
  .send-btn.active {
    background: var(--accent);
    color: var(--on-accent);
    cursor: pointer;
    box-shadow: var(--shadow-accent);
  }
  .send-btn.active:hover {
    background: var(--accent-strong);
  }
  .send-btn.active:active {
    transform: scale(0.94);
  }
  .send-btn.disabled {
    background: var(--accent-soft);
  }
  .thinking-dot {
    width: 10px;
    height: 10px;
    border-radius: var(--radius-full);
    background: var(--accent);
    animation: caret-blink 1s steps(1) infinite;
  }

  /* 移动端抽屉 */
  .drawer-mask {
    position: absolute;
    inset: 0;
    background: var(--overlay);
    z-index: 40;
  }
  .drawer {
    position: absolute;
    top: 0;
    bottom: 0;
    left: 0;
    width: min(300px, 82%);
    z-index: 41;
    background: var(--surface);
    border-right: 1px solid var(--border);
    padding: var(--space-3);
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
    box-shadow: var(--shadow-lg);
    animation: draw-in 220ms var(--ease-out);
  }
  @keyframes draw-in {
    from { transform: translateX(-100%); }
    to { transform: translateX(0); }
  }

  /* toast */
  .toast {
    position: absolute;
    top: var(--space-3);
    left: 50%;
    transform: translateX(-50%);
    z-index: 60;
    display: flex;
    align-items: center;
    gap: var(--space-2);
    max-width: 90%;
    padding: var(--space-2) var(--space-3);
    background: var(--toast-bg);
    color: var(--toast-text);
    border-radius: var(--toast-radius);
    box-shadow: var(--toast-shadow);
    font-size: var(--text-sm);
  }

  @media (max-width: 767px) {
    .bubble-row {
      max-width: 86%;
    }
    .msgs {
      padding: var(--space-3);
    }
  }
</style>
