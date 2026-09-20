"""
Study Planner module for the AI Tutor Platform.
Generates personalized, data-driven study plans based on actual learner telemetry.
"""
from typing import Dict, Any, List
from pydantic import BaseModel
from backend.domain.quiz_engine import LearnerState


class StudyItem(BaseModel):
    priority: str  # "High", "Medium", "Low"
    topic: str
    accuracy: str
    recommendation: str
    estimated_study_time: str
    reason: str


class StudyPlan(BaseModel):
    filename: str
    overall_accuracy: str
    current_phase: str
    total_attempted: int
    items: List[StudyItem]
    general_summary: str


def generate_study_plan(state: LearnerState) -> Dict[str, Any]:
    """
    Generates a personalized study plan based strictly on recorded user performance data.
    Does not fabricate stats or display metrics without sufficient data.
    """
    if state.total_attempted == 0:
        return StudyPlan(
            filename=state.filename,
            overall_accuracy="0.0%",
            current_phase=state.current_phase,
            total_attempted=0,
            items=[
                StudyItem(
                    priority="High",
                    topic="Initial Assessment",
                    accuracy="N/A",
                    recommendation="Take the initial 15-question SIMPLE assessment to diagnose your baseline knowledge.",
                    estimated_study_time="10 mins",
                    reason="No quiz attempts recorded yet.",
                )
            ],
            general_summary="Take an adaptive quiz to unlock customized study recommendations.",
        ).model_dump()

    items: List[StudyItem] = []

    # Process weak topics first (High Priority)
    weak_topics = state.get_weak_topics()
    for topic in weak_topics:
        stats = state.topic_stats[topic]
        items.append(
            StudyItem(
                priority="High",
                topic=topic,
                accuracy=f"{stats.accuracy:.1f}%",
                recommendation=f"Review concepts related to '{topic}'. Focus on core definitions and practice related questions.",
                estimated_study_time="15 mins",
                reason=f"Topic accuracy ({stats.accuracy:.1f}%) is below the 60% threshold.",
            )
        )

    # Process moderate topics (Medium Priority)
    for topic, stats in state.topic_stats.items():
        if topic not in weak_topics and stats.attempts >= 2 and 60.0 <= stats.accuracy < 80.0:
            items.append(
                StudyItem(
                    priority="Medium",
                    topic=topic,
                    accuracy=f"{stats.accuracy:.1f}%",
                    recommendation=f"Attempt medium difficulty practice questions on '{topic}' to solidify understanding.",
                    estimated_study_time="10 mins",
                    reason=f"Moderate proficiency ({stats.accuracy:.1f}%). Push towards high accuracy.",
                )
            )

    # Process strong topics (Low Priority / Mastery)
    strong_topics = state.get_strong_topics()
    for topic in strong_topics:
        stats = state.topic_stats[topic]
        items.append(
            StudyItem(
                priority="Low",
                topic=topic,
                accuracy=f"{stats.accuracy:.1f}%",
                recommendation=f"Mastered! Periodically test yourself on '{topic}' to maintain retention.",
                estimated_study_time="5 mins",
                reason=f"Strong accuracy achieved ({stats.accuracy:.1f}%).",
            )
        )

    summary = (
        f"You have attempted {state.total_attempted} questions with an overall accuracy of {state.get_overall_accuracy():.1f}%. "
        f"You are currently in the **{state.current_phase}** phase."
    )
    if weak_topics:
        summary += f" Focus on revising {len(weak_topics)} high-priority topic(s): {', '.join(weak_topics)}."

    return StudyPlan(
        filename=state.filename,
        overall_accuracy=f"{state.get_overall_accuracy():.1f}%",
        current_phase=state.current_phase,
        total_attempted=state.total_attempted,
        items=items,
        general_summary=summary,
    ).model_dump()
