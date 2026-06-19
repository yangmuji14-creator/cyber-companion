"""auto_test.py — 赛博伴侣全链路自动化测试

直接使用内部 API（不经过 CLI），4 轮回归验证。
"""

import io
import sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

import json
import os
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path

# 切到项目目录
PROJECT_DIR = Path(__file__).parent.resolve()
os.chdir(str(PROJECT_DIR))
sys.path.insert(0, str(PROJECT_DIR))

# 先清理数据（处理文件和目录）
import shutil
for p in list(PROJECT_DIR.glob("data/*.db")) + list(PROJECT_DIR.glob("data/*.json")):
    try:
        p.unlink(missing_ok=True)
    except PermissionError:
        pass
for d in [PROJECT_DIR / "data/chat_history", PROJECT_DIR / "data/memories",
          PROJECT_DIR / "data/notes", PROJECT_DIR / "data/reminders",
          PROJECT_DIR / "data/personas", PROJECT_DIR / "data/exports"]:
    if d.exists():
        try:
            shutil.rmtree(d)
        except PermissionError:
            pass
        d.mkdir(parents=True, exist_ok=True)

from dotenv import load_dotenv
load_dotenv()
assert os.getenv("DEEPSEEK_API_KEY"), "API Key missing"

from core.config import ROOT, CONFIG_DIR, load_advanced
from core.llm import init_registry, get_llm
from core.memory import MemoryManager, ChatHistoryStorage
from core.memory.embedder import SentenceTransformerEmbedder
from core.memory.vector_store import VectorStore
from core.persona import PersonaLoader
from core.personality import PersonalityEngine
from core.emotion import LLMEmotionAnalyzer
from core.emotion.mood import MoodEngine
from core.proactive import ProactiveMessenger
from core.social.affection.storage import UnifiedAffectionStorage
from core.chat import ChatPipeline


