<script>
  // SettingsAppearance.svelte — 主题与界面 (浅/深/跟随)
  import SettingsShell from './SettingsShell.svelte';
  import ThemeToggle from '../ThemeToggle.svelte';
  import './settings-base.css';
  import { I } from './icons.js';

  let { notify, onback } = $props();

  const THEME_MODES = [
    { value: 'light', icon: 'sun', label: '浅色', desc: '明亮奶油色调' },
    { value: 'dark', icon: 'moon', label: '深色', desc: '柔和夜间色调' },
    { value: 'system', icon: 'monitor', label: '跟随系统', desc: '自动匹配系统偏好' },
  ];

  let themeMode = $state((() => {
    try {
      const saved = localStorage.getItem('cc-theme');
      return saved === 'dark' || saved === 'light' || saved === 'system' ? saved : 'system';
    } catch { return 'system'; }
  })());

  function applyTheme(mode) {
    themeMode = mode;
    try {
      localStorage.setItem('cc-theme', mode);
      let effective = mode;
      if (mode === 'system') effective = window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
      document.documentElement.setAttribute('data-theme', effective);
      notify(mode === 'system' ? `已跟随系统（当前 ${effective === 'dark' ? '深色' : '浅色'}）` : `已切换到${mode === 'dark' ? '深色' : '浅色'}`, 'success');
    } catch { /* ignore */ }
  }

  function iconOf(mode) {
    const m = {
      sun: '<circle cx="12" cy="12" r="5"/><path d="M12 1v2M12 21v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M1 12h2M21 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42"/>',
      moon: '<path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/>',
      monitor: I.monitor,
    };
    return m[mode] || '';
  }
</script>

<SettingsShell title="主题与界面" desc="深浅色与跟随系统切换" {onback}>
  <section class="card card-pad">
    <div class="section-head"><h4>外观主题</h4></div>
    <div class="theme-options" role="radiogroup" aria-label="外观主题">
      {#each THEME_MODES as m}
        <button class="theme-opt {themeMode === m.value ? 'on' : ''}" type="button" role="radio" aria-checked={themeMode === m.value} onclick={() => applyTheme(m.value)}>
          <span class="theme-opt-main">
            <span class="theme-opt-icon" aria-hidden="true">{@html `<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${iconOf(m.value)}</svg>`}</span>
            <span class="theme-opt-txt">
              <span class="theme-opt-label">{m.label}</span>
              <span class="theme-opt-desc">{m.desc}</span>
            </span>
          </span>
          {#if themeMode === m.value}
            <svg viewBox="0 0 24 24" class="theme-check" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">{@html I.check}</svg>
          {/if}
        </button>
      {/each}
    </div>
    <p class="hint">选择会记忆到本机（cc-theme）。</p>
    <div class="quick-toggle card-row">
      <div class="row-main">
        <span class="row-title">快速切换</span>
        <span class="row-sub">在浅色与深色间切换</span>
      </div>
      <ThemeToggle />
    </div>
  </section>
</SettingsShell>

<style>
  .theme-options { display: flex; flex-direction: column; gap: var(--space-2); }
  .theme-opt {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--space-3);
    padding: var(--space-3) var(--space-4);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    background: var(--surface);
    cursor: pointer;
    transition: border-color var(--transition), background var(--transition), transform var(--transition);
    font-family: inherit;
  }
  .theme-opt:hover { background: var(--row-hover); }
  .theme-opt:active { transform: scale(0.99); }
  .theme-opt.on { border-color: var(--accent); background: var(--tint); }
  .theme-opt-main { display: flex; align-items: center; gap: var(--space-3); }
  .theme-opt-icon {
    display: inline-flex; align-items: center; justify-content: center;
    width: 34px; height: 34px; border-radius: var(--radius);
    background: var(--surface-2); color: var(--text-2);
  }
  .theme-opt.on .theme-opt-icon { background: var(--accent-soft); color: var(--accent-strong); }
  .theme-opt-txt { display: flex; flex-direction: column; gap: 1px; text-align: left; }
  .theme-opt-label { font-weight: 600; color: var(--text-1); font-size: var(--text-sm); }
  .theme-opt-desc { font-size: var(--text-xs); color: var(--text-3); }
  .theme-check { flex: none; color: var(--accent); }

  .quick-toggle { margin-top: var(--space-3); }
  .quick-toggle > :global(.theme-toggle) { flex: none; }
</style>
