"""PostProcessOrchestrator — v1.3 后台后处理

处理：关系事件记录、人生摘要生成、人格漂移检测、对话计数。
"""

from loguru import logger

from core.config import DEFAULT_PERSONA_ID


class PostProcessOrchestrator:
    """v1.3 后台后处理编排器

    在每次 LLM 回复后以后台任务形式运行，不会阻塞主流程。
    """

    def __init__(self, pipeline):
        """从 ChatPipeline 提取所需依赖。

        Args:
            pipeline: ChatPipeline 实例，提供 _memory_mgr, _life_summary,
                      _relationship_events, _drift_monitor, _last_replies,
                      _last_drift_check, _conversation_counter 等引用。
        """
        self._pipeline = pipeline

    async def run(self, user_id: str, content: str, reply: str):
        """执行后台处理：关系事件/人生摘要/对话计数/漂移检测"""
        try:
            pipeline = self._pipeline

            # 1. 关系事件
            pipeline._relationship_events.detect_and_record(user_id, content, reply)

            # 2. 对话计数
            pipeline._conversation_counter[user_id] = (
                pipeline._conversation_counter.get(user_id, 0) + 1
            )
            conv_count = pipeline._conversation_counter[user_id]

            # 3. 收集回复用于漂移检测
            if user_id not in pipeline._last_replies:
                pipeline._last_replies[user_id] = []
            pipeline._last_replies[user_id].append(reply)
            if len(pipeline._last_replies[user_id]) > 50:
                pipeline._last_replies[user_id] = pipeline._last_replies[user_id][-50:]

            # 4. 人生摘要生成
            try:
                if pipeline._life_summary and pipeline._life_summary.should_generate(
                    user_id, conv_count
                ):
                    all_memories = pipeline._memory_mgr.get_memories(user_id, limit=50)
                    memory_texts = [m.content for m in all_memories if m.content]
                    pipeline._life_summary.generate_from_memories(
                        user_id, conv_count, memory_texts,
                    )
            except Exception as e:
                logger.debug(f"LifeSummary generation failed: {e}")

            # 5. 人格漂移检测
            try:
                last_check = pipeline._last_drift_check.get(user_id, 0)
                if pipeline._drift_monitor.should_check(conv_count, last_check):
                    recent = pipeline._last_replies.get(user_id, [])
                    report = pipeline._drift_monitor.analyze(
                        user_id, DEFAULT_PERSONA_ID, conv_count, recent[-20:],
                    )
                    pipeline._last_drift_check[user_id] = conv_count
                    if not report.passed:
                        logger.warning(
                            f"Persona drift: score={report.consistency_score:.2%}, "
                            f"suggestions={report.suggestions}"
                        )
            except Exception as e:
                logger.debug(f"Persona drift check failed: {e}")

        except Exception as e:
            logger.debug(f"v1.3 post-process failed: {e}")
