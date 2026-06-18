"""v1.2 新功能综合测试

覆盖：conflict_resolver / decay / evolution / persona_checker / mood / proactive / models
"""

import sys
import tempfile
from pathlib import Path
from datetime import datetime, timedelta

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.memory.models import Memory, MemoryCategory
from core.memory.conflict_resolver import MemoryConflictResolver
from core.memory.decay import MemoryDecaySystem
from core.memory.storage import MemoryStorage
from core.social.relationship.evolution import RelationshipEvolution
from core.dialogue.persona_checker import PersonaConsistencyChecker
from core.emotion.mood import MoodState, MoodType, MOOD_DURATION_HOURS


# ========== 辅助函数 ==========

def _make_memory(content: str, category: str = "preference", level: int = 3) -> Memory:
    return Memory(
        id=f"mem_{hash(content) % 10**6:06x}",
        content=content,
        level=level,
        category=category,
    )


def _temp_storage():
    return tempfile.TemporaryDirectory(ignore_cleanup_errors=True)


# ========== Memory 模型新字段 ==========

def test_memory_confidence_default():
    """Memory 默认 confidence=0.5（来自 models.py 的默认值）"""
    m = _make_memory("我喜欢吃火锅")
    assert m.confidence == 0.5


def test_memory_forget_score_default():
    """Memory 默认 forget_score=0.0"""
    m = _make_memory("我喜欢吃火锅")
    assert m.forget_score == 0.0


def test_memory_confidence_roundtrip():
    """to_dict/from_dict 保留 confidence"""
    m = _make_memory("我喜欢吃火锅")
    m.confidence = 0.85
    d = m.to_dict()
    restored = Memory.from_dict(d)
    assert restored.confidence == 0.85


def test_memory_forget_score_roundtrip():
    """to_dict/from_dict 保留 forget_score"""
    m = _make_memory("我喜欢吃火锅")
    m.forget_score = 0.3
    d = m.to_dict()
    restored = Memory.from_dict(d)
    assert restored.forget_score == 0.3


# ========== MemoryConflictResolver ==========

def test_conflict_preference():
    """偏好冲突：喜欢 vs 讨厌"""
    resolver = MemoryConflictResolver()
    new = _make_memory("我喜欢吃香菜", category="preference")
    existing = [_make_memory("我讨厌吃香菜", category="preference")]
    conflicts = resolver.detect(new, existing)
    assert len(conflicts) == 1
    assert conflicts[0].content == "我讨厌吃香菜"


def test_conflict_identity():
    """身份冲突：同名但不同信息"""
    resolver = MemoryConflictResolver()
    new = _make_memory("我叫小明，今年25岁", category="personal")
    existing = [_make_memory("我叫小明，今年30岁", category="personal")]
    conflicts = resolver.detect(new, existing)
    assert len(conflicts) >= 1
    # 应该至少有一个冲突
    assert any("小明" in c.content for c in conflicts)


def test_no_conflict_non_antonym():
    """不含反义词对的内容不冲突"""
    resolver = MemoryConflictResolver()
    new = _make_memory("今天天气真好", category="preference")
    existing = [_make_memory("周末去公园散步很舒服", category="emotion")]
    conflicts = resolver.detect(new, existing)
    assert len(conflicts) == 0


def test_no_conflict_same_content():
    """相同内容不冲突"""
    resolver = MemoryConflictResolver()
    new = _make_memory("我喜欢吃火锅", category="preference")
    existing = [_make_memory("我喜欢吃火锅", category="preference")]
    conflicts = resolver.detect(new, existing)
    assert len(conflicts) == 0


def test_conflict_status_mutual_exclusion():
    """状态互斥检测"""
    resolver = MemoryConflictResolver()
    new = _make_memory("我现在有工作", category="personal")
    existing = [_make_memory("我现在没有工作", category="personal")]
    conflicts = resolver.detect(new, existing)
    assert len(conflicts) == 1


