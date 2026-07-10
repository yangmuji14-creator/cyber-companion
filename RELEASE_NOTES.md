# 更新日志

## v4.1.1 — 安全加固 + 代码质量清理（2026-07-10）

### 🔒 安全修复

- **MCP `read_text_file` 路径白名单** — 新增 `_is_path_safe()` 检查：路径必须在安全目录（data/logs/config）内，扩展名限制（.txt/.md/.json/.log/.csv/.yaml），防止路径遍历攻击读取 `.env` 等敏感文件
- **MCP `web_fetch` SSRF 防护** — 新增内网 IP 黑名单（localhost/127.0.0.1/10.0.0.0/8/172.16.0.0/12/192.168.0.0/16），DNS 解析后二次校验防止 DNS rebinding，fail-safe 策略
- **bare except 修复** — `web_fetch.py`、`weather.py` 中 Content-Length 解析的 `except: pass` 改为 `except (ValueError, IndexError): pass`，不再吞掉 KeyboardInterrupt

### 🐛 Bug 修复

- **Fire-and-forget 任务错误处理** — `wechat.py:_do_vision()`、`debounce.py:_send()`、`mcp_client.py:list_tools()` 三处 `asyncio.create_task()` 添加 `add_done_callback` 错误日志，防止静默失败

### 🧹 代码清理

- **`core/llm/base.py`** — 删除 `chat_stream` 中未使用的 `_key` 死代码变量
- **`core/chat/handler.py`** — 移除 `__init__` 中重复的 `self._personality_engine` 赋值

### 🧪 测试

- **新增 `tests/test_stress_300_conversations.py`** — 300 轮模拟对话压测，覆盖全部模块协作：
  - 300 轮 pipeline 对话处理（记忆/情绪/亲密度/身份/开放式循环/大脑）
  - MCP `read_text_file` 路径安全验证
  - MCP `web_fetch` SSRF 拦截验证
  - 50 条并发记忆写入测试
  - 消息去抖模块集成测试
- 总测试数：**395**（390 原有 + 5 新增），全部通过

---

## v3.4.0 — 赛博伴侣 3.4（MCP 工具 + 视觉识别 + 稳定性加固）

### 🔌 MCP 工具系统（新增）

赛博伴侣现在可以作为 MCP (Model Context Protocol) Client，连接外部 MCP Server 调用工具：

- **MCPClient** — JSON-RPC 2.0 over stdio 协议客户端，支持 initialize / tools/list / tools/call
- **MCPManager** — 多 Server 并行连接管理，工具名冲突自动命名空间前缀
- **稳定性加固** — 指数退避重连（1s→2s→⋯→60s）、分级超时（启动/操作/空闲）、心跳存活监控、16MB 缓冲区保护
- **结构化异常** — `MCPError` → `ConnectionError` / `TimeoutError` / `ProtocolError` / `ToolError`
- 配置文件：`config/mcp_servers.example.json` 模板
- LLM 可自动发现并调用 MCP 工具，结果自然融入对话

### 📷 双路径图片识别（新增）

- **路径A（多模态直传）**：主模型支持图片（GPT-4o、Claude 3.5 等）→ 直接发送图片
- **路径B（降级方案）**：主模型是纯文本（DeepSeek 等）→ 用户配置独立视觉模型 → 图片→描述文字→主模型
- 自动检测模型是否支持多模态（30+ 已知模型匹配）
- 配置：`settings.json` → `advanced.vision_model`（用户自行配置 API key）

### 🏗️ 架构优化

- **数据库连接统一** — 新增 `core/storage/db.py`，12 个模块改用 `open_db()` 统一连接管理，补全 `foreign_keys=ON`
- **SQLite 研究结论** — WAL 模式 + 单文件架构为最佳实践，当前 9 分离文件保留但推荐后续迁移
- **Commands 拆分** — `commands.py` (713行) → `commands/` 9 文件包，每文件 <160 行
- **Collector 简化** — `brain/collector.py` 498→445 行，删除 3 段旧 API 兼容代码
- **显示逻辑去重** — `core/chat/display.py` 共享 spinner/流式输出/欢迎语/统计
- **DebounceManager 提取** — `adapters/debounce.py` 独立模块
- **模块去重** — 删除 `core/identity.py` / `core/open_loop.py` / `core/summary.py`，统一到 `core/memory/` 包
- **配置常量化** — `DEFAULT_PERSONA_ID` 统一管理，14 个文件消除硬编码
- **包导出完善** — `core/multimodal/`、`core/tools/`、`core/storage/` 均完成 `__init__.py`

### 🧪 测试

- 总测试数：**390**（356 原有 + 34 稳定性新增）
- 集成连通性测试：23 项跨模块导入验证
- 稳定性边缘测试：MCP 崩溃恢复、空消息、多参数、超时、冲突检测
- 端到端烟雾测试：真实 DeepSeek LLM 调用通过

---

## v3.1.0 — 赛博伴侣 3.1（情感系统增强）

### ✨ 新功能
- **LLM 驱动亲密度系统** — 基于 LLM 理解对话情感变化自动调整亲密度
- **分段回复** — AI 回复自动按语义分段
- **ex-skill 人设导入工具** — 支持 `--dry-run` / `--force` 模式

### 🏗️ 改进
- 配置模板、项目重命名"赛博伴侣"、数据持久化升级

---

## v3.0.0 — 赛博伴侣 3.0

### 🧠 人格与记忆
- 五维人格模型 + 持久化、记忆冲突解析器、记忆衰减系统

### 🎭 情绪与关系
- 情绪增强、关系进化系统、Persona 漂移监控

### 🏗️ 架构升级
- 身份层（IdentityLayer）、开放式循环（OpenLoopEngine）、人生总结（LifeSummaryEngine）
- 消息总线：多平台消息去抖合并
- 工具系统：ToolRegistry 注册

---

## v2.0.0 — 赛博伴侣 2.0

- 模块化重构、语义向量记忆、8 种情感识别、适配器模式

---

## v1.0.0 — 赛博伴侣 1.0

- 纯 CMD 聊天模式、LiteLLM 多模型支持、记忆系统、人设系统

---

## v0.x — 赛博伴侣 早期版本

- 基础聊天、丰富人设数据模型、消息去抖、环境隔离安装
