"""大脑模块自测脚本

检查所有 Brain 模块组件是否可以正常导入和初始化，
运行基础烟雾测试，打印状态摘要。

用法:
    python -m core.brain.self_test
"""

import importlib
import sys
import traceback
from dataclasses import dataclass, field
from types import ModuleType

if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass


# ═══════════════════════════════════════════
# 测试结果收集
# ═══════════════════════════════════════════

@dataclass
class TestResult:
    """单个测试结果"""
    name: str
    passed: bool = False
    detail: str = ""


@dataclass
class TestSuite:
    """测试套件"""
    results: list[TestResult] = field(default_factory=list)

    def add(self, name: str, passed: bool, detail: str = ""):
        self.results.append(TestResult(name=name, passed=passed, detail=detail))

    @property
    def total(self) -> int:
        return len(self.results)

    @property
    def passed_count(self) -> int:
        return sum(1 for r in self.results if r.passed)

    @property
    def failed_count(self) -> int:
        return sum(1 for r in self.results if not r.passed)

    @property
    def all_passed(self) -> bool:
        return self.failed_count == 0


# ═══════════════════════════════════════════
# 组件导入测试
# ═══════════════════════════════════════════

def _import(module_path: str) -> ModuleType | None:
    """安全导入模块，失败时返回 None"""
    try:
        return importlib.import_module(module_path)
    except Exception:
        return None


def test_imports(suite: TestSuite) -> dict[str, type]:
    """测试所有 Brain 模块组件的导入

    Returns:
        成功导入的组件名 → 类型的映射
    """
    components: dict[str, type] = {}
    imports = [
        ("BrainConfig", "core.brain.models", "BrainConfig"),
        ("BrainInput", "core.brain.models", "BrainInput"),
        ("BrainOutput", "core.brain.models", "BrainOutput"),
        ("MonologueThought", "core.brain.models", "MonologueThought"),
        ("BrainDisabledError", "core.brain.models", "BrainDisabledError"),
        ("StateCollector", "core.brain.collector", "StateCollector"),
        ("ThoughtOrganizer", "core.brain.organizer", "ThoughtOrganizer"),
        ("MonologueWeaver", "core.brain.weaver", "MonologueWeaver"),
        ("MemoryTrigger", "core.brain.triggers", "MemoryTrigger"),
        ("CharacterBreakDetector", "core.brain.checker", "CharacterBreakDetector"),
        ("CharacterBreakResult", "core.brain.checker", "CharacterBreakResult"),
        ("BrainCoordinator", "core.brain.coordinator", "BrainCoordinator"),
    ]

    for label, module_name, class_name in imports:
        mod = _import(module_name)
        if mod is None:
            suite.add(label, False, f"Module '{module_name}' import failed")
            continue
        cls = getattr(mod, class_name, None)
        if cls is None:
            suite.add(label, False, f"Class '{class_name}' not found in {module_name}")
            continue
        suite.add(label, True, f"from {module_name} import {class_name}")
        components[label] = cls

    return components


# ═══════════════════════════════════════════
# 烟雾测试
# ═══════════════════════════════════════════

def test_models(suite: TestSuite, components: dict[str, type]):
    """测试数据模型实例化"""
    # BrainConfig
    BrainConfig = components.get("BrainConfig")
    if BrainConfig:
        try:
            cfg = BrainConfig(enabled=True, max_tokens=500, debug=False, checker_enabled=True)
            assert cfg.enabled is True
            assert cfg.max_tokens == 500
            suite.add("BrainConfig()", True, "Instantiation OK")
        except Exception as e:
            suite.add("BrainConfig()", False, str(e))
    else:
        suite.add("BrainConfig()", False, "Not imported")

    # BrainInput
    BrainInput = components.get("BrainInput")
    if BrainInput:
        try:
            inp = BrainInput(mood_valence=0.8, mood_arousal=0.3)
            assert inp.mood_valence == 0.8
            assert inp.mood_arousal == 0.3
            suite.add("BrainInput()", True, "Instantiation OK")
        except Exception as e:
            suite.add("BrainInput()", False, str(e))
    else:
        suite.add("BrainInput()", False, "Not imported")

    # BrainOutput
    BrainOutput = components.get("BrainOutput")
    MonologueThought = components.get("MonologueThought")
    if BrainOutput and MonologueThought:
        try:
            thought = MonologueThought(source="test", content="测试思考", priority=0.5)
            output = BrainOutput(monologue="测试独白", thoughts=[thought])
            assert output.monologue == "测试独白"
            assert len(output.thoughts) == 1
            assert output.thoughts[0].source == "test"
            suite.add("BrainOutput()", True, "Instantiation OK")
        except Exception as e:
            suite.add("BrainOutput()", False, str(e))
    else:
        suite.add("BrainOutput()", False, "Not imported")

    # BrainDisabledError
    BrainDisabledError = components.get("BrainDisabledError")
    if BrainDisabledError:
        try:
            err = BrainDisabledError("test")
            assert str(err) == "test"
            suite.add("BrainDisabledError()", True, "Instantiation OK")
        except Exception as e:
            suite.add("BrainDisabledError()", False, str(e))
    else:
        suite.add("BrainDisabledError()", False, "Not imported")


