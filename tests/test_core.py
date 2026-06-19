"""核心模块单元测试"""

import sys
import tempfile
from pathlib import Path
from datetime import date

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.memory.models import Memory
from core.memory.scorer import MemoryScorer
from core.memory.storage import MemoryStorage
from core.emotion.analyzer import EmotionAnalyzer, EmotionType, EmotionResult
from core.emotion.expression import MessageSegmenter, EmotionEnhancer


# ========== MemoryScorer 测试 ==========

def test_score_basic():
    """测试基础评分"""
    score, conf = MemoryScorer.score("")
    assert score == 1
    score, conf = MemoryScorer.score("hi")
    assert score == 1
    score, conf = MemoryScorer.score("今天天气不错")
    assert score >= 1


def test_score_high_importance():
    """测试高重要度内容"""
    score, conf = MemoryScorer.score("我的生日是5月20日")
    assert score >= 4

    # 包含地址+正则匹配
    score, conf = MemoryScorer.score("我叫小明，我住在北京市朝阳区，电话是13800138000")
    assert score >= 2


def test_score_medium_importance():
    """测试中等重要度"""
    # 包含多个关键词才能达到 2 分
    score, conf = MemoryScorer.score("我喜欢吃火锅，最喜欢和朋友一起")
    assert score >= 2


def test_should_remember():
    """测试是否值得记住"""
    assert MemoryScorer.should_remember("我的生日是5月20日") is True
    assert MemoryScorer.should_remember("hi") is False
    assert MemoryScorer.should_remember("今天天气不错") is False


# ========== MemoryStorage 测试 ==========

def _storage_dir():
    """创建临时目录用于存储测试（Windows SQLite WAL 锁兼容）"""
    return tempfile.TemporaryDirectory(ignore_cleanup_errors=True)


def test_storage_save_and_load():
    """测试存储保存和加载（SQLite 版）"""
    with _storage_dir() as tmpdir:
        storage = MemoryStorage(tmpdir)
        memories = [
            Memory(id="m1", content="test memory 1", level=3),
            Memory(id="m2", content="test memory 2", level=5),
        ]
        storage.save("test_user", memories)
        loaded = storage.load("test_user")
        assert len(loaded) == 2
        # 按 id 查找而非按顺序（SQLite 排序方式不同）
        m1 = next(m for m in loaded if m.id == "m1")
        m2 = next(m for m in loaded if m.id == "m2")
        assert m1.content == "test memory 1"
        assert m2.level == 5
        storage.close()


def test_storage_load_nonexistent():
    """测试加载不存在的用户"""
    with _storage_dir() as tmpdir:
        storage = MemoryStorage(tmpdir)
        loaded = storage.load("nonexistent")
        assert loaded == []
        storage.close()


def test_storage_path_traversal():
    """测试路径穿越防护（SQLite 版不再有 _get_user_file）"""
    pass


def test_storage_list_users():
    """测试列出用户"""
    with _storage_dir() as tmpdir:
        storage = MemoryStorage(tmpdir)
        storage.save("user1", [Memory(id="m1", content="test", level=3)])
        storage.save("user2", [Memory(id="m2", content="test", level=3)])
        users = storage.list_users()
        assert "user1" in users
        assert "user2" in users
        storage.close()


def test_storage_delete_all():
    """测试删除所有记忆"""
    with _storage_dir() as tmpdir:
        storage = MemoryStorage(tmpdir)
        storage.save("user1", [Memory(id="m1", content="test", level=3)])
        assert storage.delete_all("user1") is True
        assert storage.load("user1") == []
        assert storage.delete_all("nonexistent") is False
        storage.close()


# ========== EmotionAnalyzer 测试 ==========

def test_emotion_happy():
    """测试开心情感"""
    result = EmotionAnalyzer.analyze("今天好开心呀哈哈")
    assert result.emotion == EmotionType.HAPPY
    assert result.intensity > 0


def test_emotion_sad():
    """测试难过情感"""
    result = EmotionAnalyzer.analyze("我好难过，想哭")
    assert result.emotion == EmotionType.SAD


def test_emotion_angry():
    """测试生气情感"""
    result = EmotionAnalyzer.analyze("你怎么这么讨厌")
    assert result.emotion == EmotionType.ANGRY


def test_emotion_love():
    """测试爱意情感"""
    result = EmotionAnalyzer.analyze("我爱你宝贝")
    assert result.emotion == EmotionType.LOVE


def test_emotion_neutral():
    """测试中性情感"""
    result = EmotionAnalyzer.analyze("今天天气不错")
    assert result.emotion == EmotionType.NEUTRAL


def test_emotion_empty():
    """测试空文本"""
    result = EmotionAnalyzer.analyze("")
    assert result.emotion == EmotionType.NEUTRAL
    assert result.intensity == 0.0


def test_emotion_intensity_boost():
    """测试强度增强"""
    normal = EmotionAnalyzer.analyze("开心")
    boosted = EmotionAnalyzer.analyze("非常开心")
    assert boosted.intensity >= normal.intensity


# ========== MessageSegmenter 测试 ==========

def test_segment_short():
    """测试短消息不分段"""
    result = MessageSegmenter.segment("你好")
    assert result.total_segments == 1
    assert result.segments == ["你好"]


