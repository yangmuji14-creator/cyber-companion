# Changelog

## v3.3.1 — 2026-06-22（🛠️ 项目加固 + 全功能用户测试）

### ✨ 新功能

- **模型列表实时拉取** — 配置向导 Step 1 输入 API Key 后，自动从厂商 API 拉取可用模型列表供用户选择（支持 DeepSeek / OpenAI / Gemini / 通义千问 / Kimi / 智谱）
- **启动依赖检查** — `main.py` 启动前自动检测关键依赖是否安装，缺失时给出友好提示
- **`import-skill` 命令** — 新增 `python main.py import-skill <路径>` 独立导入 ex-skill 人设
- **`install.py --dev` 标志** — 安装开发依赖（pytest 等）
- **uv 自动检测** — `install.py` 自动检测系统是否安装 uv，使用 uv 安装（64 包 23s）或回退 pip

### 🔧 改进

- **setup.py → setup_wizard.py** — 重命名避免与 pip 打包脚本混淆
- **TAG_TRANSLATION 抽离** — 性格标签翻译表从代码移至 `config/persona_tags.json`
- **`pyproject.toml`** — 新增项目元数据 + pytest 配置
- **`requirements-dev.txt`** — 分离开发依赖
- **`requirements.txt` 补全** — 加入 `sentence-transformers`（可选）
- **`import_exskill.py`** — 添加 `run_import()` 函数供 main.py 调用

### 🐛 修复

- **settings.json 缺少 `models` 段** → LLMRegistry 找不到模型，"没有可用的模型"
- **`_prompt_int` 空值不返回默认** → 死循环消耗后续 stdin 输入
- **`input()` 无 EOF 保护** — 修复 `install.py`、`setup_wizard.py`、`main.py` 中所有 `input()` 调用在非交互模式下的 EOFError
- **`install.py` 非交互崩溃** — 所有交互提示添加 try/except EOFError
- **`main.py` 无 `.env` 路径崩溃** — 友好提示不再 traceback
- **`auto_test.py` 硬编码路径** → 动态 `Path(__file__).parent`

### 🧪 测试

- 332/332 单元测试通过（+ 31/31 大脑自测）
- 全功能用户视角测试（7 阶段 30+ 项）覆盖：环境安装 → 配置向导 → 启动聊天 → 15 个斜杠命令 → 边界异常 → 其他入口

## v3.3.0 — 2026-06-18（🧠 内心独白大脑系统）

### 🧠 大脑模块（全新）

AI 伴侣现在拥有**自主内心思考**能力，在回复用户前先进行完整的内心独白编织：

- **StateCollector** — 从 14 个子系统（情绪/人格/亲密度/身份/人生总结/主动行为/时间环境等）收集当前状态，所有子系统可选，缺失静默降级
- **ThoughtOrganizer** — 将 BrainInput 多维状态转换为多条 `MonologueThought` 内心思绪碎片（feeling/memory/intention/observation/concern）
- **MonologueWeaver** — 将碎片融合为第一人称连贯内心独白叙事，支持多段结构，配以 LLM 驱动的叙事衔接
- **MemoryTrigger** — 三种主动回忆触发：关键词匹配、用户负面情绪触发、随机自发回忆（10%概率），让 AI 仿佛真的"想起"了往事
- **CharacterBreakDetector** — 检测回复是否偏离角色设定（性格/亲密方式/人设），自动报警提示
- **BrainCoordinator** — 统一编排[收集→触发→组织→编织→检查]完整流程，pipeline 中单次调用即可

### 🔧 集成与命令

- **pipeline 集成** — 在对话处理流程中自动触发大脑模块，输出注入 system prompt
- **`/stats` 增强** — 输出中附带大脑叙事统计（来源、片段数）
- **配置开关** — `brain_enabled` / `brain_max_tokens` / `brain_debug` / `checker_enabled`

### 🧪 测试

- `tests/test_brain.py` — 644 行单元测试（含集成测试）
- `tests/test_brain_edge.py` — 925 行边缘情况测试（41 个极端场景）
- `core/brain/self_test.py` — 509 行内置自测套件，可独立运行验证

