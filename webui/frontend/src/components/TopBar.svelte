<script>
  // TopBar.svelte — 移动端顶栏 (品牌 + 右侧可插槽)
  // 桌面端由 PhoneShell 隐藏 (改用侧边栏), 移动端显示。
  import ThemeToggle from './ThemeToggle.svelte';
</script>

<header class="topbar">
  <div class="brand">
    <span class="brand-dot" aria-hidden="true"></span>
    <span class="brand-name">慕</span>
  </div>

  <div class="actions">
    <slot name="actions">
      <ThemeToggle />
    </slot>
  </div>
</header>

<style>
  .topbar {
    position: sticky;
    top: 0;
    z-index: 30;
    display: flex;
    align-items: center;
    gap: var(--space-3);
    height: var(--topbar-h);
    padding: 0 var(--space-4);
    background: color-mix(in srgb, var(--topbar-bg) 86%, transparent);
    border-bottom: 1px solid var(--topbar-border);
    backdrop-filter: blur(var(--blur-heavy)) saturate(1.4);
    -webkit-backdrop-filter: blur(var(--blur-heavy)) saturate(1.4);
  }

  .brand {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    min-width: 0;
  }

  .brand-dot {
    position: relative;
    flex: none;
    width: 16px;
    height: 16px;
    border-radius: var(--radius-full);
    background: linear-gradient(135deg, var(--accent), var(--accent-strong));
    box-shadow: 0 0 0 3px var(--tint), var(--shadow-sm);
  }
  /* 品牌小光点 */
  .brand-dot::after {
    content: '';
    position: absolute;
    top: 2px;
    left: 3px;
    width: 4px;
    height: 4px;
    border-radius: var(--radius-full);
    background: color-mix(in srgb, var(--on-accent) 70%, transparent);
  }

  .brand-name {
    font-weight: 700;
    font-size: var(--text-lg);
    letter-spacing: 0.3px;
    color: var(--topbar-text);
    white-space: nowrap;
    background: linear-gradient(120deg, var(--text-1), var(--accent-strong));
    -webkit-background-clip: text;
    background-clip: text;
    -webkit-text-fill-color: transparent;
  }

  .actions {
    margin-left: auto;
    display: flex;
    align-items: center;
    gap: var(--space-2);
  }
</style>
