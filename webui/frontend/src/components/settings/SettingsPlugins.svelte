<script>
  // SettingsPlugins.svelte — 插件 / 工具 (只读概览)
  import SettingsShell from './SettingsShell.svelte';
  import EmptyState from './EmptyState.svelte';
  import './settings-base.css';
  import { I } from './icons.js';
  import { pluginsApi } from '../../lib/settingsApi.js';

  let { notify, onback } = $props();

  let plugins = $state(null);
  let loaded = $state(false);

  $effect(() => {
    let alive = true;
    (async () => {
      const r = await pluginsApi.list();
      if (!alive) return;
      if (r.ok) plugins = r.data || {};
      else notify(errMsg(r, '加载插件失败'), 'error');
      loaded = true;
    })();
    return () => (alive = false);
  });

  function errMsg(err, fallback) {
    const m = err?.data?.error || err?.data?.message || err?.data?.detail || err?.data;
    if (typeof m === 'string' && m) return m;
    return fallback || (err?.status ? `请求失败（HTTP ${err.status}）` : String(err?.message ?? err));
  }
</script>

<SettingsShell title="插件 / 工具" desc="已安装的能力概览（只读）" {onback}>
  {#if !loaded}
    <div class="card card-pad"><EmptyState icon="puzzle" title="正在加载…" compact /></div>
  {:else if !plugins?.plugins?.length}
    <div class="card card-pad">
      <EmptyState icon="puzzle" title="暂无插件" desc="当前没有已安装的插件或工具能力" />
    </div>
  {:else}
    <section class="card card-pad">
      <div class="section-head">
        <h4>插件列表</h4>
        <span class="head-sub">{plugins.builtin_count ?? 0} 内置 · {plugins.mcp_count ?? 0} MCP</span>
      </div>
      <div class="card-list">
        {#each plugins.plugins as p}
          <div class="card-row">
            <span class="row-icon" aria-hidden="true">{@html `<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${I.puzzle}</svg>`}</span>
            <div class="row-main">
              <span class="row-title">{p.name}</span>
              {#if p.description}<span class="row-sub">{p.description}</span>{/if}
            </div>
            <span class="badge {p.source === 'builtin' ? 'info' : 'ok'}">{p.source === 'builtin' ? '内置' : (p.source ?? 'MCP')}</span>
          </div>
        {/each}
      </div>
      {#if plugins.mcp_status}<p class="hint">MCP 状态：{plugins.mcp_status}</p>{/if}
    </section>
  {/if}
</SettingsShell>
