# 慕（Mu）项目后续改造执行方案

> 交接对象：DeepSeek Flash 或其他能力有限、需要明确步骤的代码模型  
> 项目目录：`C:\Users\30216\Desktop\cc\cyber-companion`  
> 项目名称：慕（Mu）  
> 产品文案：**慕，只是你夜航时偶遇的浮灯，它能温柔你回望的旧岸，却无法替你横渡真实的黎明。**

这不是产品介绍，而是一份可以直接执行的工程交接单。执行时必须按阶段推进，每完成一个阶段就运行该阶段的测试并记录结果。不要一次性重写整个后端，也不要为了换页面而改变已有接口的返回结构。

## 1. 执行规则

### 1.1 先读、后改

开始前先阅读：

```text
README.md
core/app.py
core/chat/pipeline.py
core/chat/context_builder.py
core/brain/runtime_context.py
core/memory/life_summary.py
core/storage/migrations.py
core/storage/backup.py
webui/server.py
webui/schema.py
webui/static/index.html
webui/static/modules/main.js
webui/static/modules/chat-stream.js
scripts/build_portable.py
packaging/README.md
```

然后执行：

```powershell
Set-Location C:\Users\30216\Desktop\cc\cyber-companion
git status --short
.venv\Scripts\python.exe -m pytest -q
```

工作树可能很脏，有旧日志、构建目录、测试临时目录和用户修改。脏工作树不等于可以覆盖或删除文件。

### 1.2 绝对禁止

- 不执行 `git reset --hard`、`git clean -fd`、`git checkout --` 或任何会覆盖用户改动的命令。
- 不直接删除 `data/`、SQLite 文件、JSON 历史、人设或配置。迁移必须先备份、再校验、再切换。
- 不把 API key、微信登录凭据、`config/secrets.dpapi`、`.env` 写进日志、前端响应、备份包或 Git。
- 不为了“单数据库”重写所有存储层；先保留兼容路径，再迁移。
- 不改变现有 API 的字段名、SSE 事件名和错误语义。需要扩展时只增加可选字段。
- 不让浏览器任意传入 `user_id` 以冒充其他用户。
- 不把文学化的 Brain Diary 全量塞入每次模型 Prompt。Diary 给用户阅读，模型只接收精简的结构化状态。
- 不只靠模型名称字符串判断多模态能力。
- 不使用在线 CDN 作为生产依赖。便携包必须包含本地静态资源。
- 不把所有逻辑塞进一个超大文件。保持 `ChatPipeline`、存储、模型适配、Web 路由、前端状态模块的边界。
- 不在没有测试的情况下宣称完成。每个阶段都要给出命令和结果。

### 1.3 处理冲突的顺序

若旧文档、代码和本文件不一致，以当前代码的实际行为为准；先补测试记录实际行为，再做兼容改造。本文件描述的是目标和约束，不是允许任意破坏现有行为的授权。

## 2. 当前基线

### 2.1 后端

- 语言和运行时：Python，核心链路为异步 `ChatPipeline`。
- Web：`aiohttp` 服务，静态 WebUI 位于 `webui/static/`。
- CLI、Web、微信适配器和外部 API 共用 `ChatPipeline`，回复逻辑只能在共享层修复。
- 主数据 SQLite：`data/companion.db`，当前 schema/user version 为 3。
- 仍有兼容 JSON：`data/chat_history/`、`data/conversations.json`、`config/personas.json`、`config/settings.json`。
- 已有备份实现：`core/storage/backup.py`。
- 已有能力：多账号、多角色、人设绑定会话、按 scope 隔离记忆、图片上传、视觉模型 fallback、语音转写、消息合并、SSE 流式回复、表情包、Brain runtime context、第一人称 LifeSummary 日记。

### 2.2 记忆隔离模型

现在的逻辑应保持为：

```text
外部 user_id + persona_id + conversation_id
        -> SHA-256
        -> scope_xxx
```

该 scope 应覆盖聊天历史、短期记忆、长期记忆、情绪、人格状态、亲密度、主动消息、Brain/runtime context、LifeSummary、`/regen`、`/memories`、`/clear`、`/undo` 和 `/export`。任何新增记忆表或缓存都必须带 scope 或可由 scope 唯一确定。

### 2.3 前端

当前前端是原生 HTML/CSS/ES Modules，主要文件：

