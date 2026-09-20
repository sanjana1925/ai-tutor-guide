"""Agent behaviour: decisions, tool selection, retries, evidence insufficiency, critic loop, hard limits."""
import unittest

from helpers import Env, critic, evaluation, supervisor, tutor

from backend.agents.retrieval import EvidenceEvaluator
from backend.agents.schemas import CriticEvaluation, RetrievalDecision, SupervisorDecision
from backend.agents.supervisor import normalize
from backend.budget import Budget
from backend.graph.workflow import run_request
from backend.guardrails.retrieval import NOT_SUPPORTED_MESSAGE
from backend.graph.nodes import TIME_MESSAGE


def steps(final):
    return [e["step"] for e in final["trace"]]


class HappyPath(unittest.TestCase):
    def test_qa_runs_supervisor_retrieval_evaluator_tutor_critic_guardrail(self):
        env = Env({
            "supervisor_agent.decide": [supervisor()],
            "evidence_evaluator.evaluate": [evaluation()],
            "tutor_agent.write": [tutor()],
            "critic_agent.review": [critic()],
        })
        final, budget = env.ask()
        self.assertEqual(final["reply"], "Mass is conserved in a chemical reaction.")
        self.assertEqual(steps(final), ["supervisor_agent", "retrieval_agent", "evidence_evaluator", "tutor_agent", "critic_agent", "output_guardrail"])
        self.assertEqual(len(env.llm.calls), 4)
        self.assertEqual((budget.retrieval_attempts, budget.revisions), (1, 0))
        env.close()

    def test_answer_cites_only_retrieved_chunks(self):
        env = Env({"supervisor_agent.decide": [supervisor()], "evidence_evaluator.evaluate": [evaluation()],
                   "tutor_agent.write": [tutor(chunks=(0,))], "critic_agent.review": [critic()]})
        final, _ = env.ask()
        self.assertEqual(len(final["retrieved_chunks"]), 1)
        self.assertIn("conservation of mass", final["retrieved_chunks"][0])
        env.close()


class SupervisorDecisions(unittest.TestCase):
    def test_explicit_mode_needs_no_llm_call(self):
        env = Env({"guide_agent.summarize": ["A summary that is long enough to be valid."]})
        final, _ = env.ask("Summarize", mode_override="summary")
        self.assertEqual(env.llm.calls, ["guide_agent.summarize"])
        self.assertEqual(final["trace"][0]["source"], "explicit_mode")
        env.close()

    def test_quiz_answer_shortcut_skips_llm_classification(self):
        env = Env({"quiz_agent.generate_question": [None]})
        env.learner.get(env.scope).current_question = {
            "question": "q", "options": ["a", "b", "c", "d"], "correct_answer_index": 0, "topic": "t", "difficulty": "simple", "explanation": "e"}
        final, _ = env.ask("1", quiz_pending=True)
        self.assertEqual(final["trace"][0]["source"], "quiz_answer_shortcut")
        self.assertNotIn("supervisor_agent.decide", env.llm.calls)
        env.close()

    def test_invalid_structured_output_falls_back_to_qa(self):
        env = Env({"supervisor_agent.decide": [None], "evidence_evaluator.evaluate": [evaluation()],
                   "tutor_agent.write": [tutor()], "critic_agent.review": [critic()]})
        final, _ = env.ask()
        self.assertEqual(final["trace"][0]["source"], "fallback")
        self.assertEqual(final["mode"], "qa")
        env.close()

    def test_python_normalises_contradictory_decisions(self):
        d = supervisor("qa", next_action="clarify", needs_retrieval=False)
        n = normalize(d, "hi")
        self.assertEqual((n.next_action, n.needs_retrieval), ("retrieve", True))
        other = normalize(supervisor("other", next_action="retrieve"), "hello")
        self.assertEqual(other.next_action, "clarify")
        quiz = normalize(supervisor("quiz", next_action="retrieve"), "quiz me")
        self.assertEqual(quiz.next_action, "quiz")

    def test_supervisor_schema_rejects_bad_values(self):
        with self.assertRaises(Exception):
            SupervisorDecision(intent="hack", goal="other", needs_retrieval=False, response_style="normal",
                               next_action="finish", confidence=0.5, standalone_query="x", reasoning="r")
        with self.assertRaises(Exception):
            supervisor(confidence=1.7)

    def test_other_intent_gets_a_clarifying_reply_without_retrieval(self):
        env = Env({"supervisor_agent.decide": [supervisor("other", next_action="clarify", clarifying_question="Which topic?")]})
        final, budget = env.ask("hmm")
        self.assertEqual(final["reply"], "Which topic?")
        self.assertEqual(budget.tool_calls, 0)
        env.close()