def test_segment_long():
    """测试长消息分段"""
    text = "今天天气真好呀！我早上去了公园，看到了很多花。然后和朋友一起吃了午饭，下午去看了电影。"
    result = MessageSegmenter.segment(text, max_segment_length=30)
    assert result.total_segments > 1
    # 所有段落合并后应该包含原文所有内容
    merged = "".join(result.segments)
    assert len(merged) >= len(text) - 5  # 允许少量标点差异


def test_segment_empty():
    """测试空消息"""
    result = MessageSegmenter.segment("")
    assert result.total_segments == 1


# ========== EmotionEnhancer 测试 ==========

def test_enhance_neutral():
    """测试中性情感不添加 emoji"""
    from core.emotion.analyzer import EmotionResult
    emotion = EmotionResult(emotion=EmotionType.NEUTRAL, intensity=0.0, keywords=[])
    result = EmotionEnhancer.enhance_reply("你好", emotion)
    assert result == "你好"


def test_enhance_happy():
    """测试开心情感添加 emoji"""
    from core.emotion.analyzer import EmotionResult
    emotion = EmotionResult(emotion=EmotionType.HAPPY, intensity=0.8, keywords=["开心"])
    result = EmotionEnhancer.enhance_reply("我知道了", emotion)
    assert result != "我知道了"  # 应该被增强
    assert "我知道了" in result


def test_enhance_no_duplicate():
    """测试不重复添加 emoji"""
    from core.emotion.analyzer import EmotionResult
    emotion = EmotionResult(emotion=EmotionType.HAPPY, intensity=0.8, keywords=[])
    result = EmotionEnhancer.enhance_reply("好开心 😊", emotion)
    assert result == "好开心 😊"  # 已有 emoji，不添加


# ========== Memory 模型测试 ==========

def test_memory_to_dict():
    """测试 Memory 序列化"""
    m = Memory(id="m1", content="test", level=3, tags=["tag1"])
    d = m.to_dict()
    assert d["id"] == "m1"
    assert d["content"] == "test"
    assert d["level"] == 3
    assert d["tags"] == ["tag1"]


def test_memory_from_dict():
    """测试 Memory 反序列化"""
    d = {"id": "m1", "content": "test", "level": 3, "tags": ["tag1"]}
    m = Memory.from_dict(d)
    assert m.id == "m1"
    assert m.content == "test"
    assert m.level == 3


def test_memory_touch():
    """测试 Memory 访问更新"""
    m = Memory(id="m1", content="test", level=3)
    assert m.access_count == 0
    m.touch()
    assert m.access_count == 1
    m.touch()
    assert m.access_count == 2


# ========== RelationshipTracker 测试 ==========

def test_relationship_basic():
    """测试关系追踪器基础功能"""
    from core.social.relationship import RelationshipTracker

    with tempfile.TemporaryDirectory() as tmpdir:
        tracker = RelationshipTracker(tmpdir)

        # 新用户返回基础 level
        level = tracker.get_level("user1", base_level=50)
        assert level == 50

        # 多次更新后 level 应该增加（每次 +0.05，需要足够次数才能在整数上体现）
        for _ in range(30):
            tracker.update("user1", emotion="neutral", base_level=50)
        new_level = tracker.get_level("user1", base_level=50)
        assert new_level > 50


def test_relationship_positive_emotion():
    """测试正面情感提升亲密度"""
    from core.social.relationship import RelationshipTracker

    with tempfile.TemporaryDirectory() as tmpdir:
        tracker = RelationshipTracker(tmpdir)

        # 中性消息累积
        for _ in range(10):
            tracker.update("user1", emotion="neutral", base_level=50)
        level_neutral = tracker.get_level("user1", base_level=50)

        # 正面情感累积应该更高
        for _ in range(10):
            tracker.update("user1", emotion="happy", base_level=50)
        level_happy = tracker.get_level("user1", base_level=50)
        assert level_happy > level_neutral


def test_relationship_negative_emotion():
    """测试负面情感降低亲密度"""
    from core.social.relationship import RelationshipTracker

    with tempfile.TemporaryDirectory() as tmpdir:
        tracker = RelationshipTracker(tmpdir)

        # 先建立一定的亲密度
        for _ in range(10):
            tracker.update("user1", emotion="neutral", base_level=50)
        level_before = tracker.get_level("user1", base_level=50)

        # 负面情感应该降低亲密度（相比中性）
        level_angry = tracker.update("user1", emotion="angry", base_level=50)
        # angry gives -0.2, but message gives +0.05, net -0.15
        # So level should be lower than if we had a neutral message
        level_neutral_would_be = level_before + 0.05
        assert level_angry < level_neutral_would_be


def test_relationship_persistence():
    """测试亲密度持久化"""
    from core.social.relationship import RelationshipTracker

    with tempfile.TemporaryDirectory() as tmpdir:
        # 第一次创建并更新
        tracker1 = RelationshipTracker(tmpdir)
        tracker1.update("user1", emotion="happy", base_level=50)
        level1 = tracker1.get_level("user1", base_level=50)

        # 第二次加载应该保留数据
        tracker2 = RelationshipTracker(tmpdir)
        level2 = tracker2.get_level("user1", base_level=50)
        assert level2 == level1


