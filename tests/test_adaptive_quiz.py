"""
Unit tests for 3-Phase Adaptive Quiz engine using unittest.
"""
import unittest
from backend.domain.quiz_engine import LearnerState, record_quiz_answer


class TestAdaptiveQuiz(unittest.TestCase):
    def test_initial_learner_state(self):
        state = LearnerState(session_id="test_session", filename="test.pdf")
        self.assertEqual(state.current_phase, "SIMPLE")
        self.assertEqual(state.phase_question_count, 0)
        self.assertEqual(state.get_overall_accuracy(), 0.0)
        self.assertEqual(state.get_weak_topics(), [])

    def test_simple_phase_progression_achieved(self):
        state = LearnerState(session_id="test_session", filename="test.pdf")
        for i in range(15):
            is_correct = (i < 12)  # 12/15 = 80% >= 70%
            record_quiz_answer(state, is_correct, "Core RAG", f"Question {i}")

        self.assertEqual(state.total_attempted, 15)
        self.assertEqual(state.current_phase, "MEDIUM")
        self.assertEqual(state.phase_question_count, 0)
        self.assertEqual(state.get_simple_accuracy(), 80.0)

    def test_simple_phase_progression_failed(self):
        state = LearnerState(session_id="test_session", filename="test.pdf")
        for i in range(15):
            is_correct = (i < 6)  # 6/15 = 40% < 70%
            record_quiz_answer(state, is_correct, "Vector Stores", f"Question {i}")

        self.assertEqual(state.total_attempted, 15)
        self.assertEqual(state.current_phase, "SIMPLE")
        self.assertIn("Vector Stores", state.get_weak_topics())

    def test_weak_topic_detection_threshold(self):
        state = LearnerState(session_id="test_session", filename="test.pdf")
        record_quiz_answer(state, False, "Neural Networks", "Q1")
        record_quiz_answer(state, False, "Neural Networks", "Q2")
        record_quiz_answer(state, True, "Neural Networks", "Q3")

        record_quiz_answer(state, True, "Embeddings", "Q4")
        record_quiz_answer(state, True, "Embeddings", "Q5")
        record_quiz_answer(state, True, "Embeddings", "Q6")

        self.assertIn("Neural Networks", state.get_weak_topics())
        self.assertIn("Embeddings", state.get_strong_topics())


if __name__ == "__main__":
    unittest.main()
