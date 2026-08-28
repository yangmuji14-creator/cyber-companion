<script>
  // SettingsModel.svelte — 模型设置
  // 服务商卡片列表 + 当前模型高亮 + 新增/删除 + 发现模型 + 视觉模型
  import SettingsShell from './SettingsShell.svelte';
  import EmptyState from './EmptyState.svelte';
  import ProviderPresetPicker from './ProviderPresetPicker.svelte';
  import SamplingPresets from './SamplingPresets.svelte';
  import UrlPreview from './UrlPreview.svelte';
  import './settings-base.css';
  import { I } from './icons.js';
  import { modelApi, visionApi, bootstrapApi } from '../../lib/settingsApi.js';
  import { confirmDialog } from '../../lib/dialog.svelte.js';

  let { notify, onback } = $props();

  let model = $state(null);
  let providers = $state([]);
  let loading = $state(true);
  let saving = $state(false);

  let showAddProvider = $state(false);
  let pf = $state({ key: '', provider: '', model_name: '', base_url: '', api_key: '', temperature: null, max_tokens: null, presence_penalty: null, frequency_penalty: null });
  let disc = $state({ base_url: '', api_key: '' });
  let vision = $state({ provider: '', model_name: '', base_url: '', api_key: '' });

  // 预设服务商 catalog key 集合 (来自 /api/bootstrap/providers)
  let catalogKeys = $state([]);
  // 连接与测试反馈  let testState = $state('idle'); // idle | testing | ok | fail
  let testMsg = $state('');

  $effect(() => {
    let alive = true;
    load();
    return () => (alive = false);
    async function load() {
      loading = true;
      try {
        const r = await modelApi.get();
        if (!alive) return;
        if (r.ok) {
          model = r.data || {};
          const avail = Array.isArray(r.data?.available) ? r.data.available : [];
          if (avail.length && typeof avail[0] === 'object') {
            providers = avail;
            model.available = avail.map((a) => a.key ?? a.model_name ?? a.provider);
          } else {
            providers = avail.map((k) => ({ key: k, provider: k, model_name: k, base_url: r.data?.base_url }));
          }
        } else notify(errMsg(r, '加载模型配置失败'), 'error');
      } catch (e) { notify(errMsg(e, '加载模型配置失败'), 'error'); }

      const rv = await visionApi.get();
      if (alive && rv.ok && rv.data) {
        vision = { provider: rv.data.provider ?? '', model_name: rv.data.model_name ?? '', base_url: rv.data.base_url ?? '', api_key: '' };
      }
      if (alive) loading = false;
    }
  });

  function errMsg(err, fallback) {
    const m = err?.data?.error || err?.data?.message || err?.data?.detail || err?.data;
    if (typeof m === 'string' && m) return m;
    return fallback || (err?.status ? `请求失败（HTTP ${err.status}）` : String(err?.message ?? err));
  }

  async function switchModel(key) {
    saving = true;
    try {
      const r = await modelApi.set(key);
      if (r.ok) { model.current = key; notify('已切换当前模型', 'success'); }
      else notify(errMsg(r, '切换失败'), 'error');
    } finally { saving = false; }
  }

  async function submitProvider(e) {
    e.preventDefault();
    saving = true;
    try {
      const body = {};
      for (const [k, v] of Object.entries(pf)) {
        if (v === '' || v === null || v === undefined) continue;
        body[k] = v;
      }
      const r = await modelApi.addProvider(body);
      if (r.ok) {
        notify('提供商已添加', 'success');
        showAddProvider = false;
        await reloadModels();
      } else notify(errMsg(r, '添加失败'), 'error');
    } finally { saving = false; }
  }

  async function removeProvider(key) {
    const ok = await confirmDialog(`删除提供商 ${key}？`, { title: '删除服务商', danger: true });
    if (!ok) return;
    saving = true;
    try {
      const r = await modelApi.remove(key);
      if (r.ok) {
        notify('已删除', 'success');
        providers = providers.filter((p) => p.key !== key);
        if (model?.available) model.available = model.available.filter((k) => k !== key);
      } else notify(errMsg(r, '删除失败'), 'error');
    } finally { saving = false; }
  }

  async function submitDiscover(e) {
    e.preventDefault();
    saving = true;
    try {
      const r = await modelApi.discover(disc.base_url, disc.api_key);
      if (r.ok) { notify('发现完成', 'success'); await reloadModels(); }
      else notify(errMsg(r, '发现失败'), 'error');
    } finally { saving = false; }
  }

  async function submitVision(e) {
    e.preventDefault();
    saving = true;
    try {
      const body = { model_name: vision.model_name };
      if (vision.provider) body.provider = vision.provider;
      if (vision.base_url) body.base_url = vision.base_url;
      if (vision.api_key) body.api_key = vision.api_key;
      const r = await visionApi.set(body);
      if (r.ok) notify('视觉配置已保存', 'success');
      else notify(errMsg(r, '保存失败'), 'error');
    } finally { saving = false; }
  }

  async function reloadModels() {
    loading = true;
    model = null;
    providers = [];
    try {
      const r = await modelApi.get();
      if (r.ok) {
        model = r.data || {};
        const avail = Array.isArray(r.data?.available) ? r.data.available : [];
        if (avail.length && typeof avail[0] === 'object') {
          providers = avail;
          model.available = avail.map((a) => a.key ?? a.model_name ?? a.provider);
        } else {
          providers = avail.map((k) => ({ key: k, provider: k, model_name: k, base_url: r.data?.base_url }));
        }
      }
    } catch { /* ignore */ }
    loading = false;
  }

  function resetPf() {
    pf = { key: '', provider: '', model_name: '', base_url: '', api_key: '', temperature: null, max_tokens: null, presence_penalty: null, frequency_penalty: null };
    testState = 'idle';
    testMsg = '';
  }

  function applyPreset(p) {
    pf = {
      key: p.key ?? '',
      provider: p.provider ?? p.key ?? '',
      model_name: p.default_model ?? '',
      base_url: p.base_url ?? '',
      api_key: '',
      temperature: null,
      max_tokens: null,
      presence_penalty: null,
      frequency_penalty: null,
    };
    testState = 'idle';
    testMsg = '';
  }

  // 采样预设: 仅当 values 非空(命中命名档位)才覆盖手填值 自定义(null)不动表单
  function applySampling(values) {
    if (!values) return;
    pf = { ...pf, ...values };
  }

  function onPresetsLoaded(list) {
    catalogKeys = (Array.isArray(list) ? list : []).map((p) => p.key).filter(Boolean);
  }

  async function testConnection() {
    if (!pf.provider) {
      testState = 'fail';
      testMsg = '请先填写 Provider（或从预设服务商中选择）';
      return;
    }
    // 非 catalog 预设 → 提示不支持在线测试 不调后端
    if (!catalogKeys.includes(pf.key)) {
      testState = 'fail';
      testMsg = '该服务商暂不支持在线测试';
      return;
    }
    testState = 'testing';
    testMsg = '';
    try {
      const body = { provider: pf.provider };
      if (pf.base_url) body.base_url = pf.base_url;
      if (pf.api_key) body.api_key = pf.api_key;
      if (pf.model_name) body.model_name = pf.model_name;
      const r = await bootstrapApi.test(body);
      if (r.ok) {
        const ok = r.data?.ok !== false;
        // HTTP 200 = ok; 消息取后端 message 或成功文案        testState = ok ? 'ok' : 'fail';
        testMsg = ok
          ? (r.data?.message && typeof r.data.message === 'string' ? r.data.message : '连接成功')
          : (typeof r.data?.message === 'string' ? r.data.message : '连接失败');
      } else {
        const m = errMsg(r, '连接失败');
        testState = 'fail';
        testMsg = m.includes('暂不支持') ? '该服务商暂不支持在线测试' : m;
      }
    } catch (e) {
      testState = 'fail';
      testMsg = errMsg(e, '连接失败');
    }
  }
