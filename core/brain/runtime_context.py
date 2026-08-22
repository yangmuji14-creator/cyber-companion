"""Compact, model-facing runtime state assembled from brain signals."""

from __future__ import annotations

import re

from .models import BrainInput, MonologueThought


_WHITESPACE_RE = re.compile(r"\s+")


class RuntimeStateFormatter:
    """Turn meaningful brain signals into a small structured prompt block.

    This is deliberately different from ``MonologueWeaver``. The latter
    produces human-readable prose for diagnostics and diary material; this
    formatter only carries actionable state into the current model request.
    """

    def __init__(self, max_tokens: int = 300):
        self.max_tokens = max(80, min(300, int(max_tokens)))

    def format(
        self,
        brain_input: BrainInput,
        thoughts: list[MonologueThought],
    ) -> str:
        by_source = {thought.source: thought for thought in thoughts}
        sections: list[tuple[str, list[str]]] = []

        mood_type = (brain_input.mood_type or "").lower()
        if mood_type not in {"", "neutral", "calm"} and "mood" in by_source:
            sections.append(("心境", [by_source["mood"].content]))

        focus = self._contents(by_source, "openloop", "topic", "user_emotion")
        if focus:
            sections.append(("本轮关注", focus))

        memories = self._contents(
            by_source, "memory_trigger", "identity", "life_summary",
        )
        if memories:
            sections.append(("关联记忆", memories))

        relationship: list[str] = []
        if "personality" in by_source:
            relationship.append(by_source["personality"].content)
        level = brain_input.affection_level
        if level is not None and (level < 30 or level >= 65) and "affection" in by_source:
            relationship.append(by_source["affection"].content)
        if relationship:
            sections.append(("关系倾向", relationship))

        if brain_input.time_period in {"night", "late_night"} and "time" in by_source:
            sections.append(("环境", [by_source["time"].content]))

        if not sections:
            return ""

        lines = ["【本轮运行时心境】"]
        used = self._estimate_tokens(lines[0])
        for label, values in sections:
            clean_values = [self._clean(value) for value in values if self._clean(value)]
            if not clean_values:
                continue
            line = f"{label}：{'；'.join(clean_values[:2])}"
            tokens = self._estimate_tokens(line)
            if used + tokens > self.max_tokens:
                continue
            lines.append(line)
            used += tokens

        return "\n".join(lines) if len(lines) > 1 else ""

    @staticmethod
    def _contents(
        by_source: dict[str, MonologueThought],
        *sources: str,
    ) -> list[str]:
        return [by_source[source].content for source in sources if source in by_source]

    @staticmethod
    def _clean(value: str) -> str:
        return _WHITESPACE_RE.sub(" ", str(value)).strip()[:180]

    @staticmethod
    def _estimate_tokens(value: str) -> int:
        return max(1, len(value) // 2)
