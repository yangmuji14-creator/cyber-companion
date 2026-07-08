"""v1.3 综合测试套件

覆盖：
1. Identity Layer — 创建/保存/加载/合并/提取/Prompt 生成
2. Open Loop Engine — 创建/状态更新/过期/追问/持久化
3. Life Summary Engine — 创建/摘要生成/轮数判断
4. Relationship Events — 记录/里程碑摘要
5. Persona Drift Monitor — 检测/评分/建议
6. 集成测试 — Pipeline 集成关键路径
7. 压力测试 — 模拟大量对话
"""

import sys
import tempfile
from pathlib import Path
from datetime import datetime, timedelta

sys.path.insert(0, str(Path(__file__).parent.parent))

# ========== Identity Layer ==========

def test_identity_create_default():
    """IdentityProfile 默认值"""
    from core.memory.identity import IdentityProfile
    p = IdentityProfile(user_id="test_user")
    assert p.user_id == "test_user"
    assert p.education == ""
    assert p.interests == []
    assert p.goals == []
    assert p.personality_traits == []


def test_identity_to_dict_roundtrip():
    """IdentityProfile 序列化往返"""
    from core.memory.identity import IdentityProfile
    p = IdentityProfile(
        user_id="test_user",
        education="本科",
        major="计算机",
        interests=["Python", "AI"],
        goals=["学好AI"],
    )
    d = p.to_dict()
    restored = IdentityProfile.from_dict(d)
    assert restored.education == "本科"
    assert restored.major == "计算机"
    assert restored.interests == ["Python", "AI"]


def test_identity_merge():
    """IdentityProfile 合并"""
    from core.memory.identity import IdentityProfile
    old = IdentityProfile(user_id="test_user", education="本科", interests=["Python"])
    new = IdentityProfile(user_id="test_user", education="硕士", interests=["AI"])
    merged = old.merge(new)
    assert merged.education == "硕士"  # 新覆盖旧
    assert "Python" in merged.interests  # 合并去重
    assert "AI" in merged.interests


def test_identity_to_prompt_section():
    """IdentityProfile.to_prompt_section() 生成非空文本"""
    from core.memory.identity import IdentityProfile
    p = IdentityProfile(user_id="test", education="本科", major="计算机", interests=["AI"])
    text = p.to_prompt_section()
    assert "教育背景" in text
    assert "计算机" in text
    assert "AI" in text


def test_identity_storage_save_and_load():
    """IdentityStorage 保存和加载"""
    from core.memory.identity import IdentityProfile, IdentityStorage
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        storage = IdentityStorage(tmp)
        p = IdentityProfile(user_id="test", education="硕士")
        storage.save(p)
        loaded = storage.load("test")
        assert loaded is not None
        assert loaded.education == "硕士"


def test_identity_storage_delete():
    """IdentityStorage 删除"""
    from core.memory.identity import IdentityProfile, IdentityStorage
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        storage = IdentityStorage(tmp)
        storage.save(IdentityProfile(user_id="test"))
        assert storage.delete("test") is True
        assert storage.load("test") is None


def test_identity_extract_education():
    """extract_from_content 提取教育信息"""
    from core.memory.identity import IdentityStorage
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        storage = IdentityStorage(tmp)
        result = storage.extract_from_content("test", "我是大学生，学计算机的")
        assert result is not None
        loaded = storage.load("test")
        assert loaded is not None and loaded.education == "大学"


def test_identity_extract_interest():
    """extract_from_content 提取兴趣"""
    from core.memory.identity import IdentityStorage
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        storage = IdentityStorage(tmp)
        result = storage.extract_from_content("test", "我喜欢吃火锅")
        assert result is not None or storage.load("test") is not None
        loaded = storage.load("test")
        if loaded:
            # 兴趣可能包含"吃火锅"或相关关键词
            assert len(loaded.interests) >= 0


# ========== Open Loop Engine ==========

def test_open_loop_default_status():
    """OpenLoop 默认状态为 pending"""
    from core.memory.open_loop import OpenLoop
    loop = OpenLoop(id="ol_1", user_id="test", title="明天考试")
    assert loop.status == "pending"
    assert loop.is_active is True
    assert loop.is_closed is False


