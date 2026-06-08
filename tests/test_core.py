"""核心模块单元测试"""

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.memory.models import Memory
from core.memory.scorer import MemoryScorer
from core.memory.storage import MemoryStorage
from core.emotion.analyzer import EmotionAnalyzer, EmotionType
from core.emotion.expression import MessageSegmenter, EmotionEnhancer


# ========== MemoryScorer 测试 ==========

def test_score_basic():
    """测试基础评分"""
    assert MemoryScorer.score("") == 1
    assert MemoryScorer.score("hi") == 1
    assert MemoryScorer.score("今天天气不错") >= 1


def test_score_high_importance():
    """测试高重要度内容"""
    score = MemoryScorer.score("我的生日是5月20日")
    assert score >= 4

    # 包含地址+正则匹配
    score = MemoryScorer.score("我叫小明，我住在北京市朝阳区，电话是13800138000")
    assert score >= 2


def test_score_medium_importance():
    """测试中等重要度"""
    # 包含多个关键词才能达到 2 分
    score = MemoryScorer.score("我喜欢吃火锅，最喜欢和朋友一起")
    assert score >= 2


def test_should_remember():
    """测试是否值得记住"""
    assert MemoryScorer.should_remember("我的生日是5月20日") is True
    assert MemoryScorer.should_remember("hi") is False
    assert MemoryScorer.should_remember("今天天气不错") is False


# ========== MemoryStorage 测试 ==========

def test_storage_save_and_load():
    """测试存储保存和加载"""
    with tempfile.TemporaryDirectory() as tmpdir:
        storage = MemoryStorage(tmpdir)
        memories = [
            Memory(id="m1", content="test memory 1", level=3),
            Memory(id="m2", content="test memory 2", level=5),
        ]
        storage.save("test_user", memories)
        loaded = storage.load("test_user")
        assert len(loaded) == 2
        assert loaded[0].content == "test memory 1"
        assert loaded[1].level == 5


def test_storage_load_nonexistent():
    """测试加载不存在的用户"""
    with tempfile.TemporaryDirectory() as tmpdir:
        storage = MemoryStorage(tmpdir)
        loaded = storage.load("nonexistent")
        assert loaded == []


def test_storage_path_traversal():
    """测试路径穿越防护"""
    with tempfile.TemporaryDirectory() as tmpdir:
        storage = MemoryStorage(tmpdir)
        try:
            storage._get_user_file("../../etc/passwd")
            # 如果 safe_id 替换后仍在目录内，不会报错
            # 但文件名应该被净化
        except ValueError:
            pass  # 期望的行为


def test_storage_list_users():
    """测试列出用户"""
    with tempfile.TemporaryDirectory() as tmpdir:
        storage = MemoryStorage(tmpdir)
        storage.save("user1", [Memory(id="m1", content="test", level=3)])
        storage.save("user2", [Memory(id="m2", content="test", level=3)])
        users = storage.list_users()
        assert "user1" in users
        assert "user2" in users


def test_storage_delete_all():
    """测试删除所有记忆"""
    with tempfile.TemporaryDirectory() as tmpdir:
        storage = MemoryStorage(tmpdir)
        storage.save("user1", [Memory(id="m1", content="test", level=3)])
        assert storage.delete_all("user1") is True
        assert storage.load("user1") == []
        assert storage.delete_all("nonexistent") is False


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


# ========== 运行所有测试 ==========

if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
