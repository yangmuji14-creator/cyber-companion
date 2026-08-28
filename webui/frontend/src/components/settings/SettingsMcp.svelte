<script>
  // SettingsMcp.svelte — MCP 扩展 (服务器 CRUD + 连接管理 + 工具查看)
  import SettingsShell from './SettingsShell.svelte';
  import EmptyState from './EmptyState.svelte';
  import './settings-base.css';
  import { I } from './icons.js';
    import { mcpApi } from '../../lib/settingsApi.js';
    import { confirmDialog } from '../../lib/dialog.svelte.js';

  let { notify, onback } = $props();

  let servers = $state([]);
  let connectedNames = $state(new Set());
  let loaded = $state(false);
  let saving = $state(false);

  let editing = $state(null);
  let form = $state({ name: '', command: '', args: '' });

  let toolsFor = $state(null);
  let toolsList = $state([]);
  let toolsLoading = $state(false);

  $effect(() => {
    let alive = true;
    refresh();
    return () => (alive = false);
    async function refresh() {
      const r = await mcpApi.list();
      if (!alive) return;
      if (r.ok && Array.isArray(r.data?.servers)) {
        servers = r.data.servers.map((s) => ({
          ...s,
          statusKind: (s.status || '').toLowerCase().includes('error') ? 'error'
            : (s.status || '').toLowerCase().includes('connect') ? 'ok' : '',
        }));
        connectedNames = new Set(servers.filter((s) => (s.status || '').toLowerCase().includes('connect')).map((s) => s.name));
      } else notify(errMsg(r, '加载 MCP 失败'), 'error');
      loaded = true;
    }
  });

  function errMsg(err, fallback) {
    const m = err?.data?.error || err?.data?.message || err?.data?.detail || err?.data;
    if (typeof m === 'string' && m) return m;
    return fallback || (err?.status ? `请求失败（HTTP ${err.status}）` : String(err?.message ?? err));
  }

  async function refresh() {
    const r = await mcpApi.list();
    if (r.ok && Array.isArray(r.data?.servers)) {
      servers = r.data.servers.map((s) => ({
        ...s,
        statusKind: (s.status || '').toLowerCase().includes('error') ? 'error'
          : (s.status || '').toLowerCase().includes('connect') ? 'ok' : '',
      }));
      connectedNames = new Set(servers.filter((s) => (s.status || '').toLowerCase().includes('connect')).map((s) => s.name));
    }
  }

  function startEdit(s) {
    editing = s;
    form = {
      name: s?.name ?? '',
      command: s?.command ?? '',
      args: Array.isArray(s?.args) ? s.args.join(' ') : (s?.args ?? ''),
    };
  }

  async function submit(e) {
    e.preventDefault();
    saving = true;
    try {
      const body = { name: form.name, command: form.command };
      if (form.args.trim()) body.args = form.args.split(' ').filter(Boolean);
      const isEdit = !!editing?.name;
      const r = isEdit ? await mcpApi.edit(editing.name, body) : await mcpApi.add(body);
      if (r.ok) { notify(isEdit ? '已更新' : '已添加', 'success'); editing = null; refresh(); }
      else notify(errMsg(r, '保存失败'), 'error');
    } finally { saving = false; }
  }

  async function remove(name) {
    const ok = await confirmDialog(`删除 MCP 服务器 ${name}？`, { title: '删除 MCP', danger: true });
    if (!ok) return;
    try {
      const r = await mcpApi.remove(name);
      if (r.ok) { notify('已删除', 'success'); refresh(); }
      else notify(errMsg(r, '删除失败'), 'error');
    } catch (e) { notify(errMsg(e, '删除失败'), 'error'); }
  }

  async function action(name, act) {
    saving = true;
    try {
      const r = await mcpApi.action(name, act);
      if (r.ok) notify(`${act} 成功`, 'success');
      else notify(errMsg(r, `${act} 失败`), 'error');
      refresh();
    } catch (e) { notify(errMsg(e, `${act} 失败`), 'error'); }
    finally { saving = false; }
  }

  async function viewTools(name) {
    toolsFor = name;
    toolsList = [];
    toolsLoading = true;
    try {
      const r = await mcpApi.tools(name);
      toolsList = (r.ok && Array.isArray(r.data?.tools)) ? r.data.tools : (r.ok && Array.isArray(r.data) ? r.data : []);
      if (!r.ok) notify(errMsg(r, '加载工具失败'), 'error');
    } catch { /* ignore */ }
    finally { toolsLoading = false; }
  }
