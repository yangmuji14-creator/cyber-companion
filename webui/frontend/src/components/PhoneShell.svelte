<script>
  // PhoneShell.svelte — 类微信"手机壳"容器
  //
  // 响应式双轨:
  //   窄屏 (<768px): 顶部 TopBar + 中间内容 + 底部毛玻璃 TabBar (近全屏)
  //   宽屏 (>=768px): 左侧 280px 侧边栏(品牌+Tab) + 右侧主内容区
  //
  // 同一套 DOM, CSS 媒体查询 + Svelte 响应式状态 (isDesktop) 双轨重排。
  import TabBar from './TabBar.svelte';
  import TopBar from './TopBar.svelte';

  let { active = 'chat', children, sidefoot } = $props();

  // 桌面判定 (>=768px); 用 matchMedia 驱动响应式状态
  let isDesktop = $state(false);

  $effect(() => {
    const mq = window.matchMedia('(min-width: 768px)');
    const apply = () => (isDesktop = mq.matches);
    apply();
    mq.addEventListener('change', apply);
    return () => mq.removeEventListener('change', apply);
  });
</script>

<div class="phone-stage">
  <div class="phone-shell" class:desktop={isDesktop}>
    {#if isDesktop}
      <aside class="sidebar" aria-label="侧边栏">
        <div class="sidebar-brand">
          <span class="brand-dot" aria-hidden="true"></span>
          <span class="brand-name">慕</span>
        </div>
        <TabBar {active} vertical />
        <div class="sidebar-foot">
          {#if sidefoot}{@render sidefoot()}{/if}
        </div>
      </aside>

      <section class="main-area">
        {@render children?.()}
      </section>
    {:else}
      <TopBar />

      <section class="main-area">
        {@render children?.()}
      </section>

      <TabBar {active} vertical={false} />
    {/if}
  </div>
</div>

<style>
  .phone-stage {
    min-height: 100dvh;
    display: flex;
    justify-content: center;
    background: var(--bg);
    /* 桌面温暖氛围: 顶部淡暖光, 底部弱阴影 */
    background-image:
      radial-gradient(60% 40% at 50% 0%, color-mix(in srgb, var(--accent-soft) 55%, transparent), transparent 70%);
  }

  .phone-shell {
    position: relative;
    display: flex;
    flex-direction: column;
    width: 100%;
    max-width: var(--phone-maxw);
    height: 100dvh;
    background: var(--bg);
    overflow: hidden;
  }

  /* ---- 移动端: 手机壳接近全屏, 顶栏+内容+底部毛玻璃 ---- */
  .main-area {
    flex: 1;
    min-height: 0;
    overflow-y: auto;
    overflow-x: hidden;
    -webkit-overflow-scrolling: touch;
    scroll-behavior: smooth;
    overscroll-behavior: contain;
    /* 细滚动条尽量少占布局宽度, 避免右侧被挤、左右不对称 */
    scrollbar-width: thin;
    scrollbar-color: var(--border-strong) transparent;
  }
  .main-area::-webkit-scrollbar {
    width: 10px;
  }
  .main-area::-webkit-scrollbar-thumb {
    background: var(--border-strong);
    border-radius: 8px;
    border: 2px solid transparent;
    background-clip: padding-box;
  }
  .main-area::-webkit-scrollbar-track {
    background: transparent;
  }

  /* ---- 桌面端 (>=768px): 应用布局, 居中加桌面圆形氛围 ---- */
  @media (min-width: 768px) {
    .phone-stage {
      align-items: center;
      padding: var(--space-6);
    }
    .phone-shell.desktop {
      flex-direction: row;
      width: 100%;
      max-width: var(--app-maxw);
      height: calc(100dvh - var(--space-6) * 2);
      border: 1px solid var(--border);
      border-radius: var(--radius-xl);
      box-shadow: var(--shadow-lg), 0 0 0 1px color-mix(in srgb, var(--border) 40%, transparent);
      overflow: hidden;
      background: var(--surface);
    }

    .sidebar {
      flex: none;
      width: var(--sidebar-w);
      display: flex;
      flex-direction: column;
      background: color-mix(in srgb, var(--sidebar-bg) 92%, transparent);
      border-right: 1px solid var(--sidebar-border);
      backdrop-filter: blur(var(--blur));
      -webkit-backdrop-filter: blur(var(--blur));
    }
    .sidebar-brand {
      display: flex;
      align-items: center;
      gap: var(--space-2);
      padding: var(--space-5) var(--space-4) var(--space-4);
    }
    .brand-dot {
      position: relative;
      flex: none;
      width: 16px;
      height: 16px;
      border-radius: var(--radius-full);
      background: linear-gradient(135deg, var(--accent), var(--accent-strong));
      box-shadow: 0 0 0 3px var(--tint), var(--shadow-sm);
    }
    .brand-dot::after {
      content: '';
      position: absolute;
      top: 2px;
      left: 3px;
      width: 4px;
      height: 4px;
      border-radius: var(--radius-full);
      background: color-mix(in srgb, var(--on-accent) 70%, transparent);
    }
    .brand-name {
      font-weight: 700;
      font-size: var(--text-lg);
      letter-spacing: 0.3px;
      color: var(--topbar-text);
      white-space: nowrap;
    }
    .sidebar-foot {
      margin-top: auto;
      padding: var(--space-3);
    }

    .main-area {
      flex: 1;
      background: var(--bg);
    }
  }
</style>
