<script>
  // SettingsMoments.svelte — 朋友圈自动发布
  import SettingsShell from './SettingsShell.svelte';
  import EmptyState from './EmptyState.svelte';
  import Switch from '../Switch.svelte';
  import './settings-base.css';
  import { I } from './icons.js';
  import { momentsApi } from '../../lib/settingsApi.js';

  let { notify, onback } = $props();

  let moments = $state(null);
  let loaded = $state(false);
  let saving = $state(false);
  let publishing = $state(false);
  let form = $state({ enabled: false, interval_minutes: 60, persona_id: '', active_start: '', active_end: '' });

  $effect(() => {
    let alive = true;
    (async () => {
      const r = await momentsApi.config();
      if (!alive) return;
      if (r.ok && r.data) {
        moments = r.data;
        const c = r.data.config || {};
        form = {
          enabled: !!c.enabled,
          interval_minutes: c.interval_minutes ?? 60,
          persona_id: c.persona_id ?? '',
          active_start: c.active_start ?? '',
          active_end: c.active_end ?? '',
        };
      } else notify(errMsg(r, '加载失败'), 'error');
      loaded = true;
    })();
    return () => (alive = false);
  });

  function errMsg(err, fallback) {
    const m = err?.data?.error || err?.data?.message || err?.data?.detail || err?.data;
    if (typeof m === 'string' && m) return m;
    return fallback || (err?.status ? `请求失败（HTTP ${err.status}）` : String(err?.message ?? err));
  }

  async function submit(e) {
    e.preventDefault();
    saving = true;
    try {
      const body = { enabled: form.enabled, interval_minutes: parseInt(form.interval_minutes, 10) || 60 };
      if (form.persona_id) body.persona_id = form.persona_id;
      if (form.active_start) body.active_start = form.active_start;
      if (form.active_end) body.active_end = form.active_end;
      const r = await momentsApi.save(body);
      if (r.ok) notify('配置已保存', 'success');
      else notify(errMsg(r, '保存失败'), 'error');
    } finally { saving = false; }
  }

  async function manualPublish() {
    publishing = true;
    try {
      const r = await momentsApi.publish();
      if (r.ok) notify('已触发自动发布', 'success');
      else notify(errMsg(r, '发布失败'), 'error');
    } finally { publishing = false; }
  }
</script>

<SettingsShell title="朋友圈自动发布" desc="定时自动发布朋友圈" {onback}>
  {#if !loaded}
    <div class="card card-pad"><EmptyState icon="moments" title="正在加载…" compact /></div>
  {:else}
    <section class="card card-pad">
      <div class="section-head"><h4>自动发布配置</h4></div>
      <form class="form" onsubmit={submit}>
        <div class="switch-row"><span class="switch-label">启用自动发布</span><Switch checked={form.enabled} onchange={(v) => (form.enabled = v)} label="启用自动发布" /></div>
        <div class="field-row">
          <label class="field"><span>间隔（分钟）</span><input class="input" type="number" min="1" bind:value={form.interval_minutes} /></label>
          <label class="field"><span>Persona</span>
            <select class="input" bind:value={form.persona_id}>
              <option value="">（不指定）</option>
              {#each moments?.personas ?? [] as per}
                <option value={per.id}>{per.name || per.id}</option>
              {/each}
            </select>
          </label>
        </div>
        <div class="field-row">
          <label class="field"><span>开始时间</span><input class="input" type="time" bind:value={form.active_start} /></label>
          <label class="field"><span>结束时间</span><input class="input" type="time" bind:value={form.active_end} /></label>
        </div>
        <div class="form-actions">
          <button class="btn-primary" type="submit" disabled={saving}>
            {@html `<svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${I.check}</svg>`}
            保存配置
          </button>
        </div>
      </form>
    </section>

    <section class="card card-pad">
      <div class="section-head"><h4>手动发布</h4></div>
      <p class="hint" style="margin:0 0 var(--space-3)">立即执行一次自动发布逻辑。</p>
      <button class="btn-primary" type="button" onclick={manualPublish} disabled={publishing}>
        {@html `<svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${I.play}</svg>`}
        {publishing ? '发布中…' : '立即发布'}
      </button>
    </section>
  {/if}
</SettingsShell>

<style>
  .switch-row { display: flex; align-items: center; justify-content: space-between; gap: var(--space-3); padding: var(--space-2) 0; }
  .switch-label { font-size: var(--text-sm); color: var(--text-1); }
</style>
