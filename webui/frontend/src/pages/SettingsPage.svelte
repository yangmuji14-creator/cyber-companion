<script>
  // SettingsPage.svelte — 设置中心 (分组索引 + 精细子页)
  //
  // 职责: 持有当前子页状态与统一 toast, 渲染:
  //   - 分组 card 索引首页 (SettingsIndex)
  //   - 或当前子页 (SettingsModel/Conversation/Wechat/Mcp/Plugins/Moments/Voice/Data/Monitor/Appearance)
  // 每个子页独立自建在 src/components/settings/, 通过 props 接收 { notify, onback }。
  //
  // 零第三方库、零外部 CDN。共享组件仅复用导出的 Switch/Toast/ThemeToggle。
  // route: 让 #/settings/<sub> 子路径能直接打开对应子页 (供聊天页"去设置"跳转使用)
  import { route } from '../lib/router.js';
  import Toast from '../components/Toast.svelte';
  import SettingsIndex from '../components/settings/SettingsIndex.svelte';
  import SettingsModel from '../components/settings/SettingsModel.svelte';
  import SettingsConversation from '../components/settings/SettingsConversation.svelte';
  import SettingsWechat from '../components/settings/SettingsWechat.svelte';
  import SettingsMcp from '../components/settings/SettingsMcp.svelte';
  import SettingsPlugins from '../components/settings/SettingsPlugins.svelte';
  import SettingsMoments from '../components/settings/SettingsMoments.svelte';
  import SettingsVoice from '../components/settings/SettingsVoice.svelte';
  import SettingsData from '../components/settings/SettingsData.svelte';
  import SettingsMonitor from '../components/settings/SettingsMonitor.svelte';
  import SettingsAppearance from '../components/settings/SettingsAppearance.svelte';

  const SUB = {
    model: SettingsModel,
    conversation: SettingsConversation,
    wechat: SettingsWechat,
    mcp: SettingsMcp,
    plugins: SettingsPlugins,
    moments: SettingsMoments,
    voice: SettingsVoice,
    data: SettingsData,
    monitor: SettingsMonitor,
    appearance: SettingsAppearance,
  };

  let current = $state(null);

  // ---- toast (统一反馈) ----
  let toast = $state(null);
  let toastTimer = null;
  function notify(msg, kind = 'info') {
    toast = { type: kind, text: msg };
    if (toastTimer) clearTimeout(toastTimer);
    toastTimer = setTimeout(() => (toast = null), 3200);
  }

  function open(key) {
    current = key;
  }
  function back() {
    current = null;
  }

  // 同步路由子路径 -> 当前子页: 让 #/settings/<key> 直接打开对应子页。
  // 例如聊天页"去设置"跳转 navigate('settings/model') 后, 这里会把 current 设为 'model'。
  // 仅在 route.sub[0] 是合法子页 key 时写入; 用户手动 back 或从索引进入不冲突 (其 sub 为空/不变)。
  $effect(() => {
    const key = Array.isArray($route.sub) && $route.sub.length > 0 ? $route.sub[0] : null;
    if (key && SUB[key]) {
      current = key;
    }
  });

  let Active = $derived(current && SUB[current] ? SUB[current] : null);
</script>

{#if !current}
  <SettingsIndex onopen={open} />
{:else if Active}
  <Active notify={notify} onback={back} />
{/if}

<Toast {toast} />
