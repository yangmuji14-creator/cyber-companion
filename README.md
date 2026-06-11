# 🎀 Cyber Girlfriend — 赛博女友

纯终端（CMD）AI 伴侣聊天机器人。支持语义记忆、情感分析、丰富人设、动态亲密度。

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
├── chat/            # 交互层
│   ├── handler.py      聊天循环 + 输入线程 + spinner
│   ├── pipeline.py     ChatPipeline 消息处理管线
│   └── commands.py     19 个斜杠命令
├── llm/             # LLM 统一接口
│   ├── base.py         抽象基类 + 指数退避重试
│   ├── deepseek.py     DeepSeek 适配
│   ├── openai_compatible.py  OpenAI 兼容适配
│   └── registry.py     注册中心 + 全局单例
├── memory/          # 记忆系统
│   ├── embedder.py     🆕 语义嵌入 (BGE-small-zh, 512维)
│   ├── vector_store.py 🆕 SQLite 向量存储 + Top-K 语义搜索
│   ├── manager.py      CRUD + LLM评分 + 冲突检测 + 向量检索
│   ├── scorer.py       关键词评分（降级用）
│   ├── summarizer.py   LLM 记忆提取/总结
│   ├── storage.py      JSON 持久化（原子写入）
│   ├── chat_history.py 对话历史 + 搜索
│   └── stats.py        ASCII 仪表盘
├── emotion/         # 情感系统（8种情感，两级分析）
├── persona/         # 人设系统（30+字段，PromptBuilder）
├── relationship/    # 亲密度动态计算
├── proactive.py     # AI 主动消息
├── dialogue/        # 对话质量（CoT思考 + 一致性保护 + 话题追踪）
├── multimodal/      # 多模态（图片识别 + 表情包回复）
└── config.py        # 🆕 配置加载
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

### 🎭 情感感知
- 8 种情感检测（关键词 + LLM 两级分析）
- 情感轨迹追踪
- 负面情绪自动安抚

### 💕 亲密度系统
- 正面/负面消息影响亲密度
- 动态衰减算法
- 5 档关系等级

### 🎀 30+ 字段人设
身份、性格、MBTI、爱好、语言习惯、情绪模式、行为倾向、关系背景…

### 📋 斜杠命令
```
/help /stats /memories /persona /debug /clear /export
/undo /regen /search /mood /img /quit
```

## 数据存储
- `data/memories/` — JSON 记忆（关键词评分）
- `data/vectors.db` — SQLite 向量库
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