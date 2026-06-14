## v3.1.0 — 赛博伴侣 3.1（情感系统增强）

### ✨ 新功能
- **LLM 驱动亲密度系统** — 新增 `core/affection/` 模块，基于 LLM 理解对话情感变化自动调整亲密度，SQLite 持久化（WAL 模式，线程安全），自动从旧版 JSON 迁移
- **分段回复** — AI 回复自动按语义分段，提升长回复可读性
- **ex-skill 人设导入工具** — 新增 `import_exskill.py` CLI 工具，支持 `--dry-run` / `--force` 模式，LLM 自动转换记忆格式和人设结构

### 🏗️ 改进
- **配置模板** — 新增 `settings.example.json` 和 `personas.example.json` 供用户参考
- **项目重命名** — 项目中文名改为「赛博伴侣」
- **数据持久化升级** — 亲密度从 JSON 文件迁移至 SQLite，支持 WAL 模式并发读写

### 🚀 升级说明
- 旧版 JSON 亲密度数据首次运行自动迁移至 SQLite，无需手动操作

## v3.0.0 — 赛博伴侣 3.0

### 🧠 人格与记忆系统
- 人格引擎：五维人格模型（trust/dependence/openness/jealousy）+ 持久化
- 记忆冲突解析器：Token 级别重叠检测 + 反义词冲突检测
- 记忆衰减系统：基于 forget_score 自动归档
- 个性化引擎：behavior profile + persona consistency checker

### 🎭 情绪与关系
- 情绪增强：Mood 增加 expires_at 和每情绪独立 duration
- 关系进化系统：RelationshipEvolution 多阶段发展 + 里程碑事件
- Persona 漂移监控：检测人设一致性偏移

### 🏗️ 架构升级
- 身份层（IdentityLayer）：结构化角色身份建模
- 开放式循环（OpenLoopEngine）：主动发起对话 + Follow-up
- 人生总结引擎（LifeSummaryEngine）：跨会话记忆聚合
- 消息总线：多平台消息去抖合并 + 统一路由
- 工具系统：ClockTool 等内置工具 + ToolRegistry 注册

### 🔧 Bug 修复
- MoodManager 重命名和 memory 置信度分类修复
- 修复微信 reply_text 事件循环阻塞
- 修复 ChatPipeline 缺少 open_loop/identity/life_summary 参数
- 修复 memory add_memory 同步调用和冲突检测
- 修复 expression-as-statement 和多余的 wait_for
- 修复代码审查问题：SeqMockLLM 重复、缺失 await、死代码

### 🚀 改进
- 47 个 v1.3 测试 + 39 个 v1.2 测试，全部通过
- 86+ 个单元测试覆盖

## v2.0.0 — 赛博伴侣 2.0

### 🏗️ 架构升级
- 模块化重构：core/ 目录分离（chat, llm, memory, emotion, persona, relationship, dialogue, multimodal）
- 适配器模式：微信/CLI/API 统一接口（adapters/）
- 人设引擎：30+ 字段，PromptBuilder 8 模块生成
- 人格系统：personality/ 独立模块
- 插件系统：plugins/ 可扩展

### 🧠 记忆系统
- 语义向量记忆（BGE-small-zh, 512维）
- SQLite 向量存储 + Top-K 语义搜索
- 关键词评分 + LLM 评分双模式
- 冲突检测：Token 级别重叠 + 反义词检测

### 🎭 情感与关系
- 8 种情感识别（关键词 + LLM 两级分析）
- 情感轨迹追踪
- 动态亲密度系统
- Mood 日常情绪系统

### 🔧 Bug 修复
- 修复 async add_memory 未 await 导致记忆丢失
- 修复 ChatHandler 缺少必要参数导致启动失败
- 修复中文冲突检测误报（字符级 → Token 级）
- 修复 CLI 模式输入无法处理
- 修复微信回复阻塞事件循环
- 修复 pipeline 表达式作为语句
- 修复 asyncio.wait_for 多余包装

### 🚀 改进
- 移除 Windows .bat 脚本（易出错），统一使用 python 命令
- 国内镜像安装自动切换
- 虚拟环境自动隔离
- 86 个单元测试全部通过

### 💻 启动方式
```bash
python install.py        # 安装
python main.py setup     # 配置
python main.py           # 启动聊天
python main.py wechat    # 配置微信
```

## v1.0.0 — 赛博伴侣 1.0

### 🔄 重构
- 从多平台（微信/QQ/Telegram + WebUI）简化为纯 CMD 聊天模式
- 移除 FastAPI 服务模式和传输层，降低复杂度

### ✨ 功能
- 项目骨架 + 大模型统一接入层（LiteLLM，支持 DeepSeek/OpenAI/Gemini 等）
- 记忆系统（5级重要度评分 + JSON 存储 + LLM 辅助总结）
- 人设系统 + 交互式聊天
- 情感层（8种情感识别 + emoji 增强）
- 消息分段 + 消息去抖
- 关系亲密度动态计算
- WebUI 管理界面
- 36 个单元测试全部通过

## v0.8.0 — 赛博伴侣 0.8

### 🎮 新增命令
- `/undo` — 撤销上一轮对话
- `/regen` — 重新生成上一条 AI 回复
- `/search` — 搜索聊天历史（关键词高亮 + 上下文）
- `/mood` — 查看当前情绪状态分布

### 🧠 智能化升级
- LLM 辅助情感分析（两级分析：关键词 + LLM）
- 自动记忆提取（从对话中自动提取关键记忆）
- 语义记忆检索增强
- 多消息 prompt 优化 — 连发消息的上下文理解

### 🔧 Bug 修复
- v0.7.0：修复 6 个关键 bug + 数据安全加固
- 修复情感匹配和 task 泄漏
- 修复空输入（直接回车）不再算作消息

### 🚀 改进
- 代码质量修复 + UX 体验升级（v0.3.0）
- 75 个单元测试全部通过

## v0.2.0 — 赛博伴侣 0.2

### ✨ 基础功能
- 丰富人设数据模型（30+ 字段：身份、性格、MBTI、兴趣、语言习惯等）
- 消息累积去抖 — 连续输入 3 秒内自动合并
- 环境隔离 + 国内镜像安装（清华/阿里/中科大/官方源自动切换）
- 一键启动脚本（start.sh 或 python main.py）

### 🐛 修复
- 修复消息重复打印（logger.info + print 去重）
- Ctrl+C 优雅退出，不再显示 traceback
- 修复 queue.Empty 异常和 get_typing_delay AttributeError
- 重写消息累积去抖，修复倒计时和显示问题

### 📦 依赖
- Python 3.11+
- LiteLLM + sentence-transformers
- 新增 `install.py` 作为环境安装入口
