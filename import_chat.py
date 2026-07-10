"""
聊天记录导入工具 — 从聊天记录中提取人设、说话风格和记忆

三阶段流程：
  1. 人设提取：LLM 分析目标发言者的所有消息，提取性格/年龄/背景
  2. 风格提取：LLM 分析语言模式，提取口头禅/emoji习惯/说话节奏
  3. 记忆导入：LLM 将聊天内容分段转为结构化记忆，写入记忆系统

支持的格式：
  - 微信导出格式：2024-01-01 12:00 用户名: 消息内容
  - 简单格式：name: message（每行一条）
  - JSON 数组：[{"role": "user", "content": "...", "timestamp": "..."}]

用法：
  python import_chat.py path/to/chat.txt --name 小可爱         # 指定目标名字
  python import_chat.py path/to/chat.txt --name 小可爱 --dry-run  # 预览不写入
  python main.py import-chat path/to/chat.txt --name 小可爱    # CLI 命令
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent

# ---- 聊天记录解析 ----

# 微信导出格式（两种变体）
WECHAT_PATTERN = re.compile(
    r"^(\d{4}[-/年]\d{1,2}[-/月]\d{1,2}[日]?)\s+"
    r"(\d{1,2}:\d{2}(?::\d{2})?)\s+"
    r"(.+?)[:：]\s*"
    r"(.+)$"
)

# 微信连续格式（每行一个发言人）
WECHAT_LINE_PATTERN = re.compile(
    r"^(\d{4}[-/]\d{1,2}[-/]\d{1,2}\s+\d{1,2}:\d{2}(?::\d{2})?)\s+(.+)$"
)

# 简单格式
SIMPLE_PATTERN = re.compile(r"^(.+?)[:：]\s*(.+)$")

# 系统消息过滤
SYSTEM_PATTERNS = [
    r"^\[图片\]", r"^\[文件\]", r"^\[语音\]", r"^\[视频\]",
    r"^\[表情\]", r"^\[位置\]", r"^\[名片\]", r"^\[链接\]",
    r"^\[红包\]", r"^\[转账\]", r"^\[小程序\]", r"^\[动画表情\]",
    r"^\[撤回了一条消息\]", r"^\[你撤回了一条消息\]",
    r"^<msg>", r"^<img", r"^<video", r"^<audio",
    r"^\[聊天记录\]", r"^\[分享\]", r"^\[引用\]",
    r"^以上是打招呼的内容", r"^你已添加了",
    r"^\d{4}年\d{1,2}月\d{1,2}日",  # 日期分隔线
]


def _is_system_message(content: str) -> bool:
    """判断是否为系统消息/媒体占位符"""
    for pattern in SYSTEM_PATTERNS:
        if re.match(pattern, content.strip()):
            return True
    return False


def parse_chat_file(file_path: str | Path) -> list[dict]:
    """解析聊天记录文件，返回消息列表

    每条消息: {"speaker": "名字", "content": "内容", "time": "时间或空"}

    自动检测格式：微信导出 / 简单 / JSON
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"文件不存在: {file_path}")

    raw = path.read_text(encoding="utf-8", errors="replace")
    return _parse_lines(raw)