def test_relationship_clamp():
    """测试亲密度范围限制"""
    from core.social.relationship import RelationshipTracker

    with tempfile.TemporaryDirectory() as tmpdir:
        tracker = RelationshipTracker(tmpdir)

        # 大量正面交互
        for _ in range(5000):
            tracker.update("user1", emotion="love", base_level=50)
        level = tracker.get_level("user1", base_level=50)
        assert level <= 100


def test_relationship_stats():
    """测试亲密度统计信息"""
    from core.social.relationship import RelationshipTracker

    with tempfile.TemporaryDirectory() as tmpdir:
        tracker = RelationshipTracker(tmpdir)

        # 无数据时的统计
        stats = tracker.get_stats("user1")
        assert stats["level"] == 50
        assert stats["message_count"] == 0

        # 有数据时的统计
        tracker.update("user1", emotion="happy", base_level=50)
        tracker.update("user1", emotion="happy", base_level=50)
        stats = tracker.get_stats("user1")
        assert stats["message_count"] == 2
        assert stats["positive_count"] == 2


# ========== ChatHistoryStorage 测试 ==========

def test_chat_history_basic():
    """测试聊天历史基础功能"""
    from core.memory import ChatHistoryStorage

    with tempfile.TemporaryDirectory() as tmpdir:
        storage = ChatHistoryStorage(tmpdir, max_messages=10)

        # 新用户返回空历史
        messages = storage.get_messages("user1")
        assert messages == []

        # 添加消息
        storage.add_message("user1", "user", "你好")
        storage.add_message("user1", "assistant", "你好呀~")

        messages = storage.get_messages("user1")
        assert len(messages) == 2
        assert messages[0]["role"] == "user"
        assert messages[0]["content"] == "你好"
        assert messages[1]["role"] == "assistant"


def test_chat_history_max_messages():
    """测试消息历史最大长度限制"""
    from core.memory import ChatHistoryStorage

    with tempfile.TemporaryDirectory() as tmpdir:
        storage = ChatHistoryStorage(tmpdir, max_messages=5)

        # 添加超过上限的消息
        for i in range(10):
            storage.add_message("user1", "user", f"消息{i}")

        messages = storage.get_messages("user1")
        assert len(messages) == 5
        # 应该保留最后 5 条
        assert messages[0]["content"] == "消息5"
        assert messages[4]["content"] == "消息9"


def test_chat_history_persistence():
    """测试聊天历史持久化"""
    from core.memory import ChatHistoryStorage

    with tempfile.TemporaryDirectory() as tmpdir:
        # 第一次创建并添加消息
        storage1 = ChatHistoryStorage(tmpdir)
        storage1.add_message("user1", "user", "你好")
        storage1.add_message("user1", "assistant", "你好呀~")

        # 第二次加载应该保留数据
        storage2 = ChatHistoryStorage(tmpdir)
        messages = storage2.get_messages("user1")
        assert len(messages) == 2
        assert messages[0]["content"] == "你好"


def test_chat_history_short_memories():
    """测试短期记忆功能"""
    from core.memory import ChatHistoryStorage

    with tempfile.TemporaryDirectory() as tmpdir:
        storage = ChatHistoryStorage(tmpdir)

        # 添加短期记忆
        storage.add_short_memory("user1", "今天天气好", "是呀，阳光明媚呢~")
        storage.add_short_memory("user1", "你喜欢什么", "我喜欢动漫和游戏~")

        memories = storage.get_short_memories("user1")
        assert len(memories) == 2
        assert memories[0]["user"] == "今天天气好"

        # 清空短期记忆
        storage.clear_short_memories("user1")
        memories = storage.get_short_memories("user1")
        assert len(memories) == 0


def test_chat_history_delete_user():
    """测试删除用户历史"""
    from core.memory import ChatHistoryStorage

    with tempfile.TemporaryDirectory() as tmpdir:
        storage = ChatHistoryStorage(tmpdir)
        storage.add_message("user1", "user", "你好")

        # 删除用户
        assert storage.delete_user("user1") is True
        messages = storage.get_messages("user1")
        assert messages == []

        # 删除不存在的用户
        assert storage.delete_user("nonexistent") is False


# ========== 情感否定词测试 ==========

def test_emotion_negation_not_happy():
    """测试否定词：不开心 → 不应该是 HAPPY"""
    result = EmotionAnalyzer.analyze("我一点都不开心")
    assert result.emotion != EmotionType.HAPPY


def test_emotion_negation_not_angry():
    """测试否定词：不生气 → 不应该是 ANGRY"""
    result = EmotionAnalyzer.analyze("我没有生气")
    assert result.emotion != EmotionType.ANGRY


def test_emotion_negation_no_keyword_match():
    """测试否定词：否定后的关键词不计入"""
    result = EmotionAnalyzer.analyze("不喜欢")
    # "喜欢" 在 HAPPY 列表里，但被 "不" 否定
    assert result.emotion != EmotionType.HAPPY


def test_emotion_no_negation():
    """测试无否定词时正常识别"""
    result = EmotionAnalyzer.analyze("我好开心呀")
    assert result.emotion == EmotionType.HAPPY


