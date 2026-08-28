<script>
  // PromptAdvancedPanel.svelte — 高级 Prompt 区 (友好、分层、不吓人)
  //
  // 结构与职责:
  //   1. 顶部「保持默认」引导条 — 安抚用户, 明确「不改也完全正常」。
  //   2. 「微调你的角色」折叠面板 (默认收起) — 5 个常用可调字段, 友好控件。
  //   3. 「深度设置（通常无需修改）」折叠面板 (默认收起, 弱化视觉):
  //      - 3 个结构化 dict 表单 + 示例对话 + 核心记忆
  //      - 内层「旧版/深度字段」次级折叠收纳 6 个旧版字段 (保持原控件)
  //
  // Props:
  //   form   - 父层 $state 表单对象 { key: { meta, value, orig? } }
  //   saving - 保存中
  //   onsave - (keys: string[], label: string) => void
  //
  // 字段来源 promptFields.js (单一事实来源, 与后端 key 精确映射)。
  import PersonaField from './PersonaField.svelte';
  import PersonaListEditor from './PersonaListEditor.svelte';
  import PromptPanel from './PromptPanel.svelte';
  import PromptDictEditor from './PromptDictEditor.svelte';
  import PromptExampleDialogsEditor from './PromptExampleDialogsEditor.svelte';
  import {
    PROMPT_TUNE,
    PROMPT_DEEP,
    PROMPT_LEGACY,
  } from './promptFields.js';

  let { form = {}, saving = false, onsave } = $props();

  let tuneOpen = $state(false);
  let deepOpen = $state(false);
  let legacyOpen = $state(false);

  const tuneKeys = $derived(PROMPT_TUNE.map((f) => f.key));
  const deepKeys = $derived([...PROMPT_DEEP.map((f) => f.key), ...PROMPT_LEGACY.map((f) => f.key)]);
  const legacyKeys = $derived(PROMPT_LEGACY.map((f) => f.key));

  const tuneMeta = PROMPT_TUNE;
  const deepMeta = PROMPT_DEEP;
  const legacyMeta = PROMPT_LEGACY;

  function saveTune() {
    onsave?.(tuneKeys, '微调你的角色');
  }
  function saveDeep() {
    onsave?.(deepKeys, '深度设置');
  }
</script>

