<script>
  // SettingsMonitor.svelte — 系统监控 / 日志 (自动刷新)
  import SettingsShell from './SettingsShell.svelte';
  import EmptyState from './EmptyState.svelte';
  import Switch from '../Switch.svelte';
  import './settings-base.css';
  import { I } from './icons.js';
  import { monitorApi } from '../../lib/monitorApi.js';

  let { notify, onback } = $props();

  let health = $state(null);
  let diag = $state(null);
  let monitorError = $state('');
  let monLoading = $state(false);
  let monLastRefresh = $state('');
  let autoRefresh = $state(true);

  let monTimer = null;
  const MONITOR_POLL_MS = 10000;

  let openDiag = $state(new Set());

  function fmtUptime(seconds) {
    if (typeof seconds !== 'number' || !isFinite(seconds)) return '—';
    const s = Math.max(0, Math.floor(seconds));
    const d = Math.floor(s / 86400);
    const h = Math.floor((s % 86400) / 3600);
    const m = Math.floor((s % 3600) / 60);
    const sec = s % 60;
    const pad = (n) => String(n).padStart(2, '0');
    const hm = `${pad(h)}:${pad(m)}:${pad(sec)}`;
    return d > 0 ? `${d} 天 ${hm}` : hm;
  }

  function opsList(ops) {
    if (!ops || typeof ops !== 'object') return [];
    return Object.entries(ops).filter(([, v]) => typeof v === 'number' || typeof v === 'string');
  }

  function toggleDiag(idx) {
    const next = new Set(openDiag);
    if (next.has(idx)) next.delete(idx);
    else next.add(idx);
    openDiag = next;
  }

  async function refreshMonitor() {
    monLoading = true;
    try {
      const [h, d] = await Promise.all([monitorApi.health(), monitorApi.diagnostics()]);
      let err = '';
      if (h.ok && h.data) health = h.data;
      else err = h.error ? `健康检查不可达：${h.error}` : `健康检查失败（HTTP ${h.status ?? '—'}）`;
      if (d.ok && d.data) diag = d.data;
      else err = err || (d.error ? `诊断检查不可达：${d.error}` : `诊断检查失败（HTTP ${d.status ?? '—'}）`);
      monitorError = err;
      if (!err) monLastRefresh = new Date().toLocaleTimeString('zh-CN', { hour12: false });
    } catch (e) {
      monitorError = String(e && e.message ? e.message : e);
    } finally {
      monLoading = false;
    }
  }

  // 进入页面启动轮询, 离开清理
  $effect(() => {
    refreshMonitor();
    monTimer = setInterval(() => { if (autoRefresh) refreshMonitor(); }, MONITOR_POLL_MS);
    return () => {
      if (monTimer) { clearInterval(monTimer); monTimer = null; }
    };
  });
</script>

