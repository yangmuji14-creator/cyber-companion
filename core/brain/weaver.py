"""MonologueWeaver — 将内心独白碎片编织为连贯的第一人称叙述

接收 ThoughtOrganizer 输出的 MonologueThought 列表，
按类别分组、加过渡词、合并段落，生成听感自然的内心独白。

用法:
    weaver = MonologueWeaver(max_tokens=1000)
    monologue = weaver.weave(thoughts)
    debug_version = weaver.weave_debug(thoughts)
"""

from __future__ import annotations

from typing import List

from .models import MonologueThought

# ────────── 编织顺序 ──────────
# 最终独白按此顺序依次呈现各类念头
CATEGORY_ORDER = ["feeling", "observation", "memory", "intention", "concern"]

# ────────── 类别间过渡词表 ──────────
# key = (前一个类别, 后一个类别), value = 可用的过渡词列表
TRANSITIONS: dict[tuple[str, str], list[str]] = {
    ("feeling", "observation"): ["不过", "说起来"],
    ("observation", "memory"): ["对了", "我记得"],
    ("memory", "intention"): ["说起来", "对了"],
    ("intention", "concern"): ["其实", "怎么说呢"],
}

# ────────── 类别优先级 ──────────
# 用于截断决策：从最低优先级组开始裁减（值越高越优先保留）
CATEGORY_PRIORITY = {
    "feeling": 5,
    "observation": 4,
    "memory": 3,
    "intention": 2,
    "concern": 1,
}

# 句尾标点集合（用于检测句子是否已完整结束）
_SENTENCE_END = set("。！？……!?")


