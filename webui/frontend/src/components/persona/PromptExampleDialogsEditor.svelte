<script>
  // PromptExampleDialogsEditor.svelte — 结构化示例对话列表编辑器
  //
  // 每条: scenario (场景) + reply[] (TA 可能的回话, 可多条)。
  // 保存时由上层 denorm 过滤掉空场景的条目、剔除空回复。
  //
  // Props:
  //   value - bind 数组 [{ scenario, reply: [] }]
  let {
    value = $bindable([]),
    scenarioPlaceholder = '场景，如 深夜你发来消息',
    replyPlaceholder = 'TA 会怎么回',
    emptyHint = '还没有示例对话，点「添加」新增一条',
  } = $props();

  function addRow() {
    value = [...value, { scenario: '', reply: [''] }];
  }
  function removeRow(i) {
    const next = value.slice();
    next.splice(i, 1);
    value = next;
  }
  function setScenario(i, v) {
    const next = value.slice();
    next[i] = { ...next[i], scenario: v };
    value = next;
  }
  function addReply(i) {
    const next = value.slice();
    next[i] = { ...next[i], reply: [...(next[i].reply || []), ''] };
    value = next;
  }
  function setReply(i, j, v) {
    const next = value.slice();
    const reply = (next[i].reply || []).slice();
    reply[j] = v;
    next[i] = { ...next[i], reply };
    value = next;
  }
  function removeReply(i, j) {
    const next = value.slice();
    const reply = (next[i].reply || []).slice();
    reply.splice(j, 1);
    next[i] = { ...next[i], reply };
    value = next;
  }
</script>

<div class="dialog-editor">
  {#if value.length === 0}
    <p class="empty-hint">{emptyHint}</p>
  {:else}
    <div class="rows">
      {#each value as row, i (i)}
        <div class="row">
          <input
            class="row-input scenario"
            type="text"
            value={row.scenario || ''}
            placeholder={scenarioPlaceholder}
            oninput={(e) => setScenario(i, e.currentTarget.value)}
            aria-label="场景 {i + 1}"
          />
          <div class="replies">
            {#each row.reply || [] as r, j (j)}
              <div class="reply">
                <input
                  class="row-input reply-input"
                  type="text"
                  value={r}
                  placeholder={replyPlaceholder}
                  oninput={(e) => setReply(i, j, e.currentTarget.value)}
                  aria-label="回复 {i + 1} 第 {j + 1} 句"
                />
                <button
                  class="row-del"
                  type="button"
                  title="删除这句回复"
                  onclick={() => removeReply(i, j)}
                  aria-label="删除回复"
                >
                  <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
                </button>
              </div>
            {/each}
            <button class="add-btn mini" type="button" onclick={() => addReply(i)}>
              <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
              + 回复
            </button>
          </div>
          <button
            class="row-del"
            type="button"
            title="删除这条例子"
            onclick={() => removeRow(i)}
            aria-label="删除示例"
          >
            <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
          </button>
        </div>
      {/each}
    </div>
  {/if}
  <button class="add-btn" type="button" onclick={addRow}>
    <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
    添加示例
  </button>
</div>

<style>
  .dialog-editor {
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
    gap: var(--space-3);
  }
  .row {
    display: flex;
    align-items: flex-start;
    gap: var(--space-2);
    padding: var(--space-3);
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
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
  .row-input.scenario {
    flex: 1;
    font-weight: 500;
  }
  .replies {
    flex: 1;
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
  }
  .reply {
    display: flex;
    align-items: center;
    gap: var(--space-2);
  }
  .reply-input {
    flex: 1;
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
  .add-btn.mini {
    height: var(--btn-h-sm);
    padding: 0 var(--space-2);
    font-size: var(--text-xs);
    align-self: flex-start;
  }

  @media (max-width: 380px) {
    .row {
      flex-wrap: wrap;
    }
    .row .scenario {
      flex-basis: 100%;
    }
  }
</style>
