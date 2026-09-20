"""Quiz: deterministic rules stay deterministic; the LLM only proposes questions and Python validates them."""
import itertools
import unittest

from helpers import DOC_TEXTS, Env

from backend.agents.schemas import QuizQuestion
from backend.services import quiz_service
from backend.domain.quiz_engine import LearnerState, record_quiz_answer


def generator(counter=None, difficulty="simple", topic=None, quote_from_prompt=True):
    counter = counter or itertools.count(1)

    def gen(prompt):
        n = next(counter)
        chunk = next(t for t in DOC_TEXTS if t in prompt)  # an excerpt the agent really sampled
        return QuizQuestion(
            question=f"Q{n} Q{n}: distinct prompt number {n} regarding {chunk[:28]}",
            options=[f"A{n}", f"B{n}", f"C{n}", f"D{n}"],
            correct_answer_index=0,
            topic=topic or f"Topic {n % 3}",
            difficulty=difficulty,
            explanation="Because the document says so.",
            source_quote=chunk[:50] if quote_from_prompt else "this quote is not in any excerpt at all",
        )

    return gen


def question(n, **kw):
    base = dict(question=f"Custom question {n} about something", options=["a", "b", "c", "d"], correct_answer_index=0,
                topic="T", difficulty="simple", explanation="e", source_quote=DOC_TEXTS[0][:50])
    base.update(kw)
    return QuizQuestion(**base)


def grounded(q):
    """Wrap a fixed question so its quote always comes from the excerpts the agent actually sampled."""
    return lambda prompt: q.model_copy(update={"source_quote": next(t for t in DOC_TEXTS if t in prompt)[:50]})


def play(env, answers):
    """Start a quiz then answer each turn with the given option index."""
    final, _ = env.ask("Start quiz", mode_override="quiz")
    for a in answers:
        final, _ = env.ask(str(a), mode_override="quiz")
    return final


class Progression(unittest.TestCase):
    def test_15_simple_questions_then_70_percent_unlocks_medium(self):
        env = Env({"quiz_agent.generate_question": [generator()]})
        final = play(env, [0] * 12 + [1] * 3)  # 12/15 = 80%
        state = env.learner.get(env.scope)
        self.assertEqual((state.total_attempted, state.total_correct), (15, 12))
        self.assertEqual(state.current_phase, "MEDIUM")
        self.assertEqual(final["quiz_details"]["current_phase"], "MEDIUM")
        self.assertEqual(final["quiz_details"]["question_dict"]["difficulty"], "medium")
        env.close()

    def test_below_benchmark_stays_in_simple(self):
        env = Env({"quiz_agent.generate_question": [generator()]})
        play(env, [0] * 6 + [1] * 9)  # 40%
        state = env.learner.get(env.scope)
        self.assertEqual(state.current_phase, "SIMPLE")
        self.assertEqual(state.simple_attempted, 15)
        env.close()

    def test_phase_does_not_advance_before_15_questions(self):
        env = Env({"quiz_agent.generate_question": [generator()]})
        play(env, [0] * 14)
        self.assertEqual(env.learner.get(env.scope).current_phase, "SIMPLE")
        env.close()

    def test_medium_to_high_after_five_questions_at_70_percent(self):
        env = Env({"quiz_agent.generate_question": [generator(difficulty="medium")]})
        state = env.learner.get(env.scope)
        state.current_phase = "MEDIUM"
        final = play(env, [0, 0, 0, 0, 1])  # 4/5 = 80%
        self.assertEqual(env.learner.get(env.scope).current_phase, "HIGH")
        self.assertEqual(final["quiz_details"]["question_dict"]["difficulty"], "high")
        env.close()

    def test_medium_stays_when_accuracy_is_low(self):
        env = Env({"quiz_agent.generate_question": [generator(difficulty="medium")]})
        env.learner.get(env.scope).current_phase = "MEDIUM"
        play(env, [1, 1, 1, 1, 0])  # 20%
        self.assertEqual(env.learner.get(env.scope).current_phase, "MEDIUM")
        env.close()

    def test_high_phase_is_terminal_and_tracked_separately(self):
        env = Env({"quiz_agent.generate_question": [generator(difficulty="high")]})
        env.learner.get(env.scope).current_phase = "HIGH"
        play(env, [0, 0, 1])
        state = env.learner.get(env.scope)
        self.assertEqual((state.current_phase, state.high_attempted, state.high_correct), ("HIGH", 3, 2))
        env.close()

    def test_engine_scoring_is_pure_python(self):
        s = LearnerState(session_id="s", filename="f")
        record_quiz_answer(s, True, "A", "q1")
        record_quiz_answer(s, False, "A", "q2")
        self.assertEqual((s.total_attempted, s.total_correct, s.get_overall_accuracy()), (2, 1, 50.0))


