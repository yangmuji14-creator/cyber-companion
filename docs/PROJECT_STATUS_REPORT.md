# 赛博女友（Cyber Girlfriend）项目状态报告

> 生成日期：2026-06-12 | 总代码行：15,293 | 测试数：115 | 全量通过：✅

---

## 一、项目概要

纯终端（CMD）AI 伴侣聊天机器人，基于 **Python 3.11+ / asyncio**，支持语义记忆、情感分析、丰富人设、动态亲密度、持续性情绪系统、工具调用。

| 维度 | 现状 |
|------|------|
| 模型接入 | 6 家（DeepSeek/OpenAI/Gemini/通义千问/Kimi/智谱），通过 LiteLLM 统一接口 |
| 核心管线 | ChatPipeline 完整编排（情感 → Mood → 记忆 → Prompt → LLM → 工具循环 → 增强） |
| 数据持久化 | SQLite 为主（记忆/向量/情绪/人格）+ JSON（关系/历史）+ 原子写入 |
| 终端交互 | 消息去抖合并 + 流式输出 + spinner 动画 + 18 个斜杠命令 |

---

## 二、代码规模分布

```
core/                      ~9,300 行
├── chat/                  1,283 行  ── pipeline(402) + commands(545) + handler(323)
├── memory/                1,613 行  ── 8 个文件（含 v1.2 新模块）
├── emotion/                 932 行  ── analyzer + expression + mood + llm_analyzer
├── relationship/            329 行  ── tracker + evolution(v1.2)
├── persona/                 472 行  ── models + loader + prompt_builder
├── dialogue/                569 行  ── thinker + consistency + topic_tracker + persona_checker(v1.2)
├── proactive.py             319 行  ── 主动消息（含 v1.2 增强）
├── personality/             246 行  ── 人格引擎
├── tools/                   367 行  ── 工具系统（time/weather/calc）
├── llm/                     295 行  ── 模型抽象层
└── multimodal/              349 行  ── 图片 + 颜文字

tests/                     ~2,000 行（115 个测试，全量通过）
main.py                      126 行  ── 入口（大幅缩减，命令已拆分）
```

---

## 三、模块状态详表

### 3.1 成熟模块（稳定，无需大改）

| 模块 | 行数 | 状态 | 关键特征 |
|------|------|------|----------|
| `llm/` | 295 | ✅ 稳定 | LiteLLM 统一接口，指数退避重试，6 家适配器 |
| `persona/models.py` | 143 | ✅ 稳定 | 30+ 字段人设，完整 to_dict/from_dict |
| `persona/loader.py` | 71 | ✅ 稳定 | JSON 加载，运行时切换 |
| `emotion/analyzer.py` | 131 | ✅ 稳定 | 8 种情感关键词检测，否定词处理 |
| `emotion/llm_analyzer.py` | 203 | ✅ 稳定 | LLM 辅助分析 + 关键词降级 + 情感轨迹 |
| `emotion/expression.py` | 246 | ✅ 稳定 | 消息分段 + emoji 增强 + MoodExpressionEngine |
| `relationship/tracker.py` | 168 | ✅ 稳定 | 复合键亲密度，情感影响 + 时间衰减 |
| `memory/storage.py` | 235 | ✅ 稳定 | SQLite 持久化，WAL 模式，JSON→SQLite 迁移 |
| `memory/scorer.py` | 199 | ✅ 稳定 | 25+ 关键词加权评分（1-5 级） |
| `memory/chat_history.py` | 224 | ✅ 稳定 | 对话存储 + 搜索 + 短期记忆 |
| `memory/stats.py` | 194 | ✅ 稳定 | ASCII 仪表盘（情绪/时间/趋势） |
| `memory/summarizer.py` | 261 | ✅ 稳定 | LLM 记忆提取 + 批量总结 + 关联检索 |
| `personality/engine.py` | 246 | ✅ 稳定 | 5 维人格（信任/依赖/开放/好感/醋意） |
| `tools/` | 367 | ✅ 稳定 | BaseTool 抽象 + 3 工具（时间/计算/天气） |
| `multimodal/` | 349 | ✅ 稳定 | 图片处理 + 颜文字/表情包回复 |
| `chat/commands.py` | 545 | ✅ 稳定 | 18 个斜杠命令，含 `/mood /personality /tools /img` |

