"""
ex-skill 记忆与人设导入工具

用法：
  python import_exskill.py path/to/ex-skill/exes/xxx/    # 正常导入
  python import_exskill.py path/to/ex-skill/exes/xxx/ --dry-run  # 预览不写入
  python import_exskill.py path/to/ex-skill/exes/xxx/ --force     # 覆盖已有
"""

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

# 修复 Windows 控制台编码（GBK → UTF-8）
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

# 确保项目根目录在 sys.path 中（使 core 包可导入）
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# ---------- LLM JSON 解析 ----------

_JSON_BLOCK_RE = re.compile(r"```(?:json)?\s*\n(.*?)\n```", re.DOTALL)


def _parse_json(text: str):
    """从 LLM 响应中提取 JSON（支持 dict 和 list）

    与 core.utils.parse_json_response 不同（只返回 dict），
    此版本也支持 JSON 数组。
    """
    text = text.strip()
    if not text:
        return None

    match = _JSON_BLOCK_RE.search(text)
    if match:
        text = match.group(1).strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


# ---------- 参数解析 ----------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="导入 ex-skill 记忆与人设")
    parser.add_argument(
        "skill_dir",
        help="ex-skill 角色目录路径（包含 memory.md 和 persona.md）",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="预览模式，不写入数据库",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="覆盖已有导入",
    )
    return parser.parse_args()


# ---------- LLM ----------

def get_llm():
    """获取已配置的 LLM 实例（懒加载）"""
    from core.llm import get_llm as _get_llm
    from core.llm.registry import init_registry

    # 初始化 LLM 注册表（加载 settings.json 中的模型配置）
    config_path = ROOT / "config" / "settings.json"
    if config_path.exists():
        init_registry(config_path)

    return _get_llm()


# ---------- 记忆导入 ----------

async def import_memory(skill_dir: Path, dry_run: bool = False, force: bool = False) -> int:
    """读取 memory.md → LLM 转日记体 → 写入 memories.db

    Returns:
        导入的记忆条数
    """
    memory_path = skill_dir / "memory.md"
    if not memory_path.exists():
        print(f"  ⚠ 未找到 memory.md: {memory_path}")
        return 0

    content = memory_path.read_text(encoding="utf-8")
    print(f"  📖 读取 memory.md（{len(content)} 字符）")

    # 检测是否已导入过
    from core.memory.storage import MemoryStorage

    storage = MemoryStorage(str(ROOT / "data"))
    existing = [m for m in storage.load("girlfriend_001") if m.source == "imported"]
    if existing and not force and not dry_run:
        print(f"  ⚠ 已存在 {len(existing)} 条导入记忆，使用 --force 覆盖")
        return 0

    # LLM 转换 — 将 memory.md 转日记体
    llm = get_llm()
    today = datetime.now().strftime("%Y年%m月%d日")

    prompt = f"""你是一个日记转换助手。请将以下记忆内容转换为日记体第一人称格式。

要求：
- 每条记忆用「今天」开头或直接写日期，像写日记一样自然
- 记录发生了什么、你的感受
- 保留所有时间信息（日期、地点、人物）
- 每条 1-3 句话
- 返回 JSON 数组，每个元素包含 content（日记内容）和 importance（1-5）

当前日期：{today}

记忆内容：
{content}

只返回 JSON 数组，不要其他文字。"""

    print("  🤖 LLM 正在转换为日记格式...")
    response = await llm.chat(
        system_prompt=prompt,
        messages=[{"role": "user", "content": "请转换"}],
        max_tokens=4000,
        temperature=0.3,
    )

    diary_entries = _parse_json(response.content)

    # 降级方案：LLM 解析失败时按段落分割
    if not diary_entries or not isinstance(diary_entries, list):
        print("  ⚠ LLM 返回格式异常，尝试直接按段落分割...")
        paragraphs = [p.strip() for p in content.split("\n\n") if p.strip()]
        diary_entries = [{"content": p, "importance": 3} for p in paragraphs[:50]]

    if dry_run:
        print(f"\n  📝 [预览模式] 将导入 {len(diary_entries)} 条记忆：")
        for entry in diary_entries:
            preview = entry.get("content", "")[:60]
            imp = entry.get("importance", 3)
            print(f"    [重要度{imp}] {preview}...")
        return len(diary_entries)

    # 写入记忆库
    from core.memory.models import Memory

    imported_count = 0
    ts = datetime.now()
    for i, entry in enumerate(diary_entries):
        memory = Memory(
            id=f"imported_{ts.strftime('%Y%m%d%H%M%S')}_{i:04d}",
            content=entry.get("content", ""),
            level=min(5, max(1, int(entry.get("importance", 3)))),
            category="personal",
            created_at=ts.isoformat(),
            source="imported",
            confidence=0.9,
            tags=["ex-skill", "导入记忆"],
        )
        storage.add("girlfriend_001", memory)
        imported_count += 1

    print(f"\n  ✅ 已导入 {imported_count} 条记忆")
    return imported_count


# ---------- 人设导入 ----------