class ScoringNeverUsesTheLLM(unittest.TestCase):
    def test_grading_turn_only_calls_the_model_to_write_the_next_question(self):
        env = Env({"quiz_agent.generate_question": [generator()]})
        play(env, [0, 1, 0])
        self.assertEqual(set(env.llm.calls), {"quiz_agent.generate_question"})
        self.assertEqual(len(env.llm.calls), 4)  # one generation per turn, zero grading calls
        env.close()

    def test_correct_and_incorrect_feedback_comes_from_stored_answer(self):
        env = Env({"quiz_agent.generate_question": [generator()]})
        env.ask("Start quiz", mode_override="quiz")
        wrong, _ = env.ask("2", mode_override="quiz")
        self.assertIn("Incorrect", wrong["reply"])
        self.assertIn("Correct option: **A1**", wrong["reply"])
        right, _ = env.ask("0", mode_override="quiz")
        self.assertIn("Correct!", right["reply"])
        env.close()

    def test_a_reply_that_is_not_an_answer_is_not_graded(self):
        env = Env({"quiz_agent.generate_question": [generator()]})
        first, _ = env.ask("Start quiz", mode_override="quiz")
        calls_before = len(env.llm.calls)
        again, _ = env.ask("Start quiz", mode_override="quiz")  # e.g. the page was reloaded
        self.assertEqual(len(env.llm.calls), calls_before)
        self.assertEqual(env.learner.get(env.scope).total_attempted, 0)
        self.assertEqual(first["quiz_details"]["question_dict"], again["quiz_details"]["question_dict"])
        env.close()


class ValidationAndDuplicates(unittest.TestCase):
    def attempts(self, final):
        return [e for e in final["trace"] if e["step"] == "quiz_agent"][0]["attempts"]

    def test_exact_duplicate_of_an_earlier_question_is_rejected(self):
        first = question(1)
        env = Env({"quiz_agent.generate_question": [grounded(first), grounded(first), grounded(question(2, question="A completely different topic entirely"))]})
        env.ask("Start quiz", mode_override="quiz")
        final, _ = env.ask("0", mode_override="quiz")
        reasons = [a["reason"] for a in self.attempts(final)]
        self.assertIn("duplicate of an earlier question", reasons)
        self.assertNotEqual(final["quiz_details"]["question_dict"]["question"], first.question)
        env.close()

    def test_near_duplicate_wording_is_rejected(self):
        self.assertTrue(quiz_service.is_duplicate("What is the law of conservation of mass?", ["what is the law of conservation of mass"]))
        self.assertTrue(quiz_service.is_duplicate("What is the law of conservation of mass??", ["What is the law of conservation of mass?"]))
        self.assertFalse(quiz_service.is_duplicate("Name the products of photosynthesis", ["What is the law of conservation of mass?"]))

    def test_invalid_questions_are_rejected_then_fallback_is_used(self):
        bad = [
            question(1, options=["a", "b", "c"]),
            question(2, options=["same", "same", "x", "y"]),
            question(3, correct_answer_index=9),
        ]
        env = Env({"quiz_agent.generate_question": bad})
        final, _ = env.ask("Start quiz", mode_override="quiz")
        event = [e for e in final["trace"] if e["step"] == "quiz_agent"][0]
        self.assertEqual([a["accepted"] for a in event["attempts"]], [False, False, False])
        self.assertTrue(event["fallback_used"])
        self.assertEqual(final["quiz_details"]["question_dict"]["topic"], "Core Concepts")
        env.close()

    def test_answer_must_be_backed_by_a_verbatim_quote_from_the_excerpts(self):
        env = Env({"quiz_agent.generate_question": [generator(quote_from_prompt=False), generator()]})
        final, _ = env.ask("Start quiz", mode_override="quiz")
        attempts = self.attempts(final)
        self.assertFalse(attempts[0]["accepted"])
        self.assertIn("verbatim quote", attempts[0]["reason"])
        self.assertTrue(attempts[1]["accepted"])
        env.close()

    def test_mislabelled_difficulty_is_corrected_by_python(self):
        env = Env({"quiz_agent.generate_question": [generator(difficulty="high")]})  # phase is SIMPLE
        final, _ = env.ask("Start quiz", mode_override="quiz")
        self.assertEqual(final["quiz_details"]["question_dict"]["difficulty"], "simple")
        env.close()

    def test_generation_attempts_are_bounded(self):
        env = Env({"quiz_agent.generate_question": [None]})
        final, budget = env.ask("Start quiz", mode_override="quiz")
        self.assertLessEqual(env.llm.calls.count("quiz_agent.generate_question"), 3)
        self.assertIn("Core Concepts", final["quiz_details"]["question_dict"]["topic"])
        env.close()


class WeakTopicsAndPrivacy(unittest.TestCase):
    def test_weak_topics_are_detected_and_targeted_in_the_next_question(self):
        env = Env({"quiz_agent.generate_question": [generator(topic="Balancing")]})
        play(env, [1, 1])  # two wrong answers on the same topic
        state = env.learner.get(env.scope)
        self.assertIn("Balancing", state.get_weak_topics())
        env.ask("1", mode_override="quiz")
        self.assertIn("Target the question on one of these identified weak topics: Balancing", env.llm.prompts[-1])
        env.close()

    def test_the_browser_never_receives_the_answer_or_explanation(self):
        env = Env({"quiz_agent.generate_question": [generator()]})
        final, _ = env.ask("Start quiz", mode_override="quiz")
        self.assertEqual(set(final["quiz_details"]["question_dict"]), {"question", "options", "topic", "difficulty"})
        stored = env.learner.get(env.scope).current_question
        self.assertIn("correct_answer_index", stored)  # kept server-side for scoring
        env.close()

    def test_no_repeat_questions_over_a_full_simple_phase(self):
        env = Env({"quiz_agent.generate_question": [generator()]})
        play(env, [0] * 15)
        asked = env.learner.get(env.scope).asked_questions
        self.assertEqual(len(asked), len(set(asked)))
        env.close()


if __name__ == "__main__":
    unittest.main()
