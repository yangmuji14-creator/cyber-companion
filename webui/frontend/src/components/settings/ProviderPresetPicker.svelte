<script>
  // ProviderPresetPicker.svelte — 内置服务商预设卡片
  // 数据源 GET /api/bootstrap/providers → { providers:[{key,label,description,base_url,default_model,env_key,provider}] }
  // 点选一张卡片回调 onselect(preset), 由父级自动填充新增提供商表单。
  // 全部使用 tokens 语义变量; 零第三方库。
  import './settings-base.css';
  import EmptyState from './EmptyState.svelte';
  import { bootstrapApi } from '../../lib/settingsApi.js';

  let { onselect, onloaded, notify } = $props();

  let presets = $state([]);
  let loading = $state(true);
  let selectedKey = $state(null);

  $effect(() => {
    let alive = true;
    load();
    return () => (alive = false);
    async function load() {
      loading = true;
      try {
        const r = await bootstrapApi.providers();
        if (!alive) return;
        if (r.ok && Array.isArray(r.data?.providers)) {
          presets = r.data.providers;
        } else if (r.ok && Array.isArray(r.data)) {
          presets = r.data;
        } else {
          notify ? notify('加载预设服务商失败', 'error') : null;
          presets = [];
        }
        onloaded?.(presets);
      } catch (e) {
        if (alive) { notify ? notify('加载预设服务商失败', 'error') : null; presets = []; }
      }
      if (alive) loading = false;
    }
  });

  function pick(p) {
    selectedKey = p.key;
    onselect?.(p);
  }
</script>

<div class="preset-block">
  <div class="preset-head">
    <span class="preset-title">预设服务商</span>
    <span class="preset-sub">点选一键填充下方表单</span>
  </div>

  {#if loading}
    <div class="preset-grid">
      {#each [1, 2, 3, 4] as _}
        <div class="preset-card skeleton" style="height: 88px;"></div>
      {/each}
    </div>
  {:else if !presets.length}
    <EmptyState icon="cpu" title="暂无预设服务商" desc="可直接在下方表单手动配置" compact />
  {:else}
    <div class="preset-grid">
      {#each presets as p}
        <button class="preset-card" class:on={p.key === selectedKey} type="button" onclick={() => pick(p)}>
          <span class="pc-head">
            <span class="pc-label">{p.label}</span>
            <span class="pc-key">{p.key}</span>
          </span>
          {#if p.description}<span class="pc-desc">{p.description}</span>{/if}
          <span class="pc-meta">
            <span class="pc-model">{p.default_model || '—'}</span>
            {#if p.env_key}<span class="pc-env">{p.env_key}</span>{/if}
          </span>
        </button>
      {/each}
    </div>
  {/if}
</div>

<style>
  .preset-block {
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
  }
  .preset-head {
    display: flex;
    align-items: baseline;
    gap: var(--space-2);
  }
  .preset-title { font-size: var(--text-sm); font-weight: 600; color: var(--text-1); }
  .preset-sub { font-size: var(--text-xs); color: var(--text-3); }

  .preset-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
    gap: var(--space-2);
  }

  .preset-card {
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    gap: var(--space-1);
    padding: var(--space-3);
    text-align: left;
    font-family: inherit;
    background: var(--row-bg);
    border: 1px solid var(--row-border);
    border-radius: var(--row-radius);
    cursor: pointer;
    transition: background var(--transition), border-color var(--transition), transform var(--transition);
  }
  .preset-card:hover { background: var(--row-hover); border-color: var(--accent); transform: translateY(-1px); }
  .preset-card.on { border-color: var(--accent); background: var(--tint); box-shadow: var(--focus-ring); }
  .preset-card:active { transform: scale(0.98); }

  .pc-head { display: flex; align-items: center; gap: var(--space-2); width: 100%; }
  .pc-label { font-weight: 600; font-size: var(--text-sm); color: var(--text-1); }
  .pc-key { margin-left: auto; font-size: var(--text-xs); color: var(--text-3); font-family: var(--font-mono); }
  .pc-desc { font-size: var(--text-xs); color: var(--text-2); line-height: var(--leading-snug); }
  .pc-meta { display: flex; align-items: center; gap: var(--space-2); flex-wrap: wrap; margin-top: var(--space-1); }
  .pc-model { font-size: var(--text-xs); font-family: var(--font-mono); color: var(--accent-strong); }
  .pc-env {
    font-size: var(--text-xs);
    font-family: var(--font-mono);
    color: var(--text-3);
    background: var(--surface-2);
    border: 1px solid var(--border);
    border-radius: var(--radius-full);
    padding: 1px var(--space-2);
  }
</style>
