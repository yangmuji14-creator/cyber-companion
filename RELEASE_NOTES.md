## v2.0.0 — 赛博女友 2.0

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
