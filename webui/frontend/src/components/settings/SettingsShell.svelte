<script>
  // SettingsShell.svelte — 设置子页统一外壳
  // 顶部返回头 (返回 + 标题 + 副标题 + 右侧操作槽), 内容滚动区, 可选底部固定保存条。
  // 全部使用 settings-base.css 类 + tokens 变量。
  import './settings-base.css';
  import { I } from './icons.js';

  let { title = '', desc = '', onback, children, footer, actions } = $props();
</script>

<div class="settings-main">
  <header class="sub-head back-head">
    <button class="icon-btn" type="button" onclick={onback} aria-label="返回">
      {@html `<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${I.back}</svg>`}
    </button>
    <div class="sub-title">
      <h3>{title}</h3>
      {#if desc}<p>{desc}</p>{/if}
    </div>
    {#if actions}
      <div class="head-actions">{@render actions?.()}</div>
    {/if}
  </header>

  <div class="sub-body">
    {@render children?.()}

    {#if footer}
      <div class="shell-footer">
        {@render footer?.()}
      </div>
    {/if}
  </div>
</div>

<style>
  .sub-head {
    display: flex;
    align-items: center;
    gap: var(--space-3);
    padding: var(--space-2) 0 var(--space-4);
  }
  .sub-head h3 { margin: 0; font-size: var(--text-lg); font-weight: 700; color: var(--text-1); }
  .sub-head p { margin: 2px 0 0; font-size: var(--text-xs); color: var(--text-3); }
  .sub-title { min-width: 0; flex: 1; }
  .head-actions { flex: none; display: flex; align-items: center; gap: var(--space-2); }

  .shell-footer {
    position: sticky;
    bottom: 0;
    background: var(--bg);
    padding: var(--space-3) 0;
    margin-top: var(--space-1);
  }
</style>
