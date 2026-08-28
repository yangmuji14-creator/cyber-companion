<script>
  // EmptyState.svelte — 精致空状态 (图标 + 标题 + 描述 + 可选主操作)
  // 使用 tokens 的 --empty-* 语义变量 + 一个 svg 图标 (通过 icon name 引用)。
  import './settings-base.css';
  import { I } from './icons.js';

  let { icon = 'puzzle', title = '', desc = '', children, compact = false } = $props();
</script>

<div class="empty-state" class:compact>
  <div class="empty-icon" aria-hidden="true">
    {@html `<svg viewBox="0 0 24 24" width="26" height="26" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${I[icon] || ''}</svg>`}
  </div>
  {#if title}<p class="empty-title">{title}</p>{/if}
  {#if desc}<p class="empty-desc">{desc}</p>{/if}
  {#if children}
    <div class="empty-action">{@render children?.()}</div>
  {/if}
</div>

<style>
  .empty-state {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    text-align: center;
    gap: var(--space-2);
    min-height: 140px;
    padding: var(--space-6) var(--space-5);
    border: 1px dashed var(--border-strong);
    border-radius: var(--card-radius);
  }
  .empty-state.compact { min-height: 96px; padding: var(--space-4); }
  .empty-icon {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 52px;
    height: 52px;
    border-radius: var(--radius-full);
    background: var(--surface-2);
    color: var(--empty-icon);
    margin-bottom: var(--space-1);
  }
  .empty-title { margin: 0; font-size: var(--text-base); font-weight: 600; color: var(--empty-title); }
  .empty-desc { margin: 0; max-width: 300px; font-size: var(--text-sm); color: var(--empty-text); line-height: var(--leading-snug); }
  .empty-action { margin-top: var(--space-2); }
</style>
