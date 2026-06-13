# 🎀 Cyber Girlfriend — 赛博女友

纯终端（CMD）AI 伴侣聊天机器人。支持语义记忆、情感分析、丰富人设、动态亲密度、持续性情绪系统、工具调用、多平台接入。

> ⚠️ **推荐使用 Windows CMD（命令提示符）运行**
> PowerShell 可能存在 Unicode 编码问题导致 emoji 显示异常。
> macOS / Linux 终端无此限制。

## 快速开始

```cmd
:: 安装依赖
python install.py

:: 配置向导（模型选择 + 人设 + 参数）
python main.py setup

:: 开始聊天
python main.py
```

## 多平台接入

支持同时接入多个聊天平台，所有平台共享同一个 AI 状态（记忆/情绪/人格）：

```cmd
:: 配置微信（扫码登录）
python main.py wechat

:: 启动（自动检测并启动已配置的平台）
python main.py
```

**消息去抖合并**：无论从哪个平台发送消息，连续输入都会在 3 秒内自动合并后一起处理。

## 特性

### 🤖 6 种大模型支持
| 提供商 | 默认模型 | 特点 |
|--------|----------|------|
| DeepSeek | deepseek-chat | 国产便宜，推荐 |
| OpenAI | gpt-4o-mini | 需海外网络 |
| Gemini | gemini-2.0-flash | Google 免费额度 |
| 通义千问 | qwen-turbo | 阿里云国内快 |
| Kimi | moonshot-v1-8k | 长上下文 |
| 智谱 | glm-4-flash | 免费额度 |

### 🧠 语义记忆（v2.0）
关键词记忆 → 向量嵌入（BAAI/bge-small-zh-v1.5）
- 搜"宠物"能想起"喜欢猫"
- SQLite 存储，余弦相似度 Top-K
- 嵌入器不可用自动降级为关键词

### 🎭 持续性情绪引擎（v3.0–v3.5）
- 14 种情绪状态的 2D valence-arousal 模型
- 跨会话持久化（SQLite），随时间自然衰减
- **情绪表达系统**：mood 直接影响 AI 的语气、回复长度、句子风格、emoji 选择
- 精力条（energy）随时间变化，低精力时回复简短慵懒
- CoT 对话思考器辅助意图理解
- 颜文字/表情包自动适配 AI 情绪

### 💕 亲密度系统
- 正面/负面消息影响亲密度
- 动态衰减算法
- 5 档关系等级

### 🛠️ 工具调用（v2.5）
- AI 可调用工具获取实时信息（时间、天气、计算）
- 无需修改 LLM 接口，prompt-based 调用格式
- 执行结果自然融入对话

### 🧠 人格成长（v2.0）
- 五维人格模型（信任/依赖/开放/好感/醋意）
- 根据交互动态变化，跨会话持久化
- 影响聊天风格和情感倾向

### 🎀 30+ 字段人设
身份、性格、MBTI、爱好、语言习惯、情绪模式、行为倾向、关系背景…

### 📋 斜杠命令
```
/help       — 显示帮助
/stats      — 亲密度统计
/memories   — 记忆管理
/persona    — 人设信息
/personality— 人格状态
/mood       — 当前情绪状态
/debug      — 查看 system prompt
/clear      — 清空聊天历史
/export     — 导出聊天记录
/undo       — 撤销上一轮
/regen      — 重新生成回复
/search     — 搜索聊天历史
/tools      — 查看可用工具
/img        — 发送图片识别
/quit       — 退出
```

## 数据存储
- `data/memories.db` — SQLite 记忆库
- `data/vectors.db` — SQLite 向量库
- `data/moods.db` — 情绪状态持久化
- `data/personality.db` — 人格状态持久化
- `data/chat_history/` — 对话历史
- `data/relationships.json` — 亲密度持久化

## 配置说明
- `.env` — API Key 配置（从 `.env.example` 复制）
- `config/settings.json` — 高级参数（首次运行 `setup` 生成）
- `config/personas.json` — 人设数据（通过 `setup` 配置）
- 以上文件包含个人配置，不会提交到 git

## 测试
```bash
pytest tests -v
```

## 技术栈
Python 3.11+ / asyncio / LiteLLM / sentence-transformers / SQLite / numpy

## 项目由来
灵感来自 [My-Dream-Moments](https://github.com/iwyxdxl/My-Dream-Moments) 和 [ex-skill](https://github.com/therealXiaomanChu/ex-skill)。

## 作者
**yangmuji14**
