<script>
  // SettingsWechat.svelte — 微信账号绑定（PawzoChat 式：选平台 → 扫码）
  import SettingsShell from './SettingsShell.svelte';
  import EmptyState from './EmptyState.svelte';
  import Switch from '../Switch.svelte';
  import './settings-base.css';
  import { I } from './icons.js';
  import { wechatApi } from '../../lib/settingsApi.js';
  import { confirmDialog, promptDialog } from '../../lib/dialog.svelte.js';

  let { notify, onback } = $props();

  let accounts = $state([]);
  let loaded = $state(false);
  let saving = $state(false);

  // 高级设置折叠
  let showAdvanced = $state(false);
  let wf = $state({ id: '', persona_id: '', enabled: true, auto_start: false });

  // 平台选择弹层
  let showPlatform = $state(false);
  // 扫码登录弹层
  let qrAccount = $state(null);
  let qrImg = $state('');
  let qrLink = $state('');
  let qrStatus = $state('');
  let qrStatusKind = $state('');
  let qrDone = $state(false);
  let qrEs = null;

  $effect(() => {
    let alive = true;
    (async () => {
      const r = await wechatApi.list();
      if (!alive) return;
      if (r.ok && Array.isArray(r.data)) accounts = r.data;
      else notify(errMsg(r, '加载账号失败'), 'error');
      loaded = true;
    })();
    return () => (alive = false);
  });

  function errMsg(err, fallback) {
    const m = err?.data?.error || err?.data?.message || err?.data?.detail || err?.data;
    if (typeof m === 'string' && m) return m;
    return fallback || (err?.status ? `请求失败（HTTP ${err.status}）` : String(err?.message ?? err));
  }

  async function refresh() {
    const r = await wechatApi.list();
    if (r.ok && Array.isArray(r.data)) accounts = r.data;
  }

  // ---- 平台预设（当前仅微信 / iLink；结构与 PawzoChat 一致，便于日后扩展）----
  const PLATFORMS = [
    {
      key: 'wechat',
      label: '微信',
      desc: '通过 iLink 协议扫码登录，自动保持在线',
      icon: 'wechat',
    },
  ];

  // ---- 一键绑定：选平台 → 自动建号/复用 → 扫码 ----
  async function startBind() {
    showPlatform = true;
  }

  async function choosePlatform(key) {
    showPlatform = false;
    // 自动确定要登录的账号：优先复用「未登录」的已有账号，否则自动创建一个
    try {
      let target = (accounts || []).find((a) => !a.has_credentials || a.session_expired);
      if (!target) {
        // 自动创建一个免填的默认账号 id（后端允许 default）
        const nid = 'default';
        const r = await wechatApi.add({ id: nid, enabled: true, auto_start: true });
        if (!r.ok && r.status !== 409) {
          notify(errMsg(r, '自动创建账号失败，请手动新增'), 'error');
          return;
        }
        target = { id: nid };
        await refresh();
      }
      openQr(target.id);
    } catch (e) {
      notify(errMsg(e, '绑定失败'), 'error');
    }
  }

  function cancelPlatform() {
    showPlatform = false;
  }

  // ---- 高级：手动新增账号 ----
  async function submitAdd(e) {
    e.preventDefault();
    saving = true;
    try {
      const body = { id: wf.id };
      if (wf.persona_id) body.persona_id = wf.persona_id;
      body.enabled = wf.enabled;
      body.auto_start = wf.auto_start;
      const r = await wechatApi.add(body);
      if (r.ok) { notify('账号已添加', 'success'); wf = { id: '', persona_id: '', enabled: true, auto_start: false }; refresh(); }
      else notify(errMsg(r, '添加失败'), 'error');
    } finally { saving = false; }
  }

  async function editPersona(id, currentPersona) {
    const nominee = await promptDialog(
      `为账号 ${id} 设置 Persona ID${currentPersona ? `（当前：${currentPersona}）` : ''}`,
      { title: '设置 Persona', defaultValue: currentPersona ?? '' },
    );
    if (nominee === null) return;
    try {
      const r = await wechatApi.edit(id, { persona_id: nominee });
      if (r.ok) { notify('Persona 已更新', 'success'); refresh(); }
      else notify(errMsg(r, '更新失败'), 'error');
    } catch (e) { notify(errMsg(e, '更新失败'), 'error'); }
  }

  async function removeAccount(id) {
    const ok = await confirmDialog(`删除微信账号 ${id}？`, { title: '删除微信账号', danger: true });
    if (!ok) return;
    try {
      const r = await wechatApi.remove(id);
      if (r.ok) { notify('已删除', 'success'); refresh(); }
      else notify(errMsg(r, '删除失败'), 'error');
    } catch (e) { notify(errMsg(e, '删除失败'), 'error'); }
  }

  async function logoutAccount(id) {
    try {
      const r = await wechatApi.logout(id);
      if (r.ok) notify('已登出', 'success');
      else notify(errMsg(r, '登出失败'), 'error');
      refresh();
    } catch (e) { notify(errMsg(e, '登出失败'), 'error'); }
  }

  // ---- 扫码登录（固定后端命名 SSE 事件：qrcode / status / done）----
  // 后端发送具名事件（event: qrcode / status / done），必须用 addEventListener 而非
  // onmessage（后者只接收默认 message 事件）。连接中断 409 会自动重连，成功后保持连接。
  let qrReconnectTimer = null;
  let qrReconnectCount = 0;

  function openQr(id) {
    closeQr();
    qrAccount = id;
    qrDone = false;
    connectQr(id);
  }

  function teardownEs() {
    try { qrEs && qrEs.close(); } catch {}
    qrEs = null;
  }

  function connectQr(id) {
    teardownEs();
    qrReconnectCount = 0;
    qrEs = new EventSource(wechatApi.qrcodeUrl(id));

    const onQr = (payload) => {
      if (!payload || payload.qr_url === undefined) return;
      if (payload.qr_base64) {
        qrImg = payload.qr_base64;
        qrLink = '';
      } else {
        // 无 qrcode 库 → 后端给 qr_url（登录链接），展示为可打开的链接
        qrImg = '';
        qrLink = payload.qr_url;
      }
      qrStatus = '请使用微信扫一扫登录';
      qrStatusKind = 'ok';
    };
    const onStatus = (payload) => {
      if (!payload || payload.status === undefined) return;
      // 后端把 SDK 未识别的状态映射成 failed + "未知状态 X"（如 waiting），
      // 这并非真正失败，而是「正在等待扫码」——统一按正常等待处理。
      if (payload.status === 'failed' && typeof payload.message === 'string' && payload.message.includes('未知状态')) {
        qrStatus = '正在等待微信扫码…';
        qrStatusKind = '';
        return;
      }
      const map = { scanning: '已进入扫码状态，请在手机上确认', confirmed: '已确认，正在登录…', expired: '二维码已过期，请重新获取', failed: '登录失败，请重试' };
      qrStatus = payload.message || map[payload.status] || payload.status;
      qrStatusKind = payload.status === 'expired' || payload.status === 'failed' ? 'error' : 'ok';
    };
    const onDone = (payload) => {
      if (!payload || payload.ok === undefined) return;
      qrDone = true;
      teardownEs();
      if (qrReconnectTimer) { clearTimeout(qrReconnectTimer); qrReconnectTimer = null; }
      if (payload.ok) { qrStatus = '登录成功 ✓'; qrStatusKind = 'ok'; refresh(); }
      else { qrStatus = payload.error || '登录失败'; qrStatusKind = 'error'; }
    };

    qrEs.addEventListener('qrcode', (ev) => { try { onQr(JSON.parse(ev.data)); } catch {} });
    qrEs.addEventListener('status', (ev) => { try { onStatus(JSON.parse(ev.data)); } catch {} });
    qrEs.addEventListener('done', (ev) => { try { onDone(JSON.parse(ev.data)); } catch {} });
    // 兼容：万一代理把事件名剥离，回退到 onmessage 也能解析
    qrEs.onmessage = (ev) => {
      try {
        const payload = JSON.parse(ev.data);
        if (!payload) return;
        if (payload.qr_url !== undefined && !qrImg && !qrLink) onQr(payload);
        else if (payload.status !== undefined && !qrDone) onStatus(payload);
        else if (payload.ok !== undefined) onDone(payload);
      } catch {}
    };
    qrEs.onerror = () => {
      if (qrDone) return;
      // 先关闭当前连接，阻止 EventSource 自带的自动重连（否则会与我们的手动重连
      // 同时发起两个连接，同一账号 → 相互 409，导致卡住"）。
      teardownEs();
      // 服务端同一账号刚断开时锁可能尚未释放（最长约 5s），稍后重试即可。
      if (qrReconnectCount >= 5) {
        qrStatus = '连接失败，请点击「刷新二维码」重试';
        qrStatusKind = 'error';
        return;
      }
      qrReconnectCount += 1;
      if (qrImg || qrLink) {
        qrStatus = '连接中断，正在重连…';
        qrStatusKind = '';
      } else {
        qrStatus = '正在连接服务器…';
        qrStatusKind = '';
      }
      if (qrReconnectTimer) clearTimeout(qrReconnectTimer);
      qrReconnectTimer = setTimeout(() => {
        if (qrDone) return;
        connectQr(qrAccount);
      }, 3000);
    };
  }

  function closeQr() {
    if (qrReconnectTimer) { clearTimeout(qrReconnectTimer); qrReconnectTimer = null; }
    teardownEs();
    qrAccount = null;
    qrImg = '';
    qrLink = '';
    qrStatus = '';
    qrDone = false;
  }
