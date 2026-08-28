<script>
  // PersonaListDictEditor.svelte — 两列"名称 + 说明"结构化编辑器
  // 用于后端类型 list[dict] 的字段（如 hobbies: [{name, detail?}]）。
  // 每一行：名称输入 + 可选说明输入，添加/删除行，不丢数据。保存时由上层过滤空名。
  let {
    value = $bindable([]), // [{name, detail?}]
    namePlaceholder = '名称',
    detailPlaceholder = '说明（可选）',
    emptyHint = '还没有内容，点「添加」新增一项',
  } = $props();

  function addRow() {
    value = [...value, { name: '', detail: '' }];
  }
  function removeRow(i) {
    const next = value.slice();
    next.splice(i, 1);
    value = next;
  }
  function setRow(j, key, v) {
    const next = value.slice();
    next[j] = { ...next[j], [key]: v };
    value = next;
  }
</script>

<div class="dict-editor">
  {#if value.length === 0}
    <p class="empty-hint">{emptyHint}</p>
  {:else}
    <div class="rows">
      {#each value as row, i (i)}
        <div class="row">
          <input
            class="row-input name"
            type="text"
            value={row.name}
            placeholder={namePlaceholder}
            oninput={(e) => setRow(i, 'name', e.currentTarget.value)}
            aria-label="名称 {i + 1}"
          />
          <input
            class="row-input detail"
            type="text"
            value={row.detail || ''}
            placeholder={detailPlaceholder}
            oninput={(e) => setRow(i, 'detail', e.currentTarget.value)}
            aria-label="说明 {i + 1}"
          />
          <button class="row-del" type="button" title="删除此项" onclick={() => removeRow(i)} aria-label="删除此项">
            <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
          </button>
        </div>
      {/each}
    </div>
  {/if}
  <button class="add-btn" type="button" onclick={addRow}>
    <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
    添加
  </button>
</div>

<style>
  .dict-editor {
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
    width: 100%;
  }
  .empty-hint {
    margin: 0;
    font-size: var(--text-xs);
    color: var(--text-3);
    padding: var(--space-1) 0;
  }
  .rows {
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
  }
  .row {
    display: grid;
    grid-template-columns: 1fr 1.4fr auto;
    gap: var(--space-2);
    align-items: center;
  }
  .row-input {
    min-width: 0;
    padding: var(--space-2) var(--space-3);
    background: var(--input-bg);
    border: 1px solid var(--input-border);
    border-radius: var(--radius-sm);
    color: var(--input-text);
    font-size: var(--text-sm);
    line-height: var(--leading-snug);
  }
  .row-input:focus-visible {
    outline: none;
    border-color: var(--input-focus-border);
    box-shadow: var(--focus-ring);
  }
  .row-input::placeholder {
    color: var(--input-placeholder);
  }
  .row-del {
    flex: none;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 30px;
    height: 30px;
    border-radius: var(--radius-full);
    border: none;
    background: transparent;
    color: var(--text-3);
    cursor: pointer;
    transition: background var(--transition), color var(--transition);
  }
  .row-del:hover {
    background: var(--row-hover);
    color: var(--error);
  }
  .add-btn {
    align-self: flex-start;
    display: inline-flex;
    align-items: center;
    gap: var(--space-1);
    height: var(--btn-h-sm);
    padding: 0 var(--space-3);
    border-radius: var(--btn-radius);
    border: 1px solid var(--btn-outline-border);
    background: var(--btn-outline-bg);
    color: var(--btn-outline-text);
    font-size: var(--text-xs);
    font-weight: 600;
    cursor: pointer;
    transition: background var(--transition), border-color var(--transition);
  }
  .add-btn:hover {
    background: var(--btn-outline-hover);
  }

  /* 窄屏两列会太紧，允许折行 */
  @media (max-width: 380px) {
    .row {
      grid-template-columns: 1fr auto;
    }
    .row .detail {
      grid-column: 1 / -1;
    }
  }
</style>
