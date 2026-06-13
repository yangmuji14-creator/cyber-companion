"""Embedder — 文本向量嵌入（同步，可直接在 async 上下文调用）

将文本转为稠密向量，用于语义搜索。
默认使用 BAAI/bge-small-zh-v1.5（33MB，中文优化），
模型不存在时优雅降级（调用方回退关键词搜索）。
"""

from abc import ABC, abstractmethod

from loguru import logger

# 默认嵌入模型（中文优化，33MB，输出 512 维）
DEFAULT_MODEL = "BAAI/bge-small-zh-v1.5"


class BaseEmbedder(ABC):
    """嵌入器基类（同步接口）"""

    @abstractmethod
    def embed(self, text: str) -> list[float] | None:
        """将单条文本转为向量，失败返回 None"""
        ...

    @abstractmethod
    def embed_batch(self, texts: list[str]) -> list[list[float]] | None:
        """批量嵌入，失败返回 None"""
        ...

    @property
    @abstractmethod
    def available(self) -> bool:
        """是否可用"""
        ...

    @property
    @abstractmethod
    def dimension(self) -> int:
        """向量维度"""
        ...


class SentenceTransformerEmbedder(BaseEmbedder):
    """基于 sentence-transformers 的本地嵌入器（同步）"""

    def __init__(self, model_name: str = DEFAULT_MODEL):
        self._model_name = model_name
        self._model = None
        self._dim = 0
        self._ready = False
        self._init_error = None

    @property
    def available(self) -> bool:
        if not self._ready and not self._init_error:
            self._lazy_init()
        return self._ready

    @property
    def dim(self) -> int:
        return self._dim

    @property
    def dimension(self) -> int:
        return self._dim

    def _lazy_init(self):
        """首次使用时延迟加载模型"""
        if self._ready or self._init_error:
            return
        try:
            from sentence_transformers import SentenceTransformer
            logger.info(f"Loading embedding model: {self._model_name} ...")
            self._model = SentenceTransformer(self._model_name)
            self._dim = self._model.get_embedding_dimension()
            self._ready = True
            logger.info(f"Embedder ready (dim={self._dim})")
        except Exception as e:
            self._init_error = str(e)
            logger.warning(f"Failed to load embedding model '{self._model_name}': {e}")
            logger.warning("Falling back to keyword-based memory search.")

    def embed(self, text: str) -> list[float] | None:
        self._lazy_init()
        if not self._ready:
            return None
        try:
            vec = self._model.encode(text, normalize_embeddings=True)
            return vec.tolist()
        except Exception as e:
            logger.error(f"Embedding failed: {e}")
            return None

    def embed_batch(self, texts: list[str]) -> list[list[float]] | None:
        self._lazy_init()
        if not self._ready:
            return None
        try:
            vecs = self._model.encode(texts, normalize_embeddings=True)
            return [v.tolist() for v in vecs]
        except Exception as e:
            logger.error(f"Batch embedding failed: {e}")
            return None