<div class="prompt-advanced">
  <!-- 顶部「保持默认」引导条 -->
  <div class="keep-default">
    <svg
      viewBox="0 0 24 24"
      width="18"
      height="18"
      fill="none"
      stroke="currentColor"
      stroke-width="2"
      stroke-linecap="round"
      stroke-linejoin="round"
      aria-hidden="true"
    ><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
    <p>
      以下提示词是系统为你自动生成的最优配置，<strong>绝大多数情况无需修改</strong>。想手动微调角色时再进入。
    </p>
  </div>

  <!-- 微调你的角色 -->
  <PromptPanel title="微调你的角色" badge="{tuneKeys.length} 个" tier={1} bind:open={tuneOpen}>
    {#snippet children()}
      {#each tuneMeta as meta (meta.key)}
        {#if meta.type === 'list'}
          <label class="field">
            <span class="field-label">{meta.label}</span>
            <PersonaListEditor bind:value={form[meta.key].value} emptyHint={meta.emptyHint || '点「添加」新增一项'} />
          </label>
        {:else}
          <label class="field">
            <span class="field-label">{meta.label}</span>
            <textarea
              class="field-input {meta.mono ? 'mono' : ''}"
              rows={meta.rows || 3}
              value={typeof form[meta.key].value === 'string' ? form[meta.key].value : ''}
              placeholder={meta.placeholder || ''}
              oninput={(e) => (form[meta.key].value = e.currentTarget.value)}
            ></textarea>
          </label>
        {/if}
        {#if meta.hint}
          <p class="field-hint">{meta.hint}</p>
        {/if}
      {/each}
    {/snippet}

    {#snippet actions()}
      <button class="btn btn-primary btn-sm" type="button" disabled={saving} onclick={saveTune}>
        {saving ? '保存中…' : '保存微调'}
      </button>
    {/snippet}
  </PromptPanel>

  <!-- 深度设置 -->
  <PromptPanel title="深度设置（通常无需修改）" badge="{deepKeys.length} 个" tier={2} bind:open={deepOpen}>
    {#snippet children()}
      <p class="deep-note">高级字段，一般不动。</p>

      <!-- 结构化 dict 表单 -->
      {#each deepMeta.slice(0, 3) as meta (meta.key)}
        <label class="field">
          <span class="field-label">{meta.label}</span>
          <PromptDictEditor bind:value={form[meta.key].value} fields={meta.spec.fields} />
        </label>
        {#if meta.hint}
          <p class="field-hint">{meta.hint}</p>
        {/if}
      {/each}

      <!-- 示例对话 -->
      <label class="field">
        <span class="field-label">{deepMeta[3].label}</span>
        <PromptExampleDialogsEditor bind:value={form[deepMeta[3].key].value} />
        {#if deepMeta[3].hint}
          <p class="field-hint">{deepMeta[3].hint}</p>
        {/if}
      </label>

      <!-- 核心记忆 -->
      <label class="field">
        <span class="field-label">{deepMeta[4].label}</span>
        <PersonaListEditor bind:value={form[deepMeta[4].key].value} emptyHint={deepMeta[4].emptyHint} />
      </label>

      <!-- 旧版 / 深度字段 (次级折叠, 保持原控件) -->
      <PromptPanel title="旧版 / 深度字段" badge="{legacyKeys.length} 个" tier={2} bind:open={legacyOpen}>
        {#snippet children()}
          {#each legacyMeta as meta (meta.key)}
            <label class="field">
              <span class="field-label">{meta.label}</span>
              <PersonaField item={form[meta.key]} />
            </label>
          {/each}
        {/snippet}
      </PromptPanel>
    {/snippet}

    {#snippet actions()}
      <button class="btn btn-outline btn-sm" type="button" disabled={saving} onclick={saveDeep}>
        {saving ? '保存中…' : '保存深度设置'}
      </button>
    {/snippet}
  </PromptPanel>
</div>

<style>
  .prompt-advanced {
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
    margin-top: var(--space-3);
  }

  /* 保持默认引导条 */
  .keep-default {
    display: flex;
    align-items: flex-start;
    gap: var(--space-2);
    padding: var(--space-3) var(--space-4);
    background: var(--info-soft);
    border: 1px solid color-mix(in srgb, var(--info) 28%, transparent);
    border-radius: var(--radius);
    color: var(--text-2);
  }
  .keep-default svg {
    flex: none;
    margin-top: 2px;
    color: var(--info);
  }
  .keep-default p {
    margin: 0;
    font-size: var(--text-sm);
    line-height: var(--leading-snug);
    color: var(--text-2);
  }
  .keep-default strong {
    color: var(--text-1);
    font-weight: 600;
  }

  .deep-note {
    margin: 0;
    font-size: var(--text-xs);
    color: var(--text-3);
  }

  .field {
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
  }
  .field-label {
    font-size: var(--text-sm);
    font-weight: 600;
    color: var(--text-2);
  }
  .field-input {
    width: 100%;
    padding: var(--space-2) var(--space-3);
    background: var(--input-bg);
    border: 1px solid var(--input-border);
    border-radius: var(--radius-sm);
    color: var(--input-text);
    font-size: var(--text-sm);
    line-height: var(--leading-snug);
    font-family: var(--font-sans);
    resize: vertical;
  }
  .field-input.mono {
    font-family: var(--font-mono);
    font-size: var(--text-sm);
  }
  .field-input:focus-visible {
    outline: none;
    border-color: var(--input-focus-border);
    box-shadow: var(--focus-ring);
  }
  .field-input::placeholder {
    color: var(--input-placeholder);
  }
  .field-hint {
    margin: -var(--space-1) 0 0;
    font-size: var(--text-xs);
    color: var(--text-3);
  }

  .btn {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: var(--space-2);
    border-radius: var(--btn-radius);
    font-size: var(--text-sm);
    font-weight: 600;
    cursor: pointer;
    transition: background var(--transition), border-color var(--transition), transform var(--transition), box-shadow var(--transition);
    border: 1px solid transparent;
    white-space: nowrap;
  }
  .btn:disabled {
    opacity: 0.55;
    cursor: not-allowed;
  }
  .btn:active:not(:disabled) { transform: scale(0.97); }
  .btn-primary {
    height: var(--btn-h-sm);
    padding: 0 var(--space-3);
    font-size: var(--text-xs);
    background: var(--btn-primary-bg);
    color: var(--btn-primary-text);
    box-shadow: var(--btn-primary-shadow);
  }
  .btn-primary:hover:not(:disabled) { background: var(--btn-primary-hover); }
  .btn-outline {
    height: var(--btn-h-sm);
    padding: 0 var(--space-3);
    font-size: var(--text-xs);
    background: var(--btn-outline-bg);
    border-color: var(--btn-outline-border);
    color: var(--btn-outline-text);
  }
  .btn-outline:hover:not(:disabled) { background: var(--btn-outline-hover); }
</style>