def _parse_lines(text: str) -> list[dict]:
    """按行解析，自动检测格式"""
    lines = text.strip().splitlines()

    # 尝试 JSON
    first = lines[0].strip()
    if first.startswith("[") or first.startswith("{"):
        try:
            data = json.loads(text)
            if isinstance(data, list):
                result = []
                for m in data:
                    content = m.get("content", m.get("text", ""))
                    if _is_system_message(content):
                        continue
                    result.append({
                        "speaker": m.get("role", m.get("speaker", m.get("name", "?"))),
                        "content": content,
                        "time": m.get("timestamp", m.get("time", "")),
                    })
                return result
        except json.JSONDecodeError:
            pass

    # 检测格式：试匹配第一行看是哪种
    is_wechat_colon = bool(WECHAT_PATTERN.match(lines[0])) if lines else False
    is_wechat_line = bool(WECHAT_LINE_PATTERN.match(lines[0])) if lines else False
    is_simple = not is_wechat_colon and not is_wechat_line

    messages = []
    current_msg = None
    current_speaker = None  # 用于微信连续格式

    for line in lines:
        line = line.strip()
        if not line or _is_system_message(line):
            continue

        matched = False

        # 微信格式：时间 + 发送者: 内容
        m = WECHAT_PATTERN.match(line)
        if m:
            if current_msg:
                messages.append(current_msg)
            current_msg = {
                "speaker": m.group(3).strip(),
                "content": m.group(4).strip(),
                "time": f"{m.group(1)} {m.group(2)}",
            }
            matched = True

        # 微信连续格式：时间 + 发送者名（消息在下一行）
        if not matched:
            m = WECHAT_LINE_PATTERN.match(line)
            if m:
                current_speaker = m.group(2).strip()
                matched = True
                continue

        # 简单格式：名字: 消息
        if not matched:
            m = SIMPLE_PATTERN.match(line)
            if m:
                if current_msg:
                    messages.append(current_msg)
                current_msg = {
                    "speaker": m.group(1).strip(),
                    "content": m.group(2).strip(),
                    "time": "",
                }
                matched = True

        # 续行（多行消息）：微信连续格式中，跟在时间行后面的内容
        if not matched and current_speaker:
            current_msg = {
                "speaker": current_speaker,
                "content": line,
                "time": "",
            }
            matched = True

        # 其他续行
        if not matched and current_msg and not is_wechat_line:
            current_msg["content"] += "\n" + line

    if current_msg:
        messages.append(current_msg)

    return messages


def filter_by_speaker(messages: list[dict], speaker_name: str) -> tuple[list[str], list[str]]:
    """分离目标发言者的消息和其他人的消息

    Returns:
        (target_messages, other_messages) — 各有 content 的字符串列表
    """
    target = [m["content"] for m in messages if m["speaker"] == speaker_name]
    other = [m["content"] for m in messages if m["speaker"] != speaker_name]
    return target, other


# ---- LLM 初始化 ----

def _get_llm():
    """获取已配置的 LLM 实例"""
    from core.llm.registry import init_registry
    from core.llm import get_llm as _get

    config_path = ROOT / "config" / "settings.json"
    if config_path.exists():
        init_registry(config_path)
    return _get()


def _parse_json(text: str):
    """从 LLM 响应中提取 JSON"""
    text = text.strip()
    m = re.search(r"```(?:json)?\s*\n(.*?)\n```", text, re.DOTALL)
    if m:
        text = m.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


# ═══════════════════════════════════════════════════════════════
# 阶段 1：人设提取
# ═══════════════════════════════════════════════════════════════

async def extract_persona(
    target_msgs: list[str],
    other_msgs: list[str],
    target_name: str,
    dry_run: bool = False,
) -> dict | None:
    """从目标发言者的消息中提取人设信息

    Returns:
        persona dict 或 None
    """
    llm = _get_llm()

    # 采样：取前 200 条（太多 token 会超限）
    sample_target = target_msgs[:200]
    sample_other = other_msgs[:100]

    target_text = "\n".join(f"- {m[:120]}" for m in sample_target)
    other_text = "\n".join(f"- {m[:120]}" for m in sample_other)
    msg_count = len(target_msgs)

    prompt = (
        f"你是一个角色分析师。请从以下 {target_name} 的 {msg_count} 条聊天记录中，"
        f"提取这个人的核心人设特征。\n\n"
        f"=== {target_name} 发的消息（共 {len(sample_target)} 条样本）===\n"
        f"{target_text[:8000]}\n\n"
        f"=== 对话中其他人的消息（{len(sample_other)} 条样本，提供上下文）===\n"
        f"{other_text[:4000]}\n\n"
        f"请以 JSON 格式返回分析结果：\n\n"
        f'{{\n'
        f'  "name": "名字",\n'
        f'  "gender": "男/女/未知",\n'
        f'  "age_estimate": "年龄段描述",\n'
        f'  "personality": ["特质1", "特质2"],\n'
        f'  "mbti_guess": "推测的MBTI",\n'
        f'  "occupation_hints": "职业线索",\n'
        f'  "interests": ["兴趣1"],\n'
        f'  "background": "一句话背景描述",\n'
        f'  "speaking_style_base": "总体说话风格描述",\n'
        f'  "hard_rules": ["不可违背的行为规则1", "规则2"],\n'
        f'  "emotional_patterns": {{"依恋类型": "安全型/焦虑型/回避型/混乱型",\n'
        f'                        "压力反应": "压力大时的表现",\n'
        f'                        "爱的语言": "如何表达爱意"}},\n'
        f'  "relationship_behavior": {{"冲突模式": "生气时的表现",\n'
        f'                          "边界需求": "需要什么边界"}}\n'
        f'}}\n\n'
        f'重要：hard_rules 必须是具体行为规则而非形容词。\n'
        f'  ❌ 错误："很敏感"\n'
        f'  ✅ 正确："回消息慢了会反复看手机，超过30分钟会发\'你在干嘛？\'"\n'
        f'所有字段尽量从聊天记录中推断，缺失的填空值。\n'
        f"只输出 JSON。"
    )

    print(f"  🤖 阶段 1/3：分析 {msg_count} 条消息，提取人设...")
    response = await llm.chat(
        system_prompt=prompt,
        messages=[{"role": "user", "content": "请分析"}],
        max_tokens=2000,
        temperature=0.2,
    )

    result = _parse_json(response.content)
    if not result:
        print("  ⚠ LLM 返回格式异常，尝试重试...")
        return None

    if dry_run:
        print(f"\n  📝 [预览] 提取的人设：")
        for k, v in result.items():
            print(f"    {k}: {v}")
        return result

    return result


