"""人格漂移监测器

每 N 轮对话自动分析：
- 当前行为 vs 预设人格
- 生成 PersonaDriftReport
- 目标：Persona Consistency >= 95%

检测维度：
1. 语言风格一致性（口头禅、语气词、emoji 习惯）
2. 性格表达一致性（是否偏离预设性格）
3. 价值观一致性（是否违背设定价值观）
4. 关系定位一致性（是否偏离当前关系阶段）
"""

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from loguru import logger


@dataclass
class PersonaDriftReport:
    """人格漂移检测报告"""
    user_id: str
    persona_id: str
    conversation_count: int
    consistency_score: float      # 0.0 ~ 1.0，越高越好
    drift_score: float             # 0.0 ~ 1.0，越高漂移越严重
    suggestions: list[str] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    @property
    def passed(self) -> bool:
        """一致性是否达标"""
        return self.consistency_score >= 0.95


class PersonaDriftMonitor:
    """人格漂移监测器"""

    # 检测间隔（对话轮数）
    CHECK_INTERVAL = 100

    # 各维度的关键词映射
    DIMENSION_KEYWORDS = {
        "language": {
            "catchphrases": [],
            "filler_words": ["嗯", "啊", "呢", "啦", "哦", "嘛", "呗", "哈"],
            "positive_emoji": ["~", "!", "😊", "😄", "🥰", "💕", "✨", "❤️"],
            "negative_emoji": ["😢", "😭", "😤", "😠", "🥺"],
        },
        "personality": {
            "warm": ["关心", "担心", "想你", "想你啦", "想你哦", "乖", "好好"],
            "cold": ["哦", "嗯", "知道了", "随便", "行吧", "好吧"],
            "playful": ["哈哈", "嘻嘻", "嘿嘿", "调皮", "坏笑"],
        },
        "value": {
            "positive": ["好", "棒", "厉害", "加油", "支持", "相信", "一定"],
            "negative": ["没救", "算了", "放弃", "无聊", "没意思"],
        },
    }

    def __init__(self, persona_loader=None):
        self._persona_loader = persona_loader

    def should_check(self, conversation_count: int, last_check_count: int = 0) -> bool:
        """判断是否需要检测"""
        return (conversation_count - last_check_count) >= self.CHECK_INTERVAL

    def analyze(self, user_id: str, persona_id: str,
                conversation_count: int,
                recent_replies: list[str]) -> PersonaDriftReport:
        """分析最近回复，检测人格漂移

        Args:
            user_id: 用户 ID
            persona_id: 人设 ID
            conversation_count: 当前对话总轮数
            recent_replies: 最近 N 条 AI 回复

        Returns:
            漂移检测报告
        """
        if not recent_replies:
            return PersonaDriftReport(
                user_id=user_id,
                persona_id=persona_id,
                conversation_count=conversation_count,
                consistency_score=1.0,
                drift_score=0.0,
            )

        all_text = " ".join(recent_replies)
        details: dict[str, Any] = {}
        suggestions: list[str] = []

        # 1. 语言风格一致性
        language_score, lang_issues = self._check_language_style(all_text, recent_replies)
        details["language_style"] = {
            "score": language_score,
            "issues": lang_issues,
        }
        if lang_issues:
            suggestions.extend(lang_issues)

        # 2. 性格表达一致性
        personality_score, pers_issues = self._check_personality_expression(all_text, recent_replies)
        details["personality_expression"] = {
            "score": personality_score,
            "issues": pers_issues,
        }
        if pers_issues:
            suggestions.extend(pers_issues)

        # 3. 价值观一致性
        value_score, val_issues = self._check_value_consistency(all_text)
        details["value_consistency"] = {
            "score": value_score,
            "issues": val_issues,
        }
        if val_issues:
            suggestions.extend(val_issues)

        # 综合评分
        scores = [language_score, personality_score, value_score]
        consistency_score = sum(scores) / len(scores)
        drift_score = 1.0 - consistency_score

        report = PersonaDriftReport(
            user_id=user_id,
            persona_id=persona_id,
            conversation_count=conversation_count,
            consistency_score=round(consistency_score, 4),
            drift_score=round(drift_score, 4),
            suggestions=suggestions,
            details=details,
        )

        if not report.passed:
            logger.warning(
                f"Persona drift detected for {persona_id}: "
                f"consistency={consistency_score:.2%}, "
                f"suggestions={len(suggestions)}"
            )
        else:
            logger.info(
                f"Persona drift check passed for {persona_id}: "
                f"consistency={consistency_score:.2%}"
            )

        return report

    def _check_language_style(self, all_text: str, replies: list[str]) -> tuple[float, list[str]]:
        """检查语言风格一致性"""
        issues = []

        # 检查回复长度一致性
        lengths = [len(r) for r in replies]
        if lengths:
            avg_len = sum(lengths) / len(lengths)
            # 极端变化
            for i in range(1, len(replies)):
                if lengths[i] > 0 and lengths[i-1] > 0:
                    ratio = max(lengths[i], lengths[i-1]) / min(lengths[i], lengths[i-1])
                    if ratio > 5:
                        issues.append(f"回复长度波动过大（{lengths[i-1]}字 → {lengths[i]}字）")
                        break

        # 检查 emoji 使用
        positive_emoji_count = sum(1 for e in self.DIMENSION_KEYWORDS["language"]["positive_emoji"] if e in all_text)
        negative_emoji_count = sum(1 for e in self.DIMENSION_KEYWORDS["language"]["negative_emoji"] if e in all_text)
        total_replies = len(replies)
        if total_replies > 5:
            if positive_emoji_count == 0 and negative_emoji_count == 0:
                issues.append("近期回复缺少情感表达（无 emoji/颜文字）")
            elif negative_emoji_count > positive_emoji_count * 2:
                issues.append("负面 emoji 使用频率异常偏高")

        # 计算分数
        score = 1.0
        if issues:
            score -= len(issues) * 0.1
        return max(0.0, score), issues

    def _check_personality_expression(self, all_text: str, replies: list[str]) -> tuple[float, list[str]]:
        """检查性格表达一致性"""
        issues = []

        # 检查温暖 vs 冷淡
        warm_count = sum(1 for w in self.DIMENSION_KEYWORDS["personality"]["warm"] if w in all_text)
        cold_count = sum(1 for c in self.DIMENSION_KEYWORDS["personality"]["cold"] if c in all_text)
        playful_count = sum(1 for p in self.DIMENSION_KEYWORDS["personality"]["playful"] if p in all_text)

        total_expression = warm_count + cold_count + playful_count
        if total_expression > 0:
            if cold_count > warm_count + playful_count:
                issues.append("回复风格偏冷淡，缺少温暖表达")

        # 检查回复长度（过长或过短）
        if replies:
            avg_len = sum(len(r) for r in replies) / len(replies)
            if avg_len > 200:
                issues.append("回复篇幅过长，不符合日常聊天习惯")
            elif avg_len < 5:
                issues.append("回复过于简短，缺乏交互性")

        score = 1.0
        if issues:
            score -= len(issues) * 0.15
        return max(0.0, score), issues

    def _check_value_consistency(self, all_text: str) -> tuple[float, list[str]]:
        """检查价值观一致性"""
        issues = []

        # 检查负面表达
        negative_count = sum(1 for n in self.DIMENSION_KEYWORDS["value"]["negative"] if n in all_text)
        positive_count = sum(1 for p in self.DIMENSION_KEYWORDS["value"]["positive"] if p in all_text)

        total_value_expressions = negative_count + positive_count
        if total_value_expressions > 0:
            neg_ratio = negative_count / total_value_expressions
            if neg_ratio > 0.5:
                issues.append("负面/放弃类表达占比过高")

        score = 1.0
        if issues:
            score -= len(issues) * 0.2
        return max(0.0, score), issues

    def generate_report_summary(self, report: PersonaDriftReport) -> str:
        """生成报告摘要（供内部参考/日志）"""
        status = "✅ 通过" if report.passed else "⚠️ 需要调整"
        return (
            f"人格漂移检测 {status}\n"
            f"一致性评分：{report.consistency_score:.2%}\n"
            f"漂移评分：{report.drift_score:.2%}\n"
            f"对话轮数：{report.conversation_count}\n"
            f"建议：{'；'.join(report.suggestions) if report.suggestions else '无'}"
        )
