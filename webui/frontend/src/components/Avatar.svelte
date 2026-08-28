<script>
  // Avatar.svelte — 圆形头像 (有图显示图, 无图用姓名哈希色块)
  // 名字哈希 -> 一组由 accent 派生的柔和暖色 (color-mix 向 theme surface 淡化)。
  let { name = '', src = '', size = 44 } = $props();

  // 柔和调色板: 由 accent 相位的暖色系, 定义在 style 里 (可随深/浅主题淡化)
  const HUES = ['h0', 'h1', 'h2', 'h3', 'h4'];

  function hashName(n) {
    let h = 0;
    for (let i = 0; i < n.length; i++) h = (h * 31 + n.charCodeAt(i)) >>> 0;
    return h;
  }

  let hue = $derived(HUES[hashName(name || '?') % HUES.length]);
  let initial = $derived((name || '?').trim().charAt(0).toUpperCase());
</script>

<span class="avatar" style="--asize:{size}px" aria-hidden={src ? undefined : 'true'}>
  {#if src}
    <img src={src} alt="" />
  {:else}
    <span class="avatar-fallback {hue}">{initial}</span>
  {/if}
</span>

<style>
  .avatar {
    flex: none;
    width: var(--asize, 44px);
    height: var(--asize, 44px);
    border-radius: var(--radius-full);
    overflow: hidden;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    background: var(--surface-2);
    border: 1px solid var(--avatar-border);
    box-shadow: var(--avatar-shadow);
  }
  .avatar img {
    width: 100%;
    height: 100%;
    object-fit: cover;
    display: block;
  }
  .avatar-fallback {
    width: 100%;
    height: 100%;
    display: flex;
    align-items: center;
    justify-content: center;
    color: var(--surface);
    font-weight: 600;
    font-size: calc(var(--asize, 44px) * 0.42);
    user-select: none;
    letter-spacing: 0.02em;
  }
  /* 柔和暖色调: 淡化向 theme surface, 深浅主题自动适配 */
  .h0 { background: color-mix(in srgb, var(--accent) 82%, var(--surface)); }
  .h1 { background: color-mix(in srgb, var(--info) 78%, var(--surface)); }
  .h2 { background: color-mix(in srgb, var(--success) 74%, var(--surface)); }
  .h3 { background: color-mix(in srgb, var(--warning) 80%, var(--surface)); }
  .h4 { background: color-mix(in srgb, var(--error) 74%, var(--surface)); }
</style>