# ═══════════════════════════════════════════════════════════════
# 阶段 2：说话风格提取
# ═══════════════════════════════════════════════════════════════

async def extract_style(
    target_msgs: list[str],
    target_name: str,
    dry_run: bool = False,
) -> dict | None:
    """从目标发言者的消息中提取说话风格特征"""
    llm = _get_llm()

    # 统计基本特征（无需 LLM）
    msg_lengths = [len(m) for m in target_msgs]
    avg_len = sum(msg_lengths) / max(len(msg_lengths), 1)

    # emoji 统计
    emoji_pattern = re.compile(r"[\U0001F300-\U0001F9FF\u2600-\u27BF\uFE00-\uFEFF\u200D]")
    all_emojis = []
    for m in target_msgs:
        all_emojis.extend(emoji_pattern.findall(m))
    top_emojis = [e for e, _ in Counter(all_emojis).most_common(10)]

    # 标点习惯
    exclaim_count = sum(1 for m in target_msgs if m.endswith("!") or m.endswith("！"))
    question_count = sum(1 for m in target_msgs if m.endswith("?") or m.endswith("？"))
    ellipsis_count = sum(1 for m in target_msgs if "..." in m or "……" in m)
    total = len(target_msgs)

    # LLM 提取：口头禅、语气词、说话节奏
    sample = target_msgs[:150]
    sample_text = "\n".join(f"- {m}" for m in sample)

    prompt = (
        f"分析 {target_name} 的说话风格。以下是 {len(sample)} 条消息样本：\n\n"
        f"{sample_text[:6000]}\n\n"
        f"统计信息（辅助参考）：\n"
        f"- 平均消息长度：{avg_len:.0f} 字\n"
        f"- 感叹号结尾比例：{exclaim_count}/{total}\n"
        f"- 问号结尾比例：{question_count}/{total}\n"
        f"- 省略号使用比例：{ellipsis_count}/{total}\n"
        f"- 常用 emoji：{', '.join(top_emojis[:8]) if top_emojis else '无'}\n\n"
        f"以 JSON 格式返回：\n"
        f'{{\n'
        f'  "catchphrases": ["口头禅1", "口头禅2"],\n'
        f'  "filler_words": ["语气词1", "呢", "啦"],\n'
        f'  "emoji_habits": "emoji使用习惯描述",\n'
        f'  "message_style": "消息风格（短句/长句/混合）",\n'
        f'  "punctuation_habits": "标点习惯描述",\n'
        f'  "speech_rhythm": "说话节奏描述（快/慢/分段多）",\n'
        f'  "example_dialogs": [\n'
        f'    {{"scenario": "有人问她今天过得怎么样", "reply": ["她可能的回复1", "回复2"]}},\n'
        f'    {{"scenario": "有人很久没回消息", "reply": ["她可能的回复"]}},\n'
        f'    {{"scenario": "有人惹她生气了", "reply": ["她可能的回复"]}}\n'
        f'  ]\n'
        f'}}\n\n'
        f'example_dialogs 是三层示范对话：有人问她日常/有人冷落她/有人惹她生气。'
        f'每个场景给 2-4 条她可能会发的消息，要像她的真实口吻。\n'
        f"只输出 JSON。"
    )

    print(f"  🤖 阶段 2/3：分析 {len(target_msgs)} 条消息，提取说话风格...")
    response = await llm.chat(
        system_prompt=prompt,
        messages=[{"role": "user", "content": "请分析说话风格"}],
        max_tokens=1000,
        temperature=0.2,
    )

    result = _parse_json(response.content)
    if not result:
        print("  ⚠ LLM 返回格式异常")
        return None

    # 合并统计信息
    result["_stats"] = {
        "avg_message_length": round(avg_len, 1),
        "total_messages": total,
        "top_emojis": top_emojis[:5],
    }

    if dry_run:
        print(f"\n  📝 [预览] 提取的说话风格：")
        for k, v in result.items():
            if k != "_stats":
                print(f"    {k}: {v}")
        return result

    return result


