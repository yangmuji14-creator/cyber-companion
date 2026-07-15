# 🎀 赛博伴侣 — Cyber Companion v4.1.4

纯终端 AI 伴侣聊天机器人。支持 **MCP 工具扩展**、**双路径图片识别**、语义记忆、情感分析、30+ 字段人设、动态亲密度、持续性情绪系统、内心独白大脑、多平台接入。

> ⚠️ **推荐使用 Windows CMD（命令提示符）运行**，PowerShell 可能有 Unicode 编码问题。

---

## 快速开始

```cmd
# 安装依赖
python install.py

# 配置向导（模型选择 + 人设 + 参数）
python main.py setup

# 开始聊天
python main.py
```

---

## 特性

### 🤖 6 种大模型支持

| 提供商 | 默认模型 | 特点 |
|---|---|---|
| DeepSeek | deepseek-chat | 国产便宜，推荐 |
| OpenAI | gpt-4o-mini | 需海外网络 |
| Gemini | gemini-2.0-flash | Google 免费额度 |
| 通义千问 | qwen-turbo | 阿里云国内快 |
| Kimi | moonshot-v1-8k | 长上下文 |
| 智谱 | glm-4-flash | 免费额度 |

### 🔌 MCP 工具系统

连接外部 MCP (Model Context Protocol) Server，内置三个 Server：

| Server | 功能 |
|---|---|
| `system_tools` | 日期时间 / 字数统计 / 随机数 / 文件读取（data/logs 真实路径白名单） |
| `web_fetch` | 网页抓取（SSRF 防护）+ Bing 搜索 |
| `weather` | 天气查询 + 预报（wttr.in，免费无需 API Key） |

- **协议兼容** — JSON-RPC 2.0 over stdio，支持 initialize / tools/list / tools/call
- **稳定可靠** — 指数退避重连、分级超时、心跳监控、读取无活动截止（阻塞管道也能触发重连）、帧大小上限保护
- **冲突处理** — 多 Server 同名工具自动加命名空间前缀
- **安全加固（v4.1.3）** — 文件读取限定 data/logs 真实路径（realpath 防符号链接）+ SSRF 内网防护 + 拒绝重定向
- 配置：`config/mcp_servers.json`

### 📷 图片识别

两种策略，自动切换：

| 主模型类型 | 策略 | 流程 |
|---|---|---|
| 多模态（GPT-4o / Claude / Gemini） | **直传** | 图片 → 主模型 → 回复 |
| 纯文本（DeepSeek / GPT-3.5） | **降级** | 图片 → 视觉模型 → 描述文字 → 主模型 → 回复 |

- 30+ 模型自动多模态检测
- 微信图片自动识别：收到图片 → 视觉模型 → 主模型 → 回复
- 配置：`settings.json → advanced.vision_model`

### 🧠 语义记忆

向量嵌入（BAAI/bge-small-zh-v1.5）+ 关键词混合检索。搜"宠物"能想起"喜欢猫"。嵌入器不可用时自动降级。

### 🎭 持续性情绪引擎

- 14 种情绪状态的 2D valence-arousal 模型
- 跨会话持久化，随时间自然衰减
- 情绪直接影响 AI 的语气、回复长度、emoji 选择
- 精力条（energy）低时回复变简短慵懒

### 🧠 内心独白大脑

AI 在回复前自主进行「内心思考」：

- **14 维度状态收集** — 情绪/人格/亲密度/身份/人生总结等
- **念头组织 + 独白编织** — 生成第一人称连贯内心独白
- **主动回忆** — 关键词触发、情绪触发、自发回忆
- **人设断裂检测** — 自动检测回复是否偏离角色

### 💕 亲密度系统

- LLM 自主理解对话情感温度，7 种情感方向调整亲密度
- SQLite 持久化，边际递减 + 自然衰减
- 人格联动：亲密度变化影响人格维度

### 🛠️ 内置工具 + MCP 扩展

| 工具 | 来源 | 功能 |
|---|---|---|
| `get_current_time` | 内置 | 当前时间 / 日期 |
| `calculate` | 内置 | 数学计算 |
| `get_weather` | MCP | 天气查询（wttr.in） |
| `fetch` / `search` | MCP | 网页抓取 / Bing 搜索 |
| `read_text_file` | MCP | 文件读取（安全白名单） |
| `get_datetime` / `random_number` | MCP | 日期 / 随机数 |

MCP 与内置工具统一在 `【工具调用：xxx()】` 格式下调用。

### 🎀 30+ 字段人设

身份、性格、MBTI、爱好、语言习惯、情绪模式、行为倾向、关系背景…

### 📦 ex-skill 人设导入

```cmd
python main.py import-skill <目录或文件>
```

### 📋 斜杠命令

