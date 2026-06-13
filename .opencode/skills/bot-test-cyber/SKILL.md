---
name: bot-test-cyber
description: Cyber Girlfriend 全链路质量测试 — 从环境搭建到 30+ 轮真实对话，覆盖所有功能模块，产出 Bug 清单和体检报告
argument-hint: [--mock-wechat]
version: 1.0.0
user-invocable: true
allowed-tools: Read, Write, Edit, Bash, Grep, Glob, Task, TodoWrite, Skill
---

# Cyber Girlfriend 全链路质量测试

## 你的角色

你现在是 Cyber Girlfriend 项目的**质量测试员 + 调试工程师**。

你的测试思路不是跑脚本——而是**以真实用户的身份**跟 AI 对话，像真人聊天一样自然地引出各项功能的测试点。

## 核心原则

```
用户视角 > 自动化脚本
发现问题 > 走过场
修好 Bug > 记下来就不管
一步步来 > 追求速度
```

---

## Phase 0: 出厂设置

### 0.1 清理数据
```bash
# 删除所有运行数据（保留 .env 里的 API Key 和 config/ 里用户配好的文件）
Remove-Item -Path "data\*.db" -Force -ErrorAction SilentlyContinue
Remove-Item -Path "data\*.json" -Force -ErrorAction SilentlyContinue
Remove-Item -Path "data\chat_history\*" -Force -ErrorAction SilentlyContinue
Write-Output "出厂设置完成 — 保留 .env 和 config/"
```

### 0.2 确认前置条件
```bash
python -c "import os; from dotenv import load_dotenv; load_dotenv(); assert os.getenv('DEEPSEEK_API_KEY'), 'API Key missing'"
print('前置条件 OK')
```

### 0.3 安装依赖
```bash
python install.py
```

### 0.4 配置向导
```bash
python main.py setup
```
测试点：
- 模型选择界面正常
- 人设配置支持"导入 skill 文件"模式
- 手动配置中的标签翻译功能（输入"嘴硬心软、粘人"看翻译）
- 高级参数默认值合理

### 0.5 验证安装
```bash
python -c "
from pathlib import Path
assert Path('config/settings.json').exists()
assert Path('config/personas.json').exists()
from core.llm.registry import init_registry
init_registry(Path('config/settings.json'))
from core.llm import get_llm
m = get_llm()
assert m.model_name
print('安装验证通过')
"
```

---

## Phase 1: CLI 基础对话（10 轮）

**目的**: 验证基础聊天 + 情绪分析 + 好感变化（以"木屿齐"身份自然聊天）

```
轮1: 你好呀 → AI 正常回复
轮2: 今天天气好，心情不错 → 正面情绪检测
轮3: （顺着AI回复聊）→ 上下文连贯
轮4: 我今天发工资了！超开心 → EXCITED + 好感↑
轮5: 我觉得你真的很懂我 → 验证好感递增
轮6: 哎，今天被老板骂了 → 负面情绪 + 好感↓
轮7: （看安慰效果）
轮8: 其实也没什么大事 → 情绪恢复
轮9: 我准备去吃饭了 → 日常闲聊
轮10: /stats → 命令正常
```

**检查点**:
- [ ] AI 能正常回复
- [ ] 正面消息后好感上升
- [ ] 负面消息后好感下降
- [ ] /stats 输出正常
- [ ] AI 不丢失上下文

---

## Phase 2: 记忆系统（10 轮）

**目的**: 验证记忆存储 + 自然回忆 + 日记体风格

```
轮11: 你知道吗，我特别喜欢重庆火锅
轮12: （顺着聊火锅）
轮13: 对了，我养了一只猫，叫咪咪
轮14: （聊猫的话题）
轮15: 我最近在学 Python，但进度好慢
轮16: （聊编程）
轮17: 你觉得我应该吃什么？ → 能想起火锅
轮18: 我家那个小祖宗又捣乱了 → 能想起猫
轮19: 学得好累，想放弃了 → 能想起学Python
轮20: /memories list → 日记体 + 重要度
```

**检查点**:
- [ ] AI 能自然回忆起之前的信息
- [ ] 不"背答案"（用自己的话回忆）
- [ ] /memories list 显示日记体记忆
- [ ] 记忆有重要度分级

---

## Phase 3: 好感系统 + 人格（10 轮）

**目的**: 验证好感递减 + 人格维度变化

```
轮21: 跟你聊天真的好开心 → 正面情绪
轮22: 我觉得我们越来越有默契了
轮23: （顺着聊）
轮24: 说实话，有你在真好 → 高亲密表现
轮25: /personality → 人格维度检查
轮26: 我今天遇到一个特别有意思的人 → jealousy测试
轮27: 骗你的，我只想跟你说话 → 好感递减观察
轮28: （继续自然聊天）
轮29: /stats dashboard → 仪表盘完整
轮30: /mood → 心情状态正常
```

**检查点**:
- [ ] 好感有涨有跌
- [ ] 接近100时增量变小（递减生效）
- [ ] /personality 5个维度
- [ ] trust/dependence有变化
- [ ] /stats dashboard 完整

---

## Phase 4: 命令系统

逐个验证：
```
/help        → 完整命令列表
/stats       → 好感+仪表盘
/mood        → 心情+情绪分布
/personality → 人格柱状图
/persona     → 人设信息
/debug       → system prompt
/memories    → 记忆管理
/undo        → 撤销
/regen       → 重新生成
/search      → 搜索
/export md   → Markdown导出
/clear       → 清空（确认后才执行）
/quit        → 退出
```

---

## Phase 5: 分段回复

测试长/短/中回复的分段效果：
- 长回复应被分段（逗号无残留）
- 短回复不应分段
- 段数 ≤ 6
- 段间延迟 0.8s

---

## Phase 6: 边缘情况

```
空消息          → 不回复不报错
纯表情 "😊😊😊"  → 正常处理
500+字长消息    → 不崩溃
特殊字符 "///"  → 正常处理
连发5条消息     → 去抖合并生效
```

---

## Phase 7: 报告

### 体检表
| 功能 | 状态 | 问题 |
|------|------|------|
| 环境搭建 | | |
| 设置向导 | | |
| 模型连接 | | |
| 基础对话 | | |
| 情绪检测 | | |
| 记忆存储 | | |
| 记忆回忆 | | |
| 日记体 | | |
| 好感变化 | | |
| 好感递减 | | |
| 人格更新 | | |
| 命令系统 | | |
| 分段回复 | | |
| 去抖合并 | | |
| 边缘情况 | | |

### Bug格式
```
Bug: [标题]
  复现: [步骤]
  实际: [发生了什么]
  期望: [应该怎样]
  文件: [影响模块]
  级别: 🔴严重/🟡中等/🟢轻微
```

## 规则

1. 发现Bug → 记下来，继续测
2. 测完统一修
3. 修完回归
4. 至少30轮对话
5. 以真人方式聊天
6. 用户视角：你是"木屿齐"