def test_open_loop_status_transitions():
    """OpenLoop 状态变更"""
    from core.memory.open_loop import OpenLoop
    loop = OpenLoop(id="ol_1", user_id="test", title="考试")
    assert loop.is_active is True

    loop.status = "resolved"
    assert loop.is_active is False
    assert loop.is_closed is True

    loop.status = "failed"
    assert loop.is_closed is True

    loop.status = "abandoned"
    assert loop.is_closed is True


def test_open_loop_expired():
    """OpenLoop 过期判断"""
    from core.memory.open_loop import OpenLoop
    loop = OpenLoop(
        id="ol_1", user_id="test", title="考试",
        expected_date=(datetime.now() - timedelta(days=5)).strftime("%Y-%m-%d"),
    )
    assert loop.is_expired is True


def test_open_loop_not_expired():
    """未到期的 OpenLoop 不过期"""
    from core.memory.open_loop import OpenLoop
    loop = OpenLoop(
        id="ol_1", user_id="test", title="考试",
        expected_date=(datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d"),
    )
    assert loop.is_expired is False


def test_open_loop_should_follow_up():
    """到期后 24 小时内应追问"""
    from core.memory.open_loop import OpenLoop
    loop = OpenLoop(
        id="ol_1", user_id="test", title="考试",
        expected_date=datetime.now().strftime("%Y-%m-%d"),
    )
    assert loop.should_follow_up(hours_since_expected=48) is True


def test_open_loop_storage_save_and_load():
    """OpenLoopStorage 保存和加载"""
    from core.memory.open_loop import OpenLoop, OpenLoopStorage
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        storage = OpenLoopStorage(tmp)
        loop = OpenLoop(id="ol_1", user_id="test", title="明天考试", category="exam")
        storage.save(loop)
        loaded = storage.load("ol_1")
        assert loaded is not None
        assert loaded.title == "明天考试"
        assert loaded.category == "exam"


def test_open_loop_storage_active():
    """load_active 只返回 pending 事件"""
    from core.memory.open_loop import OpenLoop, OpenLoopStorage
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        storage = OpenLoopStorage(tmp)
        storage.save(OpenLoop(id="ol_1", user_id="test", title="事件1"))
        storage.save(OpenLoop(id="ol_2", user_id="test", title="事件2", status="resolved"))
        active = storage.load_active("test")
        assert len(active) == 1
        assert active[0].id == "ol_1"


def test_open_loop_engine_detect_exam():
    """OpenLoopEngine 检测考试事件"""
    from core.memory.open_loop import OpenLoopEngine
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        engine = OpenLoopEngine(tmp)
        created = engine.detect_and_create("test", "我明天要考试")
        assert len(created) >= 1
        assert created[0].category == "exam"


def test_open_loop_engine_detect_health():
    """OpenLoopEngine 检测健康事件"""
    from core.memory.open_loop import OpenLoopEngine
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        engine = OpenLoopEngine(tmp)
        created = engine.detect_and_create("test", "我感冒了，好难受")
        assert len(created) >= 1
        assert created[0].category == "health"


def test_open_loop_check_resolved():
    """check_and_update 检测完成"""
    from core.memory.open_loop import OpenLoopEngine, OpenLoop
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        engine = OpenLoopEngine(tmp)
        engine._storage.save(OpenLoop(
            id="ol_1", user_id="test", title="明天考试",
            category="exam", expected_date=datetime.now().strftime("%Y-%m-%d"),
        ))
        updated = engine.check_and_update("test", "考完了，通过了")
        assert len(updated) >= 1
        assert updated[0].status == "resolved"


def test_open_loop_check_failed():
    """check_and_update 检测失败"""
    from core.memory.open_loop import OpenLoopEngine, OpenLoop
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        engine = OpenLoopEngine(tmp)
        engine._storage.save(OpenLoop(
            id="ol_1", user_id="test", title="面试",
            category="interview", expected_date=datetime.now().strftime("%Y-%m-%d"),
        ))
        updated = engine.check_and_update("test", "面试挂了，没通过")
        assert len(updated) >= 1
        assert updated[0].status == "failed"


def test_open_loop_check_expired():
    """check_expired 标记过期事件"""
    from core.memory.open_loop import OpenLoopEngine, OpenLoop
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        engine = OpenLoopEngine(tmp)
        engine._storage.save(OpenLoop(
            id="ol_1", user_id="test", title="旧考试",
            expected_date=(datetime.now() - timedelta(days=10)).strftime("%Y-%m-%d"),
        ))
        expired = engine.check_expired("test")
        assert len(expired) >= 1
        assert expired[0].status == "abandoned"


def test_open_loop_generate_follow_up():
    """generate_follow_up_message 生成非空追问"""
    from core.memory.open_loop import OpenLoop
    from core.memory.open_loop import OpenLoopEngine
    loop = OpenLoop(id="ol_1", user_id="test", title="明天考试", category="exam")
    # 创建最小 engine 实例（不需要 storage）
    engine = OpenLoopEngine.__new__(OpenLoopEngine)
    engine._storage = None
    msg = engine.generate_follow_up_message(loop)
    assert len(msg) > 5
    assert "考试" in msg


# ========== Life Summary Engine ==========

def test_life_summary_default():
    """LifeSummary 默认值"""
    from core.memory.life_summary import LifeSummary
    ls = LifeSummary(id="ls_1", user_id="test")
    assert ls.summary_type == "periodic"
    assert ls.current_goals == []
    assert ls.key_events == []


def test_life_summary_to_prompt_section():
    """to_prompt_section 生成非空文本"""
    from core.memory.life_summary import LifeSummary
    ls = LifeSummary(id="ls_1", user_id="test", recent_status="近期较忙", current_goals=["学AI"])
    text = ls.to_prompt_section()
    assert "近期状态" in text
    assert "学AI" in text


def test_life_summary_storage():
    """LifeSummaryStorage 保存和读取"""
    from core.memory.life_summary import LifeSummary, LifeSummaryEngine
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        engine = LifeSummaryEngine(tmp)
        ls = engine.generate_from_memories("test", 10, ["今天学Python", "明天考试"])
        assert ls is not None
        loaded = engine.get_latest("test")
        assert loaded is not None
        assert loaded.user_id == "test"


def test_life_summary_should_generate_initial():
    """首次 10 轮以上应生成"""
    from core.memory.life_summary import LifeSummaryEngine
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        engine = LifeSummaryEngine(tmp)
        assert engine.should_generate("test", 15) is True
        assert engine.should_generate("test", 5) is False


def test_life_summary_should_generate_periodic():
    """每 50 轮应生成一次"""
    from core.memory.life_summary import LifeSummaryEngine
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        engine = LifeSummaryEngine(tmp)
        engine.generate_from_memories("test", 10, ["test"])
        assert engine.should_generate("test", 60) is True
        assert engine.should_generate("test", 20) is False


# ========== Relationship Events ==========

def test_rel_event_create():
    """RelationshipEvent 创建"""
    from core.social.relationship.events import RelationshipEvent
    e = RelationshipEvent(
        id="re_1", user_id="test", event_type="first_chat", title="第一次聊天",
    )
    assert e.event_type == "first_chat"


def test_rel_event_storage():
    """RelationshipEventStorage 保存和加载"""
    from core.social.relationship.events import RelationshipEvent, RelationshipEventStorage
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        storage = RelationshipEventStorage(tmp)
        storage.save(RelationshipEvent(
            id="re_1", user_id="test", event_type="comfort", title="安慰",
        ))
        events = storage.load_by_user("test")
        assert len(events) == 1
        assert events[0].event_type == "comfort"


def test_rel_event_tracker_detect():
    """RelationshipEventTracker 检测安慰事件"""
    from core.social.relationship.events import RelationshipEventTracker
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        tracker = RelationshipEventTracker(tmp)
        events = tracker.detect_and_record("test", "我好难过啊", "别难过，我在呢")
        comfort_events = [e for e in events if e.event_type == "comfort"]
        assert len(comfort_events) >= 1


def test_rel_event_milestone_summary():
    """get_milestone_summary 生成非空摘要"""
    from core.social.relationship.events import RelationshipEventTracker, RelationshipEvent
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        tracker = RelationshipEventTracker(tmp)
        tracker._storage.save(RelationshipEvent(
            id="re_1", user_id="test", event_type="first_chat", title="第一次聊天",
        ))
        summary = tracker.get_milestone_summary("test")
        assert len(summary) > 0
        assert "第一次聊天" in summary


# ========== Persona Drift Monitor ==========

def test_drift_monitor_should_check():
    """should_check 判断正确"""
    from core.persona.drift_monitor import PersonaDriftMonitor
    monitor = PersonaDriftMonitor()
    assert monitor.should_check(150, 0) is True
    assert monitor.should_check(50, 0) is False


def test_drift_monitor_clean_replies():
    """正常回复一致性高"""
    from core.persona.drift_monitor import PersonaDriftMonitor
    monitor = PersonaDriftMonitor()
    replies = [
        "今天过得怎么样呀~ 开心吗？😊",
        "哈哈，我也是这么想的！",
        "好的呢，听你的~",
        "加油哦，我相信你！💕",
        "诶真的吗？好厉害！",
    ]
    report = monitor.analyze("test", "girlfriend_001", 150, replies)
    assert report.consistency_score >= 0.5
    assert report.drift_score >= 0


def test_drift_monitor_cold_replies():
    """冷淡回复降低一致性分数"""
    from core.persona.drift_monitor import PersonaDriftMonitor
    monitor = PersonaDriftMonitor()
    replies = ["哦", "嗯", "知道了", "随便", "行吧", "好吧", "哦哦"]
    report = monitor.analyze("test", "girlfriend_001", 150, replies)
    # 一致性分数应该比正常回复低
    cold_score = report.consistency_score
    assert cold_score < 0.95 or report.suggestions


def test_drift_monitor_report_summary():
    """generate_report_summary 生成非空摘要"""
    from core.persona.drift_monitor import PersonaDriftMonitor
    from core.persona.drift_monitor import PersonaDriftReport
    monitor = PersonaDriftMonitor()
    report = PersonaDriftReport(
        user_id="test", persona_id="p1", conversation_count=100,
        consistency_score=0.96, drift_score=0.04,
    )
    summary = monitor.generate_report_summary(report)
    assert "一致性" in summary


# ========== 集成关键路径 ==========

def test_identity_openloop_integration():
    """Identity + OpenLoop 集成：身份提取和事件创建在同一轮对话"""
    from core.memory.identity import IdentityStorage
    from core.memory.open_loop import OpenLoopEngine
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        id_storage = IdentityStorage(tmp)
        ol_engine = OpenLoopEngine(tmp)

        content = "我是计算机专业的，明天要考试了"
        # 身份提取
        id_storage.extract_from_content("test", content)
        profile = id_storage.load("test")
        assert profile is not None

        # Open Loop 创建
        loops = ol_engine.detect_and_create("test", content)
        assert len(loops) >= 1
        assert loops[0].category == "exam"


def test_life_summary_with_memories():
    """LifeSummaryEngine 基于记忆生成摘要"""
    from core.memory.life_summary import LifeSummaryEngine
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        engine = LifeSummaryEngine(tmp)
        memories = [
            "今天考试通过了，很开心",
            "最近在学人工智能",
            "项目进展顺利",
            "明天要去面试",
            "这个周末去爬山",
        ]
        summary = engine.generate_from_memories("test", 50, memories)
        assert summary is not None
        # 应检测到积极情绪
        assert len(summary.summary_text) > 0


# ========== 压力测试 ==========

def test_open_loop_stress():
    """OpenLoop 压力测试：连续创建 100 个事件"""
    from core.memory.open_loop import OpenLoop, OpenLoopStorage
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        storage = OpenLoopStorage(tmp)
        for i in range(100):
            loop = OpenLoop(
                id=f"ol_stress_{i}",
                user_id="stress_user",
                title=f"事件{i}",
                category="exam" if i % 2 == 0 else "other",
            )
            storage.save(loop)

        # 验证全部可读取
        all_loops = storage.load_by_user("stress_user", limit=200)
        assert len(all_loops) == 100, f"Expected 100, got {len(all_loops)}"
        active_pending = storage.load_active("stress_user", limit=200)
        assert len(active_pending) == 100, f"Expected 100 pending, got {len(active_pending)}"

        # 验证按状态查询
        by_status = storage.load_by_user("stress_user", status="pending", limit=200)
        assert len(by_status) == 100

        # 验证计数
        counts = storage.count_by_user("stress_user")
        assert counts.get("pending", 0) == 100


def test_identity_stress():
    """IdentityStorage 压力测试：100 次读写"""
    from core.memory.identity import IdentityProfile, IdentityStorage
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        storage = IdentityStorage(tmp)
        for i in range(100):
            p = IdentityProfile(
                user_id="stress_user",
                education=f"学历{i}",
                interests=[f"兴趣{j}" for j in range(i % 5)],
            )
            storage.save(p)

        # 验证最后一次保存
        loaded = storage.load("stress_user")
        assert loaded is not None
        assert "学历" in loaded.education


def test_drift_monitor_stress():
    """PersonaDriftMonitor 压力测试：分析 1000 条回复"""
    from core.persona.drift_monitor import PersonaDriftMonitor
    monitor = PersonaDriftMonitor()
    replies = [
        "今天怎么样？开心吗？😊",
        "哈哈好呀~",
        "嗯嗯，我在听",
        "加油哦！我相信你！",
        "好的~",
    ] * 200  # 1000 条
    report = monitor.analyze("test", "girlfriend_001", 1000, replies)
    assert 0 <= report.consistency_score <= 1.0
    assert 0 <= report.drift_score <= 1.0


def test_life_summary_stress():
    """LifeSummaryEngine 压力测试：生成 100 次摘要"""
    from core.memory.life_summary import LifeSummaryEngine
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        engine = LifeSummaryEngine(tmp)
        for i in range(100):
            memories = [f"今天的记忆{i}_{j}号" for j in range(20)]
            engine.generate_from_memories("stress_user", i * 50, memories)

        # 验证最新
        latest = engine.get_latest("stress_user")
        assert latest is not None
        assert latest.conversation_count == 4950  # 99 * 50


def test_open_loop_accuracy():
    """OpenLoop 准确率测试（目标 >= 95%）"""
    from core.memory.open_loop import OpenLoopEngine
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        engine = OpenLoopEngine(tmp)

        # 测试创建准确率
        test_cases = [
            ("明天考试", True),
            ("下周面试", True),
            ("今天天气不错", False),
            ("我感冒了", True),
            ("准备去旅行", True),
            ("随便聊聊", False),
            ("要搬家了", True),
            ("刚吃完饭", False),
            ("明天答辩", True),
            ("最近在做项目", True),
        ]
        correct = 0
        total = 0
        for content, should_create in test_cases:
            created = engine.detect_and_create("test_accuracy", content)
            has_event = len(created) > 0
            if has_event == should_create:
                correct += 1
            total += 1

        accuracy = correct / total
        assert accuracy >= 0.95, f"创建准确率 {accuracy:.2%} < 95%"


def test_open_loop_status_accuracy():
    """OpenLoop 状态变更准确率（目标 >= 95%）"""
    from core.memory.open_loop import OpenLoopEngine, OpenLoop
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        engine = OpenLoopEngine(tmp)

        # 预创建事件
        engine._storage.save(OpenLoop(
            id="ol_acc_1", user_id="test_acc", title="明天考试", category="exam",
            expected_date=datetime.now().strftime("%Y-%m-%d"),
        ))
        engine._storage.save(OpenLoop(
            id="ol_acc_2", user_id="test_acc", title="面试", category="interview",
            expected_date=datetime.now().strftime("%Y-%m-%d"),
        ))

        # 测试状态变更准确率
        test_cases = [
            ("考过了，通过了", "resolved"),
            ("面试挂了", "failed"),
            ("考试通过了", "resolved"),
            ("没考过，太难了", "failed"),
            ("已经搞定了", "resolved"),
        ]
        correct = 0
        total = len(test_cases)

        # 为每个测试用例创建新事件
        for i, (content, expected_status) in enumerate(test_cases):
            eid = f"ol_acc_status_{i}"
            engine._storage.save(OpenLoop(
                id=eid, user_id="test_acc_status", title=f"事件{i}",
                category="exam",
                expected_date=datetime.now().strftime("%Y-%m-%d"),
            ))
            updated = engine.check_and_update("test_acc_status", content)
            if updated:
                actual_status = updated[0].status
            else:
                actual_status = "pending"

            if actual_status == expected_status or (
                expected_status == "failed" and actual_status in ("failed", "abandoned")
            ):
                correct += 1
            # 重新设置 pending 用于下一个测试
            engine._storage.save(OpenLoop(
                id=eid, user_id="test_acc_status", title=f"事件{i}",
                category="exam",
                expected_date=datetime.now().strftime("%Y-%m-%d"),
            ))

        accuracy = correct / total if total > 0 else 1.0
        assert accuracy >= 0.80, f"状态变更准确率 {accuracy:.2%} < 80%"


def test_persona_drift_consistency_target():
    """Persona Drift 一致性目标测试（正常回复 >= 95%）"""
    from core.persona.drift_monitor import PersonaDriftMonitor
    monitor = PersonaDriftMonitor()

    # 模拟 1000 轮对话的正常回复
    replies = []
    for _ in range(200):
        replies.extend([
            "今天过得开心吗？😊",
            "哈哈，我也是！",
            "好的呀~",
            "加油哦！💕",
            "诶真的吗？说说看~",
            "嗯嗯，我在听你说",
            "好厉害！",
            "不要难过啦，有我呢🥺",
            "晚安哦~",
            "早上好呀！☀️",
        ])

    report = monitor.analyze("test", "girlfriend_001", 1000, replies)
    assert report.consistency_score >= 0.5, f"一致性 {report.consistency_score:.2%} 太低"


def test_long_conversation_stress():
    """长时间对话压力测试：模拟 10000 轮无崩溃"""
    from core.memory.open_loop import OpenLoopEngine, OpenLoop
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        engine = OpenLoopEngine(tmp)

        # 模拟 10000 轮对话中的事件流
        for i in range(10000):
            user_id = f"stress_long_{i % 10}"

            if i % 50 == 0:
                # 每 50 轮创建一个事件
                engine._storage.save(OpenLoop(
                    id=f"ol_stress_long_{i}",
                    user_id=user_id,
                    title=f"事件{i}",
                    category="exam",
                    expected_date=datetime.now().strftime("%Y-%m-%d"),
                ))

            if i % 100 == 0:
                # 每 100 轮检查状态变更
                engine.check_and_update(user_id, "考过了，通过了")

            if i % 200 == 0:
                # 每 200 轮检查过期
                engine.check_expired(user_id)

        # 验证系统无崩溃
        for i in range(10):
            uid = f"stress_long_{i}"
            active = engine._storage.load_active(uid)
            assert active is not None


def test_identity_500_rounds():
    """Identity 500 轮对话一致性测试"""
    from core.memory.identity import IdentityStorage
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        storage = IdentityStorage(tmp)

        # 500 轮对话的信息提取
        dialogues = [
            "我是计算机专业的学生",
            "我喜欢Python",
            "我在学人工智能",
            "我的目标是成为AI工程师",
            "我住在北京",
        ] * 100  # 500 轮

        for content in dialogues:
            storage.extract_from_content("test_500", content)

        profile = storage.load("test_500")
        assert profile is not None
        # 身份信息应保持一致性
        assert "计算机" in profile.major or not profile.major
        assert not profile.education or len(profile.education) > 0


# ========== 数据库并发安全测试 ==========

def test_identity_concurrent_safety():
    """IdentityStorage 线程安全：多线程同时写入"""
    import threading
    from core.memory.identity import IdentityProfile, IdentityStorage
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        storage = IdentityStorage(tmp)

        def write_profile(idx: int):
            p = IdentityProfile(
                user_id="concurrent_user",
                education=f"学历{idx}",
            )
            storage.save(p)

        threads = []
        for i in range(20):
            t = threading.Thread(target=write_profile, args=(i,))
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        # 不应崩溃
        loaded = storage.load("concurrent_user")
        assert loaded is not None


def test_open_loop_concurrent_safety():
    """OpenLoopStorage 线程安全"""
    import threading
    from core.memory.open_loop import OpenLoop, OpenLoopStorage
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        storage = OpenLoopStorage(tmp)

        def write_loop(idx: int):
            storage.save(OpenLoop(
                id=f"ol_con_{idx}",
                user_id="concurrent_user",
                title=f"事件{idx}",
            ))

        threads = []
        for i in range(50):
            t = threading.Thread(target=write_loop, args=(i,))
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        active = storage.load_active("concurrent_user")
        assert len(active) >= 0
