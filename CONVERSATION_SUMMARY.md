# Cyber Girlfriend 项目 - 对话总结

## 项目概述

**项目名**: cyber-girlfriend (赛博女友)
**仓库**: https://github.com/yangmuji14-creator/cyber-girlfriend
**目录**: C:\Users\30216\cyber-girlfriend
**Python**: 3.11（用户机器上是 3.11，不是 3.12）
**虚拟环境**: `.venv`（已创建，依赖已安装）

## 技术栈

| 模块 | 技术 |
|------|------|
| 后端 | FastAPI + Uvicorn |
| 大模型 | LiteLLM（统一接口） |
| 微信 | ilink API（用户已有账号） |
| QQ | NapCat（OneBot 11） |
| Telegram | python-telegram-bot |
| 记忆 | JSON 文件存储 |
| 情感 | 关键词分析 + LLM 辅助 |
| WebUI | FastAPI + HTML/JS |

## 已完成的 9 个阶段

### Phase 1: 项目骨架 + 大模型接入 ✅
- 目录结构搭建
- LLM 统一接口（`core/llm/base.py`）+ LiteLLM
- DeepSeek 实现 + OpenAI 兼容接口（通义/Kimi/智谱）
- 模型注册中心 + 热切换（`core/llm/registry.py`）
- 配置文件：`config/settings.json`, `config/accounts.json`, `config/personas.json`
- 默认人设：小雨（22岁大学生，温柔活泼偶尔傲娇）

### Phase 2: 记忆系统 ✅
- Memory 数据模型（`core/memory/models.py`）
- JSON 文件存储层（`core/memory/storage.py`）
- 5级重要度评分（`core/memory/scorer.py`）— 关键词 + 正则 + 长度
- MemoryManager CRUD + 搜索（`core/memory/manager.py`）

### Phase 3: 人设系统 ✅
- Persona 数据模型（`core/persona/models.py`）
- PersonaLoader JSON 配置加载（`core/persona/loader.py`）
- PromptBuilder system prompt 构建（`core/persona/prompt_builder.py`）
- 亲密度等级系统（0-100，5档）
- 交互式聊天循环

### Phase 4: 微信传输层 ✅
- 传输层统一接口（`transport/base.py`）
- WeChatTransport ilink webhook 处理（`transport/wechat/handler.py`）
- ILinkClient 消息发送（`transport/wechat/api.py`）
- FastAPI 端点：`POST /api/wechat/webhook`

### Phase 5: QQ 传输层 ✅
- NapCatClient（`transport/qq/napcat.py`）— 正向 WebSocket + HTTP API
- QQTransport（`transport/qq/handler.py`）

### Phase 6: Telegram 传输层 ✅
- TelegramTransport（`transport/telegram/bot.py`）

### Phase 7: 情感层 + 记忆总结 + 消息分段 ✅（参考 My-Dream-Moments）
- MemorySummarizer（`core/memory/summarizer.py`）— LLM 辅助记忆提取 + 短期→长期记忆总结
- EmotionAnalyzer（`core/emotion/analyzer.py`）— 8种情感识别
- EmotionEnhancer（`core/emotion/expression.py`）— 根据情感自动添加 emoji
- MessageSegmenter（`core/emotion/expression.py`）— 长消息按自然断句分段
- AsyncMessageQueue（`main.py`）— 3秒去抖，多条消息合并处理
- 时间上下文注入（早上/下午/晚上/深夜）

### Phase 8: WebUI ✅
- FastAPI 后端 API（`webui/app.py`）— 账户/人设/记忆/模型 CRUD
- 暗色主题前端（`webui/static/index.html`）
- 功能：聊天测试、人设管理、记忆管理、模型配置、账户管理

### Phase 9: 测试和优化 ✅
- 代码审查（python-reviewer agent）
- 修复 7 个 CRITICAL + 8 个 HIGH + 多个 MEDIUM 问题
- 25 个单元测试（`tests/test_core.py`，24 passed）

## 关键架构决策

1. **AsyncMessageQueue**: 用 `asyncio.sleep` 替代 `threading.Timer`，全部在事件循环内执行
2. **Lifespan**: 用 FastAPI lifespan 替代 deprecated `on_event`
3. **路径穿越防护**: `user_id` 经过 `re.sub(r'[^a-zA-Z0-9_\-.]', '_', user_id)` 净化
4. **原子写入**: 记忆存储使用 `tempfile` + `os.replace` 防止崩溃数据丢失
5. **Persona 字段白名单**: 防止属性注入攻击

## 启动命令

```powershell
cd C:\Users\30216\cyber-girlfriend
.\.venv\Scripts\activate

# 终端聊天
python main.py

# API 服务 + WebUI（默认 127.0.0.1:8080）
python main.py --mode server

# 指定端口
python main.py --mode server --port 8080 --host 0.0.0.0
```

## GitHub CLI

- 已安装 gh CLI（v2.93.0）
- 已登录账号：yangmuji14-creator
- Token 暴露在对话中，建议用户去 https://github.com/settings/tokens 撤销并重新生成

