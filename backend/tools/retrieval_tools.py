"""Retrieval tools. Each is a thin, typed wrapper over RetrievalService, scoped by ToolContext."""
from typing import List

from pydantic import Field

from backend import config
from backend.services.retrieval_service import RetrievalService
from backend.tools.base import ToolArgs, ToolContext, ToolResult, ToolSpec


class SearchDocumentArgs(ToolArgs):
    query: str = Field(min_length=1, max_length=500)
    top_k: int = Field(default=config.QA_TOP_K, ge=1, le=8)


class SearchTopicArgs(ToolArgs):
    topic: str = Field(min_length=1, max_length=200)
    top_k: int = Field(default=config.QA_TOP_K, ge=1, le=8)


class SearchSimilarArgs(ToolArgs):
    chunk_index: int = Field(ge=0)
    top_k: int = Field(default=3, ge=1, le=8)


class NeighborArgs(ToolArgs):
    chunk_index: int = Field(ge=0)
    window: int = Field(default=1, ge=1, le=2)


class SearchMetadataArgs(ToolArgs):
    page: int = Field(ge=1)


def build_retrieval_tools(service: RetrievalService) -> List[ToolSpec]:
    def search_document(ctx: ToolContext, args: SearchDocumentArgs) -> ToolResult:
        chunks = service.search(ctx.scope, args.query, args.top_k)
        return ToolResult(ok=True, tool="search_document", chunks=chunks, data={"query": args.query})

    def search_topic(ctx: ToolContext, args: SearchTopicArgs) -> ToolResult:
        chunks = service.search(ctx.scope, args.topic, args.top_k)
        return ToolResult(ok=True, tool="search_topic", chunks=chunks, data={"topic": args.topic})

    def search_similar_chunks(ctx: ToolContext, args: SearchSimilarArgs) -> ToolResult:
        anchor = service.get_by_indices(ctx.scope, [args.chunk_index])
        if not anchor:
            return ToolResult(ok=False, tool="search_similar_chunks", error="chunk not found in this document")
        chunks = service.search(ctx.scope, anchor[0]["text"], args.top_k, exclude_index=args.chunk_index)
        return ToolResult(ok=True, tool="search_similar_chunks", chunks=chunks, data={"anchor": args.chunk_index})

    def get_neighbor_chunks(ctx: ToolContext, args: NeighborArgs) -> ToolResult:
        chunks = service.neighbors(ctx.scope, args.chunk_index, args.window)
        return ToolResult(ok=True, tool="get_neighbor_chunks", chunks=chunks, data={"anchor": args.chunk_index})

    def search_by_metadata(ctx: ToolContext, args: SearchMetadataArgs) -> ToolResult:
        if not service.metadata(ctx.scope)["has_page_metadata"]:
            return ToolResult(ok=False, tool="search_by_metadata", error="this document has no page metadata")
        chunks = service.by_page(ctx.scope, args.page)
        return ToolResult(ok=True, tool="search_by_metadata", chunks=chunks, data={"page": args.page})

    return [
        ToolSpec("search_document", "semantic search over the whole document for a query", SearchDocumentArgs, search_document),
        ToolSpec("search_topic", "semantic search for a topic phrase (broader than a question)", SearchTopicArgs, search_topic),
        ToolSpec("search_similar_chunks", "find chunks similar to an already-retrieved chunk", SearchSimilarArgs, search_similar_chunks),
        ToolSpec("get_neighbor_chunks", "fetch the chunks adjacent to a retrieved chunk (definitions that span chunks)", NeighborArgs, get_neighbor_chunks),
        ToolSpec("search_by_metadata", "fetch all chunks on a given page (only if the document has page metadata)", SearchMetadataArgs, search_by_metadata),
    ]