<SettingsShell title="系统监控 / 日志" desc="运行状态、诊断检查与运维指标" {onback}>
  <div class="monitor-toolbar">
    <div class="switch-row"><span class="switch-label">自动刷新</span><Switch checked={autoRefresh} onchange={(v) => { autoRefresh = v; if (v) refreshMonitor(); }} label="自动刷新" /></div>
    <div class="toolbar-right">
      <span class="dim">{#if monLastRefresh}上次刷新 {monLastRefresh}{/if}{#if monLoading}{#if monLastRefresh} · {/if}刷新中…{/if}</span>
      <button class="btn-outline sm" type="button" onclick={refreshMonitor} disabled={monLoading}>
        {@html `<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${I.refresh}</svg>`}
        立即刷新
      </button>
    </div>
  </div>

  {#if monitorError}
    <div class="card card-pad mon-error">
      <span class="badge error">不可达</span>
      <span class="mon-error-text">{monitorError}</span>
    </div>
  {/if}

  {#if !health && !diag && !monitorError}
    <div class="card card-pad"><EmptyState icon="monitor" title="正在加载监控数据…" compact /></div>
  {:else}
    {#if health}
      <section class="card card-pad">
        <div class="section-head"><h4>健康概览</h4></div>
        <div class="health-grid">
          <div class="health-cell">
            <span class="health-k">状态</span>
            <span class="badge {health.ok ? 'ok' : 'error'}">{health.ok ? '正常' : '异常'}</span>
          </div>
          <div class="health-cell">
            <span class="health-k">模型数</span>
            <span class="health-v">{health.models ?? '—'}</span>
          </div>
          <div class="health-cell">
            <span class="health-k">MCP 服务器</span>
            <span class="health-v">{health.mcp_servers ?? '—'}</span>
          </div>
          <div class="health-cell">
            <span class="health-k">运行时长</span>
            <span class="health-v">{fmtUptime(health.runtime?.uptime_seconds)}</span>
          </div>
        </div>
      </section>
    {/if}

    {#if diag}
      <section class="card card-pad">
        <div class="section-head">
          <h4>诊断检查</h4>
          <div class="row-actions wrap">
            <span class="badge {diag.overall === 'ok' ? 'ok' : diag.overall === 'warn' ? 'warn' : 'error'}">整体 {diag.overall ?? '—'}</span>
            {#if diag.summary}
              <span class="dim">正常 {diag.summary.ok ?? 0} · 警告 {diag.summary.warn ?? 0} · 异常 {diag.summary.error ?? 0}</span>
            {/if}
          </div>
        </div>
        {#if !Array.isArray(diag.checks) || !diag.checks.length}
          <EmptyState icon="shield" title="暂无诊断检查项" compact />
        {:else}
          <div class="diag-checks">
            {#each diag.checks as c, ci}
              <div class="diag-check">
                <div class="diag-check-head">
                  <span class="badge {c.status === 'ok' ? 'ok' : c.status === 'warn' ? 'warn' : 'error'}">{c.status === 'ok' ? '正常' : c.status === 'warn' ? '警告' : (c.status || '未知')}</span>
                  <span class="diag-check-label">{c.label ?? c.id}</span>
                  {#if c.details !== undefined && c.details !== null}
                    <button class="icon-btn diag-toggle" class:on={openDiag.has(ci)} type="button" aria-label="展开详情" onclick={() => toggleDiag(ci)}>
                      {@html `<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${I.chevron}</svg>`}
                    </button>
                  {/if}
                </div>
                <p class="diag-check-msg">{c.message ?? ''}</p>
                {#if c.details !== undefined && c.details !== null && openDiag.has(ci)}
                  <pre class="payload compact">{JSON.stringify(c.details, null, 2)}</pre>
                {/if}
              </div>
            {/each}
          </div>
        {/if}
      </section>
    {/if}

    {#if health?.runtime?.operations && opsList(health.runtime.operations).length}
      <section class="card card-pad">
        <div class="section-head"><h4>操作计数</h4></div>
        <div class="ops-list">
          {#each opsList(health.runtime.operations) as [name, val]}
            <div class="ops-row">
              <span class="ops-name">{name}</span>
              <span class="ops-val">{val}</span>
            </div>
          {/each}
        </div>
      </section>
    {/if}
  {/if}
</SettingsShell>

<style>
  .monitor-toolbar { display: flex; align-items: center; justify-content: space-between; gap: var(--space-3); flex-wrap: wrap; }
  .monitor-toolbar .switch-row { padding: 0; }
  .switch-row { display: flex; align-items: center; justify-content: space-between; gap: var(--space-3); }
  .switch-label { font-size: var(--text-sm); color: var(--text-1); }
  .toolbar-right { display: flex; align-items: center; gap: var(--space-3); flex-wrap: wrap; }
  .mon-error { display: flex; align-items: center; gap: var(--space-3); border-color: var(--error); background: color-mix(in srgb, var(--error) 8%, var(--surface)); }
  .mon-error-text { font-size: var(--text-sm); color: var(--text-1); word-break: break-word; }

  .health-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: var(--space-3); }
  .health-cell { display: flex; flex-direction: column; gap: var(--space-1); padding: var(--space-3); border: 1px solid var(--border); border-radius: var(--radius); background: var(--surface-2); }
  .health-k { font-size: var(--text-xs); color: var(--text-3); }
  .health-v { font-size: var(--text-lg); font-weight: 700; color: var(--text-1); line-height: 1.2; word-break: break-word; }

  .diag-checks { display: flex; flex-direction: column; gap: var(--space-2); }
  .diag-check { padding: var(--space-3); border: 1px solid var(--border); border-radius: var(--radius); background: var(--surface); }
  .diag-check-head { display: flex; align-items: center; gap: var(--space-3); flex-wrap: wrap; }
  .diag-check-label { font-weight: 600; color: var(--text-1); font-size: var(--text-sm); flex: 1; word-break: break-word; }
  .diag-toggle { border: none; background: transparent; color: var(--text-3); transform: rotate(0deg); transition: transform var(--transition); flex: none; }
  .diag-toggle.on { transform: rotate(90deg); }
  .diag-check-msg { margin: var(--space-2) 0 0; font-size: var(--text-sm); color: var(--text-2); white-space: pre-wrap; word-break: break-word; }
  .payload { margin: 0; padding: var(--space-3); background: var(--surface-2); border: 1px solid var(--border); border-radius: var(--radius-sm); font-family: var(--font-mono); font-size: 0.78rem; overflow: auto; color: var(--text-2); white-space: pre-wrap; word-break: break-word; max-height: 240px; }
  .payload.compact { max-height: 200px; margin-top: var(--space-2); }

  .ops-list { display: flex; flex-direction: column; gap: var(--space-1); }
  .ops-row { display: flex; align-items: center; justify-content: space-between; gap: var(--space-3); padding: var(--space-2) var(--space-3); border: 1px solid var(--border); border-radius: var(--radius-sm); font-family: var(--font-mono); font-size: var(--text-xs); }
  .ops-name { color: var(--text-2); word-break: break-all; }
  .ops-val { color: var(--text-1); font-weight: 600; }

  @media (min-width: 560px) {
    .health-grid { grid-template-columns: repeat(4, 1fr); }
  }
</style>