```text
webui/static/index.html
webui/static/style.css
webui/static/modules/bootstrap.js
webui/static/modules/chat-stream.js
webui/static/modules/conversation-sidebar.js
webui/static/modules/diagnostics.js
webui/static/modules/main.js
webui/static/modules/memory-page.js
webui/static/modules/settings-panel.js
webui/static/modules/state.js
webui/static/modules/stickers.js
webui/static/modules/upload.js
webui/static/modules/wechat-accounts.js
```

用户对当前视觉效果不满意，因此可以重写页面和组件。视觉风格、颜色、排版、动效由执行模型自主设计，但下面的功能、数据契约和状态必须保留。

### 2.4 已有验证基线

最近一次完整验证为 782 个测试通过，SQLite `PRAGMA integrity_check` 为 `ok`，`PRAGMA user_version` 为 `3`，`/api/health` 返回 HTTP 200。修改后不能降低这条基线；若新增测试导致总数变化，必须说明原因。

## 3. 目标架构与不可破坏原则

```text
Web / CLI / 微信 / 外部 API
              |
              v
        ChatPipeline
          |       |
          |       +-- ContextBuilder -> 稳定 Prompt + 动态状态
          |
          +-- ConversationScope -> scope_id -> Storage/Memory
          |
          +-- ModelRouter -> text/vision/tools/stream/reasoning
          |
          +-- EventSink -> SSE / CLI / 微信适配器
```

1. `ChatPipeline` 是唯一的回复编排边界。Web 路由不能复制一份“简化版聊天逻辑”。
2. scope 在请求进入业务层时确定，并向下显式传递，不能由各模块自行猜测。
3. 结构化运行状态和用户可浏览的文学日记分离：`runtime_context` 可进入 Prompt；`Brain Diary` 只在 LifeSummary 页面展示，按低频 checkpoint 生成。
4. 同一 scope 内生成串行，不同 scope 之间允许并发。
5. 主模型、视觉模型、ASR 和工具能力均通过能力描述和路由器选择，不能写死某个供应商。
6. 所有用户数据操作都要能备份、恢复、校验和解释来源。
7. Web 页面刷新、断线、移动端尺寸变化都不能造成重复发送或布局溢出。

## 4. 优先级总表

| 优先级 | 工作 | 目的 | 完成标志 |
|---|---|---|---|
| P0 | scope 身份顺序修复 | 防止跨账号/会话/人设串记忆 | 隔离测试全通过 |
| P0 | scope 级并发锁和取消 | 防止回复乱序和重复写入 | 并发、regen、断开测试通过 |
| P0 | API/SSE 兼容测试 | 保证前端重写不破坏后端 | 契约测试固化 |
| P1 | 模型能力检测和图片/语音异步化 | 提升国内网络和多模型兼容性 | text/vision/ASR fallback 可验证 |
| P1 | 备份恢复和数据边界 | 降低安装、迁移、恢复门槛 | clean restore + checksum 通过 |
| P1 | Prompt 分层和缓存指标 | 提高缓存命中率并降低成本 | 指标可见，动态字段稳定 |
| P1 | Web 前端重写 | 改善安装后的首次使用和日常体验 | 三种 viewport + E2E 通过 |
| P2 | 跨平台便携包和 CI | 为 Windows 之外的平台铺路 | 三平台构建/冒烟记录 |

不要先做动画或换色。P0 失败时，视觉改造没有验收意义。

## 5. Phase 0：备份、环境和现状盘点

### 5.1 建立安全工作副本

```powershell
Set-Location C:\Users\30216\Desktop\cc\cyber-companion
New-Item -ItemType Directory -Force .handoff-backup | Out-Null
.venv\Scripts\python.exe -m main --help
.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider
```

如果 pytest 无法写系统临时目录：

```powershell
New-Item -ItemType Directory -Force .tmp-test | Out-Null
$env:TEMP = (Resolve-Path .tmp-test).Path
$env:TMP = (Resolve-Path .tmp-test).Path
.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider
```

记录 Python 版本、依赖版本、schema 版本、端口、当前 Git 状态。不要把 `.handoff-backup`、日志或用户数据加入发布包。

### 5.2 盘点输出

写入一个不含密钥的 `docs/implementation-log.md` 或任务评论：

- 基线测试命令和通过数量；
- 数据目录文件清单、大小、SHA-256；
- `PRAGMA integrity_check` 和 `user_version`；
- API 路由快照；
- 当前可用模型/provider；
- 当前前端构建/测试命令。

