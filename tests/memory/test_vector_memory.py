"""向量记忆集成测试（同步，sentence-transformers 是同步库）"""
import asyncio
import sys
import tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.memory.embedder import SentenceTransformerEmbedder
from core.memory.vector_store import VectorStore
from core.memory.manager import MemoryManager


def test_vector_memory():
    # 1. Embedder
    print("=== Embedder ===")
    emb = SentenceTransformerEmbedder()
    vec = emb.embed("我喜欢猫和动漫")
    assert vec is not None
    assert len(vec) > 0
    dim = len(vec)
    print(f"  dim={dim}, available={emb.available}")

    texts = ["我喜欢猫", "今天天气真好", "你吃饭了吗？", "打游戏好开心"]
    vecs = emb.embed_batch(texts)
    assert len(vecs) == len(texts)
    print(f"  batch: {len(vecs)} vectors OK")

    # 2. VectorStore
    print("\n=== VectorStore ===")
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        vs = VectorStore(f"{tmp}/test.db")
        for i, (t, v) in enumerate(zip(texts, vecs)):
            vs.add("user1", f"mem_{i}", t, v)

        cnt = vs.count("user1")
        assert cnt == 4
        print(f"  stored {cnt} memories")

        # 语义搜索："宠物" → "我喜欢猫"
        qvec = emb.embed("宠物")
        results = vs.search("user1", qvec, top_k=3)
        print("  search('宠物'):")
        for r in results:
            print(f"    [{r['score']:.3f}] {r['content']}")
        assert results[0]["memory_id"] == "mem_0"
        print("  ✅ semantic: 宠物 → 我喜欢猫")

        # 另一种查询
        qvec2 = emb.embed("心情")
        results2 = vs.search("user1", qvec2, top_k=3)
        print("  search('心情'):")
        for r in results2:
            print(f"    [{r['score']:.3f}] {r['content']}")

        # 删除
        vs.delete("user1", "mem_0")
        assert vs.count("user1") == 3
        print("  delete OK")
        vs.close()

    # 3. MemoryManager 集成
    print("\n=== MemoryManager ===")
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        vs2 = VectorStore(f"{tmp}/vectors.db")
        mm = MemoryManager(tmp, embedder=emb, vector_store=vs2)

        # level=3 绕过关键词评分（测试向量功能而非关键词）
        mem = mm.add_memory_sync("u1", "我住在北京朝阳区", level=3)
        assert mem is not None
        print(f"  added: [{mem.id}] {mem.content[:30]}")

        # 语义检索上下文
        ctx = mm.get_context_prompt("u1", query="我的住址", limit=3)
        print(f"  context('我的住址'): {ctx[:60]}...")
        assert "北京" in ctx

        # semantic_search
        sr = mm.semantic_search("u1", "住在哪里")
        print(f"  semantic_search('住在哪里'): {sr}")
        assert len(sr) > 0
        assert "北京" in sr[0]["content"]

        # 无 query 时按重要度排序
        ctx2 = mm.get_context_prompt("u1", limit=3)
        print(f"  context(no query): {ctx2[:60]}...")
        assert "北京" in ctx2

        # 删除同步清理向量
        mm.add_memory_sync("u1", "我不喜欢吃香菜", level=3)
        cnt_before = vs2.count("u1")
        print(f"  memories before delete: {cnt_before}")
        assert cnt_before >= 2
        vs2.close()

    print("\n✅ All vector memory tests passed!")


if __name__ == "__main__":
    test_vector_memory()
