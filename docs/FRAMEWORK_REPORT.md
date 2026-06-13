# 赛博伴侣项目框架报告

> 生成日期：2026-06-11 | 当前版本：v0.8.0 | 分支：master

---

## 一、项目概述

纯 CMD 模式的 AI 女友聊天机器人，基于 Python asyncio 架构，支持记忆系统、情感分析、人设管理和动态亲密度。

### 核心能力

| 能力 | 状态 | 说明 |
|------|------|------|
| LLM 多模型接入 | ✅ 已完成 | DeepSeek/OpenAI/Gemini/通义千问/Kimi/智谱，通过 LiteLLM 统一 |
| 人设系统 | ✅ 已完成 | 30+ 字段丰富角色，支持运行时切换 |
| 记忆系统 | ✅ 已完成 | 短期记忆 + LLM 长期记忆提取，关键词+LLM 双层评分 |
| 情感分析 | ✅ 已完成 | 关键词 + LLM 两层分析，8 种情感类型 |
| 关系追踪 | ✅ 已完成 | 动态亲密度计算，复合键支持多角色 |
| 主动消息 | ✅ 已完成 | 早安/晚安/长时间未联系自动触发 |
| 流式输出 | ✅ 已完成 | 逐字显示 + spinner 动画 |
| 统计仪表盘 | ✅ 已完成 | ASCII 图表展示情感/时间/趋势 |
| 斜杠命令 | ✅ 已完成 | 16 个命令（/help /stats /memories /persona /debug /clear /export /undo /regen /search /mood /quit） |
| 安装向导 | ✅ 已完成 | 三步交互式配置 + 国内镜像自动切换 |

---

## 二、架构总览

```
┌─────────────────────────────────────────────────────┐
│                    main.py (入口)                     │
│  CLI 循环 / 斜杠命令 / 去抖合并 / 流式输出 / spinner  │
└──────────┬──────────────────────────────────────────┘
           │
    ┌──────┼──────┬──────────┬──────────┬──────────┐
    ▼      ▼      ▼          ▼          ▼          ▼
 Persona Emotion Memory  Relationship Proactive   LLM
 System  System   System   Tracker    Messenger  Registry
    │      │      │          │          │          │
    ▼      ▼      ▼          ▼          ▼          ▼
 Prompt  LLM     JSON       JSON       时间       LiteLLM
 Builder Analyzer 原子写入   持久化     触发器     统一接口
```

### 数据流（单条消息处理）

```
用户输入 → 去抖合并 → 情感分析(关键词→LLM) → 存入chat_history
     → 更新亲密度 → 检索相关记忆 → 构建system prompt
     → LLM流式调用 → 情感增强(emoji) → 逐字输出
     → 后台: 自动记忆提取 + 记忆总结
```

### 设计原则

- **原子写入**：所有数据持久化使用 tempfile + os.replace，断电安全
- **两层分析**：情感分析先跑关键词（快），不确定时 fallback 到 LLM
- **两层记忆**：短期（最近对话）+ 长期（LLM 提取摘要）
- **异步后台**：记忆提取、总结等耗时操作不阻塞主线程
- **复合键**：关系数据用 `user__persona` 键，支持多人设独立追踪

---

## 三、文件结构

