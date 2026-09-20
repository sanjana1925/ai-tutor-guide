import random
from typing import List

from pydantic import Field

from backend.services.retrieval_service import RetrievalService
from backend.tools.base import ToolArgs, ToolContext, ToolResult, ToolSpec


class SampleArgs(ToolArgs):
    n: int = Field(default=3, ge=1, le=5)


def build_quiz_tools(service: RetrievalService) -> List[ToolSpec]:
    def sample_document_excerpts(ctx: ToolContext, args: SampleArgs) -> ToolResult:
        chunks, _ = service.get_records(ctx.scope)
        picked = random.sample(chunks, min(args.n, len(chunks))) if chunks else []
        return ToolResult(ok=bool(picked), tool="sample_document_excerpts", chunks=picked, error="" if picked else "no indexed chunks")

    return [ToolSpec("sample_document_excerpts", "random excerpts to ground a new quiz question", SampleArgs, sample_document_excerpts)]
