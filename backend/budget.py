"""Per-request execution budget. Deterministic Python - never controlled by an LLM."""
import threading
import time
from dataclasses import dataclass, field
from typing import Dict

from backend import config


class BudgetExceeded(Exception):
    """Raised when a request would exceed one of its hard limits."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


@dataclass
class Budget:
    max_llm_calls: int = config.MAX_LLM_CALLS
    max_tool_calls: int = config.MAX_TOOL_CALLS
    max_retrieval_attempts: int = config.MAX_RETRIEVAL_ATTEMPTS
    max_revisions: int = config.MAX_REVISIONS
    max_seconds: float = config.MAX_SECONDS
    started: float = field(default_factory=time.monotonic)
    llm_calls: int = 0
    tool_calls: int = 0
    retrieval_attempts: int = 0
    revisions: int = 0
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False, compare=False)

    def elapsed(self) -> float:
        return time.monotonic() - self.started

    def remaining_seconds(self) -> float:
        return max(0.0, self.max_seconds - self.elapsed())

    def expired(self) -> bool:
        return self.elapsed() >= self.max_seconds

    def charge_llm(self) -> None:
        if self.expired():
            raise BudgetExceeded("time_budget_exceeded")
        with self._lock:
            if self.llm_calls >= self.max_llm_calls:
                raise BudgetExceeded("llm_call_budget_exceeded")
            self.llm_calls += 1

    def charge_tool(self) -> None:
        if self.expired():
            raise BudgetExceeded("time_budget_exceeded")
        with self._lock:
            if self.tool_calls >= self.max_tool_calls:
                raise BudgetExceeded("tool_call_budget_exceeded")
            self.tool_calls += 1

    def can_retrieve(self) -> bool:
        return (
            not self.expired()
            and self.retrieval_attempts < self.max_retrieval_attempts
            and self.tool_calls < self.max_tool_calls
            and self.llm_calls < self.max_llm_calls - 2  # leave room for tutor + critic
        )

    def can_revise(self) -> bool:
        return (
            not self.expired()
            and self.revisions < self.max_revisions
            and self.llm_calls < self.max_llm_calls - 1
        )

    def snapshot(self) -> Dict[str, float]:
        return {
            "llm_calls": self.llm_calls,
            "tool_calls": self.tool_calls,
            "retrieval_attempts": self.retrieval_attempts,
            "revisions": self.revisions,
            "elapsed_seconds": round(self.elapsed(), 2),
            "max_llm_calls": self.max_llm_calls,
            "max_tool_calls": self.max_tool_calls,
            "max_retrieval_attempts": self.max_retrieval_attempts,
            "max_revisions": self.max_revisions,
            "max_seconds": self.max_seconds,
        }
