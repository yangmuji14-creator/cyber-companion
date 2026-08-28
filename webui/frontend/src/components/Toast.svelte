<script>
  // Toast.svelte — 轻量消息提示 (单一消息, 自动消失)
  // 页面持有 `toast` 状态 (null 或 {type, text}), 传入本组件渲染。
  // 入场/退场使用 Svelte transition (fade + fly 复合), 类型用到 tokens 里 toast-* 语义色。

  let { toast = null } = $props();
  // toast: { type:'success'|'error'|'info', text }

  // 自定义复合过渡: 淡入 + 上浮 (进出场共用, 反向播放)
  function toastTransition(node, { y = 14, duration = 240 } = {}) {
    return {
      duration,
      easing: (t) => 1 - Math.pow(1 - t, 3),
      css: (t) => `
        opacity: ${t};
        transform: translateY(${(1 - t) * y}px) scale(${0.96 + 0.04 * t});
      `,
    };
  }
</script>

{#if toast}
  <div class="toast-zone" role="status" aria-live="polite">
    {#key toast}
      <div
        class="toast {toast.type === 'success' ? 'is-success' : toast.type === 'error' ? 'is-error' : 'is-info'}"
        transition:toastTransition
      >
        {toast.text}
      </div>
    {/key}
  </div>
{/if}

<style>
  .toast-zone {
    position: fixed;
    bottom: calc(var(--tabbar-h) + var(--space-5));
    left: 50%;
    transform: translateX(-50%);
    z-index: 60;
    width: max-content;
    max-width: calc(100vw - var(--space-6) * 2);
    pointer-events: none;
  }
  .toast {
    position: relative;
    padding: var(--space-2) var(--space-4);
    border-radius: var(--toast-radius);
    background: var(--toast-info-bg);
    color: var(--toast-info-text);
    font-size: var(--text-sm);
    font-weight: 500;
    box-shadow: var(--toast-shadow);
    text-align: center;
    will-change: transform, opacity;
  }
  .toast.is-success {
    background: var(--toast-success-bg);
    color: var(--toast-success-text);
  }
  .toast.is-error {
    background: var(--toast-error-bg);
    color: var(--toast-error-text);
  }
</style>