```
/help       — 显示帮助        /stats      — 亲密度统计
/memories   — 记忆管理        /persona    — 人设信息
/personality— 人格状态        /mood       — 当前情绪
/debug      — System Prompt   /brain      — 内心独白
/clear      — 清空聊天        /export     — 导出记录
/undo       — 撤销上轮        /regen      — 重新生成
/search     — 搜索历史        /tools      — 工具列表
/img        — 图片识别        /quit       — 退出
```

---

## 多平台接入

```cmd
# 配置微信
python main.py wechat

# 启动（自动检测已配置的平台）
python main.py
```

消息去抖合并：连续输入在 3 秒内自动合并后一起处理。

---

## 项目结构

```
cyber-companion/
├── core/
│   ├── app.py              # 应用装配 + ComponentBuilder
│   ├── config.py           # 配置加载
│   ├── storage/            # 📦 统一数据库连接管理（v3.4）
│   │   └── db.py           #   open_db() + PRAGMA 配置
│   ├── chat/               # 聊天管线
│   │   ├── pipeline.py     #   消息处理主流程
│   │   ├── handler.py      #   终端聊天循环
│   │   ├── commands/       #   斜杠命令（v3.4 拆分）
│   │   ├── tool_handler.py #   工具调用（本地+MCP）
│   │   ├── post_process.py #   后台后处理编排
│   │   └── display.py      #   终端输出共享
│   ├── brain/              # 🧠 内心独白大脑
│   │   ├── coordinator.py  #   大脑协调器
│   │   ├── collector.py    #   状态收集
│   │   ├── organizer.py    #   念头组织
│   │   ├── weaver.py       #   独白编织
│   │   ├── triggers.py     #   主动回忆
│   │   └── checker.py      #   人设检测
│   ├── emotion/            # 情绪系统（MoodEngine）
│   ├── memory/             # 记忆系统（向量+SQLite）
│   ├── persona/            # 人设引擎
│   ├── personality/        # 人格系统
│   ├── social/             # 社交系统（亲密度+关系）
│   ├── dialogue/           # 对话思考 + 一致性
│   ├── multimodal/         # 图片处理 + 视觉识别
│   │   └── vision.py       #   双路径图片识别（v3.4）
│   ├── tools/              # 工具系统
│   │   ├── mcp_client.py   #   MCP 协议客户端（v3.4）
│   │   └── mcp_manager.py  #   MCP 多 Server 管理（v3.4）
│   ├── llm/                # LLM 抽象层
│   └── proactive.py        # 主动消息
├── adapters/               # 平台适配器（CLI/微信/API）
│   └── debounce.py         # 消息去抖（v3.4 提取）
├── plugins/                # 插件系统
├── mcp_servers/            # MCP 工具 Server（v3.4）
│   ├── system_tools.py     #   系统工具（日期/文件/随机数）
│   ├── web_fetch.py        #   网页抓取+搜索（SSRF 防护）
│   └── weather.py          #   天气查询（wttr.in）
├── plugins/                # 插件系统
├── tools/                  # 开发工具
├── tests/                  # 测试（418 tests, v4.1.3）
├── setup_wizard.py         # 配置向导
├── install.py              # 环境安装
└── config/                 # 用户配置（不进 git）
```

---

## 配置

| 文件 | 用途 |
|---|---|
| `.env` | API Key 配置 |
| `config/settings.json` | 模型 + 高级参数 + 视觉模型 |
| `config/personas.json` | 人设数据 |
| `config/mcp_servers.json` | MCP Server 列表 |

---

## 数据存储

9 个 SQLite 数据库（WAL 模式，`foreign_keys=ON`）：

| 文件 | 内容 |
|---|---|
| `data/memories.db` | 记忆库 |
| `data/vectors.db` | 向量索引 |
| `data/moods.db` | 情绪状态 |
| `data/personality.db` | 人格状态 |
| `data/unified.db` | 亲密度 |
| `data/identity.db` | 用户身份 |
| `data/open_loops.db` | 未完成事件 |
| `data/life_summaries.db` | 人生摘要 |
| `data/relationship_events.db` | 关系事件 |

---

## 测试

```bash
# 全部测试（418 tests）
pytest tests -v

# 集成连通性
pytest tests/test_integration_connectivity.py -v

# 稳定性 + MCP 测试
pytest tests/test_stability.py -v

# 300 轮对话压测 + MCP 安全验证
pytest tests/test_stress_300_conversations.py -v

# 大脑自测
python tools/brain_self_test.py
```

当前测试状态：**418/418 全部通过**

---

## 技术栈

Python 3.11+ / asyncio / LiteLLM / sentence-transformers / SQLite / numpy

---

## 作者

**yangmuji14**

---

> 🌟 如果这个项目对你有帮助，欢迎点个 Star 支持一下~
