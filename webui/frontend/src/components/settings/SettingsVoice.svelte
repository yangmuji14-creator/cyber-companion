<script>
  // SettingsVoice.svelte — 语音服务商 (TTS + 试听)
  import SettingsShell from './SettingsShell.svelte';
  import EmptyState from './EmptyState.svelte';
  import Switch from '../Switch.svelte';
  import './settings-base.css';
  import { I } from './icons.js';
  import { voiceApi } from '../../lib/settingsApi.js';
  import { confirmDialog } from '../../lib/dialog.svelte.js';

  let { notify, onback } = $props();

  let providers = $state([]);
  let loaded = $state(false);
  let saving = $state(false);

  let editing = $state(null);
  let form = $state({ name: '', type: '', base_url: '', api_key: '', model: '', voice: '', enabled: true });

  let synthText = $state('你好，这是语音合成试听。');
  let synthUrl = $state('');

  $effect(() => {
    let alive = true;
    refresh();
    return () => (alive = false);
    async function refresh() {
      const r = await voiceApi.list();
      if (!alive) return;
      if (r.ok && Array.isArray(r.data?.providers)) providers = r.data.providers;
      else notify(errMsg(r, '加载服务商失败'), 'error');
      loaded = true;
    }
  });

  function errMsg(err, fallback) {
    const m = err?.data?.error || err?.data?.message || err?.data?.detail || err?.data;
    if (typeof m === 'string' && m) return m;
    return fallback || (err?.status ? `请求失败（HTTP ${err.status}）` : String(err?.message ?? err));
  }

  async function refresh() {
    const r = await voiceApi.list();
    if (r.ok && Array.isArray(r.data?.providers)) providers = r.data.providers;
  }

  function startEdit(v) {
    editing = v;
    form = {
      name: v?.name ?? '',
      type: v?.type ?? '',
      base_url: v?.base_url ?? '',
      api_key: '',
      model: v?.model ?? '',
      voice: v?.voice ?? '',
      enabled: v ? (v.enabled ?? true) : true,
    };
  }

  async function submit(e) {
    e.preventDefault();
    saving = true;
    try {
      const body = { name: form.name };
      ['type', 'base_url', 'model', 'voice', 'enabled'].forEach((k) => {
        if (form[k] !== undefined && form[k] !== '') body[k] = form[k];
      });
      if (form.api_key) body.api_key = form.api_key;
      const isEdit = !!editing?.name;
      const r = isEdit ? await voiceApi.edit(editing.name, body) : await voiceApi.add(body);
      if (r.ok) { notify(isEdit ? '已更新' : '已添加', 'success'); editing = null; refresh(); }
      else notify(errMsg(r, '保存失败'), 'error');
    } finally { saving = false; }
  }

  async function remove(name) {
    const ok = await confirmDialog(`删除服务商 ${name}？`, { title: '删除服务商', danger: true });
    if (!ok) return;
    try {
      const r = await voiceApi.remove(name);
      if (r.ok) { notify('已删除', 'success'); refresh(); }
      else notify(errMsg(r, '删除失败'), 'error');
    } catch (e) { notify(errMsg(e, '删除失败'), 'error'); }
  }

  async function voiceTest(name) {
    try {
      const r = await voiceApi.test(name);
      if (r.ok) notify('测试通过', 'success');
      else notify(errMsg(r, '测试失败'), 'error');
    } catch (e) { notify(errMsg(e, '测试失败'), 'error'); }
  }

  function synthListen() {
    synthUrl = voiceApi.synthesizeUrl(synthText, providers[0]?.voice || '');
  }
</script>

<SettingsShell
  title="语音服务商"
  desc="TTS 服务商配置与试听"
  {onback}
>
  <section class="card card-pad">
    <div class="section-head">
      <h4>服务商</h4>
      <button class="btn-primary sm" type="button" onclick={() => startEdit(null)}>
        {@html `<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${I.plus}</svg>`}
        新增
      </button>
    </div>

    {#if !loaded}
      <EmptyState icon="voice" title="正在加载…" compact />
    {:else if !providers.length}
      <EmptyState icon="voice" title="暂无服务商" desc="点「新增」配置 TTS 服务商" compact>
        <button class="btn-primary" type="button" onclick={() => startEdit(null)}>新增服务商</button>
      </EmptyState>
    {:else}
      <div class="card-list">
        {#each providers as v}
          <div class="card-row">
            <span class="row-icon" aria-hidden="true">{@html `<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${I.voice}</svg>`}</span>
            <div class="row-main">
              <span class="row-title">{v.name}{#if v.type}<span class="dim"> · {v.type}</span>{/if}</span>
              <span class="row-sub">
                {(v.model || v.voice) ? `${v.model ?? ''}${v.voice ? ' / ' + v.voice : ''}` : (v.base_url || '未配置')}
                {#if v.enabled}<span class="badge ok">启用</span>{/if}
              </span>
            </div>
            <div class="row-actions wrap">
              <button class="btn-outline sm" type="button" onclick={() => voiceTest(v.name)}>测试</button>
              <button class="btn-outline sm" type="button" onclick={() => startEdit(v)}>编辑</button>
              <button class="icon-btn danger" type="button" title="删除" onclick={() => remove(v.name)}>
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
      <div class="section-head"><h4>{editing.name ? `编辑 ${editing.name}` : '新增服务商'}</h4></div>
      <form class="form" onsubmit={submit}>
        <div class="field-row">
          <label class="field"><span>名称</span><input class="input" type="text" bind:value={form.name} required disabled={!!editing.name} /></label>
          <label class="field"><span>类型</span><input class="input" type="text" bind:value={form.type} placeholder="如 edge / openai" /></label>
        </div>
        <div class="field-row">
          <label class="field"><span>Base URL</span><input class="input" type="text" bind:value={form.base_url} /></label>
          <label class="field"><span>API Key</span><input class="input" type="password" bind:value={form.api_key} /></label>
        </div>
        <div class="field-row">
          <label class="field"><span>模型</span><input class="input" type="text" bind:value={form.model} /></label>
          <label class="field"><span>音色</span><input class="input" type="text" bind:value={form.voice} /></label>
        </div>
        <div class="switch-row"><span class="switch-label">启用</span><Switch checked={form.enabled} onchange={(v) => (form.enabled = v)} label="启用" /></div>
        <div class="form-actions">
          <button class="btn-outline" type="button" onclick={() => (editing = null)}>取消</button>
          <button class="btn-primary" type="submit" disabled={saving}>保存</button>
        </div>
      </form>
    </section>
  {/if}

  <section class="card card-pad">
    <div class="section-head"><h4>试听（合成）</h4></div>
    <div class="form">
      <label class="field"><span>文本</span><input class="input" type="text" bind:value={synthText} placeholder="你好，这是语音合成试听。" /></label>
      <div class="form-actions">
        <button class="btn-primary" type="button" onclick={synthListen}>
          {@html `<svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${I.play}</svg>`}
          试听
        </button>
        {#if synthUrl}
          <audio controls src={synthUrl} style="flex:1"></audio>
        {/if}
      </div>
    </div>
  </section>
</SettingsShell>

<style>
  .switch-row { display: flex; align-items: center; justify-content: space-between; gap: var(--space-3); padding: var(--space-2) 0; }
  .switch-label { font-size: var(--text-sm); color: var(--text-1); }
</style>
