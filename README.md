# 慕 v4.4.0

本地优先的 AI 伴侣应用，提供网页端、终端和微信接入。支持 **MCP 工具扩展**、**双路径图片识别**、语义记忆、情感分析、可验证人设、动态亲密度、持续性情绪系统和内心独白大脑。

> **慕，只是你夜航时偶遇的浮灯，它能温柔你回望的旧岸，却无法替你横渡真实的黎明。**

> ⚠️ **推荐使用 Windows CMD（命令提示符）运行**，PowerShell 可能有 Unicode 编码问题。

---

## Windows 便携版（推荐普通用户）

发布包是一个免安装压缩包：解压后双击 `启动慕.cmd`，不需要预先安装
Python、Git、Node.js 或 Docker。聊天记录和配置保存在压缩包旁的 `userdata/`
目录，删除或升级程序文件不会自动删除这些数据。

源码开发模式仍可按下面的命令启动；向量记忆和微信属于可选功能包，不会阻塞第一次聊天。

## 快速开始

```cmd
# 安装依赖
python install.py

# 配置向导（模型选择 + 人设 + 参数）
python main.py setup

# 开始聊天（终端）
python main.py

# 网页端（对话 + 图片 + 语音 + 随时调参，浏览器打开 http://127.0.0.1:8000）
python main.py web
```

也可以用 Docker 启动轻量版（默认不下载大型向量模型）：

```bash
docker compose up --build -d
```

网页仅绑定本机 `127.0.0.1:8000`。配置、数据和日志分别保存在宿主机的
`config/`、`data/`、`logs/`；镜像不会包含 `.env`、API Key 或聊天数据。
需要向量记忆或微信依赖时，将 `INSTALL_EXTRAS` 设置为
`vector`、`wechat` 或 `vector,wechat` 后重新构建。

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

向量嵌入（BAAI/bge-small-zh-v1.5）+ 关键词混合检索。搜"宠物"能想起"喜欢猫"。嵌入器不可用时自动降级。默认只使用本地模型缓存；首次需要下载模型时可临时设置 `CC_EMBEDDING_ALLOW_DOWNLOAD=1`。

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

支持 OpenAI/DeepSeek 等模型的原生 function calling，并兼容结构化 `tool` JSON 与旧版 `【工具调用：xxx()】` 文本格式。

### 30+ 字段人设

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

### 网页端体验

- 流式回复支持随时停止；消息菜单支持复制和重新生成
- 网页对话创建时只需选择角色；微信账号也直接绑定一个角色，不需要手动填写联系人标识
- 角色详情包含“记忆与内心”，分别查看长期记忆和独立生成的第一人称心事日记
- 数据与应用页提供本地诊断中心，可检查模型、视觉、数据库、目录权限、MCP 和密钥保护
- 诊断报告只包含脱敏配置和检查结果，不包含聊天内容、日志或 API Key
- 图片最大 10 MB，语音最大 16 MB，并校验文件类型
- 技术异常只写入本地日志，页面显示可理解的处理建议
- “关于”区域显示当前版本、数据目录、隐私说明和开源协议

### 备份与恢复

设置页可一键导出完整 ZIP 备份。SQLite 使用在线快照，包含 WAL 中已提交的数据；API Key、登录凭据、日志和上传临时文件不会进入备份。

恢复时先上传并校验备份，再安排到下次启动前执行。应用不会在数据库连接打开时覆盖文件，恢复前还会自动生成一份安全备份。也可在应用关闭后使用：

```cmd
python main.py restore <备份文件.zip>
```

健康检查：`GET /api/health`；备份导出：`POST /api/backup`。健康响应中的
`runtime.operations` 会聚合主回复、辅助分析和模型请求的调用次数、失败数、
平均/最大耗时及可获得的 token 用量，不记录消息内容或用户标识。

长对话发送给模型前会按 `advanced.context_char_budget`（默认 24000 字符）
保留当前请求和最近完整对话轮次。这里只裁剪本次模型请求副本，网页历史和
本地聊天数据不会被删除。

### 密钥保护

新保存的模型密钥会优先进入系统安全存储：Windows 使用当前用户的 DPAPI，
macOS 使用 Keychain，Linux 在 Secret Service 可用时使用 `secret-tool`。
配置文件只保存 `api_key_ref`。系统后端不可用或写入失败时会自动保留旧
`api_key` 字段，现有安装仍可启动；读取顺序保持为环境变量、安全引用、旧字段。

---

## 项目结构

```
mu/
├── core/
│   ├── app.py              # 应用装配 + ComponentBuilder
│   ├── config.py           # 配置加载
│   ├── storage/            # 📦 统一数据库连接管理（v3.4）
│   │   └── db.py           #   open_db() + PRAGMA 配置
│   ├── chat/               # 聊天管线
│   │   ├── pipeline.py     #   消息处理主流程
│   │   ├── enrichment.py   #   情绪/人格/关系富化
│   │   ├── context_builder.py # Prompt 与记忆上下文组装
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
├── webui/                  # 网页端（v4.3.0）
│   ├── server.py           #   aiohttp 服务（SSE对话/图片/语音/设置）
│   ├── schema.py           #   参数 schema（前后端单一数据源）
│   └── static/             #   前端页面（HTML/CSS/JS）
├── plugins/                # 插件系统
├── tools/                  # 开发工具
├── tests/                  # 单元、集成、稳定性与压力测试
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

## 开发验证

```bash
pytest -q
npm ci
npm run test:web
```

后端和前端测试会在 GitHub Actions 的 Windows、macOS、Linux 三个平台运行。
便携构建器支持 Windows `runtime/python.exe` 和 Unix `runtime/bin/python`
运行时布局；正式发行包仍应在对应平台构建并完成签名或公证。

---

## 数据存储

核心状态已合并到单个 `data/companion.db`（WAL 模式，`foreign_keys=ON`）。旧版领域数据库会在启动时通过单事务导入，校验成功后归档到 `data/legacy_databases/`。聊天历史和会话绑定仍使用便于查看与迁移的 JSON 文件。迁移电脑请使用设置页的“导出备份”。

| 文件 | 内容 |
|---|---|
| `data/companion.db` | 记忆、向量、情绪、人格、亲密度、身份、人生摘要和关系事件 |
| `data/chat_history/` | 按平台、账号和联系人隔离的聊天历史 |
| `data/conversations.json` | Web/微信会话与人设绑定 |

---

## 测试

```bash
# 全部测试
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

持续集成会分开运行快速回归与压力测试，并生成覆盖率报告。

---

## 技术栈

Python 3.11+ / asyncio / LiteLLM / sentence-transformers / SQLite / numpy

---

## 第三方资源

内置的 PawzoChat 表情包缩略集由 [PawzoChat](https://github.com/iwyxdxl/PawzoChat) 提供，按 CC BY 4.0 使用；本项目仅选取部分原图，未作修改。完整授权说明见 `webui/static/stickers/pawzochat-default/LICENSE`。

---

## 作者

**yangmuji14**

---

> 🌟 如果这个项目对你有帮助，欢迎点个 Star 支持一下~