## 6. Phase 1：scope 安全、并发与幂等（P0）

### 6.1 修复 Web 身份计算顺序

当前边界问题位于 `webui/server.py` 约 1504、1508 行：先计算 scope，后允许 body 的 `user_id` 覆盖最终用户身份。改为：

1. 解析认证身份或可信会话身份。
2. 若 `conversation_id` 存在，读取会话记录；以会话绑定的 `user_id`、`persona_id` 为唯一来源。
3. 浏览器请求忽略或拒绝任意 body `user_id`；如果保留字段，仅用于兼容并校验必须相等。
4. 只有系统内部适配器（微信/CLI）可以提供外部用户 ID，并且要经过明确的 adapter context。
5. 确定最终 `user_id`、`persona_id`、`conversation_id` 后，再调用统一的 scope 计算函数。
6. 记录安全日志时只记录 hash/scope，不记录原始密钥或敏感消息。

伪代码：

```python
identity = identity_resolver.resolve(request, conversation_id)
scope_id = memory_scope(identity.user_id, identity.persona_id, identity.conversation_id)
pipeline.handle(..., scope_id=scope_id, identity=identity)
```

### 6.2 同一 scope 的生成锁

Debounce 只负责“等待几秒合并消息”，不是串行执行器。增加 `ScopeExecutionRegistry`（建议放在 `core/chat/` 或 `core/concurrency/`）：

- `dict[scope_id, asyncio.Lock]`；
- 同一 scope 的普通消息、`/regen`、记忆提取和主动消息通过同一锁；
- 不同 scope 不互相阻塞；
- 请求结束、取消或异常后释放锁；
- 对空闲锁做引用计数/TTL 清理，避免无限增长；
- 获取锁前支持取消，不能把已断开的客户端永久留在队列。

事件顺序必须是：用户消息持久化 -> 模型生成 -> assistant 消息持久化 -> 记忆/情绪后处理。不能先写 assistant 再补用户消息。

### 6.3 请求 ID、幂等和取消

每个发送请求生成 `request_id`（UUID）。请求记录至少包含 `request_id`、scope、创建时间、状态：`queued/running/completed/cancelled/failed`。

- 同一 scope + 同一 `request_id` 重试时返回已有结果，不重复调用模型。
- 客户端发送 `X-Request-ID` 时沿用并校验格式。
- SSE 断开后取消当前生成；如果 provider 不支持取消，停止向客户端发送并在后台安全收尾，不能留下半条 assistant 消息。
- `/regen` 必须锁住同一 scope，定位目标 assistant/user pair，生成新 request_id，不能和普通消息并行。

### 6.4 P0 测试

至少增加：

- 两个 user、两个 persona、两个 conversation 交叉读写，互相看不到记忆和历史；
- 伪造 body `user_id` 时被忽略或返回 403/400；
- 同一 scope 并发 10 个请求，结果按提交顺序落盘；
- 不同 scope 并发时总耗时接近并行而不是串行；
- `/regen` 与普通消息并发不会重复或乱序；
- SSE 客户端断开、重复 `request_id`、空回复、provider 超时。

## 7. Phase 2：数据库、JSON 边界和备份恢复（P1）

### 7.1 短期推荐：保守整合

暂时保留 `data/chat_history/` 和 `data/conversations.json` 的兼容格式，先做到：

- 所有 JSON 使用临时文件 + `os.replace` 原子写入；
- 写入前校验 schema，损坏时保留原文件并返回可读错误；
- backup 清单包含相对路径、字节数、SHA-256、消息数量、scope 数量、schema 版本；
- restore 先 `inspect`/dry-run，展示将覆盖的文件和版本，再显式确认；
- 恢复前自动创建时间戳快照；
- 恢复后执行 SQLite integrity check、JSON schema 校验和数量/顺序比对；
- 明确告诉用户 SQLite 和 JSON 目前不是一个跨文件事务。

### 7.2 长期方案：迁入 SQLite（不要一次性硬切）

设计迁移表：

```sql
conversations(id, user_id, persona_id, title, created_at, updated_at, archived)
messages(id, conversation_id, scope_id, role, content_json, request_id,
         created_at, sequence_no, status)
```

要求：

- 通过现有 `schema_migrations` 和 `PRAGMA user_version` 迁移；
- 旧 JSON 只迁移一次，保留原文件为只读备份；
- 迁移前后比较会话数量、消息数量、顺序、scope、persona 绑定和时间戳；
- 迁移失败自动回到旧读取路径，不删除原文件；
- 完成一个版本的兼容读取后，才能考虑停止写 JSON；
- 不把密钥或大型媒体 blob 塞进数据库，媒体保留文件并在消息中保存受控引用。