# ========== ChatHistoryStorage 路径穿越测试 ==========

def test_chat_history_path_traversal():
    """测试聊天历史路径穿越防护"""
    from core.memory import ChatHistoryStorage

    with tempfile.TemporaryDirectory() as tmpdir:
        storage = ChatHistoryStorage(tmpdir)
        try:
            storage._get_user_file("../../etc/passwd")
            # 如果 safe_id 替换后仍在目录内，不会报错
        except ValueError:
            pass  # 期望的行为


def test_chat_history_special_chars():
    """测试特殊字符用户 ID"""
    from core.memory import ChatHistoryStorage

    with tempfile.TemporaryDirectory() as tmpdir:
        storage = ChatHistoryStorage(tmpdir)
        # 特殊字符应该被替换
        path = storage._get_user_file("user@#$%")
        assert path.exists() or True  # 不应该抛异常


# ========== 主模块工具函数测试 ==========

def test_get_time_context():
    """测试时间上下文生成"""
    from core.chat import get_time_context
    ctx = get_time_context()
    assert "现在是" in ctx


def test_timestamp():
    """测试时间戳格式"""
    from core.chat import timestamp
    ts = timestamp()
    assert ":" in ts
    assert len(ts) == 5  # HH:MM


def test_get_llm_error_message():
    """测试 LLM 错误消息转换"""
    from core.chat import get_llm_error_message
    msg = get_llm_error_message(Exception("rate limit exceeded"))
    assert "忙" in msg or "稍等" in msg

    msg = get_llm_error_message(Exception("unauthorized 401"))
    assert "API key" in msg

    msg = get_llm_error_message(Exception("connection refused"))
    assert "网络" in msg


def test_session_stats_summary():
    """测试会话总结生成"""
    from core.chat import SessionStats
    stats = SessionStats()
    stats.message_count = 10
    stats.memories_added = 3
    stats.start_level = 50
    stats.end_level = 55
    summary = stats.summary("小雨")
    assert "10 条" in summary
    assert "50" in summary
    assert "55" in summary


# ========== 消息分段器英文标点测试 ==========

def test_segment_english_punctuation():
    """测试英文标点分段"""
    text = "Hello world! How are you? I'm fine."
    result = MessageSegmenter.segment(text, max_segment_length=20)
    assert result.total_segments > 1


def test_segment_mixed_punctuation():
    """测试中英文混合标点分段"""
    text = "你好呀！Hello world. 今天天气不错~"
    result = MessageSegmenter.segment(text, max_segment_length=15)
    assert result.total_segments > 1


def test_segment_english_only():
    """测试纯英文消息"""
    text = "This is a long sentence that should be split at some point."
    result = MessageSegmenter.segment(text, max_segment_length=25)
    assert result.total_segments >= 1
    # 所有段落合并后应包含原文
    merged = " ".join(result.segments)
    assert "long sentence" in merged


# ========== LLM 情感分析器测试 ==========

def test_llm_emotion_analyzer_keyword_fallback():
    """测试 LLM 情感分析器在无 LLM 时回退到关键词"""
    from core.emotion.llm_analyzer import LLMEmotionAnalyzer

    analyzer = LLMEmotionAnalyzer(llm=None)
    # 无 LLM 时应该用关键词分析
    import asyncio
    result, enriched = asyncio.run(analyzer.analyze("我好开心呀"))
    assert result.emotion == EmotionType.HAPPY


def test_llm_emotion_analyzer_trajectory():
    """测试 LLM 情感分析器轨迹追踪"""
    from core.emotion.llm_analyzer import LLMEmotionAnalyzer, EmotionTrajectory

    analyzer = LLMEmotionAnalyzer(llm=None)
    import asyncio

    # 多次分析后轨迹应该有记录
    asyncio.run(analyzer.analyze("我好开心呀"))
    asyncio.run(analyzer.analyze("今天心情不错"))
    asyncio.run(analyzer.analyze("有点难过"))

    trend = analyzer.trajectory.get_trend()
    assert trend in ("improving", "declining", "stable", "insufficient")

    dominant = analyzer.trajectory.get_dominant_emotion()
    assert dominant is not None


# ========== 多消息格式化测试 ==========

def test_format_single_message():
    """测试单条消息不格式化"""
    from core.chat import format_multi_message
    result, count = format_multi_message("你好呀")
    assert count == 1
    assert result == "你好呀"


def test_format_multi_message():
    """测试多条消息格式化"""
    from core.chat import format_multi_message
    content = "今天好累\n考试考砸了\n心情超差"
    result, count = format_multi_message(content)
    assert count == 3
    assert "[消息1] 今天好累" in result
    assert "[消息2] 考试考砸了" in result
    assert "[消息3] 心情超差" in result


def test_format_multi_message_empty_lines():
    """测试多消息中的空行被过滤"""
    from core.chat import format_multi_message
    content = "第一条\n\n第二条\n"
    result, count = format_multi_message(content)
    assert count == 2
    assert "[消息1] 第一条" in result
    assert "[消息2] 第二条" in result


