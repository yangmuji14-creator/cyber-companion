<script>
  // ConfigNotice.svelte — 配置引导提示组件 (纯展示 + 单一"去设置"动作)
  //
  // 用于聊天页识别"模型/服务商未配置或出错"的场景，主动引导用户去配置:
  //   - variant='banner' : 输入框上方的全宽警示条 (未配置守卫)
  //   - variant='card'   : 取代普通 AI 气泡的"配置提示卡" (后端回配置错误文案时)
  //
  // 零依赖; 所有颜色/间距/圆角/字号均取自 tokens.css 语义变量, 不发明新 token。
  let {
    variant = 'banner', // 'banner' | 'card'
    tone = 'warning',   // 'warning' | 'error' | 'info'
    icon = 'alert',
    title = '',
    text = '',
    actionLabel = '',
    onAction = null,
    checking = false,   // true -> 显示"检测中"态 (banner 守卫专用)
    foot = null,        // 可选尾巴内容 (snippet, 用于在 banner 末尾追加如"重新检测"按钮)
  } = $props();

  // 内联 SVG 图标 (Lucide 风格, 零外部依赖)
  const ICONS = {
    alert: `
      <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>`,
    alertCircle: `
      <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>`,
    info: `
      <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>`,
    key: `
      <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m21 2-2 2m-7.61 7.61a5.5 5.5 0 1 1-7.778 7.778 5.5 5.5 0 0 1 7.777-7.777zm0 0L15.5 7.5m0 0 3 3L22 7l-3-3m-3.5 3.5L19 4"/></svg>`,
  };
</script>

<div class="notice n-{variant} n-tone-{tone} {checking ? 'is-checking' : ''}" role="alert">
  <span class="n-icon" aria-hidden="true">
    {#if checking}
      <span class="n-spin" aria-hidden="true"></span>
    {:else}
      {@html ICONS[icon] || ICONS.alert}
    {/if}
  </span>

  <div class="n-body">
    {#if title}<div class="n-title">{title}</div>{/if}
    {#if text}<div class="n-text">{text}</div>{/if}
  </div>

  {#if actionLabel && onAction}
    <button class="n-action" type="button" onclick={onAction}>{actionLabel}</button>
  {/if}

  {#if foot}{@render foot()}{/if}
</div>

<style>
  .notice {
    display: flex;
    align-items: center;
    gap: var(--space-3);
    color: var(--text-1);
  }

  .n-icon {
    flex: none;
    display: inline-flex;
    align-items: center;
    justify-content: center;
  }

  .n-body {
    flex: 1;
    min-width: 0;
    display: flex;
    flex-direction: column;
    gap: 2px;
  }
  .n-title {
    font-weight: 600;
    font-size: var(--text-sm);
    color: var(--text-1);
  }
  .n-text {
    font-size: var(--text-xs);
    color: var(--text-2);
    line-height: var(--leading-snug);
    white-space: pre-wrap;
    word-break: break-word;
  }

  .n-action {
    flex: none;
    height: var(--btn-h-md);
    padding: 0 var(--space-3);
    border: none;
    border-radius: var(--btn-radius);
    background: var(--accent);
    color: var(--on-accent);
    font-size: var(--text-xs);
    font-weight: 600;
    cursor: pointer;
    white-space: nowrap;
    transition: background var(--transition), transform var(--transition), box-shadow var(--transition);
  }
  .n-action:hover {
    background: var(--accent-strong);
  }
  .n-action:active {
    transform: scale(0.96);
  }

  /* ---- 形态: banner (输入框上方的全宽警示条) ---- */
  .n-banner {
    width: 100%;
    padding: var(--space-3) var(--space-4);
    border-radius: var(--radius);
    border: 1px solid var(--border);
    background: var(--warning-soft);
  }
  .n-banner.n-tone-error {
    background: var(--error-soft);
  }
  .n-banner.n-tone-info {
    background: var(--info-soft);
  }

  /* ---- 形态: card (取代正常气泡的配置提示卡) ---- */
  .n-card {
    max-width: 320px;
    padding: var(--space-3) var(--space-3);
    border-radius: var(--bubble-radius-lg);
    border-bottom-left-radius: var(--bubble-radius-sm);
    border: 1px solid var(--border-strong);
    background: var(--warning-soft);
    box-shadow: var(--shadow-sm);
    align-items: flex-start;
  }
  .n-card.n-tone-error {
    background: var(--error-soft);
  }
  .n-card.n-tone-info {
    background: var(--info-soft);
  }
  .n-card .n-action {
    margin-top: var(--space-2);
  }

  .n-is-checking .n-icon {
    color: var(--text-3);
  }
  .n-is-checking .n-text {
    color: var(--text-3);
  }

  /* 检测中转圈 */
  .n-spin {
    width: 16px;
    height: 16px;
    border-radius: var(--radius-full);
    border: 2px solid var(--border-strong);
    border-top-color: var(--accent);
    animation: n-rotate 0.8s var(--ease-in-out) infinite;
  }
  @keyframes n-rotate {
    to { transform: rotate(360deg); }
  }

  @media (max-width: 767px) {
    .n-banner {
      padding: var(--space-2) var(--space-3);
    }
    .n-card {
      max-width: 86%;
    }
  }
</style>
