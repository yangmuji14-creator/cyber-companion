# 🎀 Cyber Girlfriend — 赛博女友

纯终端（CMD）AI 伴侣聊天机器人。支持语义记忆、情感分析、丰富人设、动态亲密度、持续性情绪系统、工具调用。

## 快速开始

```bash
# 安装
python install.py

# 配置向导（模型选择 + 人设 + 参数）
python main.py setup

# 开始聊天
python main.py
# 或双击 start.bat
```

## 架构

```
core/
├── chat/               # 交互层
│   ├── handler.py          聊天循环 + 输入线程 + spinner
│   ├── pipeline.py         ChatPipeline 消息处理管线（含工具循环）
│   └── commands.py         15 个斜杠命令
├── llm/               # LLM 统一接口
│   ├── base.py             抽象基类 + 指数退避重试
│   ├── deepseek.py         DeepSeek 适配
│   ├── openai_compatible.py  OpenAI 兼容适配
│   └── registry.py         注册中心 + 全局单例
├── memory/            # 记忆系统
│   ├── storage.py          🆕 SQLite 持久化（替代 JSON）
│   ├── manager.py          CRUD + LLM评分 + 冲突检测 + 向量检索
│   ├── embedder.py         语义嵌入 (BGE-small-zh, 512维)
│   ├── vector_store.py     SQLite 向量存储 + Top-K 语义搜索
│   ├── scorer.py           关键词评分（降级用）
│   ├── summarizer.py       LLM 记忆提取/总结
│   ├── chat_history.py     对话历史 + 搜索
│   └── stats.py            ASCII 仪表盘
├── emotion/           # 情感系统
│   ├── analyzer.py         8 种情感关键词检测
│   ├── llm_analyzer.py     LLM + 关键词两级分析 + 情感轨迹
│   ├── expression.py       消息分段 + emoji/颜文字增强 + 🆕 MoodExpressionEngine
│   └── mood.py             🆕 持续性情绪引擎（2D valence-arousal, SQLite）
├── personality/       # 🆕 人格引擎
│   └── engine.py           5维人格模型（信任/依赖/开放/好感/醋意）
├── tools/             # 🆕 工具调用系统
│   ├── base.py             BaseTool 抽象 + ToolRegistry
│   ├── time_tool.py        时间日期查询
│   ├── calculator.py       安全计算器（AST 白名单）
│   └── weather.py          城市天气预报
├── dialogue/          # 🆕 对话质量模块
│   ├── thinker.py          CoT 对话思考器（意图/语气分析）
│   ├── consistency.py      角色一致性守卫
│   └── topic_tracker.py    话题追踪
├── persona/           # 人设系统（30+字段，PromptBuilder）
├── relationship/      # 亲密度动态计算
├── proactive.py       # AI 主动消息
├── multimodal/        # 多模态（图片识别 + 颜文字回复）
└── config.py          # 配置加载
```

## 特性

### 🤖 6 种大模型支持
| 提供商 | 默认模型 | 特点 |
|--------|----------|------|
| DeepSeek | deepseek-chat | 国产便宜，推荐 |
| OpenAI | gpt-4o-mini | 需海外网络 |
| Gemini | gemini-2.0-flash | Google 免费额度 |
| 通义千问 | qwen-turbo | 阿里云国内快 |
| Kimi | moonshot-v1-8k | 长上下文 |
| 智谱 | glm-4-flash | 免费额度 |

### 🧠 语义记忆（v2.0）
关键词记忆 → 向量嵌入（BAAI/bge-small-zh-v1.5）
- 搜"宠物"能想起"喜欢猫"
- SQLite 存储，余弦相似度 Top-K
- 嵌入器不可用自动降级为关键词

### 🎭 持续性情绪引擎（v3.0–v3.5）
- 14 种情绪状态的 2D valence-arousal 模型
- 跨会话持久化（SQLite），随时间自然衰减
- **情绪表达系统**：mood 直接影响 AI 的语气、回复长度、句子风格、emoji 选择
- 精力条（energy）随时间变化，低精力时回复简短慵懒
- CoT 对话思考器辅助意图理解
- 颜文字/表情包自动适配 AI 情绪

### 💕 亲密度系统
- 正面/负面消息影响亲密度
- 动态衰减算法
- 5 档关系等级

### 🛠️ 工具调用（v2.5）
- AI 可调用工具获取实时信息（时间、天气、计算）
- 无需修改 LLM 接口，prompt-based 调用格式
- 执行结果自然融入对话

### 🧠 人格成长（v2.0）
- 五维人格模型（信任/依赖/开放/好感/醋意）
- 根据交互动态变化，跨会话持久化
- 影响聊天风格和情感倾向

### 🎀 30+ 字段人设
身份、性格、MBTI、爱好、语言习惯、情绪模式、行为倾向、关系背景…

### 📋 斜杠命令
```
/help /stats /memories /persona /debug /clear /export
/undo /regen /search /mood /personality /tools /img /quit
```

## 数据存储
- `data/memories.db` — SQLite 记忆库
- `data/vectors.db` — SQLite 向量库
- `data/moods.db` — 情绪状态持久化
- `data/personality.db` — 人格状态持久化
- `data/chat_history/` — 对话历史
- `data/relationships.json` — 亲密度持久化

## 测试
```bash
pytest tests -v    # 76 tests all pass ✅
```

## 技术栈
Python 3.11+ / asyncio / LiteLLM / sentence-transformers / SQLite / numpy

## 项目由来
灵感来自 [My-Dream-Moments](https://github.com/iwyxdxl/My-Dream-Moments) 和 [ex-skill](https://github.com/therealXiaomanChu/ex-skill)。