### 7.3 备份/恢复验收

备份必须覆盖：SQLite、JSON 配置、人设、对话、媒体引用、迁移版本；排除 API key、登录 token、日志、测试目录和缓存。恢复必须支持：

1. 上传 zip；
2. inspect 返回清单和校验结果；
3. 用户确认；
4. 创建现有数据快照；
5. 原子替换/事务提交；
6. 重启需要时返回明确状态；
7. health 和 integrity check 通过。

## 8. Phase 3：模型能力、图片、语音和网络降级（P1）

### 8.1 能力描述

在模型注册信息中增加统一能力字段，不再只检查模型名：

```json
{
  "model_key": "provider/model",
  "capabilities": {
    "text": true,
    "vision": false,
    "tools": false,
    "stream": true,
    "reasoning": false
  },
  "source": "provider_metadata|user_override|probe|heuristic",
  "last_checked_at": "2026-08-16T12:00:00Z"
}
```

能力来源优先级：用户手动覆盖 > provider metadata > 轻量 probe > 名称 heuristic。名称关键词只能作为最后 fallback，并在 UI 标注“推测”。自定义 OpenAI-compatible endpoint 也必须走同一结构。

### 8.2 图片识别路由

- 主模型 `vision=true`：将图片和文本一起发给主模型，等待正常文字流式回复。
- 主模型 `vision=false` 或请求失败：调用配置的视觉 fallback，得到描述后再将“用户原文 + 图片描述”交给主模型。
- 主模型和视觉模型都不可用：返回用户可理解的错误，保留文本消息，不伪造识别结果。
- 图片上传先完成校验（类型、大小、像素、病毒/路径穿越），生成临时引用；取消发送时删除临时文件。
- 不把 base64 图片重复塞进历史 Prompt；历史只保存安全的媒体元数据或摘要。

测试至少覆盖：多模态主模型、文本主模型 + 视觉 fallback、fallback 超时、空图片、超限图片、provider 只支持非流式视觉。

### 8.3 语音转写不得阻塞事件循环

`webui/server.py` 约 2596、2618、1752 行的 faster-whisper 加载/转写目前同步执行。改为 `asyncio.to_thread` 或受控线程池：

- 模型首次加载显示 `loading`，后续请求复用；
- 线程池有上限，不能每个请求创建新线程；
- ASR 缺失、模型下载失败、格式不支持时返回明确错误和文字输入降级；
- 聊天、SSE、微信状态接口在 ASR 工作时仍可响应；
- 前端具备录音、上传、转写中、取消、重试和手动编辑文字状态。

### 8.4 国内网络环境

- provider 请求设置连接、读取、总超时和指数退避；
- 不无限重试，不重复提交有副作用的工具调用；
- 区分 DNS、连接拒绝、认证失败、限流、超时和模型不存在；
- 日志记录 request_id、provider、耗时和错误类别，不记录 key/完整 prompt；
- UI 显示“检查设置/重试/导出诊断”操作，而不是直接展示 HTTP 500 或 `Connection refused`。

## 9. Phase 4：缓存命中率、Prompt 分层和记忆质量（P1）

### 9.1 Prompt 分层

`core/chat/context_builder.py` 当前已将稳定人设 Prompt 和动态上下文分开，继续保持：

```text
[稳定前缀]
系统规则 + 人设提示词 + 输出示例 + 工具定义（排序稳定）

[动态尾部]
当前会话历史 + 精简 runtime_context + 情绪/亲密度 + 稳定排序的记忆检索结果 + 当前用户消息
```

禁止将当前分钟、随机 ID、随机排序、每次变化的工具描述放入稳定前缀。时间改成“清晨/上午/下午/夜晚”等时间段，只有确有业务需要才发送精确时间。记忆按稳定规则排序（例如 relevance 降序、created_at 降序、id 升序）。

### 9.2 Brain Diary 与 runtime context

