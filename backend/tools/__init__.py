from typing import Callable

from backend.services.retrieval_service import RetrievalService, Scope
from backend.tools.base import ToolContext, ToolRegistry, ToolResult, ToolSpec
from backend.tools.document_tools import build_document_tools
from backend.tools.learning_tools import build_learning_tools
from backend.tools.quiz_tools import build_quiz_tools
from backend.tools.retrieval_tools import build_retrieval_tools
from backend.domain.quiz_engine import LearnerState


def build_registry(retrieval: RetrievalService, get_state: Callable[[Scope], LearnerState]) -> ToolRegistry:
    """The full tool catalogue. Each agent receives only its own allowlisted subset."""
    return ToolRegistry(
        [
            *build_retrieval_tools(retrieval),
            *build_document_tools(retrieval),
            *build_learning_tools(get_state),
            *build_quiz_tools(retrieval),
        ]
    )


__all__ = ["build_registry", "ToolContext", "ToolRegistry", "ToolResult", "ToolSpec"]