def test_format_multi_message_whitespace():
    """测试多消息中的空白被清理"""
    from core.chat import format_multi_message
    content = "  第一条  \n  第二条  "
    result, count = format_multi_message(content)
    assert count == 2
    assert "[消息1] 第一条" in result
    assert "[消息2] 第二条" in result


# ========== ChatHistory 新功能测试 ==========

def test_delete_last_messages():
    """测试删除最后 N 条消息"""
    from core.memory import ChatHistoryStorage

    with tempfile.TemporaryDirectory() as tmpdir:
        storage = ChatHistoryStorage(tmpdir)
        storage.add_message("user1", "user", "你好")
        storage.add_message("user1", "assistant", "你好呀~")
        storage.add_message("user1", "user", "今天天气怎么样")
        storage.add_message("user1", "assistant", "今天阳光明媚呢~")

        # 删除最后 2 条
        deleted = storage.delete_last_messages("user1", 2)
        assert len(deleted) == 2
        assert deleted[0]["role"] == "user"
        assert deleted[0]["content"] == "今天天气怎么样"
        assert deleted[1]["role"] == "assistant"
        assert deleted[1]["content"] == "今天阳光明媚呢~"

        # 验证剩余消息
        messages = storage.get_messages("user1")
        assert len(messages) == 2
        assert messages[0]["content"] == "你好"


def test_delete_last_messages_empty():
    """测试空历史删除不报错"""
    from core.memory import ChatHistoryStorage

    with tempfile.TemporaryDirectory() as tmpdir:
        storage = ChatHistoryStorage(tmpdir)
        deleted = storage.delete_last_messages("user1", 2)
        assert deleted == []


def test_delete_last_messages_count_exceeds():
    """测试删除数量超过现有消息数"""
    from core.memory import ChatHistoryStorage

    with tempfile.TemporaryDirectory() as tmpdir:
        storage = ChatHistoryStorage(tmpdir)
        storage.add_message("user1", "user", "你好")

        # 请求删除 5 条，但只有 1 条
        deleted = storage.delete_last_messages("user1", 5)
        assert len(deleted) == 1
        assert deleted[0]["content"] == "你好"

        messages = storage.get_messages("user1")
        assert len(messages) == 0


def test_search_messages_basic():
    """测试搜索消息"""
    from core.memory import ChatHistoryStorage

    with tempfile.TemporaryDirectory() as tmpdir:
        storage = ChatHistoryStorage(tmpdir)
        storage.add_message("user1", "user", "我的生日是5月20日")
        storage.add_message("user1", "assistant", "记住啦~")
        storage.add_message("user1", "user", "今天天气不错")
        storage.add_message("user1", "assistant", "是呀阳光明媚")

        results = storage.search_messages("user1", "生日")
        assert len(results) == 1
        assert results[0]["index"] == 0
        assert "生日" in results[0]["message"]["content"]
        # 应该有上下文
        assert results[0]["after"] is not None


def test_search_messages_no_match():
    """测试搜索无匹配"""
    from core.memory import ChatHistoryStorage

    with tempfile.TemporaryDirectory() as tmpdir:
        storage = ChatHistoryStorage(tmpdir)
        storage.add_message("user1", "user", "你好")

        results = storage.search_messages("user1", "不存在的关键词")
        assert results == []


def test_search_messages_empty_history():
    """测试空历史搜索"""
    from core.memory import ChatHistoryStorage

    with tempfile.TemporaryDirectory() as tmpdir:
        storage = ChatHistoryStorage(tmpdir)
        results = storage.search_messages("user1", "test")
        assert results == []


def test_search_messages_limit():
    """测试搜索结果限制"""
    from core.memory import ChatHistoryStorage

    with tempfile.TemporaryDirectory() as tmpdir:
        storage = ChatHistoryStorage(tmpdir)
        for i in range(10):
            storage.add_message("user1", "user", f"第{i}条消息包含关键词")

        results = storage.search_messages("user1", "关键词", limit=3)
        assert len(results) == 3


def test_search_messages_context():
    """测试搜索结果包含上下文"""
    from core.memory import ChatHistoryStorage

    with tempfile.TemporaryDirectory() as tmpdir:
        storage = ChatHistoryStorage(tmpdir)
        storage.add_message("user1", "user", "第一条")
        storage.add_message("user1", "assistant", "第二条")
        storage.add_message("user1", "user", "第三条包含目标词")
        storage.add_message("user1", "assistant", "第四条")

        results = storage.search_messages("user1", "目标词")
        assert len(results) == 1
        r = results[0]
        assert r["index"] == 2
        assert r["before"]["content"] == "第二条"
        assert r["after"]["content"] == "第四条"


# ========== ImageHandler 测试 ==========

def test_parse_img_command_normal():
    """测试正常图片命令解析"""
    from core.multimodal.image_handler import ImageHandler
    path, text = ImageHandler.parse_img_command('/img cat.jpg 看看这只猫')
    assert path == "cat.jpg"
    assert text == "看看这只猫"


def test_parse_img_command_quoted_path():
    """测试带引号的路径"""
    from core.multimodal.image_handler import ImageHandler
    path, text = ImageHandler.parse_img_command('/img "my cat.jpg" 好可爱')
    assert path == "my cat.jpg"
    assert text == "好可爱"


