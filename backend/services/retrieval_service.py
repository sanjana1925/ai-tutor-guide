"""
ChromaDB access. This is the ONLY module that touches the vector store, and every method
requires a `Scope` (session + document). Isolation filters are built here, in Python - the LLM
never supplies or influences them.
"""
import io
import uuid
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from pypdf import PdfReader

Chunk = Dict[str, Any]  # {"chunk_index": int, "text": str, "page": Optional[int], "distance": Optional[float]}


@dataclass(frozen=True)
class Scope:
    session_id: str
    document_id: str

    def __post_init__(self):
        if not self.session_id or not self.document_id:
            raise ValueError("Scope requires both a session_id and a document_id")


class RetrievalService:
    def __init__(self, collection, splitter):
        self._collection = collection
        self._splitter = splitter

    # ---- isolation ------------------------------------------------------
    @staticmethod
    def _where(scope: Scope, *extra: Dict[str, Any]) -> Dict[str, Any]:
        clauses = [{"source": scope.document_id}, {"session_id": scope.session_id}, *extra]
        return {"$and": clauses}

    @staticmethod
    def _to_chunks(documents, metadatas, distances=None) -> List[Chunk]:
        chunks: List[Chunk] = []
        for i, (doc, meta) in enumerate(zip(documents or [], metadatas or [])):
            page = meta.get("page")
            chunks.append(
                {
                    "chunk_index": int(meta.get("chunk_index", -1)),
                    "text": doc,
                    "page": int(page) if page is not None else None,
                    "distance": float(distances[i]) if distances is not None else None,
                }
            )
        return chunks

    # ---- reads ----------------------------------------------------------
    def get_records(self, scope: Scope) -> Tuple[List[Chunk], Optional[str]]:
        data = self._collection.get(where=self._where(scope), include=["documents", "metadatas"])
        docs = data.get("documents") or []
        metas = data.get("metadatas") or []
        if not docs:
            return [], None
        chunks = sorted(self._to_chunks(docs, metas), key=lambda c: c["chunk_index"])
        content_hash = metas[0].get("content_hash")
        return chunks, content_hash

    def get_texts(self, scope: Scope) -> List[str]:
        chunks, _ = self.get_records(scope)
        return [c["text"] for c in chunks]

    def total_chunks(self) -> int:
        return self._collection.count()

    def count(self, scope: Scope) -> int:
        return len(self._collection.get(where=self._where(scope), include=[]).get("ids") or [])

    def metadata(self, scope: Scope) -> Dict[str, Any]:
        chunks, content_hash = self.get_records(scope)
        pages = [c["page"] for c in chunks if c["page"] is not None]
        return {
            "document_id": scope.document_id,
            "num_chunks": len(chunks),
            "has_page_metadata": bool(pages),
            "num_pages": max(pages) if pages else None,
            "indexed": bool(chunks),
            "content_hash": content_hash,
        }

    def search(self, scope: Scope, query: str, top_k: int = 4, exclude_index: Optional[int] = None) -> List[Chunk]:
        total = self.count(scope)
        if total == 0:
            return []
        n = min(top_k + (1 if exclude_index is not None else 0), total)
        res = self._collection.query(
            query_texts=[query], n_results=n, where=self._where(scope), include=["documents", "metadatas", "distances"]
        )
        if not res["documents"]:
            return []
        chunks = self._to_chunks(res["documents"][0], res["metadatas"][0], res["distances"][0])
        if exclude_index is not None:
            chunks = [c for c in chunks if c["chunk_index"] != exclude_index]
        return chunks[:top_k]

    def get_by_indices(self, scope: Scope, indices: List[int]) -> List[Chunk]:
        if not indices:
            return []
        data = self._collection.get(
            where=self._where(scope, {"chunk_index": {"$in": [int(i) for i in indices]}}),
            include=["documents", "metadatas"],
        )
        return sorted(self._to_chunks(data.get("documents"), data.get("metadatas")), key=lambda c: c["chunk_index"])

    def neighbors(self, scope: Scope, chunk_index: int, window: int = 1) -> List[Chunk]:
        wanted = [i for i in range(chunk_index - window, chunk_index + window + 1) if i >= 0 and i != chunk_index]
        return self.get_by_indices(scope, wanted)

    def by_page(self, scope: Scope, page: int) -> List[Chunk]:
        data = self._collection.get(where=self._where(scope, {"page": int(page)}), include=["documents", "metadatas"])
        return sorted(self._to_chunks(data.get("documents"), data.get("metadatas")), key=lambda c: c["chunk_index"])

    # ---- writes ---------------------------------------------------------
    def delete(self, scope: Scope) -> None:
        self._collection.delete(where=self._where(scope))

    def index_pdf(self, scope: Scope, pdf_bytes: bytes, content_hash: str) -> int:
        """Split page by page so every chunk keeps its page number. Returns chunks added."""
        reader = PdfReader(io.BytesIO(pdf_bytes))
        texts: List[str] = []
        metadatas: List[Dict[str, Any]] = []
        for page_number, page in enumerate(reader.pages, start=1):
            page_text = page.extract_text() or ""
            for piece in self._splitter.split_text(page_text) if page_text.strip() else []:
                metadatas.append(
                    {
                        "source": scope.document_id,
                        "session_id": scope.session_id,
                        "chunk_index": len(texts),
                        "content_hash": content_hash,
                        "page": page_number,
                    }
                )
                texts.append(piece)
        if not texts:
            return 0
        self._collection.add(documents=texts, ids=[str(uuid.uuid4()) for _ in texts], metadatas=metadatas)
        return len(texts)