- Diary 继续保持第一人称、情绪化、可供用户翻阅的文学内容；这是产品体验，不能删掉或改成冷冰冰的 JSON。
- 每次回复只注入 80-300 token 左右的结构化 runtime context，字段例如 `mood`、`energy`、`unfinished_threads`、`relationship_state`。
- Diary 由 `LifeSummaryEngine.generate_diary()` 低频生成（首次约 10 次互动，之后约每 50 次），写入 SQLite `life_summaries`，按 persona/scope 查询。
- 不把整篇 Diary 当成稳定 Prompt 前缀；必要时只提取事实摘要，避免破坏缓存前缀。

### 9.3 指标和回归

每个 provider/model 统计：`prompt_tokens`、`completion_tokens`、`cache_read_tokens`、`cache_hit_ratio`、TTFT、总延迟、失败类别。指标可写本地脱敏日志并在诊断中心查看。增加固定 Prompt 回归测试，确保相同 persona/工具定义下前缀字节级稳定。

## 10. 后端 API 契约（前端必须遵守）

以下是当前路由清单。前端重写必须先调用 `/api/schema` 或对应接口确认字段，不得凭空发明另一套后端 URL。除非后端兼容地增加可选字段，否则不要改现有字段名。

### 10.1 通用约定

- 请求和响应默认 JSON，字符集 UTF-8。
- 所有写请求带 `X-Request-ID`；前端生成 UUID 并在重试时复用。
- 成功通常为 `{ "ok": true, ... }`；错误至少为 `{ "ok": false, "error": { "code": "...", "message": "...", "retryable": false, "request_id": "..." } }`。若旧接口字段不同，前端适配旧字段，不要破坏后端兼容。
- 不能把 API key 原文回显；设置接口只能返回 `configured: true`、掩码或哈希标识。
- `conversation_id`、`persona_id`、`account_id` 都当作不透明字符串处理，不在前端自行拼接 scope。

### 10.2 路由清单

```text
GET    /
GET    /api/schema
GET    /api/health
GET    /api/diagnostics
GET    /api/diagnostics/export

GET    /api/stickers
GET    /api/stickers/file/{pack}/{emotion}/{filename}
POST   /api/stickers/import

GET    /api/bootstrap/status
GET    /api/bootstrap/providers
POST   /api/bootstrap/test
POST   /api/bootstrap/models
POST   /api/bootstrap/complete
POST   /api/bootstrap/persona

GET    /api/settings
POST   /api/settings
GET    /api/about

POST   /api/backup
POST   /api/backup/inspect
GET    /api/restore/status
POST   /api/restore

GET    /api/model
POST   /api/model
POST   /api/model/provider
POST   /api/model/discover
DELETE /api/model/{model_key}

GET    /api/memory
GET    /api/memory/{memory_id}
DELETE /api/memory/{memory_id}

GET    /api/life_summary
GET    /api/life_summary/latest

GET    /api/vision/config
POST   /api/vision/config

GET    /api/history
DELETE /api/history/last

POST   /api/chat
POST   /api/upload/image
POST   /api/upload/voice

GET    /api/persona
GET    /api/persona/{persona_id}
GET    /api/persona/{persona_id}/advanced
POST   /api/persona/{persona_id}
POST   /api/persona
DELETE /api/persona/{persona_id}
POST   /api/persona/{persona_id}/avatar
DELETE /api/persona/{persona_id}/avatar

GET    /api/conversations
GET    /api/conversations/{conversation_id}
POST   /api/conversations
DELETE /api/conversations/{conversation_id}

GET    /api/wechat/accounts
POST   /api/wechat/accounts
DELETE /api/wechat/accounts/{account_id}
GET    /api/wechat/login/{account_id}/qrcode
POST   /api/wechat/logout/{account_id}
GET    /api/wechat/status/{account_id}
```

### 10.3 关键接口交互要求

#### Bootstrap

`GET /api/bootstrap/status` 返回首次运行、已配置 provider、是否有人设、是否需要重启等状态。首次引导顺序建议：检查运行环境 -> 配置 provider/key -> 拉取模型 -> 测试连接 -> 选择文本/视觉模型 -> 创建或导入人设 -> 完成。

`GET /api/bootstrap/providers` 返回 provider 的本地配置状态和能力。`POST /api/bootstrap/models` 或 `POST /api/model/discover` 拉取模型列表；UI 必须把“拉取模型”和“选择模型”分成两步，不能固定写死一个模型。网络失败时保留手动填写入口和重试按钮。

#### Chat

`POST /api/chat` 请求至少包含：

```json
{
  "conversation_id": "conversation-id",
  "persona_id": "persona-id",
  "message": "用户文本",
  "attachments": [],
  "request_id": "uuid",
  "regen_of": null
}
```