def test_state_collector(suite: TestSuite, components: dict[str, type]):
    """测试 StateCollector（无依赖模式）"""
    StateCollector = components.get("StateCollector")
    if not StateCollector:
        suite.add("StateCollector()", False, "Not imported")
        return

    try:
        collector = StateCollector()
        suite.add("StateCollector()", True, "Instantiation with no args OK")
    except Exception as e:
        suite.add("StateCollector()", False, str(e))
        return

    # 异步 collect 测试（需要事件循环）
    import asyncio
    try:
        result = asyncio.run(collector.collect("test_user"))
        suite.add("StateCollector.collect()", True, f"Returned BrainInput with {len([a for a in dir(result) if not a.startswith('_')])} fields")
    except Exception as e:
        suite.add("StateCollector.collect()", False, str(e))


def test_thought_organizer(suite: TestSuite, components: dict[str, type]):
    """测试 ThoughtOrganizer"""
    ThoughtOrganizer = components.get("ThoughtOrganizer")
    BrainInput = components.get("BrainInput")
    if not ThoughtOrganizer or not BrainInput:
        suite.add("ThoughtOrganizer()", False, "Not imported")
        return

    try:
        org = ThoughtOrganizer(max_tokens=1000)
        inp = BrainInput(
            mood_valence=0.9, mood_arousal=0.7, mood_type="happy",
            time_period="morning",
        )
        thoughts = org.organize(inp)
        assert len(thoughts) >= 1
        suite.add("ThoughtOrganizer.organize()", True, f"Generated {len(thoughts)} thoughts")
    except Exception as e:
        suite.add("ThoughtOrganizer.organize()", False, str(e))

    # 空输入测试
    try:
        empty = BrainInput()
        thoughts = org.organize(empty)
        assert len(thoughts) >= 1  # 应该返回默认念头
        suite.add("ThoughtOrganizer.organize(empty)", True, f"Default thought: {thoughts[0].content}")
    except Exception as e:
        suite.add("ThoughtOrganizer.organize(empty)", False, str(e))


def test_monologue_weaver(suite: TestSuite, components: dict[str, type]):
    """测试 MonologueWeaver"""
    MonologueWeaver = components.get("MonologueWeaver")
    MonologueThought = components.get("MonologueThought")
    if not MonologueWeaver or not MonologueThought:
        suite.add("MonologueWeaver()", False, "Not imported")
        return

    try:
        weaver = MonologueWeaver(max_tokens=1000)
        thoughts = [
            MonologueThought(source="mood", content="我心情不错", priority=0.9, category="feeling"),
            MonologueThought(source="time", content="现在是早上", priority=0.2, category="observation"),
        ]
        monologue = weaver.weave(thoughts)
        assert len(monologue) > 0
        assert "我心情不错" in monologue
        suite.add("MonologueWeaver.weave()", True, f"Output: {monologue[:30]}…")
    except Exception as e:
        suite.add("MonologueWeaver.weave()", False, str(e))

    # weave_debug 测试
    try:
        debug = weaver.weave_debug(thoughts)
        assert "[mood]" in debug
        suite.add("MonologueWeaver.weave_debug()", True, f"Debug output: {debug[:30]}…")
    except Exception as e:
        suite.add("MonologueWeaver.weave_debug()", False, str(e))

    # 空输入测试
    try:
        fallback = weaver.weave([])
        assert fallback == "此时我心里很平静。"
        suite.add("MonologueWeaver.weave([])", True, "Fallback OK")
    except Exception as e:
        suite.add("MonologueWeaver.weave([])", False, str(e))


