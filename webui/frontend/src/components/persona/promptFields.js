// promptFields.js — 高级 Prompt 字段的单一事实来源 (meta 描述 + 分层分组)
//
// 这些 meta 的 key 必须与后端 /api/persona/{id} 的 fields 完全一致，
// 也与 core/persona/prompt_builder.py 读取的 dict key 完全一致（只读参考）：
//   speaking_style        → 读 ['基础风格']
//   emotional_patterns    → 读 ['依恋类型','压力反应','爱的语言']
//   relationship_behavior → 读 ['冲突模式','边界需求']
//   example_dialogs       → list[{scenario, reply:[..]}]
//   hard_rules / taboos / core_memories → list[str]
//
// 新的类型:
//   prompt-dict   → 友好键值表单 (inner spec.fields), 保存为非空 key 的 dict
//   dialog-list   → 结构化示例对话列表 (scenario + reply[])
// 其余沿用既有类型 (textarea/list/json), 由 PersonaField 渲染。

export const PROMPT_TUNE = [
  {
    key: 'persona_prompt',
    label: '人设 Prompt',
    type: 'textarea',
    mono: true,
    rows: 5,
    placeholder: '这里可以写 TA 的人设与生活背景，比如经历、日常',
    hint: '写 TA 是谁、经历过什么、日常是怎样的。',
  },
  {
    key: 'system_prompt',
    label: 'System Prompt',
    type: 'textarea',
    mono: true,
    rows: 5,
    placeholder: '额外的系统指令',
    hint: '原样附加到系统提示的最后一层。',
  },
  {
    key: 'output_examples',
    label: '说话示例',
    type: 'textarea',
    rows: 4,
    placeholder: '给几个 TA 说话的例句，帮助把握语气',
    hint: '给几个 TA 说话的例句，帮助把握语气。',
  },
  {
    key: 'hard_rules',
    label: '硬性规则',
    type: 'list',
    emptyHint: '一条条不可违背的规则，点「添加」新增',
  },
  {
    key: 'taboos',
    label: '禁忌话题',
    type: 'list',
    emptyHint: '绝对不聊的话题，一条一条写',
  },
];

export const PROMPT_DEEP = [
  {
    key: 'speaking_style',
    label: '说话风格',
    type: 'prompt-dict',
    hint: 'TA 平时说话的基调。',
    spec: {
      keys: ['基础风格'],
      fields: [
        {
          key: '基础风格',
          label: '基础风格',
          placeholder: '如 温柔、话不多但很贴心',
          rows: 2,
        },
      ],
    },
  },
  {
    key: 'emotional_patterns',
    label: '情绪模式',
    type: 'prompt-dict',
    hint: 'TA 的情感与压力反应。',
    spec: {
      keys: ['依恋类型', '压力反应', '爱的语言'],
      fields: [
        {
          key: '依恋类型',
          label: '依恋类型',
          placeholder: '如 安全型',
          rows: 2,
        },
        {
          key: '压力反应',
          label: '压力反应',
          placeholder: '如 会先自己待一会儿再找人倾诉',
          rows: 2,
        },
        {
          key: '爱的语言',
          label: '爱的语言',
          placeholder: '如 行动付出、偶尔口头肯定',
          rows: 2,
        },
      ],
    },
  },
  {
    key: 'relationship_behavior',
    label: '关系行为',
    type: 'prompt-dict',
    hint: '相处中遇到矛盾 / 需要边界时的表现。',
    spec: {
      keys: ['冲突模式', '边界需求'],
      fields: [
        {
          key: '冲突模式',
          label: '冲突模式',
          placeholder: '如 会冷静下来再沟通',
          rows: 2,
        },
        {
          key: '边界需求',
          label: '边界需求',
          placeholder: '如 需要自己的独处时间',
          rows: 2,
        },
      ],
    },
  },
  {
    key: 'example_dialogs',
    label: '示例对话',
    type: 'dialog-list',
    hint: '给 TA 几个典型场景下的说话示范，帮助把握节奏。',
  },
  {
    key: 'core_memories',
    label: '核心记忆',
    type: 'list',
    emptyHint: '你和 TA 的共同记忆，一条一条写',
  },
];

export const PROMPT_LEGACY = [
  { key: 'identity_anchor', label: '身份锚点', type: 'json', mono: true },
  { key: 'legacy_speaking_style', label: '旧版说话风格', type: 'textarea' },
  { key: 'values', label: '价值观', type: 'list' },
  { key: 'important_moments', label: '重要时刻', type: 'list' },
  { key: 'how_we_met', label: '我们如何相识', type: 'textarea' },
  { key: 'first_impression', label: '第一印象', type: 'textarea' },
];

export const PROMPT_ALL = [...PROMPT_TUNE, ...PROMPT_DEEP, ...PROMPT_LEGACY];