`conversation_id` 有值时以后端绑定为准，前端不得传任意 `user_id` 冒充身份。发送前显示 `batching`，请求建立后显示 `sending`，收到 token 后显示 `streaming`。`regen_of` 用于重新生成，不重复追加同一条用户消息。

#### Persona

人设编辑至少包含三个主要输入：系统提示词、输出示例、人设提示词。每个输入旁边用短说明解释用途，并提供默认示例；高级设置和“人设助手/快速自定义”可以单独做成插件式入口，不能强迫用户先填写 wxid。保存成功后刷新当前会话的人设快照，旧消息不被改写。

#### Memory/LifeSummary

`GET /api/memory` 必须带当前 `conversation_id` 或由后端从当前会话推导 scope。前端展示长期记忆的分类、重要度、置信度、来源和删除操作。`GET /api/life_summary` 展示第一人称文学日记；页面要明显区分“模型运行状态”和“我自己的心事/日记”，不可将两者混成一块。

#### Backup/Restore

备份按钮调用 `POST /api/backup`，下载 zip；恢复先调用 `POST /api/backup/inspect` 或 `GET /api/restore/status` 展示清单、版本和风险，再上传到 `POST /api/restore`。恢复期间显示不可重复点击的状态，完成后按接口提示刷新或重启。

#### Diagnostics/About

诊断中心显示服务、数据库、provider、视觉模型、ASR、磁盘和端口状态；每项提供可读建议。`GET /api/diagnostics/export` 下载脱敏报告。关于页显示名称“慕”、版本、数据目录、隐私说明、开源协议和项目地址，不暴露密钥。

## 11. SSE 流式协议和前端状态机

### 11.1 事件格式

`POST /api/chat` 返回 `text/event-stream`。每个事件为 `event: <name>` + `data: <JSON>` + 空行：

```text
event: token
data: {"token":"..."}

event: phase
data: {"name":"...","label":"..."}

event: reasoning
data: {"text":"..."}

event: tool_start
data: {"name":"..."}

event: tool_end
data: {"name":"...","success":true}

event: sticker
data: {"url":"..."}

event: done
data: {"reply":"...","level":50}

event: error
data: {"error":"..."}
```

允许增加 `request_id`、`usage`、`capabilities` 等可选字段，但不能删除上述已有事件或把 JSON 改成非结构化文本。

### 11.2 强制状态机

```text
idle
  -> batching       等待几秒合并连续输入
  -> sending        已提交请求，等待首事件
  -> streaming      收到 token
  -> tool_running   收到 tool_start，显示可折叠工具状态
  -> completed      收到 done
  -> failed         收到 error/网络断开且无法恢复
  -> cancelled      用户点击停止或切换会话
```

实现要求：

- 切换会话时取消待发送队列和当前 `AbortController`；
- “停止生成”发送取消信号并将消息标记为 cancelled；
- “重新生成”使用 `regen_of` 和新 request_id；
- “复制”只复制最终可见回复，不把隐藏 reasoning/tool payload 放入剪贴板；
- 思考和工具调用默认折叠，保留滚动中的进度光线/占位效果，但不能遮挡正文；
- 断线后显示“重试/复制已生成内容/导出诊断”，不自动重复提交有副作用请求；
- 页面刷新后从历史恢复已完成消息，不能根据旧表单再次发送；
- 空回复也要进入 completed 并显示可理解的空结果提示；
- 同一会话发送按钮、停止按钮和重试按钮的启用条件必须明确。

## 12. Web 前端重写规格（视觉由执行模型设计）

可以继续使用原生 ES Modules，也可以引入 React/Vue；如果引入框架，必须同步修改便携包构建，依赖全部本地化，不能使用 CDN。必须保留 `npm run test:web` 或等价的 jsdom/vitest 测试。

### 12.1 全局布局

建议采用清晰的应用壳：桌面端侧栏 + 主内容区，移动端改为抽屉/底部导航。设置页不能把“数据与隐私”等内容堆在页面底部，应使用分组导航或二级侧栏。每个网络操作都有 loading、成功、空、错误、重试状态；长文本、按钮和卡片在手机宽度不溢出。

### 12.2 聊天页

必须有：