class RetrievalBehaviour(unittest.TestCase):
    def test_retries_with_a_different_tool_when_evidence_is_insufficient(self):
        env = Env({
            "supervisor_agent.decide": [supervisor()],
            "evidence_evaluator.evaluate": [
                evaluation("retrieve_again", sufficient=False, coverage=0.3, missing_information=["definition"]),
                evaluation(),
            ],
            "retrieval_agent.choose_strategy": [RetrievalDecision(strategy="search_topic", query="x", topic="conservation of mass", reasoning="broaden")],
            "tutor_agent.write": [tutor()],
            "critic_agent.review": [critic()],
        })
        final, budget = env.ask()
        strategies = [e["strategy"] for e in final["trace"] if e["step"] == "retrieval_agent"]
        self.assertEqual(strategies, ["search_document", "search_topic"])
        self.assertEqual(budget.retrieval_attempts, 2)
        self.assertEqual(final["reply"], "Mass is conserved in a chemical reaction.")
        env.close()

    def test_repeated_strategy_is_rejected_and_replaced(self):
        env = Env({
            "supervisor_agent.decide": [supervisor()],
            "evidence_evaluator.evaluate": [evaluation("retrieve_again", sufficient=False, coverage=0.3), evaluation()],
            "retrieval_agent.choose_strategy": [RetrievalDecision(strategy="search_document", query="what is mass conservation", reasoning="same again")],
            "tutor_agent.write": [tutor()],
            "critic_agent.review": [critic()],
        })
        final, _ = env.ask()
        second = [e for e in final["trace"] if e["step"] == "retrieval_agent"][1]
        self.assertEqual(second["strategy_source"], "deterministic_fallback")
        env.close()

    def test_unsupported_question_returns_safe_fallback_without_calling_tutor(self):
        env = Env({
            "supervisor_agent.decide": [supervisor(standalone_query="who won the 1998 world cup")],
            "evidence_evaluator.evaluate": [evaluation("answer_not_supported", sufficient=False, relevant=False, coverage=0.0)],
            "retrieval_agent.choose_strategy": [None],
        })
        final, budget = env.ask("who won the 1998 world cup")
        self.assertEqual(final["reply"], NOT_SUPPORTED_MESSAGE)
        self.assertNotIn("tutor_agent.write", env.llm.calls)
        self.assertEqual(final["retrieved_chunks"], [])
        self.assertLessEqual(budget.retrieval_attempts, 2)
        env.close()

    def test_retrieval_attempts_are_capped(self):
        env = Env({
            "supervisor_agent.decide": [supervisor()],
            "evidence_evaluator.evaluate": [evaluation("retrieve_again", sufficient=False, coverage=0.3, suggested_query="mass conservation law")],
            "retrieval_agent.choose_strategy": [None],
        })
        final, budget = env.ask()
        self.assertLessEqual(budget.retrieval_attempts, 3)
        self.assertLessEqual(budget.tool_calls, 6)
        self.assertEqual(final["reply"], NOT_SUPPORTED_MESSAGE)
        env.close()

    def test_no_evidence_is_judged_without_an_llm_call(self):
        result, source = EvidenceEvaluator(None).evaluate(question="q", evidence=[], budget=Budget())
        self.assertEqual(source, "deterministic_no_evidence")
        self.assertFalse(result.sufficient)

    def test_unindexed_document_falls_back_immediately(self):
        env = Env({"supervisor_agent.decide": [supervisor()]})
        final, _ = run_request(env.graph, message="anything", session_id="sess1", document_id="missing.pdf")
        self.assertEqual(final["reply"], NOT_SUPPORTED_MESSAGE)
        self.assertEqual(final["stop_reason"], "document_not_indexed")
        env.close()

    def test_evaluator_failure_does_not_block_a_grounded_answer(self):
        env = Env({"supervisor_agent.decide": [supervisor()], "evidence_evaluator.evaluate": [None],
                   "tutor_agent.write": [tutor()], "critic_agent.review": [critic()]})
        final, _ = env.ask()
        evaluator_event = [e for e in final["trace"] if e["step"] == "evidence_evaluator"][0]
        self.assertEqual(evaluator_event["source"], "evaluator_unavailable")
        self.assertEqual(final["reply"], "Mass is conserved in a chemical reaction.")
        env.close()


