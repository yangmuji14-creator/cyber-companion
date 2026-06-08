# 🎀 Cyber Girlfriend

一个支持多平台的赛博女友聊天机器人，具有记忆系统、情感分析、人设管理和动态亲密度功能。

## ✨ 特性

- **多平台接入** — 微信（ilink）、QQ（NapCat/OneBot 11）、Telegram
- **多模型支持** — DeepSeek、OpenAI、Gemini、通义千问、Kimi、智谱，通过 LiteLLM 统一接口
- **记忆系统** — 自动提取重要信息，LLM 辅助记忆总结，5 级重要度评分
- **情感分析** — 8 种情感识别（开心/难过/生气/爱意等），自动添加 emoji 表达
- **人设系统** — 可配置的性格、背景、说话风格，支持多人设切换
- **动态亲密度** — 根据对话互动、情感频率、时间衰减动态计算关系等级
- **消息分段** — 长消息按自然断句分段发送，模拟真人聊天节奏
- **消息去抖** — 多条消息合并处理（3 秒窗口），避免连续打扰
- **WebUI 管理** — 暗色主题管理后台，支持聊天测试、人设/记忆/模型/账户管理
- **认证系统** — PBKDF2 密码哈希 + JWT 会话认证，登录限速保护
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

复制环境变量模板并填写 API Key：

```bash
cp .env.example .env
```

编辑 `.env`：

```env
# 必填：主要模型
DEEPSEEK_API_KEY=sk-xxx

# 可选：其他模型
OPENAI_API_KEY=sk-xxx
GEMINI_API_KEY=xxx
TONGYI_API_KEY=sk-xxx
KIMI_API_KEY=sk-xxx
ZHIPU_API_KEY=xxx

# QQ（NapCat）
NAPCAT_WS_URL=ws://127.0.0.1:3001
NAPCAT_HTTP_URL=http://127.0.0.1:3000
NAPCAT_ACCESS_TOKEN=xxx

# Telegram
TELEGRAM_BOT_TOKEN=xxx

# WebUI 管理密钥（可选）
ADMIN_API_KEY=xxx
```

### 运行

```bash
# 终端聊天模式
python main.py

# 启动 API 服务 + WebUI
python main.py --mode server

# 指定端口和地址
python main.py --mode server --port 8080 --host 0.0.0.0
```

首次启动 WebUI（`http://127.0.0.1:8080`）会引导设置管理员账号。

## 📁 项目结构

```
cyber-girlfriend/
├── config/
│   ├── accounts.json         # 账户配置
│   ├── personas.json         # 人设配置（默认小雨）
│   ├── settings.json         # 模型配置
│   └── auth.json             # 认证配置（自动生成）
├── core/
│   ├── llm/                  # LLM 统一接口
│   │   ├── base.py           #   基类（LiteLLM）
│   │   ├── registry.py       #   模型注册中心 + 热切换
│   │   ├── deepseek.py       #   DeepSeek 实现
│   │   └── openai_compatible.py  #   OpenAI 兼容接口
│   ├── memory/               # 记忆系统
│   │   ├── models.py         #   Memory 数据模型
│   │   ├── storage.py        #   JSON 存储（原子写入 + 路径穿越防护）
│   │   ├── scorer.py         #   5 级重要度评分
│   │   ├── manager.py        #   CRUD + 检索
│   │   ├── summarizer.py     #   LLM 辅助记忆总结
│   │   └── chat_history.py   #   聊天历史持久化
│   ├── persona/              # 人设系统
│   │   ├── models.py         #   Persona 数据模型
│   │   ├── loader.py         #   配置加载（字段白名单防注入）
│   │   └── prompt_builder.py #   System Prompt 构建
│   ├── emotion/              # 情感系统
│   │   ├── analyzer.py       #   8 种情感识别
│   │   └── expression.py     #   消息分段 + Emoji 增强
│   └── relationship/         # 关系系统
│       └── tracker.py        #   亲密度动态计算
├── transport/                # 传输层
│   ├── base.py               #   统一接口
│   ├── wechat/               #   微信（ilink API）
│   │   ├── api.py
│   │   └── handler.py
│   ├── qq/                   #   QQ（NapCat OneBot 11）
│   │   ├── napcat.py
│   │   └── handler.py
│   └── telegram/             #   Telegram Bot
│       └── bot.py
├── webui/                    # WebUI
│   ├── app.py                #   FastAPI 后端 + 认证中间件
│   ├── auth.py               #   PBKDF2 + JWT 认证模块
│   └── static/
│       ├── index.html        #   管理后台
│       └── login.html        #   登录页
├── tests/
│   └── test_core.py          #   单元测试（41 个）
├── data/                     # 运行时数据（自动生成）
│   ├── memories/
│   ├── chat_history/
│   └── relationships.json
├── main.py                   # 主入口
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

模型配置在 `config/settings.json` 中，支持运行时热切换。

## 📱 平台接入

### 微信（ilink）

使用 [ilink](https://github.com/anthropics/ilink) API 接入，配置 webhook 回调地址：

```
POST http://your-host:8080/api/wechat/webhook
```

### QQ（NapCat）

使用 [NapCat](https://napneko.github.io/) 实现的 OneBot 11 协议，支持：
- 正向 WebSocket 连接
- HTTP API 调用
- Echo ID 匹配响应

### Telegram

使用 `python-telegram-bot` 库，配置 Bot Token 即可。

## 🧠 记忆系统

- **自动提取** — 每次对话自动分析关键词，评分 ≥ 2 的内容自动记忆
- **5 级评分** — 闲聊(1) → 偏好(2) → 个人信息(3) → 重要事件(4) → 核心记忆(5)
- **LLM 总结** — 每 15 组对话自动总结短期记忆为长期记忆
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

## 🔐 安全

- **密码哈希** — PBKDF2-HMAC-SHA256，600,000 次迭代
- **JWT 会话** — HS256 签名，7 天有效期，httponly cookie
- **登录限速** — 每 IP 5 次/5 分钟，失败延迟 2 秒
- **路径穿越防护** — 用户 ID 经过正则净化
- **原子写入** — 配置和数据文件使用 tempfile + os.replace
- **字段白名单** — Persona 属性防注入

## 🧪 测试

```bash
python -m pytest tests/test_core.py -v
```

41 个单元测试覆盖：记忆评分、存储、情感分析、消息分段、关系追踪、聊天历史、认证模块。

## 📋 TODO

- [ ] 传输层重构：事件队列 + 平台适配器模式（参考 AstrBot）
- [ ] 记忆语义检索：embedding 向量相似度搜索
- [ ] 群聊支持
- [ ] Docker 部署
- [ ] WebUI 认证强制启用

## 🙏 致谢

- [My-Dream-Moments](https://github.com/iwyxdxl/My-Dream-Moments) — 记忆总结、消息分段、情感表达设计参考
- [AstrBot](https://github.com/AstrBotDevs/AstrBot) — 登录认证系统和平台适配器架构参考
- [LiteLLM](https://github.com/BerriAI/litellm) — 统一 LLM 接口
- [NapCat](https://napneko.github.io/) — QQ OneBot 11 实现

## 📄 License

MIT