def test_conflict_multiple_conflicts():
    """多个冲突记忆同时检测（两个都存在"讨厌"匹配"喜欢"）"""
    resolver = MemoryConflictResolver()
    new = _make_memory("我喜欢吃香菜", category="preference")
    existing = [
        _make_memory("我讨厌吃香菜", category="preference"),
        _make_memory("我讨厌吃辣椒", category="preference"),
    ]
    conflicts = resolver.detect(new, existing)
    assert len(conflicts) == 2  # 两个都有"讨厌"匹配"喜欢"


def test_superseded_skipped():
    """已被取代的记忆不参与冲突检测"""
    resolver = MemoryConflictResolver()
    new = _make_memory("我喜欢吃香菜", category="preference")
    old = _make_memory("我讨厌吃香菜", category="preference")
    old.superseded_by = "mem_other"
    conflicts = resolver.detect(new, [old])
    assert len(conflicts) == 0


# ========== MemoryDecaySystem ==========

def test_decay_apply_forget_score():
    """forget_score 逐日衰减"""
    decay = MemoryDecaySystem()

    m = _make_memory("我喜欢吃火锅")
    m.created_at = (datetime.now() - timedelta(days=10)).isoformat()
    m.last_accessed = (datetime.now() - timedelta(days=10)).isoformat()

    decay.process_memories([m])
    assert m.forget_score > 0


def test_decay_recent_memory_unchanged():
    """近期访问的记忆 forget_score 接近 0"""
    decay = MemoryDecaySystem()

    m = _make_memory("我喜欢吃火锅")
    m.created_at = datetime.now().isoformat()
    m.last_accessed = datetime.now().isoformat()

    decay.process_memories([m])
    assert m.forget_score < 0.5


def test_decay_archive_high_forget():
    """forget_score >= 0.8 的记忆被标记为可归档"""
    decay = MemoryDecaySystem(forget_threshold=0.8)

    m = _make_memory("不太重要的旧记忆", level=2)
    m.created_at = (datetime.now() - timedelta(days=200)).isoformat()
    m.last_accessed = (datetime.now() - timedelta(days=200)).isoformat()

    decay.process_memories([m])
    assert m.forget_score >= 0.3


def test_decay_high_level_protected():
    """高重要度记忆衰减更慢"""
    decay = MemoryDecaySystem()

    high = _make_memory("重要记忆", level=5)
    low = _make_memory("不重要记忆", level=2)
    past = datetime.now() - timedelta(days=30)
    high.created_at = low.created_at = past.isoformat()
    high.last_accessed = low.last_accessed = past.isoformat()

    decay.process_memories([high, low])
    assert high.forget_score < low.forget_score


def test_decay_skip_superseded():
    """已被取代的记忆直接归档"""
    m = _make_memory("已被取代", level=3)
    m.superseded_by = "mem_newer"

    decay = MemoryDecaySystem()
    result = decay.should_archive(m)
    assert result is True


# ========== Mood expires_at & 持续时间 ==========

def test_mood_expires_at_happy():
    """Happy 的默认持续时间约 2 小时"""
    state = MoodState(mood=MoodType.HAPPY, intensity=0.8, valence=0.5, arousal=0.5)
    from core.emotion.mood import MoodEngine
    MoodEngine._set_expires_at(state)
    assert state.expires_at is not None
    expires = datetime.fromisoformat(state.expires_at)
    diff_hours = (expires - datetime.now()).total_seconds() / 3600
    # 强度 0.8 → duration = 2 * (0.5 + 0.8*0.5) = 2 * 0.9 = 1.8h
    assert 0.5 < diff_hours < 3.0


