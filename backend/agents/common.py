from typing import Any, Dict, Iterable, List


def format_chunks(chunks: Iterable[Dict[str, Any]]) -> str:
    parts = []
    for c in chunks:
        page = f", page {c['page']}" if c.get("page") is not None else ""
        parts.append(f"[chunk {c['chunk_index']}{page}]\n{c['text']}")
    return "\n\n".join(parts)


def format_history(history: List[Dict[str, str]], limit: int = 6, max_len: int = 300) -> str:
    lines = [f"{t.get('role', 'user')}: {str(t.get('content', ''))[:max_len]}" for t in (history or [])[-limit:]]
    return "\n".join(lines) if lines else "(none)"


def preview(text: str, n: int = 160) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= n else text[: n - 1] + "…"