</script>

<SettingsShell title="MCP 扩展" desc="管理 MCP 服务器与外部能力" {onback}>
  <section class="card card-pad">
    <div class="section-head">
      <h4>MCP 服务器</h4>
      <button class="btn-primary sm" type="button" onclick={() => startEdit(null)}>
        {@html `<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${I.plus}</svg>`}
        新增
      </button>
    </div>

    {#if !loaded}
      <EmptyState icon="plug" title="正在加载…" compact />
    {:else if !servers.length}
      <EmptyState icon="plug" title="暂无 MCP 服务器" desc="点「新增」接入外部能力服务器" compact>
        <button class="btn-primary" type="button" onclick={() => startEdit(null)}>新增服务器</button>
      </EmptyState>
    {:else}
      <div class="card-list">
        {#each servers as s}
          <div class="card-row">
            <span class="row-icon" aria-hidden="true">{@html `<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${I.plug}</svg>`}</span>
            <div class="row-main">
              <span class="row-title">{s.name}</span>
              <span class="row-sub">{(s.command ?? '—') + (s.args?.length ? ' ' + s.args.join(' ') : '')}</span>
              {#if s.status}<span class="badge {s.statusKind}">{s.status}</span>{/if}
            </div>
            <div class="row-actions wrap">
              {#if connectedNames.has(s.name)}
                <button class="btn-outline sm" type="button" onclick={() => action(s.name, 'disconnect')}>断开</button>
              {:else}
                <button class="btn-outline sm" type="button" onclick={() => action(s.name, 'connect')}>连接</button>
              {/if}
              <button class="btn-outline sm" type="button" onclick={() => action(s.name, 'test')}>测试</button>
              <button class="btn-outline sm" type="button" onclick={() => action(s.name, 'refresh')}>刷新</button>
              <button class="btn-outline sm" type="button" onclick={() => viewTools(s.name)}>工具</button>
              <button class="btn-outline sm" type="button" onclick={() => startEdit(s)}>编辑</button>
              <button class="icon-btn danger" type="button" title="删除" onclick={() => remove(s.name)}>
                {@html `<svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${I.trash}</svg>`}
              </button>
            </div>
          </div>
        {/each}
      </div>
    {/if}
  </section>

  {#if editing}
    <section class="card card-pad">
      <div class="section-head"><h4>{editing.name ? `编辑 ${editing.name}` : '新增 MCP 服务器'}</h4></div>
      <form class="form" onsubmit={submit}>
        <label class="field"><span>名称</span><input class="input" type="text" bind:value={form.name} placeholder="如 filesystem" required disabled={!!editing.name} /></label>
        <label class="field"><span>命令</span><input class="input" type="text" bind:value={form.command} placeholder="如 npx" required /></label>
        <label class="field"><span>参数</span><input class="input" type="text" bind:value={form.args} placeholder="如 -y @modelcontextprotocol/server-filesystem ./" /></label>
        <div class="form-actions">
          <button class="btn-outline" type="button" onclick={() => (editing = null)}>取消</button>
          <button class="btn-primary" type="submit" disabled={saving}>保存</button>
        </div>
      </form>
    </section>
  {/if}

  {#if toolsFor}
    <section class="card card-pad">
      <div class="section-head">
        <h4>{toolsFor} · 工具</h4>
        <button class="icon-btn" type="button" onclick={() => (toolsFor = null)}>
          {@html `<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${I.close}</svg>`}
        </button>
      </div>
      {#if toolsLoading}
        <p class="hint">加载中…</p>
      {:else if toolsList.length}
        <div class="tools-grid">
          {#each toolsList as t}
            <div class="tool-chip">
              <span class="tool-name">{t.name}</span>
              {#if t.description}<span class="tool-desc">{t.description}</span>{/if}
            </div>
          {/each}
        </div>
      {:else}
        <EmptyState icon="puzzle" title="暂无工具" compact />
      {/if}
    </section>
  {/if}
</SettingsShell>

<style>
  .tools-grid { display: flex; flex-wrap: wrap; gap: var(--space-2); }
  .tool-chip { display: flex; flex-direction: column; gap: 2px; padding: var(--space-2) var(--space-3); border: 1px solid var(--border); border-radius: var(--radius); background: var(--surface-2); }
  .tool-name { font-weight: 600; font-size: var(--text-xs); color: var(--text-1); }
  .tool-desc { font-size: var(--text-xs); color: var(--text-3); max-width: 220px; }
</style>
