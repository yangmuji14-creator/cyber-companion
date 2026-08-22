"""Bounded background work performed after a successful assistant reply."""

from __future__ import annotations

from loguru import logger

from core.config import DEFAULT_PERSONA_ID


class PostProcessOrchestrator:
    """Record relationship events, summaries and persona-drift diagnostics."""

    def __init__(
        self,
        pipeline=None,
        *,
        memory_manager=None,
        life_summary=None,
        persona_loader=None,
        affection_storage=None,
        chat_history=None,
        relationship_events=None,
        drift_monitor=None,
        max_users: int = 500,
    ) -> None:
        # The positional form remains for third-party compatibility, but private
        # pipeline state is copied once and never read during processing.
        if pipeline is not None:
            memory_manager = memory_manager or getattr(pipeline, "_memory_mgr", None)
            life_summary = life_summary or getattr(pipeline, "_life_summary", None)
            persona_loader = persona_loader or getattr(pipeline, "_persona_loader", None)
            affection_storage = affection_storage or getattr(pipeline, "_affection_storage", None)
            chat_history = chat_history or getattr(pipeline, "_chat_history", None)
            relationship_events = relationship_events or getattr(pipeline, "_relationship_events", None)
            drift_monitor = drift_monitor or getattr(pipeline, "_drift_monitor", None)
        self._memory_manager = memory_manager
        self._life_summary = life_summary
        self._persona_loader = persona_loader
        self._affection_storage = affection_storage
        self._chat_history = chat_history
        self._relationship_events = relationship_events
        self._drift_monitor = drift_monitor
        self._max_users = max_users
        self._conversation_counter: dict[str, int] = {}
        self._last_drift_check: dict[str, int] = {}
        self._last_replies: dict[str, list[str]] = {}

    def _trim_state(self) -> None:
        while len(self._conversation_counter) > self._max_users:
            oldest = next(iter(self._conversation_counter))
            for mapping in (
                self._conversation_counter,
                self._last_drift_check,
                self._last_replies,
            ):
                mapping.pop(oldest, None)

    async def run(
        self,
        user_id: str,
        content: str,
        reply: str,
        persona_id: str = DEFAULT_PERSONA_ID,
    ) -> None:
        try:
            if self._relationship_events:
                self._relationship_events.detect_and_record(user_id, content, reply)

            self._conversation_counter[user_id] = self._conversation_counter.get(user_id, 0) + 1
            conv_count = self._conversation_counter[user_id]
            self._last_replies.setdefault(user_id, []).append(reply)
            self._last_replies[user_id] = self._last_replies[user_id][-50:]
            self._trim_state()

            try:
                persistent_count = conv_count
                relationship_level = None
                if self._affection_storage:
                    stats = self._affection_storage.get_stats(user_id, persona_id)
                    persistent_count = max(persistent_count, stats.message_count)
                    relationship_level = stats.level
                if (
                    self._life_summary
                    and self._memory_manager
                    and self._life_summary.should_generate(
                        user_id, persistent_count, persona_id,
                    )
                ):
                    memories = self._memory_manager.get_memories(user_id, limit=50)
                    memory_texts = [
                        memory.content for memory in memories if memory.content
                    ]
                    recent_messages = (
                        self._chat_history.get_messages(user_id)[-20:]
                        if self._chat_history else []
                    )
                    if hasattr(self._life_summary, "generate_diary"):
                        await self._life_summary.generate_diary(
                            user_id=user_id,
                            persona_id=persona_id,
                            conversation_count=persistent_count,
                            memories=memory_texts,
                            recent_messages=recent_messages,
                            relationship_level=relationship_level,
                        )
                    else:
                        self._life_summary.generate_from_memories(
                            user_id, persistent_count, memory_texts,
                        )
            except Exception as e:
                logger.debug(f"LifeSummary generation failed: {e}")

            try:
                if self._drift_monitor:
                    last_check = self._last_drift_check.get(user_id, 0)
                    if self._drift_monitor.should_check(conv_count, last_check):
                        report = self._drift_monitor.analyze(
                            user_id,
                            persona_id,
                            conv_count,
                            self._last_replies.get(user_id, [])[-20:],
                        )
                        self._last_drift_check[user_id] = conv_count
                        if not report.passed:
                            logger.warning(
                                f"Persona drift: score={report.consistency_score:.2%}, "
                                f"suggestions={report.suggestions}"
                            )
            except Exception as e:
                logger.debug(f"Persona drift check failed: {e}")
        except Exception as e:
            logger.debug(f"v1.3 post-process failed: {e}")