# ═══════════════════════════════════════════════════════════════
# 阶段 3：记忆提取与导入
# ═══════════════════════════════════════════════════════════════

async def extract_and_import_memories(
    target_msgs: list[str],
    other_msgs: list[str],
    target_name: str,
    other_speaker: str = "对方",
    dry_run: bool = False,
    chunk_size: int = 30,
) -> int:
    """将聊天记录分段，LLM 转为结构化记忆，批量导入记忆系统

    Returns:
        导入的记忆条数
    """
    llm = _get_llm()
    total_imported = 0

    # 将消息按对话轮次分割（target + other 交替）
    # 简化处理：按 target_msgs 分批，每批带上最近的 other 消息做上下文
    batches = []
    for i in range(0, len(target_msgs), chunk_size):
        batch_target = target_msgs[i : i + chunk_size]
        # 取这个区间附近的 other 消息
        start_ratio = i / max(len(target_msgs), 1)
        other_start = int(start_ratio * len(other_msgs))
        batch_other = other_msgs[other_start : other_start + chunk_size]
        batches.append((batch_target, batch_other))

    print(f"  🤖 阶段 3/3：分 {len(batches)} 批提取记忆...")

    for batch_idx, (batch_target, batch_other) in enumerate(batches):
        target_text = "\n".join(f"{target_name}: {m}" for m in batch_target)
        other_text = "\n".join(f"{other_speaker}: {m}" for m in batch_other)
        combined = f"{other_text}\n{target_text}"

        prompt = (
            f"从以下对话中提取值得长期记住的信息。"
            f"每条记忆用第一人称写（以'{target_name}的视角'），"
            f"像写日记一样自然。\n\n"
            f"关注的类型：\n"
            f"- 个人信息（喜好、习惯、计划、经历）\n"
            f"- 关系时刻（约定、重要对话、情感表达）\n"
            f"- 趣事和日常（值得回忆的小事）\n\n"
            f"对话内容：\n{combined[:6000]}\n\n"
            f"以 JSON 数组格式返回，每项包含 content 和 importance(1-5)：\n"
            f'[{{"content": "日记体记忆内容", "importance": 3}}, ...]\n\n'
            f"只输出 JSON 数组。如果没有值得记住的内容，返回 []。"
        )

        print(f"    批次 {batch_idx + 1}/{len(batches)}...", end=" ", flush=True)
        response = await llm.chat(
            system_prompt=prompt,
            messages=[{"role": "user", "content": "请提取记忆"}],
            max_tokens=2000,
            temperature=0.3,
        )

        entries = _parse_json(response.content)
        if not entries or not isinstance(entries, list):
            print("⚠ 解析失败，跳过")
            continue

        if dry_run:
            print(f"预览 {len(entries)} 条")
            for e in entries[:3]:
                print(f"      [{e.get('importance', 3)}★] {e.get('content', '')[:60]}...")
            continue

        # 写入记忆系统
        imported = _write_memories(entries, source_tag=f"chat_import_{target_name}")
        total_imported += imported
        print(f"✓ {imported} 条")

    return total_imported