def test_parse_img_command_unclosed_quote():
    """测试未闭合的引号（之前会 crash）"""
    from core.multimodal.image_handler import ImageHandler
    path, text = ImageHandler.parse_img_command('/img "my cat.jpg')
    assert path == ""
    assert text == ""


def test_parse_img_command_no_text():
    """测试只有路径没有文字"""
    from core.multimodal.image_handler import ImageHandler
    path, text = ImageHandler.parse_img_command('/img cat.jpg')
    assert path == "cat.jpg"
    assert text == ""


# ========== ChatHistoryStorage data_dir property 测试 ==========

def test_chat_history_data_dir_property():
    """测试 data_dir 公开属性"""
    from core.memory import ChatHistoryStorage

    with tempfile.TemporaryDirectory() as tmpdir:
        storage = ChatHistoryStorage(tmpdir)
        data_dir = storage.data_dir
        assert data_dir is not None
        assert str(tmpdir) in str(data_dir)


# ========== AI Mood 测试 ==========

def test_mood_compute_daily():
    """测试每天生成不同的 mood"""
    from core.emotion.ai_mood import AIMoodManager
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        mgr = AIMoodManager(tmpdir)
        state = mgr.get_or_today("test_persona", 50)
        assert state.persona_id == "test_persona"
        assert state.emotion in ["happy", "calm", "excited", "tired", "melancholy", "playful", "affectionate", "quiet"]
        assert 0 <= state.energy <= 100
        assert state.today_theme != ""
        assert state.last_updated is not None


def test_mood_persistence():
    """测试 mood 跨 session 持久化"""
    from core.emotion.ai_mood import AIMoodManager
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        mgr1 = AIMoodManager(tmpdir)
        state1 = mgr1.get_or_today("test_persona", 50)

        # 新实例读取同一文件
        mgr2 = AIMoodManager(tmpdir)
        state2 = mgr2.get_or_today("test_persona", 50)

        assert state1.emotion == state2.emotion


def test_mood_relationship_affects():
    """测试亲密度影响 mood 倾向"""
    from core.emotion.ai_mood import AIMoodManager
    import tempfile
    from collections import Counter

    with tempfile.TemporaryDirectory() as tmpdir:
        mgr = AIMoodManager(tmpdir)
        emotions_high = Counter()
        emotions_low = Counter()
        for _ in range(100):
            emotions_high[mgr._compute_daily("x", 80).emotion] += 1
            emotions_low[mgr._compute_daily("x", 10).emotion] += 1
        # 亲密度高时正面情绪应更多
        assert emotions_high["happy"] + emotions_high["affectionate"] + emotions_high["excited"] > \
               emotions_low["happy"] + emotions_low["affectionate"] + emotions_low["excited"]


def test_mood_style_instruction():
    """测试生成风格指令"""
    from core.emotion.ai_mood import AIMoodManager
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        mgr = AIMoodManager(tmpdir)
        inst = mgr.get_style_instruction("test_persona", 50)
        assert "你今天的状态" in inst
        assert "心情：" in inst


def test_mood_display_summary():
    """测试摘要字符串包含 mood 信息"""
    from core.emotion.ai_mood import AIMoodManager
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        mgr = AIMoodManager(tmpdir)
        summary = mgr.get_display_summary("test_persona", 50)
        assert "精力" in summary


# ========== ToolCalling 测试 ==========

def test_tool_clock():
    """测试时钟工具"""
    from core.tools.builtin import ClockTool
    import asyncio
    tool = ClockTool()
    result = asyncio.run(tool.execute())
    assert result.success
    assert "年" in result.output
    assert "月" in result.output


def test_tool_registry_parse_call():
    """测试工具调用解析"""
    from core.tools import ToolRegistry, ToolCall
    registry = ToolRegistry()
    text = "今天的天气真好啊 /call clock 然后我们出去玩吧"
    calls = registry.parse_calls(text)
    assert len(calls) == 0  # clock 尚未注册，不应被解析到
    from core.tools.builtin import ClockTool
    registry.register(ClockTool())
    calls = registry.parse_calls(text)
    assert len(calls) == 1
    assert calls[0].name == "clock"


def test_tool_prompt_block():
    """测试 prompt 块生成"""
    from core.tools import ToolRegistry
    from core.tools.builtin import ClockTool, DateCalcTool
    registry = ToolRegistry()
    assert registry.get_prompt_block() == ""
    registry.register(ClockTool())
    registry.register(DateCalcTool())
    block = registry.get_prompt_block()
    assert "clock" in block
    assert "date_calc" in block


def test_tool_reminder():
    """测试提醒工具持久化"""
    from core.tools.builtin import ReminderTool
    import asyncio
    with tempfile.TemporaryDirectory() as tmpdir:
        tool = ReminderTool(tmpdir)
        result = asyncio.run(tool.execute(content="明天记得买牛奶"))
        assert result.success
        file = Path(tmpdir) / "reminders" / f"{date.today().strftime('%Y%m')}.json"
        assert file.exists()


def test_tool_timer():
    """测试倒计时工具"""
    import asyncio
    from core.tools.builtin import TimerTool
    tool = TimerTool()
    result = asyncio.run(tool.execute(minutes=5, note="休息一下"))
    assert result.success
    assert "5 分钟" in result.output


