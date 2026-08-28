<script>
  // PromptDictEditor.svelte — 友好键值表单 (用于 dict 类高级字段)
  //
  // 只渲染 spec.fields 里声明的输入框, 每个输入框对应一个后端 dict key。
  // 未知 key 不会出现在 UI, 但被保留在 value 对象中原样传回(不丢字段)。
  //
  // Props:
  //   value  - 绑定对象编辑态 (含 spec.keys 及可能的历史未知 key)
  //   fields - [{ key, label, placeholder?, rows?, mono? }]
  let { value = $bindable({}), fields = [] } = $props();
</script>

<div class="dict-editor">
  {#each fields as spec (spec.key)}
    <label class="dfield">
      <span class="dfield-label">{spec.label}</span>
      <textarea
        class="dfield-input {spec.mono ? 'mono' : ''}"
        rows={spec.rows || 2}
        value={value[spec.key] ?? ''}
        placeholder={spec.placeholder || ''}
        oninput={(e) => (value[spec.key] = e.currentTarget.value)}
      ></textarea>
    </label>
  {/each}
</div>

<style>
  .dict-editor {
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
    width: 100%;
  }
  .dfield {
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
  }
  .dfield-label {
    font-size: var(--text-sm);
    font-weight: 600;
    color: var(--text-2);
  }
  .dfield-input {
    width: 100%;
    padding: var(--space-2) var(--space-3);
    background: var(--input-bg);
    border: 1px solid var(--input-border);
    border-radius: var(--radius-sm);
    color: var(--input-text);
    font-size: var(--text-sm);
    line-height: var(--leading-snug);
    resize: vertical;
    font-family: var(--font-sans);
  }
  .dfield-input.mono {
    font-family: var(--font-mono);
    font-size: var(--text-sm);
  }
  .dfield-input:focus-visible {
    outline: none;
    border-color: var(--input-focus-border);
    box-shadow: var(--focus-ring);
  }
  .dfield-input::placeholder {
    color: var(--input-placeholder);
  }
</style>
