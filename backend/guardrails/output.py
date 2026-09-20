"""Output guardrails - deterministic checks applied to generated content."""
from typing import Any, Dict, Iterable, Optional, Tuple

MAX_ANSWER_LENGTH = 8000

# Fragments of our own system instructions; an answer containing them is a leak.
_LEAK_MARKERS = (
    "you are a friendly, patient ai tutor",
    "stay strictly grounded in the context",
    "classify the user's latest message",
    "you judge whether retrieved",
)


def validate_answer(answer: str, evidence_indices: Optional[Iterable[int]] = None, cited: Optional[Iterable[int]] = None) -> Tuple[bool, str]:
    if not answer or not answer.strip():
        return False, "empty answer"
    if len(answer) > MAX_ANSWER_LENGTH:
        return False, "answer too long"
    lowered = answer.lower()
    if any(marker in lowered for marker in _LEAK_MARKERS):
        return False, "answer exposes internal instructions"
    if evidence_indices is not None and cited is not None:
        allowed = set(evidence_indices)
        bad = [c for c in cited if c not in allowed]
        if bad:
            return False, f"answer cites chunks that were never retrieved: {bad}"
    return True, ""


def validate_quiz_question(q_data: Dict[str, Any]) -> Tuple[bool, str]:
    """
    Structural validation of a generated quiz question: question text, exactly 4 distinct
    non-empty options, a valid correct index, a topic and a known difficulty.
    """
    if not isinstance(q_data, dict):
        return False, "Quiz question must be a dictionary object."

    question = (q_data.get("question") or "").strip()
    options = q_data.get("options", [])
    correct_idx = q_data.get("correct_answer_index")
    topic = (q_data.get("topic") or "").strip()
    difficulty = (q_data.get("difficulty") or "").strip()

    if not question:
        return False, "Question text is empty."

    if not isinstance(options, list) or len(options) != 4:
        return False, "Quiz question must contain exactly 4 options."

    if any(not isinstance(opt, str) or not opt.strip() for opt in options):
        return False, "All 4 options must be non-empty strings."

    if len({opt.strip().lower() for opt in options}) != 4:
        return False, "Options must be distinct so exactly one is correct."

    if not isinstance(correct_idx, int) or isinstance(correct_idx, bool) or correct_idx < 0 or correct_idx >= 4:
        return False, "correct_answer_index must be an integer between 0 and 3."

    if not topic:
        return False, "Topic tag is missing."

    if difficulty.lower() not in ["simple", "medium", "high"]:
        return False, "Difficulty must be one of 'simple', 'medium', or 'high'."

    return True, ""
