# 🎀 赛博伴侣 — Cyber Companion

纯终端（CMD）AI 伴侣聊天机器人。支持语义记忆、情感分析、丰富人设、动态亲密度、持续性情绪系统、**内心独白大脑**、工具调用、多平台接入。

> ⚠️ **推荐使用 Windows CMD（命令提示符）运行**
> PowerShell 可能存在 Unicode 编码问题导致 emoji 显示异常。
> macOS / Linux 终端无此限制。

## 快速开始

```cmd
:: 安装依赖
python install.py

:: 配置向导（模型选择 + 人设 + 参数）
python main.py setup

:: 开始聊天
python main.py
```

## 多平台接入

支持同时接入多个聊天平台，所有平台共享同一个 AI 状态（记忆/情绪/人格）：

```cmd
:: 配置微信（扫码登录）
python main.py wechat

:: 启动（自动检测并启动已配置的平台）
python main.py
```

**消息去抖合并**：无论从哪个平台发送消息，连续输入都会在 3 秒内自动合并后一起处理。

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

### 🎭 持续性情绪引擎（v3.0–v3.1）
- 14 种情绪状态的 2D valence-arousal 模型
- 跨会话持久化（SQLite），随时间自然衰减
- **情绪表达系统**：mood 直接影响 AI 的语气、回复长度、句子风格、emoji 选择
- 精力条（energy）随时间变化，低精力时回复简短慵懒
- CoT 对话思考器辅助意图理解
- 颜文字/表情包自动适配 AI 情绪

### 🧠 内心独白大脑系统（v3.3）

AI 在回复前自主进行「内心思考」，保持人设一致性：

- **14 维度状态收集** — 收集情绪、人格、亲密度、身份、人生总结等子系统状态
- **念头组织** — 将多维状态编织为结构化的内心思绪碎片
- **独白编织** — 将碎片融合为第一人称连贯内心独白
- **三种主动回忆** — 关键词触发、情绪触发、自发回忆，让 AI 主动"想起"过往
- **人设断裂检测** — 自动检测回复是否偏离角色设定
- **可插拔设计** — 所有子系统均为可选依赖，缺失时静默降级

### 💕 亲密度系统
- **LLM 情感理解** — AI 自主理解对话中的情感温度，自然调整亲密度变化
- **多维情感方向** — 支持 7 种情感方向（强烈正向→强烈负向），3 级强度映射
- **SQLite 持久化** — 线程安全存储，带边际递减效应和自然衰减
- **自动迁移** — 旧版 JSON 数据首次运行时自动迁移到新存储
- **人格联动** — 亲密度变化影响人格维度（信任/依赖等）

### 📝 分段回复
- AI 回复自动按语义分段，提升长回复的可读性

### 🛠️ 工具调用（v2.5）
- AI 可调用工具获取实时信息（时间、天气、计算）
- 无需修改 LLM 接口，prompt-based 调用格式
- 执行结果自然融入对话

### 🧠 人格成长（v2.0）
- 五维人格模型（信任/依赖/开放/好感/醋意）
- 根据交互动态变化，跨会话持久化
- 影响聊天风格和情感倾向

### 📦 ex-skill 人设导入
- 支持导入 ex-skill 格式的外部人设数据（`persona.md` / `memory.md`）
- 命令行使用：`python import_exskill.py <目录> [--dry-run] [--force]`
- LLM 自动转换记忆格式和人设结构

### 🎀 30+ 字段人设
身份、性格、MBTI、爱好、语言习惯、情绪模式、行为倾向、关系背景…

### 📋 斜杠命令
```
/help       — 显示帮助
/stats      — 亲密度统计（含大脑叙事）
/memories   — 记忆管理
/persona    — 人设信息
/personality— 人格状态
/mood       — 当前情绪状态
/debug      — 查看 system prompt
/brain      — 内心独白统计
/clear      — 清空聊天历史
/export     — 导出聊天记录
/undo       — 撤销上一轮
/regen      — 重新生成回复
/search     — 搜索聊天历史
/tools      — 查看可用工具
/img        — 发送图片识别
/quit       — 退出
```

## 项目结构

```
cyber-companion/
├── core/                    # 核心模块
│   ├── app.py               # 应用装配 + ComponentBuilder
│   ├── config.py            # 配置加载
│   ├── summary.py           # 人生摘要引擎
│   ├── open_loop.py         # 未完成事件追踪
│   ├── identity.py          # 用户身份画像
│   ├── brain/               # 🧠 内心独白大脑系统
│   │   ├── collector.py     #   14 维度状态收集
│   │   ├── organizer.py     #   念头碎片组织
│   │   ├── weaver.py        #   内心独白编织
│   │   ├── triggers.py      #   主动记忆触发
│   │   ├── checker.py       #   人设一致性检测
│   │   ├── coordinator.py   #   大脑协调器
│   │   └── self_test.py     #   自测套件
│   ├── social/              # 社交系统（affection + relationship）
│   ├── chat/                # 聊天管线（handler/pipeline/commands）
│   ├── emotion/             # 情绪系统（MoodEngine + AIMoodManager）
│   ├── memory/              # 记忆系统（向量+关键词+SQLite）
│   ├── persona/             # 人设引擎（loader/builder/drift）
│   ├── personality/         # 人格系统（五维模型）
│   ├── llm/                 # LLM 抽象层（DeepSeek等）
│   ├── proactive.py         # 主动消息
│   ├── dialogue/            # 对话思考 + 一致性检查
│   ├── multimodal/          # 图片/表情处理
│   ├── tools/               # 工具调用（计算/天气）
│   └── utils.py             # 通用工具
├── adapters/                # 平台适配器（CLI/微信/API）
├── plugins/                 # 插件系统
├── tests/                   # 测试（分模块子目录）
│   ├── social/              # 社交系统测试
│   ├── chat/                # 聊天系统测试
│   └── memory/              # 记忆系统测试
├── auto_test.py             # 全链路自动化测试脚本
└── config/                  # 用户配置（不进 git）
```

## 数据存储
- `data/memories.db` — SQLite 记忆库
- `data/vectors.db` — SQLite 向量库
- `data/moods.db` — 情绪状态持久化
- `data/personality.db` — 人格状态持久化
- `data/chat_history/` — 对话历史
- `data/unified.db` — 亲密度统一存储（旧版 relationships.json 首次运行自动迁移）

## 配置说明
- `.env` — API Key 配置（从 `.env.example` 复制）
- `config/settings.json` — 高级参数（首次运行 `setup` 生成）
- `config/personas.json` — 人设数据（通过 `setup` 配置）
- 以上文件包含个人配置，不会提交到 git

## 测试
```bash
# 运行所有测试
pytest tests -v

# 全链路回归测试（4轮自动）
python auto_test.py

# 大脑模块自测（无需外部依赖）
python -c "from core.brain.self_test import run_self_test; asyncio.run(run_self_test())"
```

## 技术栈
Python 3.11+ / asyncio / LiteLLM / sentence-transformers / SQLite / numpy

## 项目由来
灵感来自 [My-Dream-Moments](https://github.com/iwyxdxl/My-Dream-Moments) 和 [ex-skill](https://github.com/therealXiaomanChu/ex-skill)。

## 作者
**yangmuji14**
