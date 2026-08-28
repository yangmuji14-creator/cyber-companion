<script>
  // TabBar.svelte — Tab 导航 (底部横排 / 侧边竖排 两种形态共用)
  // - active: 当前选中顶层 page (chat/contacts/discover/memory/settings)
  // - vertical: true -> 桌面侧边栏竖排; false -> 移动底栏横排
  // 点击调用 router.goTab() 切换 hash。
  import { TABS, TAB_LABELS, goTab } from '../lib/router.js';

  let { active = 'chat', vertical = false } = $props();

  // 每个 Tab 的图标 (内联 SVG, 零外部依赖)
  const iconFor = {
    chat: (color) => `
      <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="${color}" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z"/></svg>`,
    contacts: (color) => `
      <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="${color}" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>`,
    discover: (color) => `
      <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="${color}" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><polygon points="16.24 7.76 14.12 14.12 7.76 16.24 9.88 9.88 16.24 7.76" fill="${color}"/></svg>`,
    memory: (color) => `
      <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="${color}" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z"/><line x1="9" y1="10" x2="9" y2="10"/><line x1="12" y1="10" x2="12" y2="10"/><line x1="15" y1="10" x2="15" y2="10"/><line x1="9" y1="14" x2="15" y2="14"/></svg>`,
    settings: (color) => `
      <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="${color}" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>`,
  };
</script>

<nav class="tabbar {vertical ? 'vertical' : 'horizontal'}" aria-label="主导航">
  {#each TABS as tab}
    {@const selected = active === tab}
    {@const color = selected ? 'var(--tab-active)' : 'var(--tab-inactive)'}
    <button
      class="tab {selected ? 'is-active' : ''}"
      type="button"
      onclick={() => goTab(tab)}
      aria-current={selected ? 'page' : undefined}
      title={TAB_LABELS[tab]}
    >
      <span class="tab-icon" aria-hidden="true">{@html iconFor[tab](color)}</span>
      <span class="tab-label">{TAB_LABELS[tab]}</span>
    </button>
  {/each}
</nav>

<style>
  .tabbar {
    display: flex;
    gap: var(--space-1);
  }

  /* 移动端: 底部横排 (毛玻璃) */
  .horizontal {
    flex-direction: row;
    align-items: stretch;
    height: var(--tabbar-h);
    padding: var(--space-1) var(--space-2);
    background: var(--tabbar-bg);
    border-top: 1px solid var(--tabbar-border);
    backdrop-filter: blur(var(--blur));
    -webkit-backdrop-filter: blur(var(--blur));
    box-shadow: 0 -6px 24px color-mix(in srgb, var(--text-1) 4%, transparent);
  }
  .horizontal .tab {
    flex: 1;
    min-width: 0;
    flex-direction: column;
    gap: 3px;
    border-radius: var(--radius-md);
    padding: var(--space-1) 0;
  }

  /* 桌面端: 侧边竖排 */
  .vertical {
    flex-direction: column;
    gap: var(--space-1);
    padding: var(--space-1);
    width: 100%;
  }
  .vertical .tab {
    flex-direction: row;
    justify-content: flex-start;
    gap: var(--space-3);
    padding: var(--space-2) var(--space-3);
    border-radius: var(--radius);
    font-size: var(--text-base);
  }

  .tab {
    position: relative;
    display: flex;
    align-items: center;
    justify-content: center;
    border: none;
    background: transparent;
    color: var(--tab-inactive);
    font-size: var(--text-xs);
    font-weight: 500;
    line-height: 1.2;
    cursor: pointer;
    -webkit-tap-highlight-color: transparent;
    transition: color var(--transition), background var(--transition-slow),
      transform var(--transition), box-shadow var(--transition);
  }
  .tab:hover {
    color: var(--tab-hover);
    background: var(--row-hover);
  }
  .tab:active {
    transform: scale(0.96);
  }

  /* 选中态: 柔和药丸指示条 */
  .tab.is-active {
    color: var(--tab-active);
    background: var(--tint);
    box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--accent) 18%, transparent);
  }
  .tab.is-active::before {
    content: '';
    position: absolute;
    inset: 0;
    border-radius: inherit;
    background: var(--tint);
    animation: tab-pop var(--transition-snap);
    z-index: 0;
    pointer-events: none;
  }
  .tab.is-active .tab-icon {
    transform: translateY(-1px) scale(1.06);
  }
  .tab.is-active .tab-label {
    font-weight: 600;
  }

  /* 激活滑动指示条 (竖向/横向右侧/底部细条) */
  .tab.is-active::after {
    content: '';
    position: absolute;
    z-index: 1;
    pointer-events: none;
    background: var(--accent);
    border-radius: var(--radius-full);
    animation: tab-fade-in var(--transition);
  }
  .vertical .tab.is-active::after {
    left: var(--space-1);
    top: 50%;
    transform: translateY(-50%);
    width: 3px;
    height: 58%;
  }
  .horizontal .tab.is-active::after {
    left: 50%;
    bottom: 2px;
    transform: translateX(-50%);
    width: 26%;
    height: 3px;
  }

  .tab-icon {
    position: relative;
    z-index: 2;
    display: inline-flex;
    transition: transform var(--transition-snap), color var(--transition);
  }
  .tab-label {
    position: relative;
    z-index: 2;
    white-space: nowrap;
    transition: font-weight var(--transition-fast), color var(--transition);
  }

  @keyframes tab-pop {
    from { opacity: 0; transform: scale(0.72); }
    to { opacity: 1; transform: scale(1); }
  }
  @keyframes tab-fade-in {
    from { opacity: 0; }
    to { opacity: 1; }
  }
</style>