class MonologueWeaver:
    """内心独白编织器

    接收 MonologueThought 列表，按类别分组、组内按优先级排序、
    用自然过渡词串联，生成一段流畅的第一人称内心独白。

    Attributes:
        max_tokens: 输出最大 token 数（中文字符 ≈ 1 token/字）。
    """

    def __init__(self, max_tokens: int = 1000):
        self.max_tokens = max_tokens

    def weave(self, thoughts: list[MonologueThought]) -> str:
        """编织内心独白

        Args:
            thoughts: 来自 ThoughtOrganizer 的 Marche 列表。

        Returns:
            流畅的第一人称内心独白字符串。
        """
        if not thoughts:
            return "此时我心里很平静。"

        # 1. Token 截断（从最低优先级类别组开始裁减）
        thoughts = self._trim(thoughts)
        if not thoughts:
            return "此时我心里很平静。"

        # 2. 按类别分组，组内按优先级降序排列
        groups: dict[str, list[MonologueThought]] = {}
        for cat in CATEGORY_ORDER:
            cat_thoughts = [t for t in thoughts if t.category == cat]
            if cat_thoughts:
                cat_thoughts.sort(key=lambda t: t.priority, reverse=True)
                groups[cat] = cat_thoughts

        # 3. 同类别合并为一段文字，构建有序段落列表
        paragraphs: list[tuple[str, str]] = []
        for cat in CATEGORY_ORDER:
            if cat in groups:
                merged = self._merge_group(groups[cat])
                paragraphs.append((cat, merged))

        if not paragraphs:
            return "此时我心里很平静。"

        # 4. 用过渡词串联各段落
        parts: list[str] = []
        for i, (cat, text) in enumerate(paragraphs):
            if i == 0:
                parts.append(text)
            else:
                prev_cat = paragraphs[i - 1][0]
                transition = self._pick_transition(prev_cat, cat, text)
                if transition:
                    parts.append(transition + text)
                else:
                    # 无预定义过渡词时自然衔接
                    parts.append(text)

        monologue = "".join(parts)

        # 5. 确保以完整句号结尾
        if monologue and monologue[-1] not in _SENTENCE_END:
            monologue += "。"

        return monologue

    def weave_debug(self, thoughts: list[MonologueThought]) -> str:
        """编织内心独白并附加来源标注（用于调试）

        在每个思想碎片前添加 [source] 标记，其他规则与 weave() 相同。

        Args:
            thoughts: 来自 ThoughtOrganizer 的念头列表。

        Returns:
            带 [source] 标注的内心独白字符串。
        """
        if not thoughts:
            return "[brain]此时我心里很平静。"

        thoughts = self._trim(thoughts)
        if not thoughts:
            return "[brain]此时我心里很平静。"

        # 按类别分组
        groups: dict[str, list[MonologueThought]] = {}
        for cat in CATEGORY_ORDER:
            cat_thoughts = [t for t in thoughts if t.category == cat]
            if cat_thoughts:
                cat_thoughts.sort(key=lambda t: t.priority, reverse=True)
                groups[cat] = cat_thoughts

        # 调试模式：不合并同类别，每个 thought 独立标注 [source]
        fragments: list[str] = []
        prev_cat: str | None = None

        for cat in CATEGORY_ORDER:
            if cat not in groups:
                continue

            # 过渡词
            if prev_cat is not None:
                first_content = groups[cat][0].content if groups[cat] else ""
                transition = self._pick_transition(prev_cat, cat, first_content)
                if transition:
                    fragments.append(transition)

            # 每个 thought 独立标注
            for t in groups[cat]:
                fragments.append(f"[{t.source}]{t.content}")

            prev_cat = cat

        return "".join(fragments)

    # ────────── 内部工具方法 ──────────

    @staticmethod
    def _merge_group(thoughts: list[MonologueThought]) -> str:
        """合并同一类别内的多条思绪为一段连贯文字

        将同一类别的多个 MonologueThought 以句号分隔拼接，
        确保合并结果以句尾标点结尾，便于后续添加过渡词。

        Args:
            thoughts: 同一类别的念头列表（已按优先级降序排列）。

        Returns:
            合并后的字符串，末尾总是以句尾标点结尾。
        """
        texts = [t.content for t in thoughts]
        if len(texts) <= 1:
            merged = texts[0] if texts else ""
        else:
            merged = texts[0]
            for t in texts[1:]:
                if merged and merged[-1] not in _SENTENCE_END:
                    merged += "。"
                merged += t

        # 确保以句尾标点结尾，以便后续过渡词自然衔接
        if merged and merged[-1] not in _SENTENCE_END:
            merged += "。"

        return merged

    @staticmethod
    def _pick_transition(prev_cat: str, next_cat: str, next_text: str = "") -> str:
        """选择合适的过渡词

        优先选择不会与下一条内容开头重复的过渡词。
        若所有选项都冲突，使用默认的第一个。

        Args:
            prev_cat: 前一个类别。
            next_cat: 后一个类别。
            next_text: 后一类别的合并文本（用于避免重复）。

        Returns:
            选定的过渡词字符串，若无可用过渡词则返回空字符串。
        """
        key = (prev_cat, next_cat)
        options = TRANSITIONS.get(key, [])
        if not options:
            return ""

        # 优先选择不会与 next_text 开头冲突的过渡词
        for trans in options:
            if trans and next_text.startswith(trans):
                continue
            return trans

        # 所有过渡词都冲突，使用第一个
        return options[0]

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        """估算 token 数

        中文文本：len(text) // 2（中文字符 ≈ 1 token/字）。
        至少返回 1。

        Args:
            text: 待估算的文本。

        Returns:
            估算的 token 数。
        """
        return max(1, len(text) // 2)

    def _trim(self, thoughts: list[MonologueThought]) -> list[MonologueThought]:
        """按 token 预算截断，从最低优先级类别组开始裁减

        1. 先移除整个类别组中优先级最低的念头
        2. 从最低优先级类别（concern）开始处理
        3. 至少保留一条念头

        Args:
            thoughts: 原始 MonologueThought 列表。

        Returns:
            截断后的列表，至少包含一条念头。
        """
        total = sum(self._estimate_tokens(t.content) for t in thoughts)
        if total <= self.max_tokens:
            return thoughts

        # 按截断优先级排序：类别优先级升序 → 同类别内优先级升序 → 原始索引（稳定）
        keyed = [(i, t) for i, t in enumerate(thoughts)]
        keyed.sort(
            key=lambda x: (
                CATEGORY_PRIORITY.get(x[1].category, 0),  # 类别：低优先级类别先裁
                x[1].priority,  # 同类别内：低优先级念头先裁
                x[0],  # 原始顺序（稳定排序）
            )
        )

        remaining = list(thoughts)
        total_est = total

        for _, t in keyed:
            if total_est <= self.max_tokens:
                break
            if len(remaining) <= 1:
                break
            tok = self._estimate_tokens(t.content)
            try:
                remaining.remove(t)
                total_est -= tok
            except ValueError:
                continue

        return remaining
