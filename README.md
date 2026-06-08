# 🎀 Cyber Girlfriend

纯 CMD 模式的赛博女友聊天机器人，具有记忆系统、情感分析、人设管理和动态亲密度功能。

## ✨ 特性

- **多模型支持** — DeepSeek、OpenAI、Gemini、通义千问、Kimi、智谱
- **记忆系统** — 自动提取重要信息，LLM 辅助记忆总结，5 级重要度评分
- **情感分析** — 8 种情感识别（开心/难过/生气/爱意等），自动添加 emoji 表达
- **人设系统** — 可配置的性格、背景、说话风格，支持导入 ex-skill 文件
- **动态亲密度** — 根据对话互动、情感频率、时间衰减动态计算关系等级
- **消息分段** — 长消息按自然断句分段发送，模拟真人聊天节奏
- **消息去抖** — 多条消息合并处理（默认 3 秒窗口），避免连续打扰
- **数据持久化** — 聊天历史、关系亲密度、记忆数据全部持久化存储

## 🚀 快速开始

### 环境要求

- Python 3.11+
- Windows / Linux / macOS

### 安装

```bash
git clone https://github.com/yangmuji14-creator/cyber-girlfriend.git
cd cyber-girlfriend
python -m venv .venv

# Windows
.venv\Scripts\activate
# Linux/macOS
source .venv/bin/activate

pip install -r requirements.txt
```

### 配置

运行设置向导：

```bash
python main.py setup
```

向导会引导你完成：

1. **选择模型** — 输入序号选择大模型提供商，填写 API Key
2. **配置人设** — 导入 ex-skill 文件或手动配置（名字、年龄、性格、说话风格）
3. **高级参数** — 亲密度、消息分段长度、去抖延迟、记忆总结阈值（都有默认值）

### 运行

```bash
python main.py
```

直接进入终端聊天，输入消息即可对话，输入 `quit` 退出。

## 📁 项目结构

```
cyber-girlfriend/
├── main.py                   # 主入口（CMD 聊天）
├── setup.py                  # 3 步设置向导
├── config/
│   ├── personas.json         # 人设配置（默认小雨）
│   ├── settings.json         # 模型配置 + 高级参数
│   └── platforms.json        # 平台配置（预留）
├── core/
│   ├── llm/                  # LLM 统一接口
│   │   ├── base.py           #   基类
│   │   ├── registry.py       #   模型注册中心
│   │   ├── deepseek.py       #   DeepSeek 实现
│   │   └── openai_compatible.py  #   OpenAI 兼容接口
│   ├── memory/               # 记忆系统
│   │   ├── models.py         #   Memory 数据模型
│   │   ├── storage.py        #   JSON 存储（原子写入）
│   │   ├── scorer.py         #   5 级重要度评分
│   │   ├── manager.py        #   CRUD + 检索
│   │   ├── summarizer.py     #   LLM 辅助记忆总结
│   │   └── chat_history.py   #   聊天历史持久化
│   ├── persona/              # 人设系统
│   │   ├── models.py         #   Persona 数据模型
│   │   ├── loader.py         #   配置加载
│   │   └── prompt_builder.py #   System Prompt 构建
│   ├── emotion/              # 情感系统
│   │   ├── analyzer.py       #   8 种情感识别
│   │   └── expression.py     #   消息分段 + Emoji 增强
│   └── relationship/         # 关系系统
│       └── tracker.py        #   亲密度动态计算
├── tests/
│   └── test_core.py          #   单元测试（36 个）
├── data/                     # 运行时数据（自动生成，不提交）
├── requirements.txt
├── .env.example
└── .gitignore
```

## 🤖 支持的模型

| 模型 | 环境变量 | 说明 |
|------|----------|------|
| DeepSeek | `DEEPSEEK_API_KEY` | 默认模型，性价比高 |
| OpenAI GPT-4o | `OPENAI_API_KEY` | GPT-4o-mini 等 |
| Gemini | `GEMINI_API_KEY` | Gemini 2.0 Flash |
| 通义千问 | `TONGYI_API_KEY` | qwen-turbo |
| Kimi | `KIMI_API_KEY` | moonshot-v1-8k |
| 智谱 GLM | `ZHIPU_API_KEY` | glm-4-flash |

## 🧠 记忆系统

- **自动提取** — 每次对话自动分析关键词，评分 ≥ 2 的内容自动记忆
- **5 级评分** — 闲聊(1) → 偏好(2) → 个人信息(3) → 重要事件(4) → 核心记忆(5)
- **LLM 总结** — 每 N 组对话自动总结短期记忆为长期记忆（可配置阈值）
- **持久化** — 聊天历史和短期记忆重启不丢失

## 💕 亲密度系统

亲密度根据互动动态变化：

| 因素 | 影响 |
|------|------|
| 每次对话 | +0.05 |
| 正面情感（开心/爱意） | +0.3 |
| 负面情感（生气/难过） | -0.2 |
| 3 天不聊天 | 每天 -0.05 |

亲密度影响 AI 的语气和亲密程度（0-100，5 档描述）。

## 📥 导入 Skill 文件

支持导入 [ex-skill](https://github.com/therealXiaomanChu/ex-skill) 项目生成的 SKILL.md 文件，LLM 会自动解析并生成人设配置：

```bash
python main.py setup
# 选择「导入 skill 文件」→ 输入 SKILL.md 路径 → 自动配置人设
```

## ⚙️ 高级参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| 初始亲密度 | 50 | 0-100，50=朋友，80=恋人 |
| 消息分段长度 | 50 字 | 超过此长度自动分段发送 |
| 去抖延迟 | 3 秒 | 连续消息合并等待时间 |
| 记忆总结阈值 | 15 组 | 多少组对话后自动总结长期记忆 |

## 🧪 测试

```bash
python -m pytest tests/test_core.py -v
```

36 个单元测试覆盖：记忆评分、存储、情感分析、消息分段、关系追踪、聊天历史。

## 🙏 致谢

- [My-Dream-Moments](https://github.com/iwyxdxl/My-Dream-Moments) — 记忆总结、消息分段、情感表达设计参考
- [LiteLLM](https://github.com/BerriAI/litellm) — 统一 LLM 接口
- [ex-skill](https://github.com/therealXiaomanChu/ex-skill) — Skill 文件格式参考

## 📄 License

MIT