## v3.2.0 — 2026-06-18（代码结构重构）

### 🏗️ 架构优化

- **包扁平化** — core/summary/, core/open_loop/, core/identity/ 从单文件包展平为直接文件
- **模块分组** — affection + relationship 合并为 core/social/ 子包
- **清理死代码** — 删除未使用的 core/state/，AIMoodManager 移至 core/emotion/
- **修复 memory 导出** — 移除 OpenLoopEngine/IdentityLayer/LifeSummaryEngine 从 core.memory 的错误导出
- **app.py 解耦** — 引入 ComponentBuilder 按领域分组组件创建
- **测试分目录** — tests/ 下按模块分 social/ chat/ memory/ 子目录
- **修复 3 处 None 安全** — pipeline.py 中 _topic_tracker/_dialogue_thinker 判空保护

### ✅ 验证
- 4 轮全链路回归测试通过，0 回归 Bug
- 好感/记忆/命令/情绪分析/边缘情况全部正常

## v3.1.0 — 2026-06-14（情感系统增强）

### ✨ 新功能

- **LLM 驱动亲密度** — 新增 affection 模块，基于 LLM 理解对话情感变化自动调整亲密度
- **分段回复** — AI 回复支持逻辑分段，提升可读性
- **ex-skill 人设导入** — 支持导入 ex-skill 格式的外部人设数据

### 🐛 修复

- 更新 .gitignore 测试产物规则，防止证据文件再次上传

---

## 2026-06-13（v2.0 + v3.0 合并发布）

### 🏗️ v2.0 架构升级

- **模块化重构** — core/ 目录分离（chat, llm, memory, emotion, persona, relationship, dialogue, multimodal）
- **适配器模式** — 微信/CLI/API 统一接口（adapters/）
- **人设引擎** — 30+ 字段，PromptBuilder 8 模块生成
- **人格系统** — personality/ 独立模块
- **插件系统** — plugins/ 可扩展

### 🧠 v1.2 记忆与冲突管理

- **记忆冲突解析器** — Token 级别重叠检测 + 反义词冲突检测
- **记忆衰减系统** — 基于 forget_score 自动归档和清理
- **置信度评分** — memory.confidence 和 memory.forget_score 字段
- **Mood 过期机制** — 每种情绪独立 duration + expires_at

### 🎭 v1.3 人格与主动对话

- **身份层（IdentityLayer）** — 结构化角色身份建模（教育、兴趣、职业等）
- **开放式循环（OpenLoopEngine）** — AI 主动发起对话 + 智能 Follow-up
- **人生总结引擎（LifeSummaryEngine）** — 跨会话记忆聚合与自动更新
- **人格引擎** — 五维模型（trust/dependence/openness/jealousy）持久化
- **Persona 漂移监控** — 检测回复偏离人设并生成报告
- **行为画像** — behavior profile + persona consistency checker

### 🔧 修复

- 修复 async add_memory 未 await 导致记忆丢失
- 修复 ChatHandler 缺少必要参数导致启动失败
- 修复中文冲突检测误报（字符级 → Token 级）
- 修复 CLI 模式输入无法处理
- 修复微信回复阻塞事件循环
- 修复 pipeline 表达式作为语句，移除多余 wait_for
- 修复 MoodManager 重命名和置信度分类
- 修复代码审查问题：SeqMockLLM 重复、缺失 await、死代码

### 🚀 v3.0 多平台消息总线

- **消息去抖合并** — 多平台统一消息队列，3 秒去抖自动合并
- **多平台接入** — 支持同时接入微信/CLI，共享 AI 状态
- **移除 Windows .bat 脚本** — 统一使用 python 命令

### 📦 测试

- 86+ 个单元测试全部通过
- v1.2 测试套件（39 个测试）
- v1.3 测试套件（47 个测试）
- 压力和并发安全测试

---

## 2026-06-12（模块化重构 v1.0-v1.2）