class TutorBehaviour(unittest.TestCase):
    def test_tutor_can_ask_for_more_evidence(self):
        env = Env({
            "supervisor_agent.decide": [supervisor()],
            "evidence_evaluator.evaluate": [evaluation(), evaluation()],
            "retrieval_agent.choose_strategy": [None],
            "tutor_agent.write": [tutor("need_more_evidence", chunks=(), answer="", missing_information=["units of mass"]), tutor()],
            "critic_agent.review": [critic()],
        })
        final, budget = env.ask()
        self.assertEqual(budget.retrieval_attempts, 2)
        self.assertEqual(final["reply"], "Mass is conserved in a chemical reaction.")
        env.close()

    def test_tutor_declaring_insufficient_evidence_ends_safely(self):
        env = Env({"supervisor_agent.decide": [supervisor()], "evidence_evaluator.evaluate": [evaluation()],
                   "tutor_agent.write": [tutor("insufficient_evidence", chunks=(), answer="")]})
        final, _ = env.ask()
        self.assertEqual(final["reply"], NOT_SUPPORTED_MESSAGE)
        self.assertNotIn("critic_agent.review", env.llm.calls)
        env.close()

    def test_answer_citing_unretrieved_chunk_is_rejected_and_revised(self):
        env = Env({"supervisor_agent.decide": [supervisor()], "evidence_evaluator.evaluate": [evaluation()],
                   "tutor_agent.write": [tutor(chunks=(99,)), tutor(answer="Corrected answer.", chunks=(0,))],
                   "critic_agent.review": [critic()]})
        final, budget = env.ask()
        self.assertEqual(final["reply"], "Corrected answer.")
        self.assertEqual(budget.revisions, 1)
        env.close()

    def test_answer_with_no_citations_is_rejected(self):
        env = Env({"supervisor_agent.decide": [supervisor()], "evidence_evaluator.evaluate": [evaluation()],
                   "tutor_agent.write": [tutor(chunks=()), tutor(chunks=(0,), answer="Grounded answer.")], "critic_agent.review": [critic()]})
        final, _ = env.ask()
        self.assertEqual(final["reply"], "Grounded answer.")
        env.close()

    def test_response_style_is_passed_to_the_tutor(self):
        env = Env({"supervisor_agent.decide": [supervisor(response_style="eli5")], "evidence_evaluator.evaluate": [evaluation()],
                   "tutor_agent.write": [tutor()], "critic_agent.review": [critic()]})
        env.ask("explain like I am five")
        tutor_prompt = env.llm.prompts[env.llm.calls.index("tutor_agent.write")]
        self.assertIn("eli5", tutor_prompt)
        env.close()


