<script>
  // App.svelte — 应用外壳 (阶段2: shell 布局 + hash 路由 + 占位页)
  //
  // 职责:
  //   - 启动 hash 路由监听 (startRouter)
  //   - 订阅 route store, 按顶层 page 渲染对应页面组件 (svelte:component)
  //   - 用 PhoneShell 包裹: 移动端顶栏+底部Tab / 桌面端侧边栏
  //   - 子级 hash (如 #/settings/mcp) 当前只解析, 具体子页留阶段3
  import PhoneShell from './components/PhoneShell.svelte';
  import AppDialog from './components/AppDialog.svelte';
  import { route, startRouter } from './lib/router.js';

  import ChatPage from './pages/ChatPage.svelte';
  import ContactsPage from './pages/ContactsPage.svelte';
  import DiscoverPage from './pages/DiscoverPage.svelte';
  import MemoryPage from './pages/MemoryPage.svelte';
  import SettingsPage from './pages/SettingsPage.svelte';

  // 顶层 page -> 组件映射
  const pageMap = {
    chat: ChatPage,
    contacts: ContactsPage,
    discover: DiscoverPage,
    memory: MemoryPage,
    settings: SettingsPage,
  };

  // Svelte 5: 模板中 $route 自动解引用可订阅 store (含 runes 模式)
  let ready = $state(false);

  $effect(() => {
    startRouter();
    // 微任务后标记就绪, 确保 route 已初始化
    queueMicrotask(() => (ready = true));
  });

  let activePage = $derived($route.page ?? 'chat');
  // 大写变量名: Svelte 5 runes 将其视为动态组件引用，随 route 变化重新渲染
  let Current = $derived(pageMap[$route.page] ?? ChatPage);

  // 页面切换过渡: 淡入 + 轻微上滑
  function pageIn(node) {
    return {
      duration: 280,
      easing: (t) => 1 - Math.pow(1 - t, 3),
      css: (t) => `
        opacity: ${t};
        transform: translateY(${(1 - t) * 8}px);
        filter: blur(${(1 - t) * 2}px);
      `,
    };
  }
</script>

<svelte:head><title>慕</title></svelte:head>

{#if !ready}
  <div class="boot">
    <div class="boot-logo" aria-hidden="true"></div>
    <span class="boot-text">引导中…</span>
  </div>
{:else}
  <PhoneShell active={activePage}>
    {#key activePage}
      <div class="page-enter" transition:pageIn>
        <Current></Current>
      </div>
    {/key}
  </PhoneShell>
  <AppDialog />
{/if}

<style>
  .page-enter {
    min-height: 100%;
    will-change: opacity, transform;
  }
  .boot {
    min-height: 100dvh;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: var(--space-4);
    color: var(--text-2);
    font-size: var(--text-sm);
  }
  .boot-logo {
    position: relative;
    width: 40px;
    height: 40px;
    border-radius: var(--radius-lg);
    background: linear-gradient(135deg, var(--accent), var(--accent-strong));
    box-shadow: 0 0 0 8px var(--tint), var(--shadow);
    animation: boot-pulse 1.3s var(--ease-in-out) infinite;
  }
  .boot-logo::after {
    content: '';
    position: absolute;
    inset: 9px;
    border-radius: var(--radius-sm);
    background: var(--on-accent);
    opacity: 0.85;
  }
  .boot-text {
    letter-spacing: 0.4px;
  }
  @keyframes boot-pulse {
    0%, 100% { transform: scale(0.92); opacity: 0.55; }
    50% { transform: scale(1.05); opacity: 1; }
  }
</style>