```
cyber-girlfriend/
├── main.py                     # 入口，1163 行，CLI + 16 个斜杠命令
├── setup.py                    # 三步安装向导
├── install.py                  # 环境安装（venv + 国内镜像）
├── start.sh                    # 启动脚本（Linux/macOS）
├── requirements.txt            # 依赖声明
├── .env / .env.example         # API 密钥配置
│
├── config/
│   ├── settings.json           # 模型配置 + 高级参数
│   ├── personas.json           # 人设定义（默认"小雨"）
│   ├── platforms.json          # 平台配置（预留，当前为空）
│   └── accounts.json           # 账号配置（预留，当前为空）
│
├── core/
│   ├── proactive.py            # 主动消息（早安/晚安/未联系）
│   │
│   ├── llm/
│   │   ├── base.py             # 抽象基类 + 重试 + 流式（221 行）
│   │   ├── deepseek.py         # DeepSeek 适配器（14 行）
│   │   ├── openai_compatible.py # OpenAI 兼容适配器（16 行）
│   │   └── registry.py         # 模型注册表 + 单例（131 行）
│   │
│   ├── memory/
│   │   ├── models.py           # Memory 数据类（47 行）
│   │   ├── storage.py          # JSON 存储 + 原子写入（78 行）
│   │   ├── scorer.py           # 关键词评分（89 行）
│   │   ├── manager.py          # CRUD + 检索 + 上下文注入（205 行）
│   │   ├── summarizer.py       # LLM 记忆提取/总结（187 行）
│   │   ├── chat_history.py     # 聊天历史持久化（265 行）
│   │   └── stats.py            # 统计 + ASCII 仪表盘（239 行）
│   │
│   ├── persona/
│   │   ├── models.py           # Persona 数据类 30+ 字段（160 行）
│   │   ├── loader.py           # 配置加载 + CRUD（86 行）
│   │   └── prompt_builder.py   # System Prompt 生成器（235 行）
│   │
│   ├── emotion/
│   │   ├── analyzer.py         # 关键词情感分析（158 行）
│   │   ├── expression.py       # 消息分段 + emoji 增强（151 行）
│   │   └── llm_analyzer.py     # LLM 辅助情感分析（135 行）
│   │
│   └── relationship/
│       └── tracker.py          # 亲密度追踪器（196 行）
│
├── tests/
│   ├── test_core.py            # 主测试文件（~48 测试）
│   └── test_persona.py         # 人设测试（~12 测试）
│
├── data/                       # 运行时数据（.gitignore）
│   ├── chat_history/           # 聊天记录
│   ├── memories/               # 长期记忆
│   ├── relationships.json      # 亲密度数据
│   ├── exports/                # 导出文件
│   └── personas/               # 空目录（预留）
│
├── docs/
│   └── FRAMEWORK_REPORT.md     # 本文件
│
└── logs/
    └── app.log                 # 运行日志
```

---

## 四、模块详细分析

### 4.1 main.py — 入口（1163 行）

**职责**：CLI 循环、命令路由、组件编排、流式输出

**核心组件**：
- `load_advanced_config()` — 从 settings.json 加载高级参数
- `SessionStats` — 会话统计（消息数、情绪分布、时间）
- `handle_message()` — 核心消息处理管线
- 消息去抖系统 — threading + queue，可配置合并窗口
- 16 个斜杠命令处理器

**消息处理管线**：
```
handle_message(user_input):
  1. 情感分析（LLMEmotionAnalyzer.analyze）
  2. 存入 chat_history（含 emotion 字段）
  3. 更新亲密度（RelationshipTracker）
  4. 检索相关记忆（MemoryManager.get_context_prompt）
  5. 构建 system prompt（PromptBuilder.build）
  6. LLM 流式调用（chat_stream + on_token 回调）
  7. 情感增强（EmotionEnhancer）
  8. 后台：自动记忆提取 + 记忆总结
```

**已知问题**：
- 超过 1100 行，建议拆分命令处理到独立模块

---

### 4.2 core/llm/ — LLM 抽象层

**base.py**（221 行）— 核心基类：
- `chat()` — 同步调用
- `chat_stream()` — async generator 流式调用
- `_retry()` — 指数退避重试（1s→2s，最多 2 次）
- `_is_retryable()` — 区分可重试（429/5xx/timeout）和永久错误（401/403）

**registry.py**（131 行）— 模型注册表：
- 从 settings.json 加载模型配置
- 从 .env 读取 API 密钥
- 单例模式 `_global_registry`

**状态**：✅ 完整，无需修改

---

### 4.3 core/memory/ — 记忆系统

| 文件 | 行数 | 职责 |
|------|------|------|
| models.py | 47 | Memory 数据类 |
| storage.py | 78 | JSON 原子写入 + 路径穿越防护 |
| scorer.py | 89 | 25+ 关键词加权评分（1-5 级） |
| manager.py | 205 | CRUD + 检索 + 上下文生成 |
| summarizer.py | 187 | LLM 记忆提取/总结/检索 |
| chat_history.py | 265 | 聊天历史 + 短期记忆 |
| stats.py | 239 | 统计分析 + ASCII 仪表盘 |

**记忆流程**：
```
对话 → scorer.py 评分（关键词）
  → level >= 2 → 自动存入 manager
  → 后台 LLM 提取结构化记忆
  → 超过 15 条未总结 → LLM 批量总结
  → 对话时检索相关记忆注入 prompt
```

**状态**：✅ 完整

---

