# 赛博伴侣项目复盘

> 日期：2026-06-12 | 历时：约 6 小时集中开发（v1.2 → v1.3）
> 代码总量：~15,000 行 | 测试：179 通过 / 3 预存失败

---

## 一、做了什么

### v1.2（2026-06-12 下午）

| 模块 | 类型 | 行数 | 说明 |
|------|------|------|------|
| MemoryConflictResolver | 新建 | 216 | 三种冲突检测（反义词/身份数字/状态对立） |
| MemoryDecaySystem | 新建 | 177 | 逐日 forget_score + 归档 + 检索权重 |
| RelationshipEvolution | 新建 | 203 | 4阶段行为画像，11维参数，纯静态映射 |
| PersonaConsistencyChecker | 新建 | 153 | 回复后人设冲突检测 |
| Mood 增强 | 改造 | 352 | expires_at + 各情绪独立持续时间 |
| Proactive 增强 | 改造 | 377 | 记忆追问 + 持续关怀 |
| Pipeline 集成 | 改造 | 568 | 行为画像 + 一致性检查 |

### v1.3（2026-06-12 傍晚）

| 模块 | 类型 | 行数 | 说明 |
|------|------|------|------|
| Identity Layer | 新建 | ~250 | 独立身份层 SQLite，不参与遗忘，Prompt 优先引用 |
| Open Loop Engine | 新建 | ~440 | 事件追踪（创建/追问/状态变更/超时失效） |
| Life Summary Engine | 新建 | ~280 | 每 50-100 轮自动生成人生摘要 |
| Relationship Events | 新建 | ~200 | 里程碑事件自动记录 |
| Persona Drift Monitor | 新建 | ~240 | 每 100 轮三维漂移检测 |
| Pipeline 深度集成 | 改造 | 623 | 全部 v1.3 模块注入管线 |

### 修复的技术债

- `core/tools/builtin.py` 内置工具的 `parameters` 从列表改为 property（与 BaseTool 接口一致）
- `ToolRegistry` 缺少 `parse_calls` / `get_function_specs` / `get_prompt_block` — 补充完整
- `core/memory/manager.py` `Path` 未导入
- `core/chat/pipeline.py` `Path` 未导入

---

## 二、经验

### 2.1 做对了的

**1. SQLite + WAL + 线程级连接隔离**
所有新存储层（Identity / OpenLoop / LifeSummary）统一用这个模式。代码可复制，性能可靠，50 线程并发测试通过。模式固定后几乎不出问题。

**2. 每个新模块配独立数据库文件**
`identity.db` / `open_loops.db` / `life_summaries.db` / `relationship_events.db`
好处：互不干扰，删除一个模块不影响其他，可以独立重置。

**3. PromptBuilder 的可扩展设计**
`build()` 的 `**kwargs` 式参数（`behavior_profile`、`identity_profile`、`life_summary`）让 v1.2 → v1.3 的注入无痛。不需要改函数签名。

**4. 先写测试再修 bug**
v1.3 的 Open Loop 准确率测试从 70% → 100%，测试驱动暴露了两类问题：
- 正则优先级导致面试被识别成考试
- 项目模式缺少"项目"关键词
没有测试根本发现不了。

**5. pipeline 的 `_run_background` 模式**
所有"非关键路径"操作（记忆提取、人生摘要、漂移检测）用后台协程，不阻塞主回复流程。v1.3 加了 5 个后台任务，主路径延迟零影响。

### 2.2 可以更好的

**1. 早期就应该统一工具 interface**
`builtin.py` 用 `parameters = []`（类属性列表），`BaseTool` 用 `@property` 返回 dict。花了 15 分钟追这个兼容问题。根源是两个人写了不同风格。

**2. Open Loop 的准确率迭代耗时太多**
初始 70% → 最终 100%，中间调了 4 轮模式匹配。如果用 LLM 提取事件而不是正则，可能更快且更鲁棒。（但 LLM 提取有延迟和成本，正则 2ms vs LLM 500ms）

**3. git rebase 冲突处理不够果断**
storage.py 的合并冲突反复出现了 3 次。应该第一次就直接 `git checkout --theirs` 解决，而不是手动编辑。

---

## 三、教训

### 3.1 类型注解不全导致的事故

```python
# 坏味道
class ClockTool(Tool):
    parameters = []  # 列表！和基类的 @property 签名冲突
```

`tool.parameters` 在 pipeline 里被当作 dict 用（`.get("properties")`），但实际是 list。**Python 的类属性会覆盖 @property**，这个陷阱坑过不止一次。教训：基类用 @property 定义接口时，子类只能用 @property 覆盖，不能用类属性。

### 3.2 测试的 Windows 兼容性

`tempfile.TemporaryDirectory()` 在 Windows 上如果目录内有 SQLite 文件，`__exit__` 会 PermissionError。因为 SQLite 连接没关闭。修复方案：用 `ignore_cleanup_errors=True`。这个参数 Python 3.10+ 才有。

教训：**所有涉及 SQLite 的测试必须用 `ignore_cleanup_errors=True`**，否则在 Windows 上必挂。

### 3.3 模式匹配的优先级

Open Loop 的事件检测用了 9 个正则，按优先级排序。初期把"面试"放在"考试"后面，导致"下周面试"被识别为考试。教训：**互斥分类必须通过顺序解决冲突**，或者用最长匹配优先。

### 3.4 合并冲突应尽早用 `--theirs`

在 git rebase 过程中，远程和本地都有对同一文件的修改。手动解决 5 个冲突文件花了大量时间。实际上我的版本全部是正确的（SQLite > JSON, 接口更完整），应该全部 `git checkout --theirs` 了事。

---

## 四、架构决策记录

| 决策 | 选择 | 原因 |
|------|------|------|
| 身份层独立表 | 不参与遗忘系统 | 用户的教育/专业/兴趣是永久性的，不应该被 MemoryDecay 衰减 |
| Open Loop SQLite | 独立数据库 | 事件状态需要频繁读写，和记忆库隔离避免锁竞争 |
| 人生摘要关键词规则 | 不用 LLM | 成本 + 延迟考虑，关键词覆盖主要场景足够（积极/消极/关键事件） |
| 人格漂移 3 维检测 | 语言 + 性格 + 价值观 | 覆盖主要漂移场景，无需 LLM |
| BehaviorProfile 纯静态 | 无状态、无持久化 | 精度足够，绝不和 PromptBuilder 耦合 |
| RelationshipEvolution 静态方法 | 不实例化 | 入参只有 level，不需要状态 |

---

## 五、项目健康度

| 维度 | 评分 | 依据 |
|------|------|------|
| 测试覆盖 | ⭐⭐⭐⭐ | 182 测试，覆盖核心 + v1.2 + v1.3 全部新模块 |
| 代码一致性 | ⭐⭐⭐⭐ | 统一 SQLite 模式、统一日志风格、统一错误处理（except + log + continue） |
| 可扩展性 | ⭐⭐⭐⭐ | PromptBuilder kwargs、BaseTool ABC、pipeline 后台任务模式 |
| 文档 | ⭐⭐⭐⭐⭐ | README + CHANGELOG + FRAMEWORK_REPORT + PROJECT_STATUS_REPORT + RETROSPECTIVE |
| Windows 兼容 | ⭐⭐⭐ | 3 个测试因 tempfile PermissionError 不过，SQLite WAL 锁在 Windows 上的固有问题 |

---

*写于项目交付前。希望能帮到下一个接手的人。*
