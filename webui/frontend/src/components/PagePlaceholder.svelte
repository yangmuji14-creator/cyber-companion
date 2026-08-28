<script>
  // PagePlaceholder.svelte — 通用页面占位骨架 (阶段2)
  // 每个 Tab 页在阶段2 复用此骨架: 页头 + 状态徽章 + 空状态区。
  // 阶段3 用真实业务内容替换空状态区。
  import { TAB_LABELS } from '../lib/router.js';

  let { page = 'chat', note = '', wide = false, children, icon, title } = $props();
  let active = $derived(TAB_LABELS[page] ?? page);
</script>

<div class="page {wide ? 'wide' : ''}">
  <header class="page-head">
    <h1>{active}</h1>
    {#if note}
      <span class="page-badge">{note}</span>
    {/if}
  </header>

  <!-- 阶段2 空状态占位; 阶段3 被真实内容替换 -->
  <div class="empty-state">
    <span class="empty-icon" aria-hidden="true">
      {#if icon}{@render icon()}{/if}
    </span>
    <div class="empty-body">
      <p class="empty-title">{#if title}{@render title()}{:else}{active}模块建设中{/if}</p>
      <p class="empty-desc">此区域将在下一阶段填充完整业务功能。当前为布局与导航骨架。</p>
    </div>
  </div>

  <!-- 页内可选额外占位 (如设置页的诊断卡) -->
  {#if children}{@render children()}{/if}
</div>

<style>
  .page {
    padding: var(--space-5) var(--space-4);
    max-width: 720px;
    margin: 0 auto;
  }
  .page.wide {
    max-width: 960px;
  }

  .page-head {
    display: flex;
    align-items: center;
    gap: var(--space-3);
    margin-bottom: var(--space-5);
  }
  .page-head h1 {
    margin: 0;
    font-size: var(--text-xl);
    font-weight: 700;
    color: var(--text-1);
  }

  .page-badge {
    font-size: var(--text-xs);
    padding: 2px var(--space-2);
    border-radius: var(--radius-full);
    border: 1px solid var(--border);
    color: var(--text-2);
    background: var(--surface);
    white-space: nowrap;
  }

  .empty-state {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    text-align: center;
    gap: var(--space-3);
    min-height: 280px;
    padding: var(--space-7) var(--space-5);
    border: 1px dashed var(--border-strong);
    border-radius: var(--radius-xl);
    background: color-mix(in srgb, var(--surface) 62%, transparent);
  }

  .empty-icon {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 72px;
    height: 72px;
    border-radius: var(--radius-xl);
    background: var(--tint);
    color: var(--tab-active);
    box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--accent) 16%, transparent);
  }

  .empty-body {
    max-width: 420px;
  }
  .empty-title {
    margin: 0 0 var(--space-1);
    font-size: var(--text-lg);
    font-weight: 600;
    color: var(--empty-title);
  }
  .empty-desc {
    margin: 0;
    font-size: var(--text-sm);
    color: var(--empty-text);
    line-height: var(--leading-normal);
  }
</style>