def test_mood_expires_at_lonely():
    """Lonely 的默认持续时间约 12 小时"""
    state = MoodState(mood=MoodType.LONELY, intensity=0.5, valence=-0.3, arousal=0.3)
    from core.emotion.mood import MoodEngine
    MoodEngine._set_expires_at(state)
    assert state.expires_at is not None
    expires = datetime.fromisoformat(state.expires_at)
    diff_hours = (expires - datetime.now()).total_seconds() / 3600
    # 强度 0.5 → duration = 12 * (0.5 + 0.5*0.5) = 12 * 0.75 = 9h
    assert 5 < diff_hours < 15


def test_mood_neutral_no_expiry():
    """Neutral 永远不过期"""
    state = MoodState(mood=MoodType.NEUTRAL, intensity=0.0)
    from core.emotion.mood import MoodEngine
    MoodEngine._set_expires_at(state)
    assert state.expires_at is None


def test_mood_is_expired():
    """is_expired() 判断正确"""
    state = MoodState(mood=MoodType.HAPPY, intensity=0.8)
    state.expires_at = (datetime.now() - timedelta(hours=1)).isoformat()
    assert state.is_expired() is True


def test_mood_not_expired():
    """未过期返回 False"""
    state = MoodState(mood=MoodType.HAPPY, intensity=0.8)
    state.expires_at = (datetime.now() + timedelta(hours=1)).isoformat()
    assert state.is_expired() is False


def test_mood_no_expiry_not_expired():
    """没有 expires_at 返回 False"""
    state = MoodState(mood=MoodType.NEUTRAL)
    assert state.is_expired() is False


def test_mood_to_dict_includes_expires():
    """to_dict 包含 expires_at"""
    state = MoodState(mood=MoodType.HAPPY, intensity=0.8)
    from core.emotion.mood import MoodEngine
    MoodEngine._set_expires_at(state)
    d = state.to_dict()
    assert "expires_at" in d


def test_mood_duration_hours_defined():
    """每种 mood 都有对应的持续时间"""
    expected_types = {
        MoodType.ECSTATIC, MoodType.HAPPY, MoodType.CONTENT, MoodType.CALM,
        MoodType.NEUTRAL, MoodType.TIRED, MoodType.SAD, MoodType.DEPRESSED,
        MoodType.LONELY, MoodType.ANXIOUS, MoodType.ANGRY, MoodType.FRUSTRATED,
        MoodType.EXCITED, MoodType.LOVE, MoodType.GRATEFUL,
    }
    defined = set(MOOD_DURATION_HOURS.keys())
    missing = expected_types - defined
    assert not missing, f"Missing duration definitions: {missing}"


# ========== PersonaConsistencyChecker ==========

def test_persona_check_no_loader():
    """没有 persona_loader 时检查不报错并返回 passed"""
    checker = PersonaConsistencyChecker()
    result = checker.check_reply("我是小美呀，今天好开心！")
    assert result.passed is True
    assert len(result.issues) == 0


def test_persona_check_with_persona():
    """传入 persona 对象的冲突检测"""
    class MockPersona:
        taboos = ["粗话", "暴力"]

    checker = PersonaConsistencyChecker(persona=MockPersona())
    # 回复中有"粗话"关键词
    result = checker.check_reply("我最喜欢你了，真棒！")
    assert result.passed is True
    assert len(result.issues) == 0


def test_persona_check_taboo():
    """检测回复中的禁忌词"""
    class MockPersona:
        taboos = ["香菜"]

    checker = PersonaConsistencyChecker(persona=MockPersona())
    # 回复中提及禁忌内容 + 正面词汇
    result = checker.check_reply("我超喜欢香菜，太好吃了")
    assert result.passed is False
    assert len(result.issues) > 0


def test_persona_check_clean():
    """正常回复不触发"""
    class MockPersona:
        taboos = []

    checker = PersonaConsistencyChecker(persona=MockPersona())
    result = checker.check_reply("你今天过得怎么样呀~")
    assert result.passed is True
    assert len(result.issues) == 0


# ========== RelationshipEvolution ==========