### 3.2 中等成熟模块（近期有改动）

| 模块 | 行数 | 状态 | 说明 |
|------|------|------|------|
| `chat/pipeline.py` | 402 | ✅ 已增强 | v1.2 新增人设一致性检查 + 行为画像注入 |
| `emotion/mood.py` | 352 | ✅ 已增强 | v1.2 新增 `expires_at` + 各情绪独立持续时间 |
| `memory/manager.py` | 357 | ✅ 已增强 | v1.2 集成冲突解析器 + 遗忘衰减 + 置信度 |
| `persona/prompt_builder.py` | 258 | ✅ 已增强 | v1.2 新增可选 behavior_profile 参数 |
| `proactive.py` | 319 | ✅ 已增强 | v1.2 新增记忆追问 + 持续关怀 |

### 3.3 v1.2 新模块（2026-06-12 上线）

| 模块 | 行数 | 说明 |
|------|------|------|
| `memory/conflict_resolver.py` | 187 | 三种冲突检测（反义词/身份数字/状态对立），批量版 detect() + 单条版 detect_conflict() |
| `memory/decay.py` | 140 | 遗忘系统：逐日 forget_score 计算 + 归档判断 + 检索权重 + 重要度/分类修正 |
| `relationship/evolution.py` | 161 | 纯静态关系行为画像：4 阶段（陌生→深度），11 维 BehaviorProfile 参数，to_prompt_instructions() |
| `dialogue/persona_checker.py` | 114 | 回复后人设冲突检查：偏好冲突/行为规则/语言风格，返回 ConsistencyCheckResult |
| `memory/models.py`（增强） | 156 | 新增 confidence / forget_score / archived 字段 + infer_confidence() 静态方法 |

---

## 四、数据流架构

```
用户输入
  │
  ▼
handler.py 去抖合并（3s 窗口）
  │
  ▼
pipeline.py 核心处理管线：
  │
  ├─ 1. LLM 情感分析（关键词 → LLM 降级）
  ├─ 2. Mood 更新（2D valence/arousal，按类型分配 expires_at）
  ├─ 3. 人格更新（5 维人格引擎）
  ├─ 4. 对话思考（CoT 意图分析）
  ├─ 5. 存入 chat_history
  ├─ 6. 更新亲密度（情感影响 + 时间衰减）
  ├─ 7. 记忆检索（向量 Top-K → 语义降级关键词 → LLM 关联检索）
  ├─ 8. 生成行为画像（RelationshipEvolution.get_profile）
  ├─ 9. 构建 system prompt（PromptBuilder + 行为画像 + Mood 指令 + 工具描述）
  ├─ 10. LLM 调用（含工具循环，最多 1 轮）
  ├─ 11. 人设一致性检查（PersonaConsistencyChecker.check_reply）
  ├─ 12. 情绪增强（emoji/颜文字/表情包）
  ├─ 13. 保存回复 + 短期记忆
  └─ 14. 后台：记忆提取 + 批量总结

         同时
proactive.py 定时检查（被动触发）：
  ├─ 早安（8-10 点 / 每日一次）
  ├─ 晚安（21-22 点 / 每日一次）
  ├─ 长时间未联系（可配天数）
  ├─ 记忆追问（考试/面试/生日/旅行等场景分类）
  └─ 持续关怀（连续 3+ 负面消息后主动关心）
```

---

## 五、配置系统

### settings.json 主要参数

```json
{
  "default_model": "deepseek",
  "models": { "deepseek": { "provider": "deepseek", "model_name": "deepseek-chat", ... }, ... },
  "advanced": {
    "segment_max_length": 50,
    "debounce_seconds": 3,
    "summarize_threshold": 15,
    "max_retries": 2,
    "max_messages": 50,
    "proactive_enabled": true,
    "proactive_memory_recall": true,
    "proactive_morning": true,
    "proactive_evening": true,
    "proactive_missing_days": 3,
    "proactive_min_level": 20
  }
}
```

### 数据文件

| 文件 | 格式 | 内容 |
|------|------|------|
| `data/memories.db` | SQLite | 记忆库（含 confidence / forget_score） |
| `data/vectors.db` | SQLite | 512 维向量嵌入（BGE-small-zh） |
| `data/moods.db` | SQLite | 情绪状态（含 expires_at） |
| `data/personality.db` | SQLite | 5 维人格状态 |
| `data/chat_history/` | JSON | 对话历史 |
| `data/relationships.json` | JSON | 亲密度数据 |
| `config/settings.json` | JSON | 模型 + 高级参数 |
| `config/personas.json` | JSON | 人设定义 |