### 4.4 core/persona/ — 人设系统

**models.py**（160 行）— 30+ 字段人设：
- 基础：name, age, gender, location, occupation
- 身份：birthday, zodiac, education, mbti
- 性格：traits, strengths, weaknesses
- 兴趣：hobbies, favorite_topics, disliked_topics
- 语言：catchphrases, speaking_style, vocabulary_level
- 情感：emotional_expressions, comfort_words, teasing_style
- 行为：daily_routines, habits, response_patterns
- 关系：relationship_background, love_languages
- 沟通：communication_preferences, conflict_style

**prompt_builder.py**（235 行）— 8 模块 prompt 生成：
1. 身份模块 → 角色定义
2. 性格模块 → 行为特征
3. 兴趣模块 → 话题偏好
4. 语言模块 → 说话风格
5. 情感模块 → 表达方式
6. 价值观模块 → 世界观
7. 关系模块 → 动态亲密度描述（5 档）
8. 行为规则 → 约束条件

**状态**：✅ 完整

---

### 4.5 core/emotion/ — 情感系统

**两层分析架构**：
```
用户消息 → analyzer.py（关键词，8 种情感）
  → NEUTRAL + 长文本/低置信 → llm_analyzer.py（LLM 二次判断）
  → 最终情感 + 强度（0.0-1.0）
```

**8 种情感**：HAPPY, SAD, ANGRY, NEUTRAL, EXCITED, LONELY, ANXIOUS, LOVE

**增强**：expression.py 为 AI 回复添加上下文 emoji（强度 >= 0.3 时）

**状态**：✅ 完整

---

### 4.6 core/relationship/ — 关系追踪

**tracker.py**（196 行）— 动态亲密度：
- 复合键：`user_id__persona_id`
- 算法：+0.05/消息，+0.3 正面情感，-0.2 负面情感，-0.05/天（3 天未联系后）
- 范围：0-100
- 持久化：原子 JSON

**亲密度等级映射**：
```
0-20:   陌生人 → 20-40: 朋友 → 40-60: 好友
60-80:  暧昧 → 80-100: 亲密
```

**状态**：✅ 完整

---

### 4.7 core/proactive.py — 主动消息

**触发条件**：
- 早安（8-10 点）— 每天一次
- 晚安（21-22 点）— 每天一次
- 长时间未联系 — 可配置天数
- 最低亲密度要求：可配置

**消息风格**：按亲密度分 3 档（低/中/高）

**状态**：✅ 完整

---

## 五、配置系统

### settings.json

```json
{
  "default_model": "deepseek",
  "models": {
    "deepseek": { "provider": "deepseek", "model_name": "deepseek-chat", "max_tokens": 2000, "temperature": 0.8, "base_url": null },
    "openai": { "provider": "openai_compatible", "model_name": "gpt-4o", "max_tokens": 2000, "temperature": 0.8, "base_url": null },
    "gemini": { "provider": "openai_compatible", "model_name": "gemini-2.0-flash", "max_tokens": 2000, "temperature": 0.8, "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/" },
    "qwen": { "provider": "openai_compatible", "model_name": "qwen-plus", "max_tokens": 2000, "temperature": 0.8, "base_url": null },
    "kimi": { "provider": "openai_compatible", "model_name": "moonshot-v1-8k", "max_tokens": 2000, "temperature": 0.8, "base_url": null },
    "zhipu": { "provider": "openai_compatible", "model_name": "glm-4-flash", "max_tokens": 2000, "temperature": 0.8, "base_url": null }
  },
  "advanced": {
    "segment_max_length": 50,
    "debounce_seconds": 3,
    "summarize_threshold": 15,
    "max_retries": 2,
    "max_messages": 50,
    "proactive_enabled": true,
    "proactive_morning": true,
    "proactive_evening": true,
    "proactive_missing_days": 3,
    "proactive_min_level": 20
  }
}
```

### 环境变量（.env）

```
DEEPSEEK_API_KEY=sk-xxx
OPENAI_API_KEY=sk-xxx
GEMINI_API_KEY=xxx
QWEN_API_KEY=xxx
KIMI_API_KEY=xxx
ZHIPU_API_KEY=xxx
```

---

## 六、依赖

```
python-dotenv>=1.1.0    # .env 文件加载
pydantic>=2.10.0        # （声明但未直接使用，litellm 依赖）
litellm>=1.65.0         # 统一 LLM 接口
loguru>=0.7.0           # 结构化日志
```