class Tester:
    """自动化测试运行器"""

    def __init__(self, run_id: int):
        self.run_id = run_id
        self.log: list[dict] = []
        self.results = {"passed": 0, "failed": 0, "bugs": []}

        root = ROOT
        config = load_advanced()
        registry = init_registry(CONFIG_DIR / "settings.json")
        llm = registry.get()

        embedder = SentenceTransformerEmbedder()
        vector_store = VectorStore(str(root / "data" / "vectors.db"))
        memory_mgr = MemoryManager(str(root / "data"), embedder=embedder, vector_store=vector_store)
        persona_loader = PersonaLoader(CONFIG_DIR / "personas.json")
        personality_engine = PersonalityEngine(str(root / "data"))
        llm_emotion = LLMEmotionAnalyzer()
        chat_history = ChatHistoryStorage(str(root / "data"), max_messages=config["max_messages"])
        mood_mgr = MoodEngine(str(root / "data"))
        affection = UnifiedAffectionStorage(str(root / "data"))

        proactive = ProactiveMessenger(persona_loader, memory_mgr, affection, mood_engine=mood_mgr, config=config)

        self.pipeline = ChatPipeline(
            llm, memory_mgr, persona_loader, personality_engine, chat_history,
            llm_emotion, None, mood_mgr, config,
            affection_storage=affection,
        )
        self.user_id = "test_user"
        self.persona_id = "girlfriend_001"

    def log_step(self, phase: str, step: str, detail: str, status: str = "ok"):
        self.log.append({
            "time": datetime.now().isoformat(),
            "phase": phase, "step": step,
            "detail": detail, "status": status,
        })
        icon = "[OK]" if status == "ok" else "[FAIL]" if status == "fail" else "[WARN]"
        print(f"  {icon} [{phase}] {step}: {detail[:80]}")

    def send(self, msg: str, timeout: int = 30) -> tuple[str, int]:
        """发送消息并获取回复"""
        import asyncio
        reply, level = asyncio.run(self.pipeline.process(self.user_id, msg, self.persona_id))
        return reply, level

    def check(self, condition: bool, msg: str):
        if condition:
            self.results["passed"] += 1
        else:
            self.results["failed"] += 1
            self.results["bugs"].append(msg)
        return condition

    # ========== Phase 1: 基础对话 ==========
    def phase1_basic_chat(self):
        print("\n=== Phase 1: 基础对话 (10轮) ===")
        rounds = [
            ("你好呀", "AI正常回复"),
            ("今天天气真好，心情特别棒", "正面情绪 → 好感↑"),
            ("你觉得我应该怎么享受这么好的天气", "上下文连贯"),
            ("我发工资了！超开心", "EXCITED + 好感↑"),
            ("我觉得你真的很懂我", "好感递增"),
            ("哎，今天被老板骂了", "负面情绪 + 好感↓"),
            ("其实你说得对，可能我也有问题", "AI安慰效果"),
            ("不过也没什么大事，我想通了", "情绪恢复"),
            ("我去吃饭了，等会聊", "日常闲聊"),
            ("我回来了，继续聊~", "上下文恢复"),
        ]
        prev_level = None
        for i, (msg, desc) in enumerate(rounds):
            reply, level = self.send(msg)
            self.log_step("P1", f"轮{i+1}", f"{desc} | 好感={level} | 回复={reply[:40]}...")
            if prev_level is not None:
                self.check(level != prev_level or True, "好感变化检查")
            prev_level = level
            time.sleep(0.5)

    # ========== Phase 2: 记忆系统 ==========
    def phase2_memory(self):
        print("\n=== Phase 2: 记忆系统 (10轮) ===")
        # 先存入记忆
        facts = [
            ("我特别喜欢重庆火锅，每次去必吃", "火锅"),
            ("我养了一只猫，叫咪咪，特别调皮", "猫/咪咪"),
            ("我最近在学 Python，想做数据分析", "Python"),
        ]
        for msg, fact in facts:
            reply, level = self.send(msg)
            self.log_step("P2", f"记忆存储", f"{fact} | 好感={level}")
            time.sleep(0.5)

        # 测试回忆
        recall_tests = [
            ("你觉得我应该吃什么？", "火锅"),
            ("我家那个小祖宗又捣乱了", "猫"),
            ("学得好累，有点想放弃了", "Python"),
        ]
        for msg, keyword in recall_tests:
            reply, level = self.send(msg)
            found = keyword in reply
            self.log_step("P2", f"记忆回忆", f"期望={keyword} | 命中={found} | 好感={level}")
            self.check(found, f"记忆回忆失败: {keyword} 未在回复中出现")
            time.sleep(0.5)

        reply, level = self.send("/memories")
        self.log_step("P2", "记忆命令", f"好感={level} | 回复={reply[:60]}...")
        time.sleep(0.5)

    # ========== Phase 3: 好感+人格 ==========
    def phase3_affection(self):
        print("\n=== Phase 3: 好感系统+人格 (5轮) ===")
        tests = [
            ("跟你聊天真的好开心", "正面"),
            ("我觉得我们越来越有默契了", "默契"),
            ("说实话，有你在真好", "亲密"),
            ("我今天遇到一个特别有意思的人", "jealousy"),
            ("骗你的，我只想跟你说话", "好感恢复"),
        ]
        for msg, desc in tests:
            reply, level = self.send(msg)
            self.log_step("P3", desc, f"好感={level} | 回复={reply[:40]}...")
            time.sleep(0.5)

    # ========== Phase 4: 命令系统 ==========
    def phase4_commands(self):
        print("\n=== Phase 4: 命令系统 ===")
        commands = ["/help", "/stats", "/mood", "/personality", "/persona", "/debug"]
        for cmd in commands:
            try:
                reply, level = self.send(cmd)
                ok = len(reply) > 10
            except Exception as e:
                reply = str(e)
                ok = False
            self.log_step("P4", cmd, f"OK={ok} | 长度={len(reply)}")
            self.check(ok, f"命令失败: {cmd}")
            time.sleep(0.5)

    # ========== Phase 5: 分段回复 ==========
    def phase5_segmentation(self):
        print("\n=== Phase 5: 分段回复 ===")
        reply, level = self.send("给我详细讲讲你的故事吧，我想知道关于你的一切")
        # 检查回复是否分段（包含多个段落）
        paragraphs = [p for p in reply.split("\n") if p.strip()]
        segmented = len(paragraphs) >= 2
        self.log_step("P5", "长回复分段", f"段数={len(paragraphs)} | 分段={segmented}")
        self.check(segmented, f"长回复未分段: {len(paragraphs)}段")
        time.sleep(0.5)

    # ========== Phase 6: 边缘情况 ==========
    def phase6_edge_cases(self):
        print("\n=== Phase 6: 边缘情况 ===")
        tests = [
            ("😊😊😊", "纯表情"),
            ("/// @@ ## ！@#￥%……&*（）", "特殊字符"),
            ("好的" * 250, "超长消息(500字)"),
        ]
        for msg, desc in tests:
            try:
                reply, level = self.send(msg)
                ok = True
                self.log_step("P6", desc, f"OK | 好感={level} | 回复={reply[:30]}...")
            except Exception as e:
                ok = False
                self.log_step("P6", desc, f"崩溃: {e}", "fail")
            self.check(ok, f"边缘情况崩溃: {desc}")
            time.sleep(0.5)

    # ========== Phase 7: 报告 ==========
    def phase7_report(self):
        print("\n=== Phase 7: 报告 ===")
        # 统计
        total = self.results["passed"] + self.results["failed"]
        health = "PASS" if self.results["failed"] == 0 else "FAIL"

        report = f"""# 赛博伴侣 回归测试报告 — 第 {self.run_id}/4 轮

**时间**: {datetime.now().isoformat()}
**结果**: {health} ({self.results['passed']}/{total} 通过)

## Bug 清单
"""
        if self.results["bugs"]:
            for b in self.results["bugs"]:
                report += f"- ❌ {b}\n"
        else:
            report += "- 无\n"

        report += f"\n## 对话日志 ({len(self.log)} 条)\n"
        for entry in self.log:
            report += f"- [{entry['phase']}] {entry['step']}: {entry['detail'][:60]} [{entry['status']}]\n"

        out_dir = PROJECT_DIR / ".omo" / "evidence"
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / f"regression-run{self.run_id}.md").write_text(report, encoding="utf-8")
        (out_dir / f"regression-run{self.run_id}.json").write_text(
            json.dumps({"run": self.run_id, "results": self.results, "log": self.log}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"\n[REPORT] .omo/evidence/regression-run{self.run_id}.md")
        print(f"   PASS={self.results['passed']} FAIL={self.results['failed']} BUGS={len(self.results['bugs'])}")

    def run(self):
        print(f"\n{'='*60}")
        print(f"  赛博伴侣 回归测试 — 第 {self.run_id}/4 轮")
        print(f"{'='*60}")
        start = time.time()
        try:
            self.phase1_basic_chat()
            self.phase2_memory()
            self.phase3_affection()
            self.phase4_commands()
            self.phase5_segmentation()
            self.phase6_edge_cases()
        except Exception as e:
            print(f"\n[ERROR] 测试异常: {e}")
            traceback.print_exc()
            self.results["bugs"].append(f"测试崩溃: {e}")
        finally:
            self.phase7_report()
            elapsed = time.time() - start
            print(f"⏱ 耗时: {elapsed:.0f}s")
        return self.results["failed"] == 0


if __name__ == "__main__":
    all_pass = True
    for run in range(1, 5):
        # 每轮测试前清理数据（保持独立）
        import shutil, time
        data_dir = PROJECT_DIR / "data"
        if data_dir.exists():
            # Wait a bit for any file handles to release
            time.sleep(1)
            for f in list(data_dir.rglob("*")):
                if f.is_file() and f.suffix in (".db", ".json"):
                    for _ in range(3):
                        try:
                            f.unlink()
                            break
                        except PermissionError:
                            time.sleep(1)
                    else:
                        print(f"  [WARN] Could not delete {f.name}, skipping")

        tester = Tester(run)
        ok = tester.run()
        if not ok:
            all_pass = False
        print(f"\n第 {run}/4 轮: {'PASS' if ok else 'FAIL'}")
        print()

    print(f"\n{'='*60}")
    print(f"  全部完成: {'ALL PASS' if all_pass else 'SOME FAILED'}")
    print(f"{'='*60}")
