"""Retrieval guardrails - what counts as usable evidence, and the safe fallback message."""
from typing import Any, Dict, List

NOT_SUPPORTED_MESSAGE = "I couldn't find enough information about that in the uploaded document."


def get_grounding_fallback() -> str:
    """Standard reply when the document does not contain enough evidence."""
    return NOT_SUPPORTED_MESSAGE


def has_usable_evidence(chunks: List[Dict[str, Any]]) -> bool:
    return any((c.get("text") or "").strip() for c in chunks)
