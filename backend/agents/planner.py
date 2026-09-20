"""
Study Planner Agent.

The learner's statistics and priorities come from Python (planner.py via planner_service) and the
read-only learning tools. The agent decides only the study activity, the time to spend and the
wording of the reason. `planner_service.validate_proposal` rejects any proposal that invents
topics, changes a priority, or quotes numbers that are not in the learner's recorded data; in that
case (or if the model is unavailable) the deterministic plan is returned unchanged.
"""
from typing import Any, Dict, Optional, Tuple

from backend.agents.schemas import StudyPlanProposal
from backend.budget import Budget, BudgetExceeded
from backend.services import planner_service
from backend.services.learner_state_service import LearnerStateService
from backend.services.llm_service import LLM
from backend.services.retrieval_service import Scope
from backend.tools.base import ToolContext, ToolRegistry

PLANNER_SYSTEM = (
    "You are a study planner. You are given the learner's REAL recorded performance per topic. For every topic, "
    "decide the best study activity (review, practice, review_and_practice, or maintain), a realistic time "
    "estimate in minutes (5-60), and a one-sentence encouraging reason. Include every topic exactly once and keep "
    "each topic's priority exactly as given (lowercase). Do not mention any number that is not in the data given."
)

PLANNER_TOOLS = ["get_learning_history", "get_topic_performance"]


class StudyPlannerAgent:
    name = "study_planner_agent"

    def __init__(self, llm: LLM, registry: ToolRegistry, learner: LearnerStateService):
        self.llm = llm
        self.registry = registry.subset(PLANNER_TOOLS)
        self.learner = learner
        self._cache: Dict[Tuple[str, str], Tuple[str, Dict[str, Any]]] = {}

    def plan(self, *, scope: Scope, budget: Budget) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        state = self.learner.get(scope)
        det = planner_service.deterministic_plan(state)
        meta: Dict[str, Any] = {"step": "study_planner_agent"}

        if state.total_attempted == 0:
            meta["source"] = "deterministic_no_data"
            return det, meta
        if not det["items"]:
            # Nothing to advise on yet (no topic has enough answers): no model call needed.
            meta["source"] = "deterministic_no_topics"
            return det, meta

        signature = planner_service.plan_signature(state)
        cached = self._cache.get((scope.session_id, scope.document_id))
        if cached and cached[0] == signature:
            meta["source"] = "cache"
            return cached[1], meta

        ctx = ToolContext(scope=scope, budget=budget)
        history = self.registry.run("get_learning_history", ctx, {})
        perf = self.registry.run("get_topic_performance", ctx, {})
        meta["observed"] = {"history_ok": history.ok, "performance_ok": perf.ok}

        stats = perf.data.get("topic_stats", {}) if perf.ok else {}
        rows = [
            {
                "topic": i["topic"],
                "priority": i["priority"].lower(),
                "accuracy": i["accuracy"],
                "attempts": stats.get(i["topic"], {}).get("attempts"),
                "correct": stats.get(i["topic"], {}).get("correct"),
            }
            for i in det["items"]
        ]
        prompt = f"Learner performance (real data): {history.data if history.ok else {}}\nTopics: {rows}"
        try:
            proposal: Optional[StudyPlanProposal] = self.llm.structured(StudyPlanProposal, prompt, PLANNER_SYSTEM, budget=budget, name="study_planner_agent.propose")
        except BudgetExceeded:
            proposal = None

        rejection = planner_service.validate_proposal(proposal, det)
        if rejection is not None:
            meta["source"] = "deterministic_fallback"
            meta["rejected_because"] = rejection
            return det, meta

        enriched = planner_service.merge(det, proposal)
        self._cache[(scope.session_id, scope.document_id)] = (signature, enriched)
        meta["source"] = "agent"
        return enriched, meta
