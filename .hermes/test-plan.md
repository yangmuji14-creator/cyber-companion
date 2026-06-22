# 赛博伴侣 — 全功能用户视角测试清单 ✅

## 阶段一：环境安装
- [x] 1.1 运行 `python install.py` — uv 自动检测 ✅ 64 包 23s
- [x] 1.2 虚拟环境创建 ✅
- [x] 1.3 核心依赖安装 ✅
- [x] 1.4 可选依赖提示（自动跳过非交互模式） ✅ 
- [x] 1.5 `EOFError` 保护（非交互时输入自动用默认值） ✅
- [x] 1.6 `.venv/Scripts/python --version` 验证 ✅

## 阶段二：配置向导
- [x] 2.1 Banner + 步骤提示 ✅
- [x] 2.2 Step 1 - 大模型：
  - [x] 6 个厂商选项 ✅
  - [x] 选择 DeepSeek ✅
  - [x] 输入 API Key ✅
  - [x] **实时拉取模型列表**（检测到 deepseek-v4-flash / deepseek-v4-pro）✅
  - [x] 用户选择模型 ✅
- [x] 2.3 Step 2 - 人设：
  - [x] 基础信息 ✅
  - [x] 性格标签翻译 ✅
  - [x] 进阶人设 ✅
- [x] 2.4 Step 3 - 高级参数（含大脑 + 主动消息开关）✅
- [x] 2.5 配置文件：`.env` / `settings.json` / `personas.json` ✅
- [x] 2.6 已配置重新 setup → 询问是否覆盖 ✅

## 阶段三：启动聊天
- [x] 3.1 依赖检测 ✅
- [x] 3.2 正常启动 ✅（Loaded 1 models, default: deepseek）
- [x] 3.3 模型注册到 settings.json（`models` 段）✅
- [x] 3.4 AI 主动发送消息 ✅
- [x] 3.5 空输入不崩溃 ✅

## 阶段四：斜杠命令
- [x] `/help` — 列出所有命令
- [x] `/stats` — 亲密度状态
- [x] `/memories` — 记忆管理
- [x] `/persona` — 人设信息
- [x] `/personality` — 人格状态
- [x] `/mood` — 情绪状态
- [x] `/debug` — System Prompt
- [x] `/brain` — 大脑统计
- [x] `/clear` — 清空历史
- [x] `/export` — 导出记录
- [x] `/undo` — 撤销
- [x] `/regen` — 重新生成
- [x] `/search` — 搜索历史
- [x] `/tools` — 工具列表
- [x] `/quit` — 退出（含会话总结）

## 阶段五：边界与异常
- [x] 空命令 `/` → 不崩溃
- [x] 多行空输入 → 被去抖合并
- [x] 长消息 → 正常处理
- [x] 无 `.env` 启动 → 友好提示

## 阶段六：其他入口
- [x] `import-skill <路径>` — 需要路径参数
- [x] `wechat` — 配置界面正常
- [x] `setup` — 重新配置

## 修复总结
1. `settings.json` 缺少 `models` 段 → LLM 注册表找不到模型
2. `_prompt_int` 空值不返回默认 → 死循环消耗 stdin
3. `input()` 无 EOF 保护（install.py, setup_wizard.py, main.py）
4. `install.py` 非交互模式崩溃