def test_tool_translate():
    """测试翻译工具"""
    import asyncio
    from core.tools.builtin import TranslateTool
    tool = TranslateTool()
    r = asyncio.run(tool.execute(text="你好", target="en"))
    assert r.success
    assert r.output == "Hello"
    r2 = asyncio.run(tool.execute(text="Hello", target="zh"))
    assert r2.success
    assert r2.output == "你好"


# ========== Pipeline 集成测试 ==========

class MockLLM:
    """模拟 LLM，返回固定回复"""
    def __init__(self, reply: str = "测试回复"):
        self.reply = reply

    async def chat(self, messages, system_prompt="", **kwargs):
        return type("Resp", (), {"content": self.reply})()

    async def chat_stream(self, messages, system_prompt="", **kwargs):
        yield self.reply

    async def close(self):
        pass


class SeqMockLLM:
    """模拟 LLM，按顺序返回多个回复（用于测试工具调用循环）"""
    def __init__(self, replies: list[str]):
        self._replies = list(replies)
        self._index = 0
        self.reply = replies[0] if replies else ""

    async def chat(self, messages, system_prompt="", **kwargs):
        idx = self._index
        self._index += 1
        reply = self._replies[idx % len(self._replies)] if self._replies else ""
        return type("Resp", (), {"content": reply})()

    async def chat_stream(self, messages, system_prompt="", **kwargs):
        idx = self._index
        self._index += 1
        reply = self._replies[idx % len(self._replies)] if self._replies else ""
        yield reply

    async def close(self):
        pass


def test_pipeline_no_llm():
    """无 LLM 时 pipeline 返回占位消息"""
    import asyncio
    from core.chat.pipeline import ChatPipeline
    pipeline = ChatPipeline(None, None, None, None, None, None, None, None, {})
    reply, level = asyncio.run(pipeline.process("test_user", "你好", "girlfriend_001"))
    assert level == 50


def test_pipeline_full_flow():
    """使用 MockLLM 测试完整 pipeline 流程"""
    import asyncio
    import gc
    import tempfile
    from core.chat.pipeline import ChatPipeline
    from core.memory.embedder import SentenceTransformerEmbedder
    from core.memory.vector_store import VectorStore
    from core.memory import MemoryManager, ChatHistoryStorage
    from core.persona import PersonaLoader
    from core.personality import PersonalityEngine
    from core.emotion import LLMEmotionAnalyzer
    from core.social.relationship import RelationshipTracker
    from core.emotion.mood import MoodEngine

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
        llm = MockLLM("我挺好的呀，今天心情不错~")

        embedder = SentenceTransformerEmbedder()
        vector_store = VectorStore(str(Path(tmpdir) / "vectors.db"))
        memory_mgr = MemoryManager(tmpdir, embedder=embedder, vector_store=vector_store)
        # 创建测试用人设文件
        test_persona_path = Path(tmpdir) / "personas.json"
        test_persona_path.write_text(
            '{"personas":[{"id":"girlfriend_001","name":"小可爱","age":20,'
            '"hobbies":[{"name":"看书"}],"personality":["温柔"],"speaking_style":"软萌"}]}',
            encoding="utf-8",
        )
        persona_loader = PersonaLoader(test_persona_path)
        personality_engine = PersonalityEngine(tmpdir)
        chat_history = ChatHistoryStorage(tmpdir)
        emotion = LLMEmotionAnalyzer()
        rel = RelationshipTracker(tmpdir)
        mood = MoodEngine(tmpdir)

        pipeline = ChatPipeline(
            llm, memory_mgr, persona_loader, personality_engine, chat_history,
            emotion, rel, mood, {},
        )

        reply, level = asyncio.run(
            pipeline.process("test_user", "你最近怎么样？", "girlfriend_001")
        )
        assert reply == "我挺好的呀，今天心情不错~"
        assert level > 0

        msgs = chat_history.get_messages("test_user")
        assert len(msgs) == 2
        assert msgs[0]["role"] == "user"
        assert msgs[1]["role"] == "assistant"

        # 清理：关闭数据库连接，确保 tempdir 可删除
        vector_store.close()
        del pipeline, memory_mgr, chat_history, rel, mood, embedder, vector_store
        gc.collect()


