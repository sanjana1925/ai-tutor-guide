"""
Unit tests for Learner Dashboard metrics calculation using unittest.
"""
import unittest
from backend.domain.quiz_engine import LearnerState, record_quiz_answer
from backend.domain.planner import generate_study_plan


class TestDashboard(unittest.TestCase):
    def test_dashboard_empty_state(self):
        state = LearnerState(session_id="empty_session", filename="doc.pdf")
        plan = generate_study_plan(state)
        self.assertEqual(plan["total_attempted"], 0)
        self.assertEqual(plan["overall_accuracy"], "0.0%")
        self.assertIn("Take an adaptive quiz", plan["general_summary"])

    def test_study_plan_generation_with_weak_topics(self):
        state = LearnerState(session_id="session1", filename="doc.pdf")
        record_quiz_answer(state, False, "Backpropagation", "Q1")
        record_quiz_answer(state, False, "Backpropagation", "Q2")

        plan = generate_study_plan(state)
        self.assertEqual(plan["total_attempted"], 2)
        self.assertTrue(len(plan["items"]) > 0)

        high_prio_item = plan["items"][0]
        self.assertEqual(high_prio_item["priority"], "High")
        self.assertEqual(high_prio_item["topic"], "Backpropagation")
        self.assertIn("below the 60% threshold", high_prio_item["reason"])


if __name__ == "__main__":
    unittest.main()