**运行时实际使用**：dotenv, loguru, litellm + Python 标准库（asyncio, json, threading, queue, uuid, dataclasses, enum, re, pathlib, tempfile, collections）

---

## 七、测试覆盖

### 当前测试分布

| 测试文件 | 测试数 | 覆盖范围 |
|----------|--------|----------|
| test_core.py | ~48 | MemoryScorer, MemoryStorage, EmotionAnalyzer, MessageSegmenter, EmotionEnhancer, RelationshipTracker, ChatHistoryStorage, LLMEmotionAnalyzer, 多消息格式化, 主模块工具函数 |
| test_persona.py | ~12 | Persona 序列化, PromptBuilder, PersonaLoader |
| **总计** | **~60** | |

### 未覆盖的模块

| 模块 | 原因 | 建议 |
|------|------|------|
| core/proactive.py | 无测试 | 可 mock 时间+关系数据测试 |
| core/memory/stats.py | 无测试 | 可构造数据测试 ASCII 输出 |
| core/llm/ | 需要 API Key | 可 mock LiteLLM 测试 |
| main.py 集成测试 | 复杂异步循环 | 可 mock LLM 做端到端测试 |
| setup.py | 交互式输入 | 可 mock input 测试 |
| LLMEmotionAnalyzer._llm_analyze() | 需要 LLM | 可 mock 测试 |
| MemorySummarizer 方法 | 需要 LLM | 可 mock 测试 |

---

## 八、已知问题和待改进

### 🔴 高优先级

1. **setup.py 人设字段不匹配** — 手动配置只生成 8 个基础字段，而 prompt_builder 依赖 30+ 字段。运行 setup 会用简化人设覆盖丰富配置。
2. **setup.py 覆盖 settings.json** — `_save_settings()` 会丢失 memory 部分和自定义模型配置。
3. **pydantic 依赖未使用** — requirements.txt 声明但无直接导入，可清理。

### 🟡 中优先级

4. **main.py 过大** — 1163 行，建议拆分命令处理到 `commands/` 模块。
5. **README 测试数过时** — 声明 36 个测试，实际约 60 个。
6. **后台任务异常吞没** — `_background_extract_memory` 和 `_background_summarize` 用 debug/warning 级别记录异常，生产调试困难。
7. **ProactiveMessenger 耦合私有属性** — 直接访问 `RelationshipTracker._data` 和 `_make_key`。

### 🟢 低优先级

8. **config/platforms.json 和 accounts.json 为空** — 从多平台重构遗留，可清理或保留。
9. **data/personas/ 目录未使用** — persona 系统读 config/personas.json。
10. **data/conversations/ 遗留目录** — 旧架构遗留，无代码引用。
11. **无异步测试基础设施** — pytest 未配置 asyncio 模式。

---

## 九、开发路线图

### 近期（可直接开始）

| 优先级 | 任务 | 预计工作量 | 说明 |
|--------|------|------------|------|
| P0 | 修复 setup.py 人设字段匹配 | 1-2 小时 | 让 setup 向导生成 30+ 字段人设 |
| P0 | 修复 setup.py settings.json 覆盖 | 1 小时 | 合并写入而非覆盖 |
| P1 | 清理 pydantic 依赖 | 5 分钟 | 从 requirements.txt 移除 |
| P1 | 修复 README 测试数 | 5 分钟 | 更新为实际数量 |
| P2 | 添加 proactive.py 测试 | 2 小时 | Mock 时间+关系数据 |
| P2 | 添加 stats.py 测试 | 1 小时 | 构造数据验证 ASCII 输出 |

### 中期（功能增强）

| 优先级 | 任务 | 预计工作量 | 说明 |
|--------|------|------------|------|
| P1 | 拆分 main.py 命令处理 | 4-6 小时 | 提取到 commands/ 模块 |
| P1 | 修复 ProactiveMessenger 私有属性耦合 | 1 小时 | RelationshipTracker 提供公开 API |
| P2 | 改进后台任务错误处理 | 2 小时 | 用独立日志文件记录后台异常 |
| P2 | LLM 调用可 mock 测试 | 3-4 小时 | 为 LLM 相关模块添加 mock 测试 |
| P3 | 集成测试框架 | 4-6 小时 | mock LLM 做端到端测试 |

### 远期（新功能）

