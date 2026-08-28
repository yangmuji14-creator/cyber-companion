<script>
  // Switch.svelte — 开关 (使用 --switch-* 组件 token, 双向可控)
  let { checked = false, disabled = false, label = '', onchange } = $props();

  function toggle() {
    if (disabled) return;
    checked = !checked;
    onchange?.(checked);
  }
</script>

<button
  type="button"
  class="switch {checked ? 'is-on' : ''}"
  role="switch"
  aria-checked={checked}
  aria-label={label}
  disabled={disabled}
  onclick={toggle}
>
  <span class="knob"></span>
</button>

<style>
  .switch {
    position: relative;
    flex: none;
    width: var(--switch-w);
    height: var(--switch-h);
    border-radius: var(--radius-full);
    background: var(--switch-bg);
    border: none;
    cursor: pointer;
    transition: background var(--transition), box-shadow var(--transition),
      transform var(--transition-fast);
    padding: 0;
  }
  .switch .knob {
    position: absolute;
    top: 50%;
    left: calc((var(--switch-h) - var(--switch-knob-size)) / 2);
    width: var(--switch-knob-size);
    height: var(--switch-knob-size);
    border-radius: var(--radius-full);
    background: var(--switch-knob);
    transform: translateY(-50%);
    transition: transform var(--transition-snap), width var(--transition-fast),
      height var(--transition-fast);
    box-shadow: var(--switch-shadow);
  }
  .switch.is-on {
    background: var(--switch-bg-on);
    box-shadow: var(--switch-shadow-on);
  }
  .switch.is-on .knob {
    transform: translate(calc(var(--switch-w) - var(--switch-h)), -50%);
    background: var(--switch-knob-on);
  }
  .switch:active:not(:disabled) .knob {
    width: calc(var(--switch-knob-size) * 1.14);
    height: calc(var(--switch-knob-size) * 1.14);
  }
  .switch:disabled {
    opacity: 0.5;
    cursor: not-allowed;
    box-shadow: none;
  }
  .switch:focus-visible {
    outline: none;
    box-shadow: var(--focus-ring);
  }
</style>
