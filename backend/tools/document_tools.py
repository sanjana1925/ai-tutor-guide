from typing import List

from backend.services.retrieval_service import RetrievalService
from backend.tools.base import ToolArgs, ToolContext, ToolResult, ToolSpec


class NoArgs(ToolArgs):
    pass


def build_document_tools(service: RetrievalService) -> List[ToolSpec]:
    def get_document_metadata(ctx: ToolContext, args: NoArgs) -> ToolResult:
        return ToolResult(ok=True, tool="get_document_metadata", data=service.metadata(ctx.scope))

    return [
        ToolSpec("get_document_metadata", "chunk count, page count and whether the document is indexed", NoArgs, get_document_metadata)
    ]