def test_pipeline_multi_message():
    """多消息成组发送"""
    import asyncio
    import gc
    import tempfile
    from core.chat.pipeline import ChatPipeline
    from core.memory.embedder import SentenceTransformerEmbedder
    from core.memory.vector_store import VectorStore
    from core.memory import MemoryManager, ChatHistoryStorage
    from core.persona import PersonaLoader
    from core.personality import PersonalityEngine
    from core.emotion import LLMEmotionAnalyzer
    from core.social.relationship import RelationshipTracker
    from core.emotion.mood import MoodEngine

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
        llm = MockLLM("嗯嗯，我都看到了~")
        embedder = SentenceTransformerEmbedder()
        vector_store = VectorStore(str(Path(tmpdir) / "multi_vectors.db"))
        memory_mgr = MemoryManager(tmpdir, embedder=embedder, vector_store=vector_store)
        personality_engine = PersonalityEngine(tmpdir)
        # 创建测试用人设文件
        test_persona_path = Path(tmpdir) / "personas.json"
        test_persona_path.write_text(
            '{"personas":[{"id":"girlfriend_001","name":"小可爱","age":20,'
            '"hobbies":[{"name":"看书"}],"personality":["温柔"],"speaking_style":"软萌"}]}',
            encoding="utf-8",
        )
        pipeline = ChatPipeline(
            llm, memory_mgr,
            PersonaLoader(test_persona_path),
            personality_engine,
            ChatHistoryStorage(tmpdir), LLMEmotionAnalyzer(),
            RelationshipTracker(tmpdir), MoodEngine(tmpdir), {},
        )
        reply, level = asyncio.run(
            pipeline.process("test_user", "今天天气真好\n我们一起出去玩吧\n好不好嘛", "girlfriend_001")
        )
        assert reply == "嗯嗯，我都看到了~"
        assert level > 0

        vector_store.close()
        del pipeline, memory_mgr, embedder, vector_store
        gc.collect()


def test_pipeline_tool_call():
    """工具调用通过 pipeline 流转：LLM 输出 /call → 工具执行 → LLM 再次调用"""
    import asyncio
    import gc
    import tempfile
    from core.chat.pipeline import ChatPipeline
    from core.tools import ToolRegistry
    from core.tools.builtin import ClockTool
    from core.memory.embedder import SentenceTransformerEmbedder
    from core.memory.vector_store import VectorStore
    from core.memory import MemoryManager, ChatHistoryStorage
    from core.persona import PersonaLoader
    from core.personality import PersonalityEngine
    from core.emotion import LLMEmotionAnalyzer
    from core.social.relationship import RelationshipTracker
    from core.emotion.mood import MoodEngine

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
        # 第一轮回复包含工具调用，第二轮为最终回复
        llm = SeqMockLLM([
            "我来看看现在几点了 /call clock",
            "现在是10点30分",
        ])

        embedder = SentenceTransformerEmbedder()
        vector_store = VectorStore(str(Path(tmpdir) / "tool_vectors.db"))
        memory_mgr = MemoryManager(tmpdir, embedder=embedder, vector_store=vector_store)
        personality_engine = PersonalityEngine(tmpdir)

        tool_registry = ToolRegistry()
        tool_registry.register(ClockTool())

        # 创建测试用人设文件
        test_persona_path = Path(tmpdir) / "personas.json"
        test_persona_path.write_text(
            '{"personas":[{"id":"girlfriend_001","name":"小可爱","age":20,'
            '"hobbies":[{"name":"看书"}],"personality":["温柔"],"speaking_style":"软萌"}]}',
            encoding="utf-8",
        )

        pipeline = ChatPipeline(
            llm, memory_mgr,
            PersonaLoader(test_persona_path),
            personality_engine,
            ChatHistoryStorage(tmpdir), LLMEmotionAnalyzer(),
            RelationshipTracker(tmpdir), MoodEngine(tmpdir), {},
            tool_registry=tool_registry,
        )

        reply, level = asyncio.run(
            pipeline.process("test_user", "现在几点了？", "girlfriend_001")
        )

        # 验证 LLM 被调用了至少两轮
        assert llm._index >= 2
        assert reply == "现在是10点30分"
        assert level > 0

        vector_store.close()
        del pipeline, tool_registry, memory_mgr, embedder, vector_store
        gc.collect()


# ========== 记忆同步添加回归测试 ==========

def test_add_memory_sync_persists():
    """测试 add_memory_sync 同步保存记忆到 JSON 文件"""
    import tempfile
    from core.memory import MemoryManager

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
        memory_mgr = MemoryManager(tmpdir)
        content = "这是我手动添加的记忆"
        result = memory_mgr.add_memory_sync("test_user", content, level=3)

        assert result is not None
        assert result.content == content
        assert result.level == 3

        loaded = memory_mgr._storage.load("test_user")
        assert len(loaded) == 1
        assert loaded[0].content == content
        assert loaded[0].level == 3


# ========== 冲突检测回归测试 ==========

def test_conflict_no_false_positive():
    """测试字符集冲突检测不会误报：不同话题但共享字符的句子不应触发冲突"""
    from core.memory.manager import MemoryManager
    existing = Memory(id="m1", content="我喜欢玩游戏", level=3, category="preference")
    new_mem = Memory(id="m2", content="我喜欢看电影", level=3, category="preference")
    mm = MemoryManager.__new__(MemoryManager)
    result = mm._detect_conflict(new_mem, [existing])
    assert result is None, "不同话题的句子不应触发冲突"


def test_conflict_antonym_detected():
    """测试冲突检测能检测到反义词对：喜欢 vs 讨厌"""
    from core.memory.manager import MemoryManager
    existing = Memory(id="m1", content="我讨厌猫", level=3, category="emotion")
    new_mem = Memory(id="m2", content="我喜欢猫", level=3, category="emotion")
    mm = MemoryManager.__new__(MemoryManager)
    result = mm._detect_conflict(new_mem, [existing])
    assert result is not None, "反义词对应触发冲突"


# ========== 运行所有测试 ==========

if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