| 优先级 | 任务 | 预计工作量 | 说明 |
|--------|------|------------|------|
| P2 | /undo 撤销最后回复 | 2-3 小时 | 从 chat_history 移除最后一条 AI 回复 |
| P2 | /regen 重新生成回复 | 2-3 小时 | 删除最后回复并重新调用 LLM |
| P2 | /search 聊天记录搜索 | 2 小时 | 基于关键词搜索 chat_history |
| P2 | /mood 情绪控制 | 1-2 小时 | 手动设置当前情绪状态 |
| P3 | 多用户支持 | 8-12 小时 | 并发用户隔离、用户管理 |
| P3 | WebUI 界面 | 20-30 小时 | WebSocket + React/Vue 前端 |
| P3 | 语音输入/输出 | 10-15 小时 | TTS/STT 集成 |
| P3 | 图片生成 | 5-8 小时 | DALL-E/Stable Diffusion 集成 |
| P3 | 插件系统 | 10-15 小时 | 可扩展的技能/插件架构 |

---

## 十、快速上手

### 环境要求

- Python 3.11+
- pip
- 网络（LLM API 调用）

### 安装和运行

```bash
# 1. 进入项目目录
cd cyber-girlfriend

# 2. 创建虚拟环境 + 安装依赖
python install.py

# 3. 运行设置向导（配置 API Key + 人设）
python setup.py

# 4. 启动聊天
python main.py

# 或直接 python main.py
```

### 项目命令

| 命令 | 说明 |
|------|------|
| `/help` | 显示所有可用命令 |
| `/stats` | 亲密度统计 |
| `/stats dashboard` | ASCII 图表仪表盘 |
| `/memories list` | 列出所有记忆 |
| `/memories search <query>` | 搜索记忆 |
| `/memories add <content>` | 手动添加记忆 |
| `/memories delete <id>` | 删除记忆 |
| `/memories export` | 导出记忆到 JSON |
| `/memories clear --confirm` | 清空所有记忆 |
| `/persona list` | 列出所有人设 |
| `/persona switch <id>` | 切换人设 |
| `/debug` | 查看当前 system prompt |
| `/clear --confirm` | 清空聊天历史 |
| `/export md` | 导出为 Markdown |
| `/export json` | 导出为 JSON |
| `/quit` | 退出 |

---

## 十一、技术决策记录

| 决策 | 选择 | 原因 |
|------|------|------|
| LLM 接口 | LiteLLM | 统一 6 个提供商，流式支持好 |
| 数据持久化 | JSON + 原子写入 | 简单可靠，无需数据库 |
| 情感分析 | 关键词 + LLM 两层 | 速度和准确性的平衡 |
| 记忆存储 | 关键词评分 + LLM 提取 | 兼顾速度和语义理解 |
| 输入去抖 | threading + queue | 非阻塞，支持连续输入合并 |
| 流式输出 | on_token 回调 | 后处理需要在流式结束后同步执行 |
| 重试机制 | BaseLLM 层包装器 | 所有调用方都受益 |
| 关系数据 | 复合键 `user__persona` | 比嵌套结构简单，向后兼容 |
| 主动消息 | debounce 超时检查 | 不需要额外调度器 |

---

## 十二、文件大小参考

| 文件 | 行数 | 备注 |
|------|------|------|
| main.py | 1163 | 偏大，建议拆分 |
| core/memory/chat_history.py | 265 | |
| core/persona/prompt_builder.py | 235 | |
| core/memory/stats.py | 239 | |
| core/llm/base.py | 221 | |
| core/memory/manager.py | 205 | |
| core/relationship/tracker.py | 196 | |
| core/memory/summarizer.py | 187 | |
| core/persona/models.py | 160 | |
| core/emotion/analyzer.py | 158 | |
| core/emotion/expression.py | 151 | |
| core/emotion/llm_analyzer.py | 135 | |
| core/llm/registry.py | 131 | |
| core/persona/loader.py | 86 | |
| core/memory/scorer.py | 89 | |
| core/memory/storage.py | 78 | |
| core/memory/models.py | 47 | |
| core/llm/deepseek.py | 14 | |
| core/llm/openai_compatible.py | 16 | |
| **总计** | **~3800** | |

---

*此报告由 Claude 自动生成，基于 2026-06-11 项目状态。*
*如需更新，请在新工具中重新生成或手动补充。*