async def import_persona(skill_dir: Path, dry_run: bool = False, force: bool = False) -> bool:
    """读取 persona.md → LLM 提取 5 层结构 → 更新 personas.json

    Returns:
        是否成功
    """
    persona_path = skill_dir / "persona.md"
    if not persona_path.exists():
        print(f"  ⚠ 未找到 persona.md: {persona_path}")
        return False

    content = persona_path.read_text(encoding="utf-8")
    print(f"  📖 读取 persona.md（{len(content)} 字符）")

    llm = get_llm()

    prompt = f"""请从以下人设文件中提取角色信息，返回 JSON 格式。

要求提取以下字段（缺失则用空值）：
1. name: 角色名（字符串）
2. age: 年龄（整数）
3. personality: 性格标签（字符串数组，如 ["温柔", "活泼"]）
4. speaking_style: 说话风格（对象，包含说话量、语气、口头禅、示例对话等）
5. emotional_patterns: 情感模式（对象，包含依恋类型、表达方式、触发点等）
6. relationship_behavior: 关系行为（对象，包含争吵模式、日常互动、底线等）
7. hard_rules: 硬规则（字符串数组，不可违背的原则）
8. background: 背景描述（字符串）

只返回 JSON，不要其他文字。

人设文件内容：
{content[:10000]}"""

    print("  🤖 LLM 正在提取人设信息...")
    response = await llm.chat(
        system_prompt=prompt,
        messages=[{"role": "user", "content": "请提取人设"}],
        max_tokens=4000,
        temperature=0.1,
    )

    persona_data = _parse_json(response.content)

    if not persona_data or "name" not in persona_data:
        print("  ⚠ LLM 返回格式异常")
        print(f"     原始响应: {response.content[:200]}")
        return False

    if dry_run:
        print(f"\n  📝 [预览模式] 将更新人设：")
        print(f"    角色名: {persona_data.get('name')}")
        print(f"    年龄: {persona_data.get('age', '未知')}")
        print(f"    性格: {persona_data.get('personality', [])}")
        print(f"    硬规则: {len(persona_data.get('hard_rules', []))} 条")
        print(f"    说话风格: {'有' if persona_data.get('speaking_style') else '无'}")
        print(f"    情感模式: {'有' if persona_data.get('emotional_patterns') else '无'}")
        print(f"    关系行为: {'有' if persona_data.get('relationship_behavior') else '无'}")
        return True

    # 写入 personas.json
    from core.utils import atomic_write_json, read_json

    personas_path = ROOT / "config" / "personas.json"
    current = read_json(personas_path, default={"personas": []})

    new_name = persona_data.get("name", "小雨")
    existing_personas = current.get("personas", [])

    # 查找已有同 id 的 persona
    found = False
    for p in existing_personas:
        if p.get("id") == "girlfriend_001":
            if not force:
                print("  ⚠ 人设已存在，使用 --force 覆盖")
                return False
            # 保留基础字段，覆盖 5 层结构
            p["name"] = new_name
            if persona_data.get("age"):
                p["age"] = persona_data["age"]
            if persona_data.get("personality"):
                p["personality"] = persona_data["personality"]
            if persona_data.get("background"):
                p["background"] = persona_data["background"]
            for key in [
                "hard_rules",
                "speaking_style",
                "emotional_patterns",
                "relationship_behavior",
            ]:
                if key in persona_data and persona_data[key]:
                    p[key] = persona_data[key]
            # 映射 identity_anchor
            identity = {}
            if persona_data.get("mbti"):
                identity["mbti"] = persona_data["mbti"]
            if persona_data.get("gender"):
                identity["gender"] = persona_data["gender"]
            if persona_data.get("hometown"):
                identity["hometown"] = persona_data["hometown"]
            if identity:
                p["identity_anchor"] = identity
            found = True
            break

    if not found:
        new_persona = {
            "id": "girlfriend_001",
            "name": new_name,
            "age": persona_data.get("age", 20),
            "gender": persona_data.get("gender", "女"),
            "personality": persona_data.get("personality", ["温柔"]),
            "background": persona_data.get("background", ""),
            "hard_rules": persona_data.get("hard_rules", []),
            "speaking_style": persona_data.get("speaking_style", {}),
            "emotional_patterns": persona_data.get("emotional_patterns", {}),
            "relationship_behavior": persona_data.get("relationship_behavior", {}),
            "relationship_level": 50,
            "system_prompt": "",
        }
        identity = {}
        if persona_data.get("mbti"):
            identity["mbti"] = persona_data["mbti"]
        if persona_data.get("gender"):
            identity["gender"] = persona_data["gender"]
        if persona_data.get("hometown"):
            identity["hometown"] = persona_data["hometown"]
        if identity:
            new_persona["identity_anchor"] = identity
        current.setdefault("personas", []).append(new_persona)

    atomic_write_json(personas_path, current)
    print(f"  ✅ 人设已更新: {new_name}")
    return True


# ---------- 主流程 ----------

async def main() -> None:
    args = parse_args()
    skill_dir = Path(args.skill_dir).expanduser().resolve()

    if not skill_dir.exists():
        print(f"❌ 目录不存在: {skill_dir}")
        sys.exit(1)

    print(f"\n  🎯 导入 ex-skill 角色: {skill_dir.name}")
    print(f"  {'=' * 40}\n")

    if args.dry_run:
        print("  🔍 [预览模式] 仅展示不写入\n")

    memory_count = await import_memory(skill_dir, args.dry_run, args.force)
    persona_ok = await import_persona(skill_dir, args.dry_run, args.force)

    # 摘要
    print(f"\n  {'=' * 40}")
    print(f"  📊 导入摘要")
    print(f"  {'=' * 40}")
    if memory_count:
        print(f"    记忆: {memory_count} 条")
    else:
        print(f"    记忆: 0 条")
    print(f"    人设: {'✅ 成功' if persona_ok else '❌ 失败或跳过'}")

    if not args.dry_run and (memory_count or persona_ok):
        print(f"\n  💡 重启应用后生效")
    print()


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
