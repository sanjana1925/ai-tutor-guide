"""
Deterministic quiz rules. Nothing in this module calls an LLM.

Python owns: validating generated questions (schema, distinct options, difficulty == phase,
duplicates, grounding in the provided excerpts), scoring, progression (via quiz_engine),
and what the browser is allowed to see.
"""
import re
from typing import Any, Dict, List, Optional, Tuple

from backend import config
from backend.agents.schemas import QuizEvaluation
from backend.guardrails.output import validate_quiz_question
from backend.domain.quiz_engine import SIMPLE_REQUIRED_QUESTIONS, LearnerState, record_quiz_answer

_WS = re.compile(r"\s+")
_NON_WORD = re.compile(r"[^\w\s]")


def normalize(text: str) -> str:
    return _WS.sub(" ", _NON_WORD.sub(" ", (text or "").lower())).strip()


def similarity(a: str, b: str) -> float:
    ta, tb = set(normalize(a).split()), set(normalize(b).split())
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def is_duplicate(question: str, asked: List[str], threshold: float = config.QUIZ_DUPLICATE_SIMILARITY) -> bool:
    norm = normalize(question)
    return any(norm == normalize(q) or similarity(question, q) >= threshold for q in asked)


def quote_is_grounded(quote: str, excerpts: List[str]) -> bool:
    """The model must back its correct answer with a verbatim quote from the excerpts it was given."""
    q = normalize(quote)
    if len(q) < 15:
        return False
    return any(q in normalize(e) for e in excerpts)


def validate_generated_question(
    q: Optional[Dict[str, Any]], phase: str, asked: List[str], excerpts: List[str]
) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
    if not q:
        return False, "no question produced", None
    q = dict(q)
    ok, reason = validate_quiz_question(q)
    if not ok:
        return False, reason, None
    if q["difficulty"].lower() != phase.lower():
        # The phase is decided by Python. A mismatched label is corrected, not trusted.
        q["difficulty"] = phase.lower()
    if is_duplicate(q["question"], asked):
        return False, "duplicate of an earlier question", None
    if not quote_is_grounded(q.get("source_quote", ""), excerpts):
        return False, "answer is not backed by a verbatim quote from the document excerpts", None
    return True, "", q


def fallback_question(document_id: str, phase: str) -> Dict[str, Any]:
    return {
        "question": f"What is a fundamental concept discussed in {document_id}?",
        "options": ["Core Definition", "Unsupported Claim", "Irrelevant Detail", "Random Fact"],
        "correct_answer_index": 0,
        "topic": "Core Concepts",
        "difficulty": phase.lower(),
        "explanation": "Derived from key document concepts.",
    }


def parse_selection(message: str) -> int:
    """Turns a learner's raw reply into an option index 0..3, or -1."""
    clean = message.strip().lower()
    if clean.isdigit():
        idx = int(clean)
        if 0 <= idx <= 3:
            return idx
    mapping = {"a": 0, "b": 1, "c": 2, "d": 3, "option 1": 0, "option 2": 1, "option 3": 2, "option 4": 3}
    for k, v in mapping.items():
        if clean == k or clean.startswith(k):
            return v
    return -1


def score_pending_answer(state: LearnerState, message: str) -> Tuple[QuizEvaluation, str, List[str]]:
    """Grades the pending question in pure Python and updates the learner's profile via quiz_engine."""
    q = state.current_question or {}
    correct_idx = q.get("correct_answer_index", 0)
    options = q.get("options", [])
    selected = parse_selection(message)
    if selected == -1:
        text_match = any(opt.lower() in message.lower() for opt in options[correct_idx : correct_idx + 1]) if options else False
        is_correct = text_match
        selected = correct_idx if text_match else -1
    else:
        is_correct = selected == correct_idx

    phase_before = state.current_phase
    res = record_quiz_answer(state, is_correct, q.get("topic", "General"), q.get("question", ""))
    evaluation = QuizEvaluation(
        correct=is_correct,
        selected_index=selected,
        correct_index=correct_idx,
        phase_before=phase_before,
        phase_after=state.current_phase,
        phase_transitioned=res["phase_transitioned"],
        overall_accuracy=res["overall_accuracy"],
    )
    status = "✅ **Correct!**" if is_correct else f"❌ **Incorrect.** (Correct option: **{options[correct_idx]}**)"
    parts = [f"{status}\n\n*{q.get('explanation', '')}*"]
    if res["phase_transitioned"]:
        parts.append(
            f"🎉 **Benchmark Achieved!** You scored **{res['overall_accuracy']}%** and progressed "
            f"to the **{res['current_phase']}** difficulty phase!"
        )
    return evaluation, status, parts


def public_question(q: Dict[str, Any]) -> Dict[str, Any]:
    """What the browser may see before answering: never the answer, explanation or source quote."""
    return {"question": q["question"], "options": q["options"], "topic": q["topic"], "difficulty": q["difficulty"]}


def format_question_block(state: LearnerState, q: Dict[str, Any]) -> str:
    opts = "\n".join(f"{i}. {opt}" for i, opt in enumerate(q["options"]))
    phase_info = f"Phase: **{state.current_phase}** | Question **{state.phase_question_count + 1}**"
    if state.current_phase == "SIMPLE":
        phase_info += f" of {SIMPLE_REQUIRED_QUESTIONS}"
    return (
        f"--- \n\n📊 `{phase_info}`\n\n**Question:** {q['question']}\n\n{opts}\n\n"
        "_Type the option index (0, 1, 2, 3) or option text below._"
    )