## 参考项目

- **My-Dream-Moments** (iwyxdxl/My-Dream-Moments): 借鉴了记忆总结、消息分段、情感表情、消息队列等设计
- 项目地址: https://github.com/iwyxdxl/My-Dream-Moments

## 未完成 / 待修复

### 1. QQ/Telegram handler coroutine await 问题
`main.py` 中：
```python
qq.set_message_handler(lambda msg: handle_message(msg.user_id, msg.content))
```
`handle_message` 是 async 函数，lambda 返回的是 coroutine 对象。QQ 的 `_wrap_handler` 没有 await 它，导致用户看到的是 `<coroutine object ...>` 而不是实际回复。

**修复方案**：改为 async handler：
```python
async def _qq_handler(msg):
    return await handle_message(msg.user_id, msg.content)
qq.set_message_handler(_qq_handler)
```

### 2. NapCat WS API echo 匹配
`transport/qq/napcat.py` 的 `_call_ws_api` 方法用 `self._ws.receive()` 等待响应，但 WebSocket 可能先收到事件消息而非 API 响应。需要实现 echo ID 匹配。

### 3. 单元测试 1 个断言调整
`tests/test_core.py::test_score_high_importance` 第二个断言 `assert score >= 2` 可能需要根据实际评分逻辑调整。

### 4. 记忆语义检索（P2）
当前记忆检索是精确关键词匹配，可以用 embedding 做语义相似度检索。

### 5. 关系亲密度动态计算（P1）
当前 `relationship_level` 是配置文件里的静态值，应根据对话互动动态变化。

### 6. 消息历史持久化（P1）
`_user_histories` 和 `_short_memories` 是内存 dict，重启丢失。应持久化到文件。

### 7. WebUI 认证（P1）
管理 API 无认证。环境变量 `ADMIN_API_KEY` 已支持但未强制启用。

### 8. Docker 部署
项目还没有 Dockerfile。

## 环境变量（.env）

需要配置的 Key：
```
DEEPSEEK_API_KEY=sk-xxx          # 必填，主要模型
OPENAI_API_KEY=sk-xxx            # 可选
GEMINI_API_KEY=xxx               # 可选
TONGYI_API_KEY=sk-xxx            # 可选（通义千问）
KIMI_API_KEY=sk-xxx              # 可选
ZHIPU_API_KEY=xxx                # 可选

NAPCAT_WS_URL=ws://127.0.0.1:3001    # QQ
NAPCAT_HTTP_URL=http://127.0.0.1:3000 # QQ
NAPCAT_ACCESS_TOKEN=xxx               # QQ

TELEGRAM_BOT_TOKEN=xxx           # Telegram

ADMIN_API_KEY=xxx                # WebUI 认证（可选）
```

## 项目文件结构

```
cyber-girlfriend/
├── config/
│   ├── accounts.json         # 账户配置
│   ├── personas.json         # 人设配置（默认小雨）
│   └── settings.json         # 模型配置
├── core/
│   ├── llm/
│   │   ├── base.py           # LLM 统一接口（LiteLLM）
│   │   ├── registry.py       # 模型注册中心
│   │   ├── deepseek.py       # DeepSeek 实现
│   │   └── openai_compatible.py  # OpenAI 兼容接口
│   ├── memory/
│   │   ├── models.py         # Memory 数据模型
│   │   ├── storage.py        # JSON 存储层（原子写入+路径穿越防护）
│   │   ├── scorer.py         # 5级重要度评分
│   │   ├── manager.py        # 记忆 CRUD + 检索
│   │   └── summarizer.py     # LLM 辅助记忆总结
│   ├── persona/
│   │   ├── models.py         # Persona 数据模型
│   │   ├── loader.py         # 人设加载器（字段白名单）
│   │   └── prompt_builder.py # System prompt 构建
│   └── emotion/
│       ├── analyzer.py       # 情感分析（8种情感）
│       └── expression.py     # 消息分段 + Emoji 增强
├── transport/
│   ├── base.py               # 传输层统一接口
│   ├── wechat/
│   │   ├── api.py            # ilink 客户端
│   │   └── handler.py        # 微信消息处理
│   ├── qq/
│   │   ├── napcat.py         # NapCat OneBot 11 客户端
│   │   └── handler.py        # QQ 消息处理
│   └── telegram/
│       └── bot.py            # Telegram Bot
├── webui/
│   ├── app.py                # FastAPI 后端 API
│   └── static/
│       └── index.html        # WebUI 前端
├── tests/
│   └── test_core.py          # 单元测试（25个）
├── data/
│   ├── memories/             # 记忆数据
│   ├── personas/             # 人设数据
│   └── exports/              # 导出文件
├── main.py                   # 主入口（chat/server 两种模式）
├── requirements.txt          # 依赖清单
├── .env.example              # 环境变量模板
├── .gitignore
└── .venv/                    # 虚拟环境（已创建）
```