class CriticLoop(unittest.TestCase):
    def test_critic_failure_triggers_revision_with_feedback_then_passes(self):
        env = Env({
            "supervisor_agent.decide": [supervisor()],
            "evidence_evaluator.evaluate": [evaluation()],
            "tutor_agent.write": [tutor(answer="Draft one."), tutor(answer="Draft two, better.")],
            "critic_agent.review": [critic("revise", complete=False, missing_information=["second condition"]), critic("finish")],
        })
        final, budget = env.ask()
        self.assertEqual(final["reply"], "Draft two, better.")
        self.assertEqual(budget.revisions, 1)
        second_tutor_prompt = [p for c, p in zip(env.llm.calls, env.llm.prompts) if c == "tutor_agent.write"][1]
        self.assertIn("second condition", second_tutor_prompt)
        env.close()

    def test_critic_can_send_the_workflow_back_to_retrieval(self):
        env = Env({
            "supervisor_agent.decide": [supervisor()],
            "evidence_evaluator.evaluate": [evaluation(), evaluation()],
            "retrieval_agent.choose_strategy": [None],
            "tutor_agent.write": [tutor(), tutor(answer="Now complete.")],
            "critic_agent.review": [critic("retrieve_again", complete=False, missing_information=["exceptions"]), critic("finish")],
        })
        final, budget = env.ask()
        self.assertEqual(budget.retrieval_attempts, 2)
        self.assertEqual(final["reply"], "Now complete.")
        env.close()

    def test_ungrounded_answers_never_ship_after_max_revisions(self):
        env = Env({
            "supervisor_agent.decide": [supervisor()],
            "evidence_evaluator.evaluate": [evaluation()],
            "tutor_agent.write": [tutor()],
            "critic_agent.review": [critic("revise", grounded=False, unsupported_claims=["made-up claim"])],
        })
        final, budget = env.ask()
        self.assertEqual(final["reply"], NOT_SUPPORTED_MESSAGE)
        self.assertEqual(budget.revisions, 2)
        self.assertLessEqual(len(env.llm.calls), 12)
        env.close()

    def test_incomplete_but_grounded_answer_is_accepted_when_revisions_run_out(self):
        env = Env({
            "supervisor_agent.decide": [supervisor()],
            "evidence_evaluator.evaluate": [evaluation()],
            "tutor_agent.write": [tutor()],
            "critic_agent.review": [critic("revise", complete=False, missing_information=["detail"])],
        })
        final, _ = env.ask()
        self.assertEqual(final["reply"], "Mass is conserved in a chemical reaction.")
        env.close()

    def test_critic_unavailable_accepts_a_cited_draft_and_says_so_in_the_trace(self):
        env = Env({"supervisor_agent.decide": [supervisor()], "evidence_evaluator.evaluate": [evaluation()],
                   "tutor_agent.write": [tutor()], "critic_agent.review": [None]})
        final, _ = env.ask()
        critic_event = [e for e in final["trace"] if e["step"] == "critic_agent"][0]
        self.assertEqual(critic_event["reason"], "critic unavailable")
        env.close()

    def test_critic_decision_is_made_by_python_not_the_llm(self):
        # The LLM says "finish" but reports unsupported claims: Python must not finish.
        from backend.agents.critic import CriticAgent
        bad = CriticEvaluation(grounded=True, relevant=True, complete=True, unsupported_claims=["x"], missing_information=[],
                               contradictions=[], revision_required=False, recommended_action="finish")
        action, _ = CriticAgent.decide(bad, Budget())
        self.assertEqual(action, "revise")


class HardLimits(unittest.TestCase):
    def test_llm_call_budget_is_enforced(self):
        env = Env({"supervisor_agent.decide": [supervisor()], "evidence_evaluator.evaluate": [evaluation()], "tutor_agent.write": [tutor()]})
        final, budget = env.ask(budget=Budget(max_llm_calls=2))
        self.assertLessEqual(budget.llm_calls, 2)
        self.assertEqual(final["stop_reason"], "llm_call_budget_exceeded")
        self.assertEqual(final["reply"], TIME_MESSAGE)
        env.close()

    def test_time_budget_is_enforced(self):
        env = Env({"supervisor_agent.decide": [supervisor()]})
        final, _ = env.ask(budget=Budget(max_seconds=0))
        self.assertEqual(final["reply"], TIME_MESSAGE)
        self.assertEqual(env.llm.calls, [])
        env.close()

    def test_tool_call_budget_is_enforced(self):
        env = Env({"supervisor_agent.decide": [supervisor()], "evidence_evaluator.evaluate": [evaluation()]})
        final, budget = env.ask(budget=Budget(max_tool_calls=1))  # metadata call uses the only tool call
        self.assertEqual(budget.tool_calls, 1)
        self.assertEqual(final["stop_reason"], "tool_call_budget_exceeded")
        env.close()

    def test_worst_case_llm_calls_stay_within_the_hard_cap(self):
        env = Env({
            "supervisor_agent.decide": [supervisor()],
            "evidence_evaluator.evaluate": [evaluation("retrieve_again", sufficient=False, coverage=0.7, suggested_query="mass law")],
            "retrieval_agent.choose_strategy": [None],
            "tutor_agent.write": [tutor()],
            "critic_agent.review": [critic("revise", complete=False, missing_information=["x"])],
        })
        _, budget = env.ask()
        self.assertLessEqual(budget.llm_calls, 12)
        self.assertLessEqual(budget.tool_calls, 6)
        env.close()

    def test_unexpected_agent_exception_becomes_a_safe_fallback(self):
        env = Env({"supervisor_agent.decide": [supervisor()]})

        def boom(**kwargs):
            raise RuntimeError("bug")

        env.deps.retrieval_agent.step = boom
        final, _ = env.ask()
        self.assertEqual(final["stop_reason"], "internal_error")
        self.assertEqual(final["reply"], NOT_SUPPORTED_MESSAGE)
        env.close()


if __name__ == "__main__":
    unittest.main()
