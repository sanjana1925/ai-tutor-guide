"""POST /agent - the single chat/quiz/guide endpoint. Request and response shapes are unchanged."""
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException

from backend import config
from backend.agents.supervisor import VALID_MODES
from backend.api.schemas import AgentRequest, AgentResponse
from backend.api.security import require_api_key
from backend.container import Container, get_container
from backend.graph.workflow import run_request
from backend.guardrails.input import validate_input, validate_request_identity
from backend.services.retrieval_service import Scope

router = APIRouter()

QUIZ_EXIT_PHRASES = {"stop", "stop quiz", "end quiz", "quit", "quit quiz", "cancel", "cancel quiz", "exit quiz"}
DOCUMENT_MODES = {"summary", "key_points", "eli5", "glossary", "quiz"}


@router.post("/agent", response_model=AgentResponse)
def agent(
    request: AgentRequest,
    background: BackgroundTasks,
    _: None = Depends(require_api_key),
    c: Container = Depends(get_container),
):
    ok, err = validate_request_identity(request.session_id, request.filename)
    if not ok:
        raise HTTPException(status_code=400, detail=err)

    # Input guardrail - deterministic, before any agent sees the request.
    valid_input, guardrail_err = validate_input(request.message)
    if not valid_input:
        return AgentResponse(mode="guardrail_blocked", reply=f"⚠️ {guardrail_err}")

    if request.mode and request.mode not in VALID_MODES:
        raise HTTPException(status_code=400, detail=f"Unknown mode '{request.mode}'")

    scope = Scope(request.session_id, request.filename)
    if request.mode in DOCUMENT_MODES and c.retrieval.count(scope) == 0:
        raise HTTPException(status_code=404, detail=f"No indexed document found named '{request.filename}'")

    state = c.learner.get(scope)
    if request.reset_quiz:
        state.current_question = None
        c.learner.save(state)

    if state.current_question and request.message.strip().lower() in QUIZ_EXIT_PHRASES:
        score, total, acc = state.total_correct, state.total_attempted, state.get_overall_accuracy()
        state.current_question = None
        c.learner.save(state)
        return AgentResponse(
            mode="quiz_end",
            reply=f"🏁 Quiz ended. Final Score: {score}/{total} ({acc:.1f}% accuracy).",
            quiz_score=score,
            quiz_total=total,
        )

    # Memory: only the recent window and a rolling summary go to the model - never the full history.
    # The server's stored history is authoritative; a client-supplied history is only a fallback for
    # conversations that pre-date server-side storage.
    chat_id = c.chat.find_session(request.session_id, request.filename)
    recent = c.chat.recent_messages(chat_id, config.CHAT_RECENT_MESSAGES) or request.history[-config.CHAT_RECENT_MESSAGES :]

    final, budget = run_request(
        c.graph,
        message=request.message,
        session_id=request.session_id,
        document_id=request.filename,
        history=recent,
        conversation_summary=c.chat.summary(chat_id),
        mode_override=request.mode,
        quiz_pending=state.current_question is not None,
    )

    llm_error = final.get("llm_error")
    if llm_error:
        raise HTTPException(status_code=llm_error["status"], detail=llm_error["detail"])

    mode, reply = final.get("mode", "qa"), final.get("reply", "")
    if mode != "quiz" and reply:  # quiz turns are quiz attempts, not chat
        chat_id = c.chat.get_or_create_session(request.session_id, request.filename)
        c.chat.add_exchange(chat_id, request.message, reply, request.filename, final.get("source_chunk_ids"))
        background.add_task(c.memory.refresh, chat_id)

    return AgentResponse(
        mode=mode,
        reply=reply,
        retrieved_chunks=final.get("retrieved_chunks", []),
        search_query=final.get("search_query", ""),
        retrieval_attempts=budget.retrieval_attempts,
        generation_attempts=final.get("generation_attempts", 0),
        quiz_score=final.get("quiz_score", 0),
        quiz_total=final.get("quiz_total", 0),
        quiz_details=final.get("quiz_details"),
        agent_trace={"events": final.get("trace", []), "budget": budget.snapshot(), "stop_reason": final.get("stop_reason")},
    )
