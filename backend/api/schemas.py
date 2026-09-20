from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class IngestResponse(BaseModel):
    filename: str
    chunks_added: int


class AgentRequest(BaseModel):
    message: str
    filename: str
    session_id: str = "default"
    mode: str = ""  # optional explicit override; empty => the Supervisor Agent decides
    reset_quiz: bool = False
    history: List[Dict[str, str]] = []  # recent {role, content} turns, for follow-up context


class AgentResponse(BaseModel):
    mode: str
    reply: str
    retrieved_chunks: List[str] = []
    search_query: str = ""
    retrieval_attempts: int = 0
    generation_attempts: int = 0
    quiz_score: int = 0
    quiz_total: int = 0
    quiz_details: Optional[Dict[str, Any]] = None
    agent_trace: Optional[Dict[str, Any]] = None  # supervisor decision, tool calls, evaluations, budget usage
