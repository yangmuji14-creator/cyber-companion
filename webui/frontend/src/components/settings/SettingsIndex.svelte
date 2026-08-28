<script>
  // SettingsIndex.svelte — 设置中心分类导航首页 (PawzoChat 式分组 card)
  // 按功能归类为若干"卡片分组", 每个子页入口是 card-row (图标+标题+副标题+右箭头)。
  import './settings-base.css';
  import { I } from './icons.js';

  let { onopen } = $props(); // (key) => void

  // 分组结构: { key, title, icon, desc, items:[{key, icon, title, desc}] }
  const GROUPS = [
    {
      key: 'conn',
      title: '连接 / 服务',
      icon: 'link',
      desc: '模型、账号与外部能力接入',
      items: [
        { key: 'model', icon: 'cpu', title: '模型设置', desc: '切换模型与管理提供商' },
        { key: 'wechat', icon: 'wechat', title: '微信账号', desc: '账号绑定与扫码登录' },
        { key: 'mcp', icon: 'plug', title: 'MCP 扩展', desc: '外部能力服务器接入' },
        { key: 'voice', icon: 'voice', title: '语音服务商', desc: 'TTS 合成与试听' },
        { key: 'plugins', icon: 'puzzle', title: '插件 / 工具', desc: '已装能力概览（只读）' },
      ],
    },
    {
      key: 'behavior',
      title: '对话 / 行为',
      icon: 'message',
      desc: '回复风格与主动消息偏好',
      items: [
        { key: 'conversation', icon: 'message', title: '对话设置', desc: '回复风格、智能开关与主动消息' },
        { key: 'moments', icon: 'moments', title: '朋友圈自动发布', desc: '定时自动发朋友圈' },
      ],
    },
    {
      key: 'system',
      title: '系统',
      icon: 'monitor',
      desc: '数据、诊断与外观',
      items: [
        { key: 'data', icon: 'data', title: '数据与关于', desc: '诊断、备份与恢复' },
        { key: 'monitor', icon: 'monitor', title: '系统监控 / 日志', desc: '运行状态、诊断检查与运维指标' },
        { key: 'appearance', icon: 'palette', title: '主题与界面', desc: '浅色 / 深色 / 跟随系统' },
      ],
    },
  ];

  function renderIcon(name, size) {
    return `<svg viewBox="0 0 24 24" width="${size}" height="${size}" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${I[name] || ''}</svg>`;
  }
</script>

<div class="settings-main">
  <header class="index-head">
    <h2>设置</h2>
    <p>管理模型、对话、扩展与系统偏好</p>
  </header>

  <div class="index-groups">
    {#each GROUPS as g}
      <section class="card index-group" aria-label={g.title}>
        <div class="group-head">
          <span class="group-icon" aria-hidden="true">{@html renderIcon(g.icon, 18)}</span>
          <div class="group-head-txt">
            <span class="group-title">{g.title}</span>
            <span class="group-desc">{g.desc}</span>
          </div>
        </div>
        <div class="card-list">
          {#each g.items as item}
            <button class="card-row group-row" type="button" onclick={() => onopen(item.key)}>
              <span class="row-icon" aria-hidden="true">{@html renderIcon(item.icon, 20)}</span>
              <span class="row-main">
                <span class="row-title">{item.title}</span>
                <span class="row-sub">{item.desc}</span>
              </span>
              <svg viewBox="0 0 24 24" class="chevron" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">{@html I.chevron}</svg>
            </button>
          {/each}
        </div>
      </section>
    {/each}
  </div>
</div>

<style>
  .index-head { padding: var(--space-2) 0 var(--space-4); }
  .index-head h2 { margin: 0; font-size: var(--text-xl); font-weight: 700; color: var(--text-1); }
  .index-head p { margin: 2px 0 0; font-size: var(--text-xs); color: var(--text-3); }

  .index-groups { display: flex; flex-direction: column; gap: var(--space-4); }

  .index-group { padding: var(--card-pad); }

  .group-head { display: flex; align-items: center; gap: var(--space-3); margin-bottom: var(--space-3); }
  .group-icon {
    flex: none;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 34px;
    height: 34px;
    border-radius: var(--radius);
    background: var(--tint);
    color: var(--tab-active);
  }
  .group-head-txt { display: flex; flex-direction: column; gap: 1px; min-width: 0; }
  .group-title { font-weight: 700; color: var(--text-1); font-size: var(--text-base); }
  .group-desc { font-size: var(--text-xs); color: var(--text-3); }

  .group-row { cursor: pointer; transition: background var(--transition), transform var(--transition); }
  .group-row:hover { background: var(--row-hover); transform: translateX(2px); }
  .group-row:focus-visible { box-shadow: var(--focus-ring); }
</style>
