<script>
  // SamplingPresets.svelte — 采样参数预设档位
  // 一排档位卡片, 点选即把推荐值填入表单; "自定义" 不覆盖手填值。
  // 组件根据当前 temperature/presence/frequency 是否精确命中某档来高亮。
  // 纯 UI 快捷填充, 不直接改 pf, 通过 onselect(presetValues | null) 回调交给父级。

  let { temperature = null, presence = null, frequency = null, onselect } = $props();

  const PRESETS = [
    {
      id: 'balanced',
      name: '标准对话',
      tag: '推荐',
      desc: '平衡自然，日常陪伴刚刚好',
      values: { temperature: 0.8, presence_penalty: 0.6, frequency_penalty: 0.5 },
    },
    {
      id: 'steady',
      name: '克制稳定',
      tag: null,
      desc: '回复更稳、少发散，适合正经场合',
      values: { temperature: 0.5, presence_penalty: 0.2, frequency_penalty: 0.3 },
    },
    {
      id: 'playful',
      name: '活泼创新',
      tag: '敢玩',
      desc: '更敢玩、更多新意，脑洞大开',
      values: { temperature: 1.2, presence_penalty: 1.0, frequency_penalty: 0.8 },
    },
    { id: 'custom', name: '自定义', tag: null, desc: '保持当前手填值，不覆盖表单', values: null },
  ];

  let selectedId = $derived(matchPreset());

  function matchPreset() {
    for (const p of PRESETS) {
      if (!p.values) continue;
      const v = p.values;
      if (temperature === v.temperature && presence === v.presence_penalty && frequency === v.frequency_penalty) {
        return p.id;
      }
    }
    return 'custom';
  }

  function pick(p) {
    if (p.values) onselect?.(p.values);
    else onselect?.(null);
  }
</script>

<div class="sampling-presets" role="group" aria-label="采样参数预设档位">
  <div class="presets-head">
    <span class="presets-title">一键档位</span>
    <span class="presets-sub">点一个档位，自动填好下面的参数</span>
  </div>
  <div class="presets-grid">
    {#each PRESETS as p}
      <button
        type="button"
        class="preset-card"
        class:on={selectedId === p.id}
        onclick={() => pick(p)}
      >
        <span class="preset-name">
          {p.name}
          {#if p.tag}<span class="preset-tag">{p.tag}</span>{/if}
        </span>
        <span class="preset-desc">{p.desc}</span>
      </button>
    {/each}
  </div>
</div>

<style>
  .sampling-presets {
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
    padding: var(--space-3);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    background: var(--surface);
  }

  .presets-head {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    gap: var(--space-3);
    flex-wrap: wrap;
  }
  .presets-title {
    font-size: var(--text-sm);
    font-weight: 600;
    color: var(--text-1);
  }
  .presets-sub {
    font-size: var(--text-xs);
    color: var(--text-3);
  }

  .presets-grid {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: var(--space-2);
  }

  .preset-card {
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    gap: var(--space-1);
    padding: var(--space-3);
    border: 1px solid var(--border-strong);
    border-radius: var(--radius-sm);
    background: var(--surface-2);
    color: var(--text-1);
    font-family: inherit;
    text-align: left;
    cursor: pointer;
    transition: background var(--transition), border-color var(--transition),
      transform var(--transition), box-shadow var(--transition);
  }
  .preset-card:hover {
    background: var(--surface-3);
    border-color: var(--accent);
    transform: translateY(-1px);
    box-shadow: var(--shadow-sm);
  }
  .preset-card.on {
    background: var(--tint);
    border-color: var(--accent);
    box-shadow: var(--shadow-accent);
  }
  .preset-card:active { transform: scale(0.97); }

  .preset-name {
    display: inline-flex;
    align-items: center;
    gap: var(--space-1);
    font-size: var(--text-sm);
    font-weight: 600;
  }
  .preset-card.on .preset-name { color: var(--accent-strong); }

  .preset-tag {
    font-size: var(--text-xs);
    font-weight: 500;
    padding: 0 var(--space-1);
    border-radius: var(--radius-full);
    color: var(--on-accent);
    background: var(--accent);
  }

  .preset-desc {
    font-size: var(--text-xs);
    color: var(--text-3);
    line-height: var(--leading-snug);
  }

  /* 移动端: 两列; 桌面: 四列 */
  @media (max-width: 640px) {
    .presets-grid { grid-template-columns: repeat(2, 1fr); }
  }
</style>
