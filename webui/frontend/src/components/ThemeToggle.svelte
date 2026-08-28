<script>
  // ThemeToggle.svelte — 深浅主题切换 (cc-theme localStorage + data-theme)
  // 自包含: 读取/写入 DOM 的 data-theme 属性。
  let theme = $state(
    (() => {
      try {
        return document.documentElement.getAttribute('data-theme') || 'light';
      } catch {
        return 'light';
      }
    })()
  );

  function toggle() {
    theme = theme === 'light' ? 'dark' : 'light';
    try {
      document.documentElement.setAttribute('data-theme', theme);
      localStorage.setItem('cc-theme', theme);
    } catch {
      /* ignore */
    }
  }
</script>

<button
  class="theme-toggle"
  type="button"
  onclick={toggle}
  aria-label={theme === 'light' ? '切换到深色' : '切换到浅色'}
  title={theme === 'light' ? '深色模式' : '浅色模式'}
>
  {#key theme}
    <span class="theme-icon">
      {#if theme === 'light'}
        <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>
      {:else}
        <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/></svg>
      {/if}
    </span>
  {/key}
</button>

<style>
  .theme-toggle {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: var(--btn-h-md);
    height: var(--btn-h-md);
    padding: 0;
    border: 1px solid var(--btn-outline-border);
    background: var(--btn-outline-bg);
    color: var(--btn-outline-text);
    border-radius: var(--radius-full);
    cursor: pointer;
    transition: background var(--transition), border-color var(--transition),
      transform var(--transition), box-shadow var(--transition);
  }
  .theme-toggle:hover {
    background: var(--btn-outline-hover);
    border-color: var(--accent);
    color: var(--accent-strong);
    transform: scale(1.06);
  }
  .theme-toggle:active {
    transform: scale(0.92) rotate(-8deg);
  }
  .theme-toggle:focus-visible {
    outline: none;
    box-shadow: var(--focus-ring);
  }
  .theme-icon {
    display: inline-flex;
    animation: theme-pop var(--transition-snap);
  }
  @keyframes theme-pop {
    from { opacity: 0; transform: scale(0.6) rotate(-30deg); }
    to { opacity: 1; transform: scale(1) rotate(0deg); }
  }
</style>