def _write_memories(entries: list[dict], source_tag: str = "chat_import") -> int:
    """将记忆条目写入记忆系统"""
    from core.memory.manager import MemoryManager
    from core.memory.models import Memory

    try:
        mgr = MemoryManager(str(ROOT / "data"))
    except Exception:
        # MemoryManager 在无 embedder 时会失败，降级为直接存储
        from core.memory.storage import MemoryStorage
        storage = MemoryStorage(str(ROOT / "data"))
        ts = datetime.now()
        imported = 0
        for i, entry in enumerate(entries):
            if not entry.get("content"):
                continue
            mem = Memory(
                id=f"{source_tag}_{ts.strftime('%Y%m%d%H%M%S')}_{i:04d}",
                content=entry["content"],
                level=min(5, max(1, int(entry.get("importance", 3)))),
                category="personal",
                created_at=ts.isoformat(),
                source=source_tag,
                confidence=0.85,
                tags=["聊天导入"],
            )
            storage.add("local_user", mem)
            imported += 1
        return imported

    imported = 0
    ts = datetime.now()
    for i, entry in enumerate(entries):
        if not entry.get("content"):
            continue
        mem = Memory(
            id=f"{source_tag}_{ts.strftime('%Y%m%d%H%M%S')}_{i:04d}",
            content=entry["content"],
            level=min(5, max(1, int(entry.get("importance", 3)))),
            category="personal",
            created_at=ts.isoformat(),
            source=source_tag,
            confidence=0.85,
            tags=["聊天导入"],
        )
        try:
            mgr.add_memory_sync("local_user", mem)
            imported += 1
        except Exception:
            continue

    return imported


# ═══════════════════════════════════════════════════════════════
# 主流程
# ═══════════════════════════════════════════════════════════════

async def run_import(
    chat_path: str,
    target_name: str,
    dry_run: bool = False,
    skip_persona: bool = False,
    skip_style: bool = False,
    skip_memories: bool = False,
) -> dict:
    """主导入流程

    Returns:
        导入结果摘要
    """
    print()
    print("=" * 50)
    print("  📥 聊天记录导入工具")
    print("=" * 50)
    print()

    # 解析聊天记录
    print(f"  📖 解析聊天记录: {chat_path}")
    messages = parse_chat_file(chat_path)
    speakers = Counter(m["speaker"] for m in messages)
    print(f"  ✅ 解析完成：{len(messages)} 条消息，{len(speakers)} 个发言者")
    for name, count in speakers.most_common():
        marker = " ← 目标" if name == target_name else ""
        print(f"    {name}: {count} 条{marker}")

    if target_name not in speakers:
        print(f"\n  ⚠ 未找到目标发言者「{target_name}」")
        print(f"  可用的发言者：{', '.join(speakers.keys())}")
        return {"error": f"speaker '{target_name}' not found"}

    target_msgs, other_msgs = filter_by_speaker(messages, target_name)
    print(f"\n  🎯 目标发言者「{target_name}」: {len(target_msgs)} 条消息")
    print(f"  👤 其他发言者: {len(other_msgs)} 条消息")

    result = {"messages_parsed": len(messages), "target_messages": len(target_msgs)}

    # ---- 阶段 1：人设提取 ----
    if not skip_persona:
        persona = await extract_persona(target_msgs, other_msgs, target_name, dry_run)
        if persona:
            result["persona"] = persona
            if not dry_run:
                _apply_persona(persona)

    # ---- 阶段 2：风格提取 ----
    if not skip_style:
        style = await extract_style(target_msgs, target_name, dry_run)
        if style:
            result["style"] = style
            if not dry_run:
                _apply_style(style, target_name)

    # ---- 阶段 3：记忆导入 ----
    if not skip_memories:
        other_name = [s for s in speakers.keys() if s != target_name][0] if len(speakers) > 1 else "对方"
        imported = await extract_and_import_memories(
            target_msgs, other_msgs, target_name, other_name, dry_run,
        )
        result["memories_imported"] = imported

    # 完成
    print()
    print("=" * 50)
    if dry_run:
        print("  ✅ 预览完成（未写入任何数据）")
    else:
        print("  ✅ 导入完成！")
    print("=" * 50)
    print()

    return result


