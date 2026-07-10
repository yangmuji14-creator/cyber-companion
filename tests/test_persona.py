"""Person module unit tests""" 

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.persona.models import Persona
from core.persona.prompt_builder import PromptBuilder


def test_persona_to_dict():
    p = Persona(id="test_001", name="测试", age=20, gender="女", hometown="北京",
                personality=["温柔", "活泼"], mbti="INFP",
                hobbies=[{"name": "看书", "detail": "喜欢推理小说", "level": "喜欢"}],
                catchphrases=["诶嘿"], values=["真诚"], taboos=["说谎"],
                happy_expression="会发很多颜文字", nickname_for_user="笨蛋")
    d = p.to_dict()
    assert d["id"] == "test_001"
    assert d["name"] == "测试"
    assert d["hometown"] == "北京"
    assert d["mbti"] == "INFP"
    assert d["hobbies"] == [{"name": "看书", "detail": "喜欢推理小说", "level": "喜欢"}]
    assert d["catchphrases"] == ["诶嘿"]
    assert d["nickname_for_user"] == "笨蛋"


def test_persona_to_dict_omits_defaults():
    p = Persona(id="t", name="T")
    d = p.to_dict()
    assert "mbti" not in d
    assert "hometown" not in d
    assert "hobbies" not in d
    assert "catchphrases" not in d
    assert "nickname_for_user" not in d
    assert "id" in d
    assert "name" in d


def test_persona_from_dict_backward_compat():
    old_data = {"id": "old_001", "name": "旧角色", "age": 18, "personality": ["温柔"],
                "background": "大学生", "speaking_style": "可爱",
                "core_memories": ["记得某事"], "relationship_level": 60, "system_prompt": ""}
    p = Persona.from_dict(old_data)
    assert p.id == "old_001"
    assert p.mbti == ""
    assert p.hobbies == []
    assert p.catchphrases == []


def test_prompt_basic():
    p = Persona(id="t", name="小测试", age=20, gender="女", personality=["温柔"])
    prompt = PromptBuilder.build(p)
    assert "小测试" in prompt
    assert "20岁" in prompt


def test_prompt_with_full_persona():
    p = Persona(id="t", name="小测试", age=20, gender="女", personality=["温柔"],
                hometown="成都", occupation="大学生", mbti="INFP",
                catchphrases=["诶嘿"], nickname_for_user="笨蛋",
                happy_expression="会发很多消息", values=["真诚"], taboos=["说谎"],
                how_we_met="社团认识的", favorite_topics=["动漫"], avoided_topics=["前任"])
    prompt = PromptBuilder.build(p)
    assert "小测试" in prompt
    assert "20岁" in prompt
    assert "成都" in prompt
    assert "INFP" in prompt
    assert "诶嘿" in prompt
    assert "笨蛋" in prompt
    assert "社团认识的" in prompt
    # 叙事化prompt不再逐项列出情绪反应和价值观，但核心身份信息都有


def test_prompt_empty_fields():
    p = Persona(id="t", name="T", personality=[])
    prompt = PromptBuilder.build(p)
    assert isinstance(prompt, str)
    assert len(prompt) > 0


def test_prompt_with_relationship_level():
    p = Persona(id="t", name="T", personality=[], relationship_level=50)
    prompt_low = PromptBuilder.build(p, relationship_level=10)
    prompt_high = PromptBuilder.build(p, relationship_level=90)
    assert "刚认识" in prompt_low
    assert "在一起很久" in prompt_high


def test_prompt_hobbies():
    p = Persona(id="t", name="T", personality=[],
                hobbies=[{"name": "看动漫", "detail": "最爱EVA", "level": "狂热"}],
                music_taste="日系", food_preferences="火锅")
    prompt = PromptBuilder.build(p)
    assert "看动漫" in prompt
    assert "日系" in prompt
    assert "火锅" in prompt


def test_prompt_emotions():
    """叙事化prompt不再逐项列出情绪反应模式，只验证核心结构"""
    p = Persona(id="t", name="T", personality=[],
                happy_expression="会发很多消息", sad_expression="变安静",
                angry_expression="冷淡", jealous_expression="阴阳怪气",
                shy_expression="转移话题")
    prompt = PromptBuilder.build(p)
    # 验证叙事化prompt结构完整
    assert "你是T" in prompt
    assert "说话的时候记住" in prompt
    assert "像真人聊微信" in prompt


def test_prompt_behavior_rules():
    p = Persona(id="t", name="T", personality=[],
                catchphrases=["诶嘿"], filler_words=["嘿嘿"], nickname_for_user="笨蛋")
    prompt = PromptBuilder.build(p)
    assert "诶嘿" in prompt
    assert "笨蛋" in prompt
    assert "口头禅" in prompt


def test_loader_save_and_load():
    from core.persona.loader import PersonaLoader
    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = Path(tmpdir) / "personas.json"
        config_path.write_text(r'{"personas": [{"id": "test", "name": "测试"}]}', encoding="utf-8")
        loader = PersonaLoader(str(config_path))
        persona = loader.get("test")
        assert persona is not None
        assert persona.name == "测试"


def test_loader_add_new_fields():
    from core.persona.loader import PersonaLoader
    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = Path(tmpdir) / "personas.json"
        config_path.write_text(r'{"personas": []}', encoding="utf-8")
        loader = PersonaLoader(str(config_path))
        p = Persona(id="new", name="新人设", mbti="ENFP", catchphrases=["哈喽"],
                    hobbies=[{"name": "唱歌", "detail": "唱周杰伦", "level": "喜欢"}])
        loader.add(p)
        loader2 = PersonaLoader(str(config_path))
        loaded = loader2.get("new")
        assert loaded is not None
        assert loaded.mbti == "ENFP"
        assert loaded.catchphrases == ["哈喽"]
