<script>
  // SettingsData.svelte — 数据与关于 (诊断 / 备份 / 恢复 / 关于)
  import SettingsShell from './SettingsShell.svelte';
  import EmptyState from './EmptyState.svelte';
  import './settings-base.css';
  import { I } from './icons.js';
  import { diagApi } from '../../lib/settingsApi.js';
  import { confirmDialog } from '../../lib/dialog.svelte.js';

  let { notify, onback } = $props();

  let diagReport = $state(null);
  let diagText = $state('');
  let diagOk = $state(true);
  let diagLoading = $state(false);

  let about = $state(null);

  let restoreFile = $state('');

  $effect(() => {
    let alive = true;
    (async () => {
      const r = await diagApi.about();
      if (alive && r.ok) about = r.data || {};
    })();
    return () => (alive = false);
  });

  function errMsg(err, fallback) {
    const m = err?.data?.error || err?.data?.message || err?.data?.detail || err?.data;
    if (typeof m === 'string' && m) return m;
    return fallback || (err?.status ? `请求失败（HTTP ${err.status}）` : String(err?.message ?? err));
  }

  async function runDiag() {
    diagLoading = true;
    diagReport = null;
    try {
      const r = await diagApi.report();
      diagReport = r.ok ? r.data : { error: errMsg(r, '诊断失败') };
      diagText = JSON.stringify(diagReport, null, 2);
      diagOk = !!r.ok && !r.data?.error;
    } catch (e) { const v = { error: String(e) }; diagReport = v; diagText = JSON.stringify(v, null, 2); diagOk = false; }
    finally { diagLoading = false; }
  }

  async function exportDiag() {
    try {
      const r = await diagApi.export();
      if (!r.ok) notify(errMsg(r, '导出失败'), 'error');
      else notify('诊断已导出', 'success');
    } catch (e) { notify(errMsg(e, '导出失败'), 'error'); }
  }

  async function backup() {
    try {
      const r = await diagApi.backup();
      if (!r.ok) notify(errMsg(r, '备份失败'), 'error');
      else notify('备份已下载', 'success');
    } catch (e) { notify(errMsg(e, '备份失败'), 'error'); }
  }

  async function restore(e) {
    const file = e.currentTarget.files?.[0];
    if (!file) return;
    restoreFile = file.name;
    const ok = await confirmDialog(`确定用 ${file.name} 恢复数据？此操作将覆盖当前数据。`, { title: '恢复数据', danger: true });
    if (!ok) { restoreFile = ''; e.currentTarget.value = ''; return; }
    try {
      const r = await diagApi.restore(file);
      if (r.ok) notify('恢复成功', 'success');
      else notify(errMsg(r, '恢复失败'), 'error');
    } catch (err) { notify(errMsg(err, '恢复失败'), 'error'); }
    finally { restoreFile = ''; e.currentTarget.value = ''; }
  }
</script>

<SettingsShell title="数据与关于" desc="诊断报告、备份与恢复、关于信息" {onback}>
  <section class="card card-pad">
    <div class="section-head">
      <h4>诊断中心</h4>
      <div class="row-actions">
        <button class="btn-outline sm" type="button" onclick={runDiag} disabled={diagLoading}>{diagLoading ? '诊断中…' : '运行诊断'}</button>
        <button class="btn-outline sm" type="button" onclick={exportDiag}>
          {@html `<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${I.download}</svg>`}
          导出
        </button>
      </div>
    </div>
    {#if diagLoading}
      <EmptyState icon="gauge" title="正在诊断…" compact />
    {:else if diagReport === null}
      <EmptyState icon="gauge" title="尚未诊断" desc="点击「运行诊断」生成系统健康报告" />
    {:else}
      <div class="diag-short">
        <span class="badge {diagOk ? 'ok' : 'error'}">整体 {diagOk ? '正常' : '有异常'}</span>
        {#if diagReport.timestamp}<span class="dim">{diagReport.timestamp}</span>{/if}
      </div>
      <details class="diag-details" open>
        <summary>查看 JSON 报告</summary>
        <pre class="payload">{diagText}</pre>
      </details>
    {/if}
  </section>

  <section class="card card-pad">
    <div class="section-head"><h4>备份与恢复</h4></div>
    <div class="backup-actions">
      <button class="btn-primary" type="button" onclick={backup}>
        {@html `<svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${I.download}</svg>`}
        下载备份
      </button>
      <label class="btn-outline file-btn">
        {@html `<svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${I.upload}</svg>`}
        选择备份文件
        <input type="file" accept=".zip,application/zip" hidden onchange={restore} />
      </label>
      {#if restoreFile}<span class="dim">{restoreFile}</span>{/if}
    </div>
    <p class="hint">恢复将覆盖当前数据，请谨慎操作。</p>
  </section>

  <section class="card card-pad">
    <div class="section-head"><h4>关于</h4></div>
    {#if !about}
      <p class="hint">正在加载…</p>
    {:else}
      <div class="about-grid">
        {#if about.name}<div class="about-item"><span class="about-k">名称</span><span class="about-v">{about.name}</span></div>{/if}
        {#if about.version}<div class="about-item"><span class="about-k">版本</span><span class="about-v">{about.version}</span></div>{/if}
        {#if about.license}<div class="about-item"><span class="about-k">许可证</span><span class="about-v">{about.license}</span></div>{/if}
      </div>
      {#if about.extra}
        <pre class="payload compact">{JSON.stringify(about.extra, null, 2)}</pre>
      {/if}
    {/if}
  </section>
</SettingsShell>

<style>
  .diag-short { display: flex; align-items: center; gap: var(--space-3); margin-bottom: var(--space-3); }
  .diag-details { border: 1px solid var(--border); border-radius: var(--radius); background: var(--surface-2); overflow: hidden; }
  .diag-details summary { cursor: pointer; padding: var(--space-2) var(--space-3); font-size: var(--text-sm); color: var(--text-2); }
  .payload { margin: 0; padding: var(--space-3); background: var(--surface-2); border: 1px solid var(--border); border-radius: var(--radius-sm); font-family: var(--font-mono); font-size: 0.78rem; overflow: auto; color: var(--text-2); white-space: pre-wrap; word-break: break-word; max-height: 320px; }
  .payload.compact { max-height: 220px; margin-top: var(--space-3); }

  .backup-actions { display: flex; align-items: center; gap: var(--space-3); flex-wrap: wrap; }
  .file-btn { position: relative; cursor: pointer; }
  .file-btn input { position: absolute; inset: 0; opacity: 0; cursor: pointer; }

  .about-grid { display: flex; flex-direction: column; gap: var(--space-2); }
  .about-item { display: flex; gap: var(--space-3); padding: var(--space-2) 0; border-bottom: 1px solid var(--border); }
  .about-item:last-child { border-bottom: none; }
  .about-k { flex: none; width: 72px; font-size: var(--text-sm); color: var(--text-3); }
  .about-v { font-size: var(--text-sm); color: var(--text-1); word-break: break-all; }
</style>