def test_character_break_detector(suite: TestSuite, components: dict[str, type]):
    """测试 CharacterBreakDetector"""
    CharacterBreakDetector = components.get("CharacterBreakDetector")
    if not CharacterBreakDetector:
        suite.add("CharacterBreakDetector()", False, "Not imported")
        return

    try:
        detector = CharacterBreakDetector(persona_name="小雨")
        # 正常回复
        normal = detector.check("今天天气真好呀")
        assert not normal.is_break
        suite.add("CharacterBreakDetector.check(normal)", True, "No break detected")
    except Exception as e:
        suite.add("CharacterBreakDetector.check(normal)", False, str(e))

    try:
        detector = CharacterBreakDetector(persona_name="小雨")
        # AI 语气回复
        broken = detector.check("作为AI，我今天天气真好呀")
        assert broken.is_break
        suite.add("CharacterBreakDetector.check(broken)", True, f"Break detected: {broken.trigger_phrase}")
    except Exception as e:
        suite.add("CharacterBreakDetector.check(broken)", False, str(e))

    try:
        detector = CharacterBreakDetector(persona_name="小雨")
        # 用户先提到 AI，AI 回复 AI 相关内容不算崩塌
        result = detector.check("作为AI助手", user_message="你是不是AI")
        assert not result.is_break
        suite.add("CharacterBreakDetector.context_aware", True, "User mentioned AI, bypass OK")
    except Exception as e:
        suite.add("CharacterBreakDetector.context_aware", False, str(e))


def test_memory_trigger(suite: TestSuite, components: dict[str, type]):
    """测试 MemoryTrigger"""
    MemoryTrigger = components.get("MemoryTrigger")
    if not MemoryTrigger:
        suite.add("MemoryTrigger()", False, "Not imported")
        return

    try:
        trigger = MemoryTrigger(memory_mgr=None)
        suite.add("MemoryTrigger(None)", True, "Instantiation with None OK")
    except Exception as e:
        suite.add("MemoryTrigger(None)", False, str(e))
        return

    # 重置每日计数
    try:
        trigger.reset_daily()
        suite.add("MemoryTrigger.reset_daily()", True, "OK")
    except Exception as e:
        suite.add("MemoryTrigger.reset_daily()", False, str(e))


def test_brain_coordinator(suite: TestSuite, components: dict[str, type]):
    """测试 BrainCoordinator"""
    BrainCoordinator = components.get("BrainCoordinator")
    BrainConfig = components.get("BrainConfig")
    if not BrainCoordinator or not BrainConfig:
        suite.add("BrainCoordinator()", False, "Not imported")
        return

    # 实例化（所有依赖 None）
    try:
        cfg = BrainConfig(enabled=True, max_tokens=500, debug=False)
        coordinator = BrainCoordinator(cfg)
        assert coordinator.config.enabled
        assert coordinator.collector is not None
        assert coordinator.organizer is not None
        assert coordinator.weaver is not None
        assert coordinator.checker is not None
        assert coordinator.memory_trigger is None  # 未传 memory_mgr
        suite.add("BrainCoordinator()", True, "All components initialized")
    except Exception as e:
        suite.add("BrainCoordinator()", False, str(e))
        return

    # get_debug_info
    try:
        info = coordinator.get_debug_info()
        assert "config" in info
        assert "components" in info
        assert info["components"]["collector"] is True
        assert info["components"]["memory_trigger"] is False  # None
        suite.add("BrainCoordinator.get_debug_info()", True, "Debug info OK")
    except Exception as e:
        suite.add("BrainCoordinator.get_debug_info()", False, str(e))

    # check_character_break
    import asyncio
    try:
        broken = asyncio.run(coordinator.check_character_break("作为AI，你好"))
        assert broken is True
        suite.add("BrainCoordinator.check_character_break()", True, "Detected AI pattern")
    except Exception as e:
        suite.add("BrainCoordinator.check_character_break()", False, str(e))


# ═══════════════════════════════════════════
# 主入口
# ═══════════════════════════════════════════