---

## 六、测试覆盖

**总计 115 个测试，全部通过**（2026-06-12）。

| 测试文件 | 测试数 | 覆盖范围 |
|----------|--------|----------|
| `test_core.py` | 63 | MemoryScorer, Storage, EmotionAnalyzer, Expression, Relationship, ChatHistory, LLM分析, 管道工具函数, 否定词处理, 搜索, 格式化 |
| `test_persona.py` | 12 | Persona 序列化, PromptBuilder, PersonaLoader |
| `test_v12_features.py` | 39 | v1.2 全模块：conflict_resolver(7), decay(5), mood(8), persona_checker(4), evolution(6), proactive(2), manager集成(3), model字段(4) |
| `test_vector_memory.py` | 1 | 向量存储端到端 |

### 未覆盖的模块

| 模块 | 原因 | 建议 |
|------|------|------|
| `proactive.py` 主动消息 | 依赖定时器和情绪 | Mock 时间/关系/session 可测 |
| `memory/stats.py` | ASCII 输出 | 构造数据验证输出格式 |
| `llm/` 调用 | 需要 API Key | Mock LiteLLM 测试 |
| `personality/engine.py` | 需更多交互数据 | 构造序列测试人格漂移 |
| `chat/pipeline.py` 集成 | 全链路复杂 | Mock LLM 做端到端 |
| `tools/` 工具执行 | 依赖外部 API | Mock 工具结果测试 |

---

## 七、已知问题和风险

### 🔴 高优先级

| # | 问题 | 影响 | 建议修复 |
|---|------|------|----------|
| 1 | **setup.py 人设字段不匹配**：向导只生成 8 个基础字段，而 prompt_builder 依赖 30+ 字段。运行 setup 会用简化人设覆盖已有配置 | 运行 setup 后丢失丰富人设 | 让 setup 向导支持 30+ 字段，或合并而非覆盖 |
| 2 | **setup.py `_save_settings()` 覆盖 settings.json**：写入时会丢失 memory 部分和自定义模型配置 | 运行 setup 后自定义配置丢失 | 改为合并写入 |
| 3 | **ProactiveMessenger 耦合私有属性**：直接访问 `RelationshipTracker._data` 和 `_make_key` | 内部重构易断 | RelationshipTracker 提供公开 API |

### 🟡 中优先级

| # | 问题 | 建议 |
|---|------|------|
| 4 | **后台任务异常吞没**：`_extract_memory` 和 `_summarize_memories` 的异常只记 debug/warning | 用独立日志文件记录后台异常详情 |
| 5 | **pydantic 依赖未使用** | 从 requirements.txt 移除 |
| 6 | **无异步测试基础设施** | pytest-asyncio 配置 |
| 7 | **config/platforms.json 和 accounts.json 为空** | 清理遗留文件 |

### 🟢 低优先级

| # | 问题 |
|---|------|
| 8 | `data/personas/` 目录未使用（读 config/personas.json） |
| 9 | `data/conversations/` 遗留目录（旧架构残留） |

---

## 八、导师推荐后续工作（按优先级排列）

### 第一阶段：稳定性和易用性（预估 1-2 天）

| 任务 | 工作量 | 说明 |
|------|--------|------|
| **P0** 修复 setup.py 人设字段 | 2-3h | 让向导生成 30+ 字段，或合并而非覆盖 |
| **P0** 修复 setup.py settings 覆盖 | 1h | `_save_settings()` 改为合并写入 |
| **P0** `RelationshipTracker` 提供公开 API | 1-2h | 替代 `proactive.py` 对私有属性的直接访问 |
| **P1** 后台任务日志增强 | 1h | 后台异常写入独立日志文件 |
| **P1** 清理 pydantic + 空配置 | 30min | 移除未用依赖和遗留文件 |
| **P1** 补充测试（proactive + stats） | 3-4h | Mock 定时器和关系数据 |

### 第二阶段：功能增强（预估 3-5 天）