- 会话侧栏：新建、删除、重命名、搜索、当前会话高亮；
- 当前人设名称和头像，切换人设时显示绑定关系；
- 用户/助手消息、时间、生成中占位、错误消息；
- 停止生成、重新生成、复制；
- reasoning/tool 默认折叠，点击展开；
- 图片选择、预览、移除、上传失败重试；
- 表情包面板和发送结果；
- 语音录音、上传、转写、编辑后发送；
- 消息合并等待状态，例如“正在整理这几条消息”；
- 服务停止、离线和首次配置空状态。

### 12.3 记忆页

- 当前 persona/conversation 标识；
- 长期记忆分类、搜索、重要度、置信度、来源、创建时间；
- 删除前确认，删除后可撤销或明确不可恢复；
- 第一人称 LifeSummary 日记时间线；
- 独立展示结构化 runtime state，说明它服务于回复生成而不是日记原文；
- 空状态要告诉用户何时会生成下一篇日记，而不是显示内部异常。

### 12.4 设置页

分组至少包括：人设、模型、图片识别、语音、主动消息、回复风格、对话节奏、微信账号、数据与应用、诊断、关于。

- 模型：拉取列表、选择主模型、选择视觉 fallback、测试连接、能力标签；
- 密钥：输入、保存、掩码，不回显；
- 人设：三个主要文本框 + 默认示例；人设助手作为小插件入口；
- 微信：账号列表、登录二维码、状态、退出、账号与 persona/conversation 绑定；
- 数据：备份、检查备份、恢复、数据目录、日志路径；
- 诊断：逐项状态、脱敏导出；
- 关于：慕的名称和文案、版本、协议、隐私说明。

### 12.5 前端模块边界

至少保留类似边界：`state`、`chat-stream`、`conversation-sidebar`、`memory-page`、`settings-panel`、`bootstrap`、`upload`、`stickers`、`wechat-accounts`、`diagnostics`。不要让页面组件直接修改 SQLite、推测 scope 或自己拼接 provider 请求。

## 13. 测试矩阵

### 13.1 后端单元/集成

- scope 计算和身份覆盖攻击；
- conversation/persona/user 隔离；
- scope 锁、取消、幂等、消息顺序；
- SQLite migration、JSON 原子写入、备份清单、restore dry-run；
- 模型能力 metadata/probe/override；
- 视觉主模型/fallback；
- ASR 在线程池，不阻塞事件循环；
- Prompt 稳定前缀、缓存字段和 runtime context 上限；
- API 错误映射和敏感信息脱敏。

### 13.2 Web 单元/E2E

用 vitest/jsdom 或现有等价工具测试：

- bootstrap 首次引导和拉取模型后选择；
- chat 状态机每个转换；
- SSE token/reasoning/tool/sticker/done/error 解析；
- 停止、重试、regen、切换会话、刷新恢复；
- 备份/恢复状态和错误；
- 图片、表情包、语音录音/转写；
- 设置页分组和密钥不回显。

### 13.3 浏览器和设备

启动服务后用 Playwright 或浏览器检查：桌面 1440x900、平板 1024x768、手机 390x844。检查首屏、滚动、长消息、图片预览、流式滚动、抽屉、设置页、无服务和窄屏溢出。控制台不能有未处理异常。

### 13.4 数据和服务验收命令

```powershell
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\python.exe -c "import sqlite3; c=sqlite3.connect('data/companion.db'); print(c.execute('PRAGMA integrity_check').fetchone()[0]); print(c.execute('PRAGMA user_version').fetchone()[0]); c.close()"
Invoke-WebRequest http://127.0.0.1:8000/api/health | Select-Object StatusCode,Content
npm run test:web
```

## 14. 便携包、跨平台和安装成功率

### 14.1 Windows 当前构建方式

构建器需要一个预先准备好的、自包含 runtime，不要把开发 `.venv` 直接当发布 Python：

```powershell
Set-Location C:\Users\30216\Desktop\cc\cyber-companion
.venv\Scripts\python.exe scripts/prepare_windows_runtime.py --output build/windows-runtime
.venv\Scripts\python.exe scripts/build_portable.py --runtime-dir build/windows-runtime --output dist --target-platform windows
.venv\Scripts\python.exe scripts/smoke_test_portable.py dist/Mu-4.3.0-portable.zip
```

### 14.2 ZIP 白名单和发布内容

ZIP 应包含程序代码、锁定依赖、本地前端静态资源、启动脚本、LICENSE、README、版本清单和运行时；必须排除：`.env`、API key、`config/secrets.dpapi`、日志、`data/` 用户数据、`.venv` 开发缓存、`node_modules`、`.pytest_cache`、`.tmp-*`、旧 build/dist。发布前生成 SHA-256。