</script>

<SettingsShell title="微信账号" desc="选平台、扫码即绑定" {onback}>
  <!-- 一键绑定引导卡 -->
  <section class="card card-pad bind-hero">
    <div class="bind-hero-icon" aria-hidden="true">{@html `<svg viewBox="0 0 24 24" width="30" height="30" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">${I.wechat}</svg>`}</div>
    <div class="bind-hero-text">
      <h4>绑定微信账号</h4>
      <p class="bind-hero-desc">三步搞定：① 选择平台 → ② 扫码 → ③ 完成。无需手动填写账号信息。</p>
    </div>
    <button class="btn-primary" type="button" onclick={startBind}>开始扫码绑定</button>
  </section>

  <section class="card card-pad">
    <div class="section-head">
      <h4>已绑定账号</h4>
      <button class="btn-outline sm" type="button" onclick={() => (showAdvanced = !showAdvanced)}>{showAdvanced ? '收起高级' : '高级'}</button>
    </div>

    {#if !loaded}
      <EmptyState icon="wechat" title="正在加载…" compact />
    {:else if !accounts.length}
      <EmptyState icon="wechat" title="暂未绑定" desc="点「开始扫码绑定」，选平台后扫码即可" compact>
        <button class="btn-primary" type="button" onclick={startBind}>开始扫码绑定</button>
      </EmptyState>
    {:else}
      <div class="card-list">
        {#each accounts as acc}
          <div class="card-row">
            <span class="row-icon" aria-hidden="true">{@html `<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${I.wechat}</svg>`}</span>
            <div class="row-main">
              <span class="row-title">{acc.id}</span>
              <span class="row-sub">
                {#if acc.enabled}<span class="badge ok">启用</span>{:else}<span class="badge">停用</span>{/if}
                {#if acc.adapter_running}<span class="badge ok">运行中</span>{/if}
                {#if acc.session_expired}<span class="badge error">会话过期</span>{/if}
                {#if acc.auto_start}<span class="badge info">开机自启</span>{/if}
                {#if acc.persona_name}<span class="badge">{acc.persona_name}</span>{/if}
              </span>
            </div>
            <div class="row-actions wrap">
              {#if acc.has_credentials && !acc.session_expired}
                <button class="btn-outline sm" type="button" onclick={() => logoutAccount(acc.id)}>登出</button>
              {/if}
              {#if !acc.has_credentials || acc.session_expired}
                <button class="btn-primary sm" type="button" onclick={() => openQr(acc.id)}>扫码登录</button>
              {/if}
              <button class="btn-outline sm" type="button" onclick={() => editPersona(acc.id, acc.persona_name)}>编辑</button>
              <button class="icon-btn danger" type="button" title="删除" onclick={() => removeAccount(acc.id)}>
                {@html `<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${I.trash}</svg>`}
              </button>
            </div>
          </div>
        {/each}
      </div>
    {/if}
  </section>

  {#if showAdvanced}
    <section class="card card-pad">
      <div class="section-head"><h4>高级：手动新增账号</h4></div>
      <p class="field-hint">一般不需手动填写。仅在自动绑定遇到问题时，用高级选项手工指定账号 ID 与乐观人设。</p>
      <form class="form" onsubmit={submitAdd}>
        <label class="field"><span>Account ID</span><input class="input" type="text" bind:value={wf.id} placeholder="如 wx_001" required /></label>
        <label class="field"><span>Persona ID</span><input class="input" type="text" bind:value={wf.persona_id} placeholder="可选" /></label>
        <div class="switch-row"><span class="switch-label">启用</span><Switch checked={wf.enabled} onchange={(v) => (wf.enabled = v)} label="启用" /></div>
        <div class="switch-row"><span class="switch-label">自动启动</span><Switch checked={wf.auto_start} onchange={(v) => (wf.auto_start = v)} label="自动启动" /></div>
        <div class="form-actions">
          <button class="btn-outline" type="button" onclick={() => (showAdvanced = false)}>收起</button>
          <button class="btn-primary" type="submit" disabled={saving}>保存账号</button>
        </div>
      </form>
    </section>
  {/if}

  <!-- 平台选择弹层 -->
  {#if showPlatform}
    <div class="qr-overlay" role="dialog" aria-modal="true" aria-label="选择平台">
      <div class="card card-pad platform-card">
        <div class="section-head">
          <h4>选择平台</h4>
          <button class="icon-btn" type="button" title="关闭" onclick={cancelPlatform}>
            {@html `<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${I.close}</svg>`}
          </button>
        </div>
        <div class="platform-list">
          {#each PLATFORMS as p}
            <button class="platform-item" type="button" onclick={() => choosePlatform(p.key)}>
              <span class="platform-icon" aria-hidden="true">{@html `<svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">${I[p.icon] || I.wechat}</svg>`}</span>
              <span class="platform-main">
                <span class="platform-label">{p.label}</span>
                <span class="platform-desc">{p.desc}</span>
              </span>
              <span class="platform-arrow" aria-hidden="true">→</span>
            </button>
          {/each}
        </div>
      </div>
    </div>
  {/if}

  <!-- 扫码登录弹层 -->
  {#if qrAccount}
    <div class="qr-overlay" role="dialog" aria-modal="true" aria-label="扫码登录">
      <div class="card card-pad qr-card">
        <div class="section-head">
          <h4>微信扫码登录 · {qrAccount}</h4>
          <button class="icon-btn" type="button" title="关闭" onclick={closeQr}>
            {@html `<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${I.close}</svg>`}
          </button>
        </div>
        {#if qrImg}
          <img class="qr-img" src={qrImg} alt="微信登录二维码" />
        {:else if qrLink}
          <a class="qr-link" href={qrLink} target="_blank" rel="noopener noreferrer">点击在浏览器打开登录链接</a>
        {:else}
          <div class="qr-wait"><span class="badge info">等待二维码…</span></div>
        {/if}
        {#if qrStatus}
          <p class="qr-status {qrStatusKind === 'error' ? 'is-error' : qrStatusKind === 'ok' ? 'is-ok' : 'is-muted'}">{qrStatus}</p>
        {/if}
        <div class="qr-actions">
          <button class="btn-outline sm" type="button" onclick={() => openQr(qrAccount)}>
            {qrDone ? (qrImg || qrLink ? '重新获取二维码' : '重试') : '刷新二维码'}
          </button>
        </div>
      </div>
    </div>
  {/if}
</SettingsShell>

<style>
  .switch-row { display: flex; align-items: center; justify-content: space-between; gap: var(--space-3); padding: var(--space-2) 0; }
  .switch-label { font-size: var(--text-sm); color: var(--text-1); }
  .field-hint { margin: 0 0 var(--space-3); font-size: var(--text-sm); color: var(--text-2); }

  /* 一键绑定引导 */
  .bind-hero { display: flex; align-items: center; gap: var(--space-3); }
  .bind-hero-icon {
    flex: none; width: 52px; height: 52px; border-radius: var(--radius);
    display: flex; align-items: center; justify-content: center;
    color: var(--accent); background: var(--accent-soft, color-mix(in srgb, var(--accent) 14%, transparent));
  }
  .bind-hero-text { flex: 1; min-width: 0; }
  .bind-hero-text h4 { margin: 0 0 2px; }
  .bind-hero-desc { margin: 0; font-size: var(--text-sm); color: var(--text-2); }

  /* 平台选择 */
  .platform-card { width: 100%; max-width: 400px; }
  .platform-list { display: flex; flex-direction: column; gap: var(--space-2); margin-top: var(--space-2); }
  .platform-item {
    display: flex; align-items: center; gap: var(--space-3);
    padding: var(--space-3); border: 1px solid var(--border);
    border-radius: var(--radius); background: var(--bg-1); cursor: pointer;
    text-align: left; transition: border-color .15s, background .15s;
  }
  .platform-item:hover { border-color: var(--accent); background: var(--accent-soft, color-mix(in srgb, var(--accent) 8%, transparent)); }
  .platform-icon { flex: none; color: var(--accent); display: flex; }
  .platform-main { flex: 1; min-width: 0; }
  .platform-label { display: block; font-weight: 600; color: var(--text-1); }
  .platform-desc { display: block; font-size: var(--text-sm); color: var(--text-2); margin-top: 2px; }
  .platform-arrow { color: var(--text-3); font-size: 18px; }

  /* 扫码 */
  .qr-overlay {
    position: fixed; inset: 0; z-index: 50;
    display: flex; align-items: center; justify-content: center;
    background: var(--overlay); padding: var(--space-4);
  }
  .qr-card { width: 100%; max-width: 320px; text-align: center; }
  .qr-img { width: 200px; height: 200px; object-fit: contain; border: 1px solid var(--border); border-radius: var(--radius); background: #fff; margin: var(--space-2) auto; display: block; }
  .qr-link { display: inline-block; margin: var(--space-3) auto; color: var(--accent); font-size: var(--text-sm); word-break: break-all; }
  .qr-wait { padding: var(--space-5); }
  .qr-status { margin: 0; font-size: var(--text-sm); color: var(--text-2); }
  .qr-status.is-ok { color: var(--success); }
  .qr-status.is-error { color: var(--error); }
  .qr-status.is-muted { color: var(--text-3); }
  .qr-actions { margin-top: var(--space-3); display: flex; justify-content: center; gap: var(--space-2); }
</style>