def _apply_persona(persona: dict):
    """将提取的人设写入 personas.json"""
    from core.utils import read_json, atomic_write_json

    path = ROOT / "config" / "personas.json"
    current = read_json(path, default={"personas": []})
    personas = current.get("personas", [])

    # 查找或创建 girlfriend_001
    target = None
    for p in personas:
        if p.get("id") == "girlfriend_001":
            target = p
            break

    if not target:
        target = {
            "id": "girlfriend_001",
            "name": persona.get("name", "小雨"),
            "relationship_level": 50,
        }
        personas.append(target)

    # 合并人设字段
    if persona.get("name"):
        target["name"] = persona["name"]
    if persona.get("gender"):
        target["gender"] = persona["gender"]
    if persona.get("age_estimate"):
        target["age"] = persona.get("age_estimate", "")
    if persona.get("personality"):
        target["personality"] = persona["personality"]
    if persona.get("mbti_guess"):
        target["mbti"] = persona["mbti_guess"]
    if persona.get("interests"):
        target.setdefault("hobbies", [])
        for interest in persona["interests"]:
            if isinstance(interest, str):
                target["hobbies"].append({"name": interest})
    if persona.get("background"):
        target["background"] = persona["background"]
    if persona.get("hard_rules"):
        target["hard_rules"] = persona["hard_rules"]
    if persona.get("emotional_patterns"):
        target["emotional_patterns"] = persona["emotional_patterns"]
    if persona.get("relationship_behavior"):
        target["relationship_behavior"] = persona["relationship_behavior"]

    current["personas"] = personas
    atomic_write_json(path, current)
    print(f"  ✅ 人设已更新: {target.get('name', '?')}")


def _apply_style(style: dict, target_name: str):
    """将提取的说话风格写入 personas.json"""
    from core.utils import read_json, atomic_write_json

    path = ROOT / "config" / "personas.json"
    current = read_json(path, default={"personas": []})

    for p in current.get("personas", []):
        if p.get("id") == "girlfriend_001":
            if style.get("catchphrases"):
                p["catchphrases"] = style["catchphrases"]
            if style.get("filler_words"):
                p["filler_words"] = style["filler_words"]
            if style.get("emoji_habits"):
                p["emoji_habits"] = style["emoji_habits"]
            if style.get("speech_rhythm"):
                p["speech_rhythm"] = style["speech_rhythm"]
            if style.get("example_dialogs"):
                p["example_dialogs"] = style["example_dialogs"]

            # 更新 speaking_style
            speaking = p.get("speaking_style", {})
            if not isinstance(speaking, dict):
                speaking = {}
            if style.get("message_style"):
                speaking["基础风格"] = style["message_style"]
            if style.get("punctuation_habits"):
                speaking["标点习惯"] = style["punctuation_habits"]
            if speaking:
                p["speaking_style"] = speaking

            atomic_write_json(path, current)
            print(f"  ✅ 说话风格已更新: {len(style.get('catchphrases', []))} 个口头禅")
            return

    print("  ⚠ 未找到 girlfriend_001 人设，风格数据未写入")


# ---- CLI ----

def parse_args():
    parser = argparse.ArgumentParser(description="从聊天记录导入人设、风格和记忆")
    parser.add_argument("chat_file", help="聊天记录文件路径")
    parser.add_argument("--name", "-n", required=True, help="目标发言者的名字")
    parser.add_argument("--dry-run", action="store_true", help="预览模式，不写入数据")
    parser.add_argument("--skip-persona", action="store_true", help="跳过人设提取")
    parser.add_argument("--skip-style", action="store_true", help="跳过风格提取")
    parser.add_argument("--skip-memories", action="store_true", help="跳过记忆导入")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    try:
        asyncio.run(run_import(
            args.chat_file,
            args.name,
            dry_run=args.dry_run,
            skip_persona=args.skip_persona,
            skip_style=args.skip_style,
            skip_memories=args.skip_memories,
        ))
    except KeyboardInterrupt:
        print("\n\n  已取消\n")
    except Exception as e:
        print(f"\n  ❌ 导入失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