### 🔄 重构

- **v1.0-v1.1 模块化** — 核心模块拆分，向量记忆升级，setup 增强
- **Merge 合并** — 合并对话/多模态远程分支与 v1.0-v1.2 重构

### ✨ 新功能

- **Mood 情绪系统** — 基于 14 种情绪的 2D valence-arousal 模型，跨会话持久化
- **对话层** — 独立 dialogue 模块，多轮对话管理
- **工具调用** — 内置工具系统（时间/天气/计算器），prompt-based 调用格式
- **混合记忆** — 关键词 + 向量语义双模式
- **集成测试** — 端到端 pipeline 测试
- **README 更新** — v2.0 架构/向量记忆/完整特性文档

---

## 2026-06-11（对话质量 + 多模态）

### ✨ 新功能

- **对话质量系统** — 对话评估和回复质量优化
- **多模态支持** — 图像处理和贴纸回复
- **情感/记忆增强** — v0.8.0 功能扩展

### 🐛 修复

- 适配 v0.8.0 API 变更，修复 4 个失败测试

### 📦 文档

- 添加项目框架报告 — 完整架构/模块/路线图

---

## 2026-06-10（v0.8.0 命令系统）

### ✨ 新功能

- **v0.8.0 命令系统** — 新增 `/undo`（撤销）、`/regen`（重新生成）、`/search`（搜索历史）、`/mood`（情绪状态）
- **智能化升级** — LLM 辅助情感分析 + 自动记忆提取 + 语义记忆检索
- **多消息 prompt 优化** — 连发消息的上下文理解
- **v0.3.0 代码质量** — UX 体验升级

### 🐛 修复

- **v0.7.0** — 修复 6 个关键 bug + 数据安全加固
- 修复情感匹配和 task 泄漏
- 修复空输入（直接回车）不再算作消息

### 📦 测试

- 75 个单元测试全部通过

---

## 2026-06-09（第二轮开发）

### ✨ 新功能

- **人设数据模型丰富化** — Persona 从 9 个字段扩展到 30+，支持身份细节、兴趣爱好、语言习惯、情绪模式、行为倾向、关系背景、沟通偏好
- **PromptBuilder 重写** — 按 8 个模块生成自然的角色描述（身份→性格→兴趣→语言→情绪→价值观→关系→话题），让 AI 真正"成为"角色
- **消息累积去抖** — 用户在倒计时期间可继续输入，新消息加入队列并重置倒计时，所有累积消息合并后一起发给模型
- **国内镜像安装** — install.py 自动尝试清华/阿里/中科大/官方源，失败自动切换
- **虚拟环境隔离** — 首次运行自动创建 .venv，不依赖系统 Python 环境
- **一键启动脚本** — start.sh（Linux/macOS），或直接 `python main.py` 启动

### 🐛 修复

- **消息重复打印** — logger.info 和 print 输出重复显示，改为 logger.debug
- **Ctrl+C traceback** — 优雅退出，不再显示丑陋的异常堆栈
- **queue.Empty 异常** — run_in_executor 包装异常的正确捕获
- **get_typing_delay AttributeError** — Python 缓存导致的方法找不到问题

### 🔧 改进

- setup.py 启动时检查 venv 环境
- main.py 入口增加 venv 环境警告
- 48 个单元测试全部通过

### 📦 依赖

- Python 3.11+
- 新增 `install.py` 作为环境安装入口

---

## 2026-06-08（重构）

### 🔄 重构

- 从多平台（微信/QQ/Telegram + WebUI）简化为纯 CMD 聊天模式
- 移除 FastAPI 服务模式和传输层

### ✨ 功能

- 项目骨架 + 大模型统一接入层（LiteLLM）
- 记忆系统（5级重要度评分 + JSON 存储 + LLM 辅助总结）
- 人设系统 + 交互式聊天
- 情感层（8种情感识别 + emoji 增强）
- 消息分段 + 消息去抖
- 关系亲密度动态计算
- WebUI 管理界面
- 36 个单元测试
