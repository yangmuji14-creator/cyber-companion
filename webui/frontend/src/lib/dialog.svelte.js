// ============================================================
// lib/dialog.js — 应用内模态对话框（确认/输入），替代原生 confirm/prompt
//
// 用法:
//   const ok = await confirmDialog('确定删除吗？', { title:'删除', danger:true });
//   const text = await promptDialog('输入备注名', { defaultValue:'' });
//   // settleDialog 由 <AppDialog/> 调用
// ============================================================

let resolveFn = null;

// 唯一当前对话框；null 表示无。此 $state 在模块作用域共享，<AppDialog/> 订阅渲染。
let dialog = $state(null);

function show(opts) {
  return new Promise((res) => {
    resolveFn = res;
    dialog = { ...opts };
  });
}

/**
 * 确认框 → Promise<boolean>
 * opts: { title?, message, confirmText?, danger?, cancelText? }
 */
export function confirmDialog(message, opts = {}) {
  return show({
    type: 'confirm',
    title: opts.title || '确认操作',
    message,
    confirmText: opts.confirmText || '确定',
    cancelText: opts.cancelText || '取消',
    danger: !!opts.danger,
  });
}

/**
 * 输入框 → Promise<string|null>（取消返回 null）
 * opts: { title?, message?, defaultValue?, placeholder?, danger? }
 */
export function promptDialog(message, opts = {}) {
  return show({
    type: 'prompt',
    title: opts.title || '输入内容',
    message: opts.message ?? message,
    defaultValue: opts.defaultValue || '',
    placeholder: opts.placeholder || '',
    cancelText: opts.cancelText || '取消',
    confirmText: opts.confirmText || '确定',
    danger: !!opts.danger,
  });
}

export function getDialog() {
  return dialog;
}

/** 由 <AppDialog/> 在确认/取消/关闭时调用，resolve 对应 Promise。 */
export function settleDialog(value) {
  const r = resolveFn;
  resolveFn = null;
  dialog = null;
  if (typeof r === 'function') r(value);
}
