"""GET /chat/history - the stored conversation for one learner + document."""
from fastapi import APIRouter, Depends, HTTPException, Query

from backend.container import Container, get_container
from backend.guardrails.input import validate_request_identity

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
    return {
        "title": c.chat.title(chat_id),
        "summary": c.chat.summary(chat_id),
        "messages": c.chat.list_messages(chat_id, limit),
    }