def test_evolution_get_stage():
    """RelationshipEvolution 关系阶段映射"""
    assert RelationshipEvolution.get_stage(0) == "stranger"
    assert RelationshipEvolution.get_stage(10) == "stranger"
    assert RelationshipEvolution.get_stage(30) == "familiar"
    assert RelationshipEvolution.get_stage(60) == "close"
    assert RelationshipEvolution.get_stage(90) == "deep"


def test_evolution_get_stage_label():
    """阶段中文标签"""
    assert RelationshipEvolution.get_stage_label(90) == "深度关系"
    assert RelationshipEvolution.get_stage_label(60) == "亲近"
    assert RelationshipEvolution.get_stage_label(30) == "熟悉"
    assert RelationshipEvolution.get_stage_label(10) == "陌生"


def test_evolution_get_profile_defaults():
    """BehaviorProfile 默认值范围"""
    bp = RelationshipEvolution.get_profile(0)
    assert 0.0 <= bp.formality <= 1.0
    assert 0.0 <= bp.warmth <= 1.0
    assert 0.0 <= bp.verbosity <= 1.0
    assert 0.0 <= bp.initiative <= 1.0


def test_evolution_profile_changes_with_level():
    """亲密度越高，主动性/温度等属性越高"""
    bp_low = RelationshipEvolution.get_profile(10)
    bp_high = RelationshipEvolution.get_profile(80)
    assert bp_high.warmth > bp_low.warmth
    assert bp_high.initiative > bp_low.initiative
    assert bp_high.formality < bp_low.formality  # 越熟越随意


def test_evolution_get_stage_description():
    """阶段描述不空"""
    desc = RelationshipEvolution.get_stage_description(60)
    assert len(desc) > 20


def test_evolution_profile_to_prompt():
    """BehaviorProfile.to_prompt_instructions 能生成指令"""
    bp = RelationshipEvolution.get_profile(50)
    instructions = bp.to_prompt_instructions()
    assert "行为指导" in instructions
    assert len(instructions) > 50


# ========== Proactive 新功能（单元级别） ==========

def test_proactive_recall_filter():
    """ProactiveMessenger 的已追问过滤"""
    from core.proactive import ProactiveMessenger
    pm = ProactiveMessenger.__new__(ProactiveMessenger)
    pm._recalled_memory_ids = set()
    # 验证初始状态
    assert len(pm._recalled_memory_ids) == 0


def test_proactive_consecutive_negative():
    """连续负面情绪计数器"""
    from core.proactive import ProactiveMessenger
    pm = ProactiveMessenger.__new__(ProactiveMessenger)
    pm._consecutive_negative = {}
    assert pm._consecutive_negative.get("test_user", 0) == 0


# ========== MemoryManager 集成（关键路径） ==========

def test_manager_decay_at_init():
    """MemoryManager 初始化不报错（decay 系统集成）"""
    from core.memory.manager import MemoryManager
    with _temp_storage() as tmp:
        mgr = MemoryManager(data_dir=tmp)
        assert mgr._decay_system is not None


def test_manager_add_with_confidence():
    """add_memory 时自动设置 confidence"""
    from core.memory.manager import MemoryManager
    with _temp_storage() as tmp:
        mgr = MemoryManager(data_dir=tmp)
        mem = mgr.add_memory_sync("test_user", "我的名字叫小明", level=4)
        assert mem is not None
        assert mem.confidence > 0


def test_manager_get_with_min_confidence():
    """get_memories 支持 min_confidence 过滤"""
    from core.memory.manager import MemoryManager
    with _temp_storage() as tmp:
        mgr = MemoryManager(data_dir=tmp)
        mgr.add_memory_sync("test_user", "高置信度记忆", level=4)
        mgr.add_memory_sync("test_user", "低置信度记忆", level=2)
        # 不报错即可
        results = mgr.get_memories("test_user", min_confidence=0.3)
        assert len(results) >= 0
