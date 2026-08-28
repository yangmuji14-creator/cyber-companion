<script>
  // PersonaCard.svelte — 精简人设卡 (PawzoChat 式)
  //
  // 结构: 标题头 + 一组核心字段 + 单个「保存」按钮。
  // 只提交本卡涉及的字段 (复用父层按字段过滤的保存机制)。
  //
  // Props:
  //   form      - 父层 $state 表单对象 { key: { meta, value, orig? } }
  //   fields    - 本卡字段 metas 数组 (含 key/label/type/...)
  //   saving    - 保存中状态
  //   onsave    - (keys: string[]) => void  父层真正提交
  import PersonaField from './PersonaField.svelte';

  let { title, subtitle = '', fields = [], form = {}, saving = false, onsave } = $props();

  const keys = $derived(fields.map((f) => f.key));

  function handleSave() {
    onsave?.(keys, title);
  }
</script>

<section class="persona-card">
  <header class="pc-head">
    <h3 class="pc-title">{title}</h3>
    {#if subtitle}
      <p class="pc-sub">{subtitle}</p>
    {/if}
  </header>

  <div class="pc-fields">
    {#each fields as meta (meta.key)}
      <label class="field">
        <span class="field-label">
          {meta.label}{meta.type === 'number' && meta.key === 'age' ? ' (岁)' : ''}
        </span>
        <PersonaField item={form[meta.key]} />
      </label>
    {/each}
  </div>

  <div class="pc-save">
    <button class="btn btn-primary btn-sm" type="button" disabled={saving} onclick={handleSave}>
      {saving ? '保存中…' : '保存'}
    </button>
  </div>
</section>

<style>
  .persona-card {
    display: flex;
    flex-direction: column;
    gap: var(--space-4);
    padding: var(--card-pad);
    background: var(--card-bg);
    border: 1px solid var(--card-border);
    border-radius: var(--card-radius);
    box-shadow: var(--card-shadow);
  }
  .pc-head {
    display: flex;
    align-items: baseline;
    gap: var(--space-2);
    flex-wrap: wrap;
  }
  .pc-title {
    margin: 0;
    font-size: var(--text-lg);
    font-weight: 700;
    color: var(--text-1);
  }
  .pc-sub {
    margin: 0;
    font-size: var(--text-xs);
    color: var(--text-3);
  }
  .pc-fields {
    display: flex;
    flex-direction: column;
    gap: var(--space-4);
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
  .pc-save {
    display: flex;
    justify-content: flex-end;
    padding-top: var(--space-1);
    border-top: 1px solid var(--border);
    margin-top: var(--space-1);
  }
</style>
