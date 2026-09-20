"""Read-only views of the learner's recorded performance. Numbers come from Python state, never from an LLM."""
from typing import Callable, List

from pydantic import Field

from backend.services.retrieval_service import Scope
from backend.tools.base import ToolArgs, ToolContext, ToolResult, ToolSpec
from backend.domain.quiz_engine import LearnerState


class NoArgs(ToolArgs):
    pass


class HistoryArgs(ToolArgs):
    limit: int = Field(default=10, ge=1, le=50)


class TopicArgs(ToolArgs):
    topic: str = Field(default="", max_length=200)


def build_learning_tools(get_state: Callable[[Scope], LearnerState]) -> List[ToolSpec]:
    def get_learning_history(ctx: ToolContext, args: NoArgs) -> ToolResult:
        s = get_state(ctx.scope)
        return ToolResult(
            ok=True,
            tool="get_learning_history",
            data={
                "current_phase": s.current_phase,
                "total_attempted": s.total_attempted,
                "total_correct": s.total_correct,
                "overall_accuracy": round(s.get_overall_accuracy(), 1),
                "simple_accuracy": round(s.get_simple_accuracy(), 1),
                "medium_accuracy": round(s.get_medium_accuracy(), 1),
                "high_accuracy": round(s.get_high_accuracy(), 1),
            },
        )

    def get_quiz_history(ctx: ToolContext, args: HistoryArgs) -> ToolResult:
        s = get_state(ctx.scope)
        return ToolResult(ok=True, tool="get_quiz_history", data={"asked_questions": s.asked_questions[-args.limit :]})

    def get_topic_performance(ctx: ToolContext, args: TopicArgs) -> ToolResult:
        s = get_state(ctx.scope)
        stats = {t: v.model_dump() for t, v in s.topic_stats.items() if not args.topic or t == args.topic}
        return ToolResult(
            ok=True,
            tool="get_topic_performance",
            data={"topic_stats": stats, "weak_topics": s.get_weak_topics(), "strong_topics": s.get_strong_topics()},
        )

    return [
        ToolSpec("get_learning_history", "overall and per-phase accuracy for this learner and document", NoArgs, get_learning_history),
        ToolSpec("get_quiz_history", "recently asked quiz questions", HistoryArgs, get_quiz_history),
        ToolSpec("get_topic_performance", "per-topic attempts/accuracy plus weak and strong topics", TopicArgs, get_topic_performance),
    ]
