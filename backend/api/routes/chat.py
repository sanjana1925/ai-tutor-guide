"""GET /chat/history - the stored conversation for one learner + document."""
from fastapi import APIRouter, Depends, HTTPException, Query

from backend.container import Container, get_container
from backend.guardrails.input import validate_request_identity
from backend.services.retrieval_service import Scope

router = APIRouter()


@router.get("/chat/history")
def chat_history(session_id: str, filename: str, limit: int = Query(default=100, ge=1, le=500), c: Container = Depends(get_container)):
    ok, err = validate_request_identity(session_id, filename)
    if not ok:
        raise HTTPException(status_code=400, detail=err)
    # The chat session is resolved from (session_id, filename) only - clients never address it by id.
    chat_id = c.chat.find_session(session_id, filename)
    if not chat_id:
        return {"title": "", "summary": "", "messages": []}
    messages = c.chat.list_messages(chat_id, limit)
    # Attach the text of each cited chunk so the UI can show what an answer was based on.
    wanted = sorted({i for m in messages for s in m["sources"] for i in s["chunk_ids"]})
    text_by_index = {ch["chunk_index"]: ch["text"] for ch in c.retrieval.get_by_indices(Scope(session_id, filename), wanted)}
    for m in messages:
        for s in m["sources"]:
            s["excerpts"] = [text_by_index[i] for i in s["chunk_ids"] if i in text_by_index]
    return {
        "title": c.chat.title(chat_id),
        "summary": c.chat.summary(chat_id),
        "messages": messages,
    }