### 14.3 用户体验要求

- 用户解压后双击启动脚本即可运行，不要求预装 Python、Git、Node.js；
- 端口被占用时自动选择可用端口并打开正确 URL；
- 启动失败显示中文可理解的原因和日志位置；
- 首次运行向导负责 provider、拉取模型、选择模型、人设和可选视觉/语音配置；
- 数据目录、日志目录和备份目录可查看；
- 退出时不残留后台进程；
- 安装/启动失败不会删除用户数据。

### 14.4 跨平台设计

把路径、进程、端口、打开浏览器、数据目录、文件锁抽象成 platform service。不要在业务层写死 Windows 路径或 `.cmd` 行为。后续 Linux/macOS 复用 Python 核心和前端静态资源，Android 只在未来增加宿主适配层，不提前把桌面系统调用塞进核心。

GitHub Actions 最终应在 Windows/Linux/macOS 构建并冒烟；每个平台先验证核心服务和 Web，再接平台专属打包。

## 15. 推荐提交顺序

每一步都单独提交或至少单独记录，便于 DeepSeek 出错时定位：

1. `test: baseline and API contract fixtures`
2. `fix: resolve identity before memory scope`
3. `feat: serialize generation per scope and add idempotency`
4. `test: concurrency cancellation and isolation`
5. `fix: atomic JSON writes and backup inspect/restore validation`
6. `feat: model capability registry and vision fallback`
7. `fix: move ASR work off event loop`
8. `perf: stabilize prompt prefix and add cache metrics`
9. `refactor: replace WebUI while preserving API/SSE`
10. `build: portable allowlist and cross-platform abstractions`
11. `test: browser, clean-machine, and release smoke tests`

不要在一个提交里同时改数据库、模型路由和全部页面。每次提交后运行最小相关测试，再周期性运行全量测试。

## 16. 最终验收清单

只有以下项目全部满足才算完成：

- [ ] 同一会话内消息不会乱序，不同会话仍能并发；
- [ ] 任意 user/persona/conversation 组合不能读到其他 scope 的记忆、情绪、亲密度或日记；
- [ ] Web 不能伪造 `user_id`；
- [ ] 停止、重新生成、断线、重复 request_id 都有确定结果；
- [ ] 主模型是否多模态由能力检测决定，文本模型能自动使用视觉 fallback；
- [ ] 语音转写不阻塞聊天和 SSE；
- [ ] 模型列表由拉取结果驱动，不固定单一模型；
- [ ] Prompt 稳定前缀可复用，动态状态集中在尾部，Diary 仍保留文学体验；
- [ ] 备份可 inspect、恢复可回滚，SQLite integrity check 为 `ok`；
- [ ] Web 聊天、记忆、设置、诊断、关于、备份、微信、图片、表情包、语音功能齐全；
- [ ] SSE 状态机和错误恢复覆盖完整；
- [ ] 桌面、平板、手机无明显溢出或控制台错误；
- [ ] 干净 Windows 机器无需 Python/Git/Node.js 可启动 ZIP；
- [ ] 发布包没有密钥、用户数据和开发缓存；
- [ ] 全量 pytest、Web 测试、浏览器检查、便携包 smoke test 均有记录。

## 17. 遇到错误时怎么做

1. 先保留错误现场：命令、request_id、完整 traceback（脱敏）、Git diff 和测试名称。
2. 判断是代码错误、环境/网络错误、已有脏数据还是测试假设过时。
3. 只做最小修复，补一个能复现问题的测试。
4. 如果涉及 schema，先备份并更新 migration，不直接改生产数据库。
5. 如果涉及 API，先保持旧响应兼容，再在文档中记录新增字段。
6. 连续三次无法确认原因时停止扩大改动，报告阻塞点和需要人工决定的选项；不要用删除数据或回滚用户修改来“修复”。

## 18. 给执行模型的最后提示

先修 P0 的数据隔离、并发和契约，再做模型/语音/图片，再做 Prompt 和缓存，最后重写 Web 视觉和便携包。页面可以有自己的风格，但必须把“慕”的气质、清晰的信息层级和可靠的状态反馈做出来；视觉自由不等于功能自由。每个阶段结束时报告：改了哪些文件、跑了哪些测试、还有哪些风险。完成前不要说“应该可以”，要给出可复现的命令和结果。