| 任务 | 工作量 | 说明 |
|------|--------|------|
| **P1** LLM 调用可 mock 测试 | 4-6h | 为所有 LLM 依赖模块添加 mock 测试框架 |
| **P1** 异步测试基础设施 | 2h | pytest-asyncio 配置 + 示例 |
| **P2** 集成测试（端到端） | 4-6h | mock LLM 做全链路测试 |
| **P2** 记忆导出/导入单条编辑 | 3-4h | `/memories edit <id>` + 批量导出增强 |
| **P2** 多轮工具调用 | 4-5h | 当前最多 1 轮工具循环，可扩展 |

### 第三阶段：新特性（预估 5-10 天）

| 任务 | 工作量 | 说明 |
|------|--------|------|
| **P2** 多用户支持 | 8-12h | 并发用户隔离、用户管理、独立数据空间 |
| **P2** WebUI 界面 | 20-30h | WebSocket + React/Vue 前端 |
| **P2** 语音输入/输出 | 10-15h | TTS/STT 集成 |
| **P3** 图片生成 | 5-8h | DALL-E / Stable Diffusion 集成 |
| **P3** 插件系统 | 10-15h | 可扩展的技能/插件架构 |
| **P3** 情绪记忆回顾 | 4-6h | 基于 Mood 时间线的情绪变化报告 |
| **P3** 梦境系统 | 6-8h | AI 离线模拟对话/做梦（纯文本叙事） |

### 第四阶段：数据与运营

| 任务 | 工作量 | 说明 |
|------|--------|------|
| **P2** 遗忘系统定期调度 | 2-3h | 定时触发 `MemoryManager.apply_decay()` |
| **P2** Mood 过期主动恢复 | 1-2h | 轮询检测过期 mood 并触发主动消息 |
| **P3** 用户画像摘要 | 4-6h | 基于长期记忆自动生成用户偏好报告 |
| **P3** 对话质量评分 | 5-8h | AI 自评回复质量 + 人设一致性评分 |

---

## 九、技术决策记录

| 决策 | 选择 | 原因 |
|------|------|------|
| LLM 接口 | LiteLLM | 统一 6 个提供商，流式支持好 |
| 数据持久化 | SQLite + JSON | SQLite 用于结构化（记忆/向量/情绪），JSON 用于简单配置 |
| 情感分析 | 关键词 + LLM 两层 | 速度（关键词）和准确性（LLM 降级）的平衡 |
| 记忆评分 | 关键词 + LLM 两层 | 即时关键词评分（不阻塞）+ 后台 LLM 精细评估 |
| 情绪模型 | 2D valence-arousal | 比离散标签更细腻，支持自然衰减和平滑迁移 |
| 关系进化 | 纯静态映射 | 无状态计算，精度足够，无需持久化，绝不与 PromptBuilder 耦合 |
| 冲突解析 | 规则引擎 | 无需 LLM 调用，快速可靠，支持反义词/数字/状态三类 |
| 遗忘系统 | 函数式计算 | 每次读取时计算，无额外调度，重要度衰减倍率 5 级 |
| 人设检查 | 关键词规则 | 轻量级 post-reply 检查，不阻塞主流程 |
| 输入去抖 | threading + queue | 非阻塞，支持连续输入合并 |
| 流式输出 | on_token 回调 | 后处理在流完成后同步执行 |
| 重试机制 | BaseLLM 包装器 | 所有调用方都受益 |

---

## 十、项目健康度评分

| 维度 | 评分 | 说明 |
|------|------|------|
| 代码质量 | ⭐⭐⭐⭐ | 类型注解完整，模块职责清晰，无魔法数字/长函数 |
| 测试覆盖 | ⭐⭐⭐ | 核心模块有测试，新模块 v1.2 全覆盖，LLM 依赖模块缺 mock |
| 文档完整性 | ⭐⭐⭐⭐ | README + CHANGELOG + FRAMEWORK_REPORT 齐全 |
| 可维护性 | ⭐⭐⭐⭐ | 模块解耦良好，依赖清晰，无循环导入 |
| 可扩展性 | ⭐⭐⭐ | 工具系统/LLM 注册表设计良好，但缺插件架构 |
| 稳定性 | ⭐⭐⭐⭐ | 115 测试全通过，SQLite WAL 防并发，原子写入保数据 |

---

*此报告由 Sisyphus 生成，基于 2026-06-12 项目状态。*
*全量 115 个测试通过，无已知回归。*
