<script>
  // AppDialog.svelte — 全局模态对话框（确认/输入），替代浏览器原生 confirm/prompt
  import { getDialog, settleDialog } from '../lib/dialog.svelte.js';
  import { I } from './settings/icons.js';

  let inputEl = $state(null);

  const d = $derived(getDialog());

  function confirm() {
    if (!d) return;
    if (d.type === 'prompt') settleDialog(inputEl?.value ?? '');
    else settleDialog(true);
  }

  function cancel() {
    settleDialog(d && d.type === 'prompt' ? null : false);
  }

  function onKey(e) {
    if (!d) return;
    if (e.key === 'Enter') { e.preventDefault(); confirm(); }
    else if (e.key === 'Escape') { e.preventDefault(); cancel(); }
  }

  // 聚焦输入框 action
  function focusInput(node) {
    node.focus();
  }
</script>

{#if d}
  <div class="app-overlay" role="dialog" aria-modal="true" aria-label={d.title} tabindex="-1" onkeydown={onKey}>
    <div class="app-modal">
      <div class="app-modal-head">
        <h2 class="app-modal-title">{d.title}</h2>
        <button class="app-icon-btn" type="button" title="关闭" onclick={cancel}>
          {@html `<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${I.close}</svg>`}
        </button>
      </div>

      {#if d.message}
        <p class="app-modal-msg">{d.message}</p>
      {/if}

      {#if d.type === 'prompt'}
        <input
          key={d}
          class="app-input"
          type="text"
          value={d.defaultValue || ''}
          placeholder={d.placeholder}
          bind:this={inputEl}
          use:focusInput
        />
      {/if}

      <div class="app-modal-actions">
        <button class="app-btn app-btn-ghost" type="button" onclick={cancel}>{d.cancelText || '取消'}</button>
        <button
          class="app-btn {d.danger ? 'app-btn-danger' : 'app-btn-primary'}"
          type="button"
          onclick={confirm}
        >{d.confirmText || '确定'}</button>
      </div>
    </div>
  </div>
{/if}

<style>
  .app-overlay {
    position: fixed;
    inset: 0;
    z-index: 100;
    display: flex;
    align-items: center;
    justify-content: center;
    background: var(--overlay);
    padding: var(--space-4);
  }
  .app-modal {
    width: 100%;
    max-width: 380px;
    padding: var(--space-5);
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
    background: var(--surface);
    border: 1px solid var(--card-border);
    border-radius: var(--card-radius);
    box-shadow: var(--shadow-lg);
    animation: app-pop .18s ease-out;
  }
  @keyframes app-pop {
    from { opacity: 0; transform: scale(.96) translateY(4px); }
    to { opacity: 1; transform: none; }
  }
  .app-modal-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--space-2);
  }
  .app-modal-title {
    margin: 0;
    font-size: var(--text-lg);
    font-weight: 700;
    color: var(--text-1);
  }
  .app-icon-btn {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: var(--btn-h-sm);
    height: var(--btn-h-sm);
    border-radius: var(--radius-full);
    border: 1px solid var(--btn-outline-border);
    background: var(--btn-outline-bg);
    color: var(--btn-outline-text);
    cursor: pointer;
    transition: background var(--transition), color var(--transition);
  }
  .app-icon-btn:hover { background: var(--btn-outline-hover); color: var(--accent); }
  .app-modal-msg {
    margin: 0;
    font-size: var(--text-base);
    line-height: 1.6;
    color: var(--text-2);
    word-break: break-word;
    white-space: pre-wrap;
  }
  .app-input {
    width: 100%;
    padding: var(--space-2) var(--space-3);
    background: var(--input-bg);
    border: 1px solid var(--input-border);
    border-radius: var(--input-radius);
    color: var(--input-text);
    font-size: var(--text-base);
  }
  .app-input:focus-visible {
    outline: none;
    border-color: var(--input-focus-border);
    box-shadow: var(--focus-ring);
  }
  .app-input::placeholder { color: var(--input-placeholder); }

  .app-modal-actions {
    display: flex;
    justify-content: flex-end;
    gap: var(--space-2);
    margin-top: var(--space-1);
  }
  .app-btn {
    height: var(--btn-h-md);
    padding: 0 var(--space-4);
    border-radius: var(--btn-radius);
    border: 1px solid transparent;
    font-size: var(--text-sm);
    line-height: 1;
    cursor: pointer;
    transition: background var(--transition), color var(--transition), transform var(--transition);
  }
  .app-btn:active { transform: scale(0.97); }
  .app-btn-primary {
    background: var(--btn-primary-bg);
    color: var(--btn-primary-text);
    box-shadow: var(--btn-primary-shadow);
  }
  .app-btn-primary:hover { background: var(--btn-primary-hover); }
  .app-btn-ghost {
    background: transparent;
    border-color: var(--btn-outline-border);
    color: var(--btn-outline-text);
  }
  .app-btn-ghost:hover { background: var(--btn-outline-hover); }
  .app-btn-danger {
    background: var(--error);
    color: #fff;
  }
  .app-btn-danger:hover { filter: brightness(1.08); }
</style>
