<script>
  // PromptPanel.svelte — 可复用折叠面板 (高级 Prompt 分层用)
  //
  // Props:
  //   title    - 面板标题
  //   hint     - 展开后顶部说明文字 (可选)
  //   tier     - 1 = 常用「微调」档, 2 = 次要「深度设置」档 (弱化视觉)
  //   badge    - 右侧计数徽标 (可选)
  //   open     - 双向展开状态 (默认收起)
  //   children - 默认内容 snippet
  //   actions  - 底部操作 snippet (可选, 如保存按钮)
  let {
    title,
    hint = '',
    tier = 1,
    badge = '',
    open = $bindable(false),
    children,
    actions,
  } = $props();
</script>

<div class="panel tier-{tier}">
  <button
    class="p-head"
    type="button"
    aria-expanded={open}
    onclick={() => (open = !open)}
  >
    <span class="p-title">{title}</span>
    {#if badge}
      <span class="p-badge">{badge}</span>
    {/if}
    <svg
      class="p-arrow {open ? 'is-open' : ''}"
      viewBox="0 0 24 24"
      width="16"
      height="16"
      fill="none"
      stroke="currentColor"
      stroke-width="2"
      stroke-linecap="round"
      stroke-linejoin="round"
      aria-hidden="true"
    ><polyline points="6 9 12 15 18 9"/></svg>
  </button>

  {#if open}
    <div class="p-body">
      {#if hint}
        <p class="p-hint">{hint}</p>
      {/if}
      <div class="p-content">
        {@render children?.()}
      </div>
      {#if actions}
        <div class="p-actions">
          {@render actions()}
        </div>
      {/if}
    </div>
  {/if}
</div>

<style>
  .panel {
    background: var(--card-bg);
    border: 1px solid var(--card-border);
    border-radius: var(--card-radius);
    box-shadow: var(--card-shadow);
    overflow: hidden;
  }

  /* 深度设置档: 视觉弱化(更灰/次要) */
  .panel.tier-2 {
    background: var(--surface-2);
    border-color: var(--border);
    box-shadow: none;
  }

  .p-head {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    width: 100%;
    padding: var(--space-3) var(--space-4);
    background: transparent;
    border: none;
    color: var(--text-1);
    font-size: var(--text-sm);
    font-weight: 600;
    cursor: pointer;
    transition: background var(--transition);
  }
  .p-head:hover {
    background: var(--row-hover);
  }
  .tier-2 .p-head {
    color: var(--text-2);
    font-weight: 500;
  }
  .p-title {
    flex: 1;
    text-align: left;
  }
  .p-badge {
    font-size: var(--text-xs);
    color: var(--text-3);
    background: var(--surface-3);
    border-radius: var(--radius-full);
    padding: var(--space-1) var(--space-2);
  }
  .tier-2 .p-badge {
    background: color-mix(in srgb, var(--text-3) 16%, transparent);
  }
  .p-arrow {
    transition: transform var(--transition);
    color: var(--text-3);
  }
  .p-arrow.is-open {
    transform: rotate(180deg);
  }

  .p-body {
    padding: var(--space-4);
    border-top: 1px solid var(--border);
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
  }
  .p-hint {
    margin: 0;
    font-size: var(--text-xs);
    color: var(--text-3);
  }
  .p-content {
    display: flex;
    flex-direction: column;
    gap: var(--space-4);
  }
  .p-actions {
    display: flex;
    justify-content: flex-end;
    padding-top: var(--space-1);
    border-top: 1px solid var(--border);
    margin-top: var(--space-1);
  }
</style>
