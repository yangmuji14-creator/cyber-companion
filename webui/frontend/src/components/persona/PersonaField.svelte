<script>
  // PersonaField.svelte — 根据 meta.type 分发渲染对应控件
  //
  // 输入: item = { meta, value } （来自父层 $state 表单对象的某字段）.
  // 直接修改 item.value（Svelte 5 rune 深响应），无需 bind: 回传。
  //
  // 支持的控件类型:
  //   text      > 单行输入
  //   number    > 数字输入
  //   textarea  > 多行文本 (+ 计数)
  //   select    > 下拉 (meta.options)
  //   range     > 滑杆 (meta.min/max/step, 百分比显示用 meta.percent)
  //   switch    > Switch 开关
  //   list      > 字符串列表编辑器
  //   list-dict > 两列 (名称+说明) 编辑器
  //   json      > 等宽 JSON 文本域 (用于 dict 类高级字段)
  import Switch from '../Switch.svelte';
  import PersonaListEditor from './PersonaListEditor.svelte';
  import PersonaListDictEditor from './PersonaListDictEditor.svelte';

  let { item } = $props();
  let meta = $derived(item.meta);
  let value = $derived(item.value);

  function setRaw(v) {
    item.value = v;
  }

  // 文本域字符计数
  let count = $derived(typeof value === 'string' ? value.length : 0);

  function rangeDisplay() {
    if (meta.percent) return `${Math.round(value * 100)}%`;
    return String(value);
  }
</script>

{#if meta.type === 'text'}
  <input class="field-input" type="text" value={typeof value === 'string' ? value : ''}
    placeholder={meta.placeholder || ''} oninput={(e) => setRaw(e.currentTarget.value)} />
{:else if meta.type === 'number'}
  <input class="field-input" type="number" value={value === '' || value == null ? '' : value}
    step={meta.step || 1} min={meta.min} max={meta.max}
    oninput={(e) => {
      const n = e.currentTarget.value;
      setRaw(n === '' ? '' : Number(n));
    }} />
{:else if meta.type === 'select'}
  <select class="field-select" value={typeof value === 'string' ? value : ''} onchange={(e) => setRaw(e.currentTarget.value)}>
    {#each meta.options || [] as opt (opt)}
      <option value={opt}>{opt}</option>
    {/each}
  </select>
{:else if meta.type === 'range'}
  <div class="range-row">
    <input class="field-range" type="range" value={value == null ? (meta.min ?? 0) : value}
      min={meta.min ?? 0} max={meta.max ?? 100} step={meta.step ?? 1}
      oninput={(e) => setRaw(Number(e.currentTarget.value))} />
    <span class="range-val">{rangeDisplay()}</span>
  </div>
{:else if meta.type === 'switch'}
  <div class="field-switch">
    <Switch checked={!!value} onchange={(v) => setRaw(v)} label={meta.label} />
  </div>
{:else if meta.type === 'list'}
  <PersonaListEditor bind:value={item.value} placeholder={meta.placeholder || ''} emptyHint={meta.emptyHint || '还没有内容，点「添加」新增一项'} />
{:else if meta.type === 'list-dict'}
  <PersonaListDictEditor bind:value={item.value} namePlaceholder={meta.namePlaceholder || '名称'} detailPlaceholder={meta.detailPlaceholder || '说明（可选）'} />
{:else if meta.type === 'json'}
  <textarea class="field-input mono" rows={meta.rows || 4}
    value={typeof value === 'string' ? value : ''}
    placeholder={meta.placeholder || 'JSON 格式，保持默认即可'}
    oninput={(e) => setRaw(e.currentTarget.value)}></textarea>
{:else}
  <!-- textarea / 默认多行 -->
  <div class="textarea-wrap">
    <textarea class="field-input" rows={meta.rows || 3}
      value={typeof value === 'string' ? value : ''}
      placeholder={meta.placeholder || ''}
      oninput={(e) => setRaw(e.currentTarget.value)}></textarea>
    {#if meta.counter !== false}
      <span class="char-count">{count}</span>
    {/if}
  </div>
{/if}

{#if meta.hint}
  <p class="field-hint">{meta.hint}</p>
{/if}

<style>
  .field-input {
    width: 100%;
    padding: var(--space-2) var(--space-3);
    background: var(--input-bg);
    border: 1px solid var(--input-border);
    border-radius: var(--input-radius);
    color: var(--input-text);
    font-size: var(--text-base);
    font-family: var(--font-sans);
    line-height: var(--leading-snug);
  }
  .field-input.mono {
    font-family: var(--font-mono);
    font-size: var(--text-sm);
    border-radius: var(--radius-sm);
    resize: vertical;
  }
  textarea.field-input {
    resize: vertical;
  }
  .field-input:focus-visible {
    outline: none;
    border-color: var(--input-focus-border);
    box-shadow: var(--focus-ring);
  }
  .field-input::placeholder {
    color: var(--input-placeholder);
  }

  .field-select {
    width: 100%;
    padding: var(--space-2) var(--space-3);
    background: var(--input-bg);
    border: 1px solid var(--input-border);
    border-radius: var(--input-radius);
    color: var(--input-text);
    font-size: var(--text-base);
    font-family: var(--font-sans);
    line-height: var(--leading-snug);
    cursor: pointer;
    appearance: none;
    background-image: url("data:image/svg+xml;charset=utf-8,%3Csvg xmlns='http://www.w3.org/2000/svg' width='16' height='16' viewBox='0 0 24 24' fill='none' stroke='%23a9907d' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpolyline points='6 9 12 15 18 9'/%3E%3C/svg%3E");
    background-repeat: no-repeat;
    background-position: right var(--space-3) center;
    padding-right: var(--space-7);
  }
  .field-select:focus-visible {
    outline: none;
    border-color: var(--input-focus-border);
    box-shadow: var(--focus-ring);
  }

  .range-row {
    display: flex;
    align-items: center;
    gap: var(--space-3);
  }
  .field-range {
    flex: 1;
    min-width: 0;
    accent-color: var(--accent);
    cursor: pointer;
  }
  .range-val {
    flex: none;
    min-width: 56px;
    text-align: right;
    font-size: var(--text-sm);
    font-weight: 600;
    color: var(--text-2);
    font-variant-numeric: tabular-nums;
  }

  .field-switch {
    display: flex;
  }

  .textarea-wrap {
    position: relative;
    width: 100%;
  }
  .textarea-wrap textarea {
    width: 100%;
  }
  .char-count {
    position: absolute;
    right: var(--space-2);
    bottom: var(--space-1);
    font-size: var(--text-xs);
    color: var(--text-3);
    pointer-events: none;
    font-variant-numeric: tabular-nums;
  }

  .field-hint {
    margin: 0;
    font-size: var(--text-xs);
    color: var(--text-3);
  }
</style>