def run_all() -> TestSuite:
    """运行所有测试"""
    suite = TestSuite()

    print("=" * 52)
    print("  Brain Module Self-Test")
    print("=" * 52)

    # 1. 导入测试
    print("\n  -- Import Tests --")
    components = test_imports(suite)

    if not components:
        print("  FAIL: No components could be imported!")
        return suite

    # 2. 模型测试
    print("\n  -- Model Tests --")
    test_models(suite, components)

    # 3. 组件测试
    print("\n  -- Component Tests --")
    test_state_collector(suite, components)
    test_thought_organizer(suite, components)
    test_monologue_weaver(suite, components)
    test_character_break_detector(suite, components)
    test_memory_trigger(suite, components)
    test_brain_coordinator(suite, components)

    return suite


def print_summary(suite: TestSuite, components: dict[str, type]):
    """打印最终摘要"""
    print()
    print("=" * 52)

    if suite.all_passed:
        print("  [OK] Brain Module Status: OK")
    else:
        print("  [FAIL] Brain Module Status: DEGRADED")
    print()

    # 组件状态
    component_map = {
        "StateCollector": "StateCollector" in components,
        "ThoughtOrganizer": "ThoughtOrganizer" in components,
        "MonologueWeaver": "MonologueWeaver" in components,
        "CharacterBreakDetector": "CharacterBreakDetector" in components,
        "MemoryTrigger": "MemoryTrigger" in components,
        "BrainCoordinator": "BrainCoordinator" in components,
    }
    for name, ok in component_map.items():
        icon = "[OK]" if ok else "[--]"
        print(f"    {icon} {name}")

    print()

    # 配置信息
    try:
        from core.config import load_advanced
        cfg = load_advanced()
        brain_enabled = cfg.get("brain_enabled", True)
        max_tokens = cfg.get("brain_max_tokens", 1000)
        debug = cfg.get("brain_debug", False)
        checker = cfg.get("checker_enabled", True)
        print(f"    Config: enabled={brain_enabled}, max_tokens={max_tokens}, "
              f"debug={debug}, checker={checker}")
    except Exception:
        print("    Config: (unavailable - core.config not accessible)")

    print()

    # 测试计数
    print(f"    Tests: {suite.passed_count}/{suite.total} passed")
    if suite.failed_count > 0:
        print()
        print("  -- Failed Tests --")
        for r in suite.results:
            if not r.passed:
                print(f"    FAIL {r.name}: {r.detail}")

    print("=" * 52)


def main():
    """主入口"""
    suite = run_all()

    print()
    print_summary(suite, _get_imported_components())

    # 返回退出码
    return 0 if suite.all_passed else 1


def _get_imported_components() -> dict[str, type]:
    """获取已成功导入的组件（从 suite 中推断）"""
    result: dict[str, type] = {}
    try:
        from core.brain.models import BrainConfig, BrainInput, BrainOutput, BrainDisabledError, MonologueThought
        result["BrainConfig"] = BrainConfig
        result["BrainInput"] = BrainInput
        result["BrainOutput"] = BrainOutput
        result["BrainDisabledError"] = BrainDisabledError
        result["MonologueThought"] = MonologueThought
    except Exception:
        pass
    try:
        from core.brain.collector import StateCollector
        result["StateCollector"] = StateCollector
    except Exception:
        pass
    try:
        from core.brain.organizer import ThoughtOrganizer
        result["ThoughtOrganizer"] = ThoughtOrganizer
    except Exception:
        pass
    try:
        from core.brain.weaver import MonologueWeaver
        result["MonologueWeaver"] = MonologueWeaver
    except Exception:
        pass
    try:
        from core.brain.triggers import MemoryTrigger
        result["MemoryTrigger"] = MemoryTrigger
    except Exception:
        pass
    try:
        from core.brain.checker import CharacterBreakDetector, CharacterBreakResult
        result["CharacterBreakDetector"] = CharacterBreakDetector
        result["CharacterBreakResult"] = CharacterBreakResult
    except Exception:
        pass
    try:
        from core.brain.coordinator import BrainCoordinator
        result["BrainCoordinator"] = BrainCoordinator
    except Exception:
        pass
    return result


if __name__ == "__main__":
    sys.exit(main())
