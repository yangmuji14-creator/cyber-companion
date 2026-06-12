"""话题追踪器

维护当前对话话题上下文，让 AI 能自然地延续或切换话题。
基于滑动窗口 + 关键词提取实现，轻量级无 LLM 依赖。
"""

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
import re
from typing import Any

from loguru import logger


@dataclass
class TopicState:
    """话题状态"""
    topic: str  # 话题关键词/描述
    first_mentioned: str = field(default_factory=lambda: datetime.now().isoformat())
    last_mentioned: str = field(default_factory=lambda: datetime.now().isoformat())
    mention_count: int = 1
    source: str = "auto"  # auto=自动检测, user=用户指定

    def touch(self) -> None:
        """更新最后提及时间"""
        self.last_mentioned = datetime.now().isoformat()
        self.mention_count += 1


class TopicTracker:
    """话题追踪器

    功能：
    1. 追踪当前活跃话题（最近 3 个）
    2. 检测话题切换
    3. 生成话题上下文注入 prompt
    4. 支持话题相关性计算

    实现：
    - 基于关键词提取（无 LLM 依赖）
    - 滑动窗口维护最近话题
    - 合并相似话题
    """

    # 话题关键词提取：排除的停用词
    STOP_WORDS = {
        "的", "了", "是", "在", "我", "你", "他", "她", "它",
        "们", "这", "那", "有", "和", "与", "或", "但", "而",
        "就", "都", "也", "还", "又", "再", "很", "非常",
        "不", "没", "别", "会", "能", "可以", "应该",
        "吗", "呢", "吧", "啊", "呀", "哦", "嗯",
        "一个", "一些", "什么", "怎么", "为什么", "哪里",
        "今天", "昨天", "明天", "现在", "刚才",
    }

    def __init__(self, max_topics: int = 5):
        self._max_topics = max_topics
        self._topics: deque[TopicState] = deque(maxlen=max_topics)
        self._recent_keywords: deque[set[str]] = deque(maxlen=10)

    def update(self, user_message: str, assistant_reply: str = "") -> None:
        """根据对话更新话题

        Args:
            user_message: 用户消息
            assistant_reply: AI 回复（可选，用于更准确的话题检测）
        """
        # 提取用户消息中的关键词
        keywords = self._extract_keywords(user_message)
        if not keywords:
            return

        self._recent_keywords.append(keywords)

        # 更新已有话题或创建新话题
        matched = False
        for topic in self._topics:
            topic_keywords = self._extract_keywords(topic.topic)
            overlap = keywords & topic_keywords
            if overlap:
                topic.touch()
                matched = True
                # 如果有新关键词，扩展话题描述
                new_words = keywords - topic_keywords
                if new_words and len(topic.topic) < 50:
                    topic.topic += " " + " ".join(list(new_words)[:2])
                break

        if not matched and len(keywords) >= 1:
            # 创建新话题
            topic_text = " ".join(list(keywords)[:3])
            new_topic = TopicState(topic=topic_text)
            self._topics.append(new_topic)
            logger.debug(f"New topic detected: {topic_text}")

    def get_current_topic(self) -> str:
        """获取当前最活跃的话题"""
        if not self._topics:
            return ""
        # 返回最后提及的话题
        return self._topics[-1].topic

    def get_all_topics(self) -> list[str]:
        """获取所有活跃话题"""
        return [t.topic for t in self._topics]

    def get_topic_context(self) -> str:
        """生成话题上下文 prompt

        Returns:
            格式化的话题上下文文本，用于注入 system prompt
        """
        if not self._topics:
            return ""

        lines = ["【对话话题追踪】"]
        for i, topic in enumerate(reversed(list(self._topics)), 1):
            marker = "（当前）" if i == 1 else ""
            lines.append(f"- {topic.topic}{marker}（提及 {topic.mention_count} 次）")

        return "\n".join(lines)

    def is_topic_shift(self, user_message: str) -> bool:
        """检测是否发生了话题切换

        Args:
            user_message: 用户新消息

        Returns:
            True 表示话题发生了切换
        """
        if not self._topics:
            return False

        current_topic = self._topics[-1]
        current_keywords = self._extract_keywords(current_topic.topic)
        new_keywords = self._extract_keywords(user_message)

        if not new_keywords:
            return False

        overlap = current_keywords & new_keywords
        # 如果没有共同关键词，认为话题切换了
        return len(overlap) == 0

    def _extract_keywords(self, text: str) -> set[str]:
        """提取文本中的关键词

        简单实现：按字符分割，排除停用词和短词。
        对中文按 2-gram 提取有意义的词组。
        """
        # 清理文本
        text = re.sub(r'[^\u4e00-\u9fff\w]', ' ', text)
        words = set()

        # 中文 2-gram
        chinese_chars = re.findall(r'[\u4e00-\u9fff]+', text)
        for segment in chinese_chars:
            if len(segment) >= 2:
                for i in range(len(segment) - 1):
                    bigram = segment[i:i+2]
                    if bigram not in self.STOP_WORDS:
                        words.add(bigram)
            if len(segment) >= 3:
                words.add(segment)

        # 英文单词
        english_words = re.findall(r'[a-zA-Z]{2,}', text)
        for word in english_words:
            if word.lower() not in self.STOP_WORDS:
                words.add(word.lower())

        return words

    def get_stats(self) -> dict[str, Any]:
        """获取话题统计信息"""
        return {
            "active_topics": len(self._topics),
            "current_topic": self.get_current_topic(),
            "all_topics": self.get_all_topics(),
        }

    def clear(self) -> None:
        """清空话题追踪"""
        self._topics.clear()
        self._recent_keywords.clear()