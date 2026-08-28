<script>
  // PersonaAdvanced.svelte — 「高级 / 全部字段」折叠区
  //
  // 默认收起；点击头部展开全部字段。展开后按原分组以手风琴展示
  // (每组一个可折叠面板)。精简卡里的字段不在这些分组中重复出现，
  // 因此分组 = 原 USER_GROUPS/ADV_GROUP 减去精简字段后的剩余。
  //
  // Props:
  //   groups     - [{ id, label, hint?, fields }] 剩余字段分组
  //   form       - 父层 $state 表单对象
  //   saving     - 保存中
  //   onsave     - (keys: string[]) => void
  import PersonaField from './PersonaField.svelte';

  let { groups = [], form = {}, saving = false, onsave } = $props();

  let expanded = $state(false); // 主区开关 (头部 "展开全部")
  let openGroups = $state({}); // 每组手风琴开合 { id: bool }

  const totalCount = $derived(groups.reduce((n, g) => n + g.fields.length, 0));

  function toggleGroup(id) {
    openGroups[id] = !openGroups[id];
  }

  function toggleAll() {
    expanded = !expanded;
    if (expanded) {
      // 展开时默认打开第一组, 其余收起, 保持清爽
      const first = groups[0]?.id;
      openGroups = {};
      if (first) openGroups[first] = true;
    } else {
      openGroups = {};
    }
  }

  function saveGroup(g) {
    onsave?.(g.fields.map((f) => f.key), g.label);
  }
</script>

<div class="advanced">
  <button
    class="adv-toggle"
    type="button"
    aria-expanded={expanded}
    onclick={toggleAll}
  >
    <span class="adv-label">高级 / 全部字段</span>
    <span class="adv-count">{totalCount} 个</span>
    <svg
      class="adv-arrow {expanded ? 'is-open' : ''}"
      viewBox="0 0 24 24"
      width="18"
      height="18"
      fill="none"
      stroke="currentColor"
      stroke-width="2"
      stroke-linecap="round"
      stroke-linejoin="round"
      aria-hidden="true"
    ><polyline points="6 9 12 15 18 9"/></svg>
  </button>

  {#if expanded}
    <div class="adv-groups">
      {#each groups as g (g.id)}
        <section class="adv-group">
          <button
            class="adv-group-head"
            type="button"
            aria-expanded={!!openGroups[g.id]}
            onclick={() => toggleGroup(g.id)}
          >
            <span class="adv-group-label">{g.label}</span>
            <span class="adv-group-n">{g.fields.length}</span>
            <svg
              class="adv-arrow {openGroups[g.id] ? 'is-open' : ''}"
              viewBox="0 0 24 24"
              width="16"
              height="16"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
              stroke-linecap="round"
              stroke-linejoin="round"
              aria-hidden="true"
            ><polyline points="6 9 12 15 18 9"/></svg>
          </button>

          {#if openGroups[g.id]}
            <div class="adv-group-body">
              {#if g.hint}
                <p class="group-hint">{g.hint}</p>
              {/if}
              <div class="adv-fields">
                {#each g.fields as meta (meta.key)}
                  <label class="field">
                    <span class="field-label">{meta.label}</span>
                    <PersonaField item={form[meta.key]} />
                  </label>
                {/each}
              </div>
              <div class="adv-save">
                <button class="btn btn-outline btn-sm" type="button" disabled={saving} onclick={() => saveGroup(g)}>
                  {saving ? '保存中…' : `保存${g.label}`}
                </button>
              </div>
            </div>
          {/if}
        </section>
      {/each}
    </div>
  {/if}
</div>

<style>
  .advanced {
    margin-top: var(--space-3);
  }
  .adv-toggle {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    width: 100%;
    padding: var(--space-3) var(--space-4);
    background: transparent;
    border: 1px dashed var(--border-strong);
    border-radius: var(--radius);
    color: var(--text-2);
    font-size: var(--text-sm);
    font-weight: 600;
    cursor: pointer;
    transition: background var(--transition), border-color var(--transition), color var(--transition);
  }
  .adv-toggle:hover {
    background: var(--surface-2);
    color: var(--text-1);
  }
  .adv-label {
    flex: 1;
    text-align: left;
  }
  .adv-count {
    font-size: var(--text-xs);
    font-weight: 600;
    color: var(--text-3);
    background: var(--surface-3);
    border-radius: var(--radius-full);
    padding: var(--space-1) var(--space-2);
  }
  .adv-arrow {
    transition: transform var(--transition);
    color: var(--text-3);
  }
  .adv-arrow.is-open {
    transform: rotate(180deg);
  }

  .adv-groups {
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
    margin-top: var(--space-3);
  }
  .adv-group {
    background: var(--card-bg);
    border: 1px solid var(--card-border);
    border-radius: var(--card-radius);
    box-shadow: var(--card-shadow);
    overflow: hidden;
  }
  .adv-group-head {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    width: 100%;
    padding: var(--space-3) var(--space-4);
    background: transparent;
    border: none;
    color: var(--text-1);
    font-size: var(--text-sm);
    font-weight: 600;
    cursor: pointer;
    transition: background var(--transition);
  }
  .adv-group-head:hover {
    background: var(--row-hover);
  }
  .adv-group-label {
    flex: 1;
    text-align: left;
  }
  .adv-group-n {
    font-size: var(--text-xs);
    color: var(--text-3);
  }
  .adv-group-body {
    padding: var(--space-4);
    border-top: 1px solid var(--border);
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
  }
  .group-hint {
    margin: 0;
    font-size: var(--text-xs);
    color: var(--text-3);
  }
  .adv-fields {
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
  .adv-save {
    display: flex;
    justify-content: flex-end;
  }
</style>
