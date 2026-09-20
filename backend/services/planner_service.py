"""
Study-plan rules (deterministic). planner.py computes the learner's real statistics and
priorities; the Planner Agent may only add wording/activity/time on top of them. This module
rejects any agent proposal that invents topics, changes priorities, or quotes statistics
that are not in the learner's recorded data.
"""
import re
from typing import Any, Dict, List, Optional, Set

from backend import config
from backend.agents.schemas import StudyPlanProposal
from backend.domain.planner import generate_study_plan
from backend.domain.quiz_engine import LearnerState

_NUMBER = re.compile(r"\d+(?:\.\d+)?")


def deterministic_plan(state: LearnerState) -> Dict[str, Any]:
    return generate_study_plan(state)


THRESHOLDS = {60.0, 70.0, 80.0}  # documented weak / strong / moderate cut-offs in quiz_engine + planner


def allowed_numbers(plan: Dict[str, Any]) -> Set[float]:
    allowed: Set[float] = set(THRESHOLDS)
    for item in plan["items"]:
        for text in (item.get("accuracy", ""), item.get("estimated_study_time", "")):
            allowed.update(float(n) for n in _NUMBER.findall(text))
    allowed.update(float(n) for n in _NUMBER.findall(plan.get("overall_accuracy", "")))
    allowed.add(float(plan.get("total_attempted", 0)))
    return allowed


def validate_proposal(proposal: Optional[StudyPlanProposal], plan: Dict[str, Any]) -> Optional[str]:
    """Returns None if acceptable, otherwise the reason it was rejected."""
    if proposal is None:
        return "no proposal"
    expected = {i["topic"]: i["priority"].lower() for i in plan["items"]}
    got = {i.topic: i.priority for i in proposal.items}
    if set(got) != set(expected):
        return "proposal topics differ from the learner's recorded topics"
    if len(proposal.items) != len(got):
        return "duplicate topics in proposal"
    allowed = allowed_numbers(plan)
    for item in proposal.items:
        if got[item.topic] != expected[item.topic]:
            return f"priority for '{item.topic}' contradicts recorded performance"
        if not (config.PLANNER_MIN_MINUTES <= item.estimated_minutes <= config.PLANNER_MAX_MINUTES):
            return f"estimated minutes for '{item.topic}' out of range"
        item_allowed = allowed | {float(item.estimated_minutes)}
        invented = [n for n in _NUMBER.findall(item.reason) if float(n) not in item_allowed]
        if invented:
            return f"reason for '{item.topic}' quotes numbers that are not in the learner's data: {invented}"
    return None


def merge(plan: Dict[str, Any], proposal: StudyPlanProposal) -> Dict[str, Any]:
    by_topic = {i.topic: i for i in proposal.items}
    merged = dict(plan)
    merged_items: List[Dict[str, Any]] = []
    for item in plan["items"]:
        p = by_topic[item["topic"]]
        enriched = dict(item)
        enriched["activity"] = p.activity
        enriched["estimated_minutes"] = p.estimated_minutes
        enriched["estimated_study_time"] = f"{p.estimated_minutes} mins"
        enriched["reason"] = p.reason
        merged_items.append(enriched)
    merged["items"] = merged_items
    return merged


def plan_signature(state: LearnerState) -> str:
    """Cache key: the enhanced plan only needs regenerating when the learner's data changes."""
    topics = ",".join(f"{t}:{s.attempts}:{s.correct}" for t, s in sorted(state.topic_stats.items()))
    return f"{state.total_attempted}|{state.total_correct}|{state.current_phase}|{topics}"
