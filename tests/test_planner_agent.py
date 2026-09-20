"""Study Planner Agent: the LLM may add wording/time, never learner statistics."""
import unittest

from helpers import Env

from backend.agents.schemas import StudyPlanItem, StudyPlanProposal
from backend.budget import Budget
from backend.services import planner_service
from backend.domain.quiz_engine import record_quiz_answer


def seed(env):
    s = env.learner.get(env.scope)
    for i, ok in enumerate([False, False, False]):
        record_quiz_answer(s, ok, "Balancing", f"b{i}")          # 0%  -> weak (High)
    for i, ok in enumerate([True, True, False]):
        record_quiz_answer(s, ok, "Corrosion", f"c{i}")           # 66.7% -> Medium
    for i, ok in enumerate([True, True]):
        record_quiz_answer(s, ok, "Reactions", f"r{i}")           # 100% -> Low
    return s


def proposal(plan, **override):
    items = []
    for it in plan["items"]:
        base = dict(topic=it["topic"], priority=it["priority"].lower(), activity="review_and_practice",
                    estimated_minutes=20, reason="A short encouraging reason.")
        base.update(override.get(it["topic"], {}))
        items.append(StudyPlanItem(**base))
    return StudyPlanProposal(items=items, summary="s")


class PlannerAgent(unittest.TestCase):
    def setUp(self):
        self.env = Env()
        seed(self.env)
        self.plan = planner_service.deterministic_plan(self.env.learner.get(self.env.scope))

    def tearDown(self):
        self.env.close()

    def run_agent(self, *script):
        self.env.llm.script = {"study_planner_agent.propose": list(script)}
        return self.env.deps.planner.plan(scope=self.env.scope, budget=Budget())

    def test_valid_proposal_enriches_the_plan_and_keeps_real_statistics(self):
        plan, meta = self.run_agent(proposal(self.plan))
        self.assertEqual(meta["source"], "agent")
        for before, after in zip(self.plan["items"], plan["items"]):
            self.assertEqual((before["topic"], before["priority"], before["accuracy"]), (after["topic"], after["priority"], after["accuracy"]))
            self.assertEqual(after["activity"], "review_and_practice")
            self.assertEqual(after["estimated_study_time"], "20 mins")
        self.assertEqual(plan["overall_accuracy"], self.plan["overall_accuracy"])

    def test_agent_reads_learner_data_through_read_only_tools(self):
        _, meta = self.run_agent(proposal(self.plan))
        self.assertEqual(meta["observed"], {"history_ok": True, "performance_ok": True})
        prompt = self.env.llm.prompts[-1]
        self.assertIn("Balancing", prompt)

    def test_invented_topic_is_rejected(self):
        bad = proposal(self.plan)
        bad.items.append(StudyPlanItem(topic="Quantum Gravity", priority="high", activity="review", estimated_minutes=30, reason="r"))
        plan, meta = self.run_agent(bad)
        self.assertEqual(meta["source"], "deterministic_fallback")
        self.assertEqual(plan["items"], self.plan["items"])

    def test_changed_priority_is_rejected(self):
        plan, meta = self.run_agent(proposal(self.plan, Balancing={"priority": "low"}))
        self.assertEqual(meta["source"], "deterministic_fallback")
        self.assertIn("priority", meta["rejected_because"])

    def test_invented_statistics_in_the_reason_are_rejected(self):
        plan, meta = self.run_agent(proposal(self.plan, Balancing={"reason": "You only scored 12% here, keep going."}))
        self.assertEqual(meta["source"], "deterministic_fallback")
        self.assertIn("numbers", meta["rejected_because"])

    def test_real_statistics_in_the_reason_are_allowed(self):
        plan, meta = self.run_agent(proposal(self.plan, Balancing={"reason": "Accuracy is 0.0%, below the 60% threshold."}))
        self.assertEqual(meta["source"], "agent")

    def test_out_of_range_minutes_are_rejected(self):
        for minutes in (0, 3, 500):
            _, meta = self.run_agent(proposal(self.plan, Balancing={"estimated_minutes": minutes}))
            self.assertEqual(meta["source"], "deterministic_fallback", minutes)

    def test_invalid_model_output_falls_back_to_the_deterministic_plan(self):
        plan, meta = self.run_agent(None)
        self.assertEqual(meta["source"], "deterministic_fallback")
        self.assertEqual(plan["items"], self.plan["items"])

    def test_no_learning_data_needs_no_llm_call(self):
        env = Env()
        plan, meta = env.deps.planner.plan(scope=env.scope, budget=Budget())
        self.assertEqual(meta["source"], "deterministic_no_data")
        self.assertEqual(env.llm.calls, [])
        env.close()

    def test_no_topics_with_enough_answers_needs_no_llm_call(self):
        env = Env()
        record_quiz_answer(env.learner.get(env.scope), False, "OneAttemptTopic", "q1")  # 1 attempt: not yet a weak/strong/medium topic
        plan, meta = env.deps.planner.plan(scope=env.scope, budget=Budget())
        self.assertEqual((plan["items"], meta["source"], env.llm.calls), ([], "deterministic_no_topics", []))
        env.close()

    def test_plan_is_cached_until_the_learner_data_changes(self):
        self.run_agent(proposal(self.plan))
        calls = len(self.env.llm.calls)
        _, meta = self.env.deps.planner.plan(scope=self.env.scope, budget=Budget())
        self.assertEqual((meta["source"], len(self.env.llm.calls)), ("cache", calls))
        record_quiz_answer(self.env.learner.get(self.env.scope), True, "Balancing", "new")
        plan2 = planner_service.deterministic_plan(self.env.learner.get(self.env.scope))
        self.env.llm.script = {"study_planner_agent.propose": [proposal(plan2)]}
        _, meta = self.env.deps.planner.plan(scope=self.env.scope, budget=Budget())
        self.assertEqual(meta["source"], "agent")


if __name__ == "__main__":
    unittest.main()