</script>

<SettingsShell title="模型设置" desc="切换模型、管理提供商、发现与视觉模型" {onback}>
  {#if loading}
    <div class="card card-pad">
      <EmptyState icon="cpu" title="正在加载模型配置…" compact />
    </div>
  {:else}
    {#if model?.available?.length}
      <section class="card card-pad">
        <div class="section-head">
          <h4>切换当前模型</h4>
          <span class="head-sub">{model.current ? `当前：{model.current}` : '未选择'}</span>
        </div>
        <div class="card-list">
          {#each model.available as key}
            <button class="card-row model-row" class:on={key === model.current} type="button" onclick={() => switchModel(key)} disabled={saving}>
              <span class="row-main">
                <span class="row-title model-key">{key}</span>
              </span>
              {#if key === model.current}<span class="badge ok">当前</span>{/if}
            </button>
          {/each}
        </div>
      </section>
    {/if}

    <section class="card card-pad">
      <div class="section-head">
        <h4>提供商列表</h4>
        <button class="btn-primary sm" type="button" onclick={() => { resetPf(); showAddProvider = !showAddProvider; }}>{showAddProvider ? '收起' : '新增提供商'}</button>
      </div>
      {#if !providers.length}
        <EmptyState icon="cpu" title="暂无提供商" desc="点右上角「新增提供商」开始配置" compact />
      {:else}
        <div class="card-list">
          {#each providers as p}
            <div class="card-row">
              <span class="row-icon" aria-hidden="true">{@html `<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${I.cpu}</svg>`}</span>
              <div class="row-main">
                <span class="row-title">{p.provider || p.key}{#if p.model_name}<span class="dim"> · {p.model_name}</span>{/if}</span>
                <span class="row-sub">{p.base_url || '未配置地址'}</span>
              </div>
              <div class="row-actions">
                {#if p.key === model.current}<span class="badge ok">使用中</span>{/if}
                <button class="icon-btn danger" type="button" title="删除" onclick={() => removeProvider(p.key)}>
                  {@html `<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${I.trash}</svg>`}
                </button>
              </div>
            </div>
          {/each}
        </div>
      {/if}
    </section>

    {#if showAddProvider}
      <section class="card card-pad">
        <div class="section-head"><h4>新增提供商</h4></div>

        <div class="preset-wrap">
          <ProviderPresetPicker onselect={applyPreset} onloaded={onPresetsLoaded} {notify} />
        </div>

        <form class="form provider-form" onsubmit={submitProvider}>
          <div class="field-row">
            <label class="field"><span>Key</span><input class="input" type="text" bind:value={pf.key} placeholder="如 openai / anthropic" required /></label>
            <label class="field"><span>Provider</span><input class="input" type="text" bind:value={pf.provider} placeholder="如 openai" required /></label>
          </div>
          <label class="field"><span>模型名</span><input class="input" type="text" bind:value={pf.model_name} placeholder="如 gpt-4o" required /></label>
          <label class="field"><span>Base URL</span><input class="input" type="text" bind:value={pf.base_url} placeholder="https://api.openai.com/v1" required /></label>
          <UrlPreview base_url={pf.base_url} provider={pf.provider} />
          {#if pf.api_key}
            <label class="field"><span>API Key</span><input class="input" type="password" bind:value={pf.api_key} placeholder="留空则使用环境变量" /></label>
          {:else}
            <label class="field"><span>API Key</span><input class="input" type="password" bind:value={pf.api_key} placeholder="留空则用环境变量 {catalogKeys.includes(pf.key) ? pf.key.toUpperCase() + '_API_KEY' : '如 openai / anthropic'}" /></label>
          {/if}
          <div class="field-row">
            <label class="field"><span>Temperature</span><input class="input" type="number" step="0.1" min="0" max="2" bind:value={pf.temperature} placeholder="1.0" /></label>
            <label class="field"><span>Max Tokens</span><input class="input" type="number" min="1" bind:value={pf.max_tokens} placeholder="2048" /></label>
          </div>
          <p class="hint">温度越高，回复越随机发散（0~2，常用 0.6~1.3，1.0 默认）。想要赛博伴侣更放飞自我就调高一点~</p>

          <SamplingPresets
            temperature={pf.temperature}
            presence={pf.presence_penalty}
            frequency={pf.frequency_penalty}
            onselect={applySampling}
          />

          <div class="field-row">
            <label class="field">
              <span class="field-label">存在惩罚</span>
              <input class="input" type="number" step="0.1" min="-2" max="2" bind:value={pf.presence_penalty} placeholder="0.3" />
            </label>
            <label class="field">
              <span class="field-label">频率惩罚</span>
              <input class="input" type="number" step="0.1" min="-2" max="2" bind:value={pf.frequency_penalty} placeholder="0.3" />
            </label>
          </div>
          <p class="hint">存在惩罚：某个词只要“出现过”就降一次权，鼓励换新词、聊新话题（-2~2，0=不惩罚，正数促进多样性）。</p>
          <p class="hint">频率惩罚：按“出现次数”叠加降权，压复读、压重复措辞（-2~2，0=不惩罚）。正数让伴侣少说车辛辟话。</p>

          {#if testState !== 'idle'}
            <p class="test-msg {testState === 'ok' ? 'ok' : 'fail'}">
              {#if testState === 'testing'}
                <span class="spin" aria-hidden="true"></span> 正在测试连接…              {:else if testState === 'ok'}
                {@html `<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${I.check}</svg>`}
                {testMsg}
              {:else}
                {@html `<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${I.close}</svg>`}
                {testMsg}
              {/if}
            </p>
          {/if}

          <div class="form-actions">
            <button class="btn-outline" type="button" onclick={() => (showAddProvider = false)}>取消</button>
            <button class="btn-outline" type="button" onclick={() => testConnection()} disabled={saving || testState === 'testing'}>
              {@html `<svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${I.upload}</svg>`}
              测试连接
            </button>
            <button class="btn-primary" type="submit" disabled={saving}>保存提供商</button>
          </div>
        </form>
      </section>
    {/if}

    <section class="card card-pad">
      <div class="section-head"><h4>发现模型</h4></div>
      <form class="form" onsubmit={submitDiscover}>
        <label class="field"><span>Base URL</span><input class="input" type="text" bind:value={disc.base_url} placeholder="https://.../v1" required /></label>
        <label class="field"><span>API Key</span><input class="input" type="password" bind:value={disc.api_key} placeholder="sk-..." /></label>
        <div class="form-actions">
          <button class="btn-primary" type="submit" disabled={saving}>
            {@html `<svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${I.search}</svg>`}
            开始发现          </button>
        </div>
      </form>
    </section>

    <section class="card card-pad">
      <div class="section-head"><h4>视觉模型</h4></div>
      <form class="form" onsubmit={submitVision}>
        <div class="field-row">
          <label class="field"><span>Provider</span><input class="input" type="text" bind:value={vision.provider} placeholder="如 openai" /></label>
          <label class="field"><span>模型名</span><input class="input" type="text" bind:value={vision.model_name} placeholder="如 gpt-4o" required /></label>
        </div>
        <div class="field-row">
          <label class="field"><span>Base URL</span><input class="input" type="text" bind:value={vision.base_url} placeholder="https://..." /></label>
          <label class="field"><span>API Key</span><input class="input" type="password" bind:value={vision.api_key} placeholder="sk-..." /></label>
        </div>
        <div class="form-actions">
          <button class="btn-primary" type="submit" disabled={saving}>保存视觉配置</button>
        </div>
      </form>
    </section>
  {/if}
</SettingsShell>

<style>
  .model-row { cursor: pointer; }
  .model-row.on { border-color: var(--accent); background: var(--tint); }
  .model-row:disabled { cursor: default; }
  .model-key { font-weight: 600; word-break: break-all; }

  /* 采样参数: 字段标签小字 */
  .field-label {
    font-size: var(--text-xs);
    color: var(--text-2);
    font-weight: 500;
  }

  /* 新增提供商: 预设卡片区与表单分离 */
  .preset-wrap {
    margin-bottom: var(--space-4);
    padding-bottom: var(--space-4);
    border-bottom: 1px solid var(--border);
  }

  /* 连接与测试反馈 */
  .test-msg {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    margin: 0;
    padding: var(--space-2) var(--space-3);
    border-radius: var(--radius-sm);
    font-size: var(--text-xs);
    line-height: var(--leading-snug);
    word-break: break-all;
  }
  .test-msg.ok { color: var(--success); background: var(--success-soft); }
  .test-msg.fail { color: var(--error); background: var(--error-soft); }

  .spin {
    flex: none;
    width: 13px;
    height: 13px;
    border: 2px solid var(--border-strong);
    border-top-color: var(--accent);
    border-radius: var(--radius-full);
    animation: spin 0.8s linear infinite;
  }
  @keyframes spin { to { transform: rotate(360deg); } }
</style>
