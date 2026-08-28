<script>
  // UrlPreview.svelte — base_url 实时最终请求地址预览
  // 纯前端字符串拼接: base_url + "/chat/completions" (deepseek/openai 类型),
  // anthropic 类型 → "/messages"。base_url 为空显示 "—"。
  let { base_url = '', provider = '' } = $props();

  let preview = $derived(buildPreview(base_url, provider));

  function buildPreview(url, prov) {
    const u = (url ?? '').trim();
    if (!u) return '';
    const base = u.replace(/\/+$/, '');
    const isAnthropic = (prov ?? '').toLowerCase().includes('anthropic');
    return `${base}${isAnthropic ? '/messages' : '/chat/completions'}`;
  }
</script>

<div class="url-preview">
  {#if preview}
    <span class="up-label">请求地址</span>
    <code class="up-code">{preview}</code>
  {:else}
    <span class="up-label">请求地址</span>
    <span class="up-empty">—</span>
  {/if}
</div>

<style>
  .url-preview {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    flex-wrap: wrap;
    margin-top: var(--space-1);
    font-size: var(--text-xs);
  }
  .up-label { color: var(--text-3); }
  .up-code {
    font-family: var(--font-mono);
    font-size: var(--text-xs);
    color: var(--accent-strong);
    background: var(--surface-2);
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
    padding: 2px var(--space-2);
    word-break: break-all;
  }
  .up-empty { color: var(--text-3); }
</style>
