"""Evaluation: verified datasets only, honest metrics, baseline vs agentic arms, LangSmith dataset/experiments."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from helpers import DOC_TEXTS, Env, HashEmbedding, critic, evaluation, supervisor, tutor

from backend.evaluation import evaluators as ev
from backend.evaluation.build_golden import GoldenDraft, build, difficulty_plan
from backend.evaluation.dataset import split_verified, upload_to_langsmith, verify_item
from backend.evaluation.langsmith_experiment import make_evaluators, run_experiments
from backend.evaluation.report import SCHEMA_VERSION, load_report, save_report
from backend.guardrails.retrieval import NOT_SUPPORTED_MESSAGE
from backend.services.evaluation_service import EvaluationService, aggregate, build_report, compare
from backend.services.llm_service import LLMError
from backend.services.retrieval_service import Scope

embedder = HashEmbedding()


def item(i=1, chunk=0, **kw):
    base = dict(id=i, question="What does the law of conservation of mass state?",
                reference_answer="Mass can neither be created nor destroyed in a chemical reaction.",
                expected_keywords=["mass", "created", "destroyed", "chemical reaction"], source_document="chem.pdf",
                source_page=chunk + 1, source_chunk=chunk, topic="Conservation", difficulty="simple")
    base.update(kw)
    return base


class Verification(unittest.TestCase):
    def setUp(self):
        self.env = Env()

    def tearDown(self):
        self.env.close()

    def verify(self, **kw):
        return verify_item(self.env.retrieval, self.env.scope, item(**kw))

    def test_a_consistent_example_verifies(self):
        self.assertTrue(self.verify()["verified"])

    def test_missing_source_chunk_is_rejected(self):
        r = self.verify(chunk=99)
        self.assertFalse(r["verified"])
        self.assertIn("does not exist", r["reasons"][0])

    def test_keywords_must_appear_in_the_source_chunk(self):
        r = self.verify(expected_keywords=["quantum", "gravity", "neutrino"])
        self.assertFalse(r["verified"])
        self.assertIn("expected keywords", r["reasons"][0])

    def test_wrong_page_is_rejected(self):
        self.assertFalse(self.verify(source_page=3)["verified"])

    def test_wrong_document_is_rejected(self):
        self.assertFalse(self.verify(source_document="other.pdf")["verified"])

    def test_unindexed_document_is_never_verified(self):
        r = verify_item(self.env.retrieval, Scope("sess1", "ai-engineer.pdf"), item(source_document="ai-engineer.pdf"))
        self.assertFalse(r["verified"])
        self.assertIn("not indexed", " ".join(r["reasons"]))

    def test_split_separates_verified_from_rejected_with_reasons(self):
        good, bad = split_verified(self.env.retrieval, self.env.scope, [item(1), item(2, chunk=99)])
        self.assertEqual(([g["id"] for g in good], [b["id"] for b in bad]), ([1], [2]))
        self.assertTrue(bad[0]["verification"]["reasons"])


class Metrics(unittest.TestCase):
    chunks = [{"chunk_index": 0, "text": DOC_TEXTS[0], "page": 1, "distance": 0.1},
              {"chunk_index": 3, "text": DOC_TEXTS[3], "page": 4, "distance": 0.9}]

    def test_recall_and_precision_are_chunk_level(self):
        m = ev.retrieval_metrics(self.chunks, 0, ["mass", "destroyed"], 4)
        self.assertEqual((m["recall_at_k"], m["precision_at_k"]), (1.0, 0.5))
        self.assertEqual(ev.retrieval_metrics(self.chunks, 2, ["exothermic"], 4)["recall_at_k"], 0.0)

    def test_recall_only_looks_at_the_top_k(self):
        self.assertEqual(ev.retrieval_metrics(self.chunks, 3, [], 1)["recall_at_k"], 0.0)

    def test_empty_retrieval_scores_zero_not_a_crash(self):
        m = ev.retrieval_metrics([], 0, ["x"], 4)
        self.assertEqual((m["recall_at_k"], m["precision_at_k"], m["keyword_coverage"]), (0.0, 0.0, 0.0))

    def test_similarity_is_cosine_of_embeddings(self):
        same = ev.answer_similarity(embedder, "mass is conserved", "mass is conserved")
        different = ev.answer_similarity(embedder, "mass is conserved", "photosynthesis makes glucose")
        self.assertAlmostEqual(same, 1.0, places=5)
        self.assertLess(different, 0.5)
        self.assertIsNone(ev.answer_similarity(embedder, "", "x"))

    def test_lexical_groundedness_is_a_word_overlap_heuristic(self):
        self.assertEqual(ev.lexical_groundedness("Mass is neither created nor destroyed", [DOC_TEXTS[0]]), 1.0)
        self.assertLess(ev.lexical_groundedness("Volcanoes erupt magma", [DOC_TEXTS[0]]), 0.2)
        self.assertIsNone(ev.lexical_groundedness("", [DOC_TEXTS[0]]))

    def test_abstention_detection(self):
        self.assertTrue(ev.abstained(NOT_SUPPORTED_MESSAGE))
        self.assertFalse(ev.abstained("Mass is conserved."))

    def test_judge_returns_none_when_the_model_cannot_score(self):
        class Broken:
            def structured(self, *a, **k):
                raise RuntimeError("down")

        self.assertIsNone(ev.llm_judge(Broken(), "faithfulness", "q", "a", ["e"]))

    def test_unnecessary_retries_only_count_when_the_first_search_already_had_the_gold_chunk(self):
        snap = {"tool_calls": 3, "llm_calls": 6, "retrieval_attempts": 2, "revisions": 0}
        trace = [{"step": "retrieval_agent", "strategy": "search_document", "chunks_returned": [0, 1]},
                 {"step": "retrieval_agent", "strategy": "search_topic", "chunks_returned": [2]}]
        self.assertEqual(ev.workflow_metrics(trace, snap, 0, "answer", None)["unnecessary_retrieval_retries"], 1)
        self.assertEqual(ev.workflow_metrics(trace, snap, 2, "answer", None)["unnecessary_retrieval_retries"], 0)


class Arms(unittest.TestCase):
    def make(self, script):
        env = Env(script)
        return env, EvaluationService(env.llm, env.retrieval, env.graph, embedder)

    def test_baseline_arm_makes_one_search_and_one_llm_call(self):
        env, svc = self.make({"baseline_rag.generate": ["Mass can neither be created nor destroyed in a chemical reaction."]})
        rows = svc.run("baseline_rag", env.scope, [item()])
        row = rows[0]
        self.assertEqual((row["arm"], row["llm_calls"], row["tool_calls"], row["retrieval_recall_at_k"]), ("baseline_rag", 1, 1, 1.0))
        self.assertEqual(env.llm.calls, ["baseline_rag.generate"])
        self.assertGreater(row["answer_similarity"], 0.7)
        env.close()

    def test_agentic_arm_runs_the_full_workflow_and_counts_what_it_really_did(self):
        env, svc = self.make({"supervisor_agent.decide": [supervisor()], "evidence_evaluator.evaluate": [evaluation()],
                              "tutor_agent.write": [tutor(answer="Mass can neither be created nor destroyed in a chemical reaction.")],
                              "critic_agent.review": [critic()]})
        row = svc.run("agentic_rag", env.scope, [item()])[0]
        self.assertEqual((row["llm_calls"], row["tool_calls"], row["retrieval_attempts"], row["revisions"]), (4, 2, 1, 0))
        self.assertTrue(row["completed"])
        self.assertFalse(row["abstained"])
        env.close()

    def test_abstained_answers_are_not_scored_for_similarity_or_groundedness(self):
        env, svc = self.make({"baseline_rag.generate": [NOT_SUPPORTED_MESSAGE]})
        row = svc.run("baseline_rag", env.scope, [item()])[0]
        self.assertTrue(row["abstained"])
        self.assertIsNone(row["answer_similarity"])
        self.assertIsNone(row["groundedness_score"])
        env.close()

    def test_judge_metrics_are_none_unless_requested(self):
        env, svc = self.make({"baseline_rag.generate": ["Mass is conserved in chemical reactions."]})
        row = svc.run("baseline_rag", env.scope, [item()], judge=False)[0]
        self.assertIsNone(row["faithfulness"])
        self.assertNotIn("eval.judge_faithfulness", env.llm.calls)
        env.close()

    def test_agentic_answer_scoring_ignores_the_appended_follow_up_question(self):
        env, svc = self.make({"supervisor_agent.decide": [supervisor()], "evidence_evaluator.evaluate": [evaluation()],
                              "tutor_agent.write": [tutor(follow_up_question="Why does this matter?")], "critic_agent.review": [critic()]})
        out = svc.run_agentic(env.scope, "q", 0)
        self.assertNotIn("Check your understanding", out["answer"])
        env.close()


class ProviderFailures(unittest.TestCase):
    """A rate limit or outage says nothing about answer quality, so it must never be scored as an abstention."""

    def service(self, script):
        env = Env(script)
        return env, EvaluationService(env.llm, env.retrieval, env.graph, embedder)

    def flaky(self, failures, then="Mass can neither be created nor destroyed in a chemical reaction."):
        state = {"n": 0}

        def call(prompt):
            state["n"] += 1
            if state["n"] <= failures:
                raise LLMError(429, "quota")
            return then

        return call

    def test_transient_errors_are_retried_and_then_scored_normally(self):
        env, svc = self.service({"baseline_rag.generate": [self.flaky(2)]})
        row = svc.run("baseline_rag", env.scope, [item()], retries=2, backoff=0)[0]
        self.assertFalse(row.get("errored"))
        self.assertGreater(row["answer_similarity"], 0.7)
        env.close()

    def test_persistent_errors_are_marked_errored_not_abstained(self):
        env, svc = self.service({"baseline_rag.generate": [self.flaky(99)]})
        row = svc.run("baseline_rag", env.scope, [item()], retries=1, backoff=0)[0]
        self.assertTrue(row["errored"])
        self.assertIn("429", row["error"])
        self.assertNotIn("abstained", row)
        env.close()

    def test_agentic_provider_errors_are_not_counted_as_safe_fallbacks(self):
        def boom(prompt):
            raise LLMError(429, "quota")

        env, svc = self.service({"supervisor_agent.decide": [boom]})
        row = svc.run("agentic_rag", env.scope, [item()], retries=0, backoff=0)[0]
        self.assertTrue(row["errored"])
        env.close()

    def test_a_time_budget_stop_is_infrastructure_not_an_answer(self):
        from backend.budget import Budget as B

        env, svc = self.service({"supervisor_agent.decide": [supervisor()], "evidence_evaluator.evaluate": [evaluation()]})
        svc.run_agentic = lambda scope, q, gold: {"answer": "I ran out of time", "workflow": {"stop_reason": "time_budget_exceeded"}, "llm_error": None}
        row = svc.run("agentic_rag", env.scope, [item()], retries=0, backoff=0)[0]
        self.assertTrue(row["errored"])
        self.assertIn("time budget", row["error"])
        env.close()

    def test_errored_rows_are_excluded_from_metrics_and_reported_separately(self):
        good = Aggregation().rows()
        errored = {"id": 3, "question": "q", "arm": "baseline_rag", "errored": True, "error": "429: quota"}
        agg = aggregate(good + [errored])
        self.assertEqual((agg["num_questions"], agg["num_errored_excluded"]), (2, 1))
        report = build_report({"baseline_rag": good + [errored]}, {"path": "x"})
        self.assertEqual(len(report["results"]), 2)
        self.assertEqual(report["arms"]["baseline_rag"]["errored"], [{"id": 3, "error": "429: quota"}])

    def test_all_rows_errored_means_metrics_are_not_evaluated(self):
        agg = aggregate([{"id": 1, "question": "q", "arm": "a", "errored": True, "error": "x"}])
        self.assertEqual(agg["num_questions"], 0)
        self.assertIsNone(agg["avg_answer_similarity"])
        self.assertIn("avg_answer_similarity", agg["not_evaluated"])


class Aggregation(unittest.TestCase):
    def rows(self, **over):
        base = dict(retrieval_recall_at_k=1.0, retrieval_precision_at_k=0.5, keyword_coverage=1.0, answer_similarity=0.8,
                    groundedness_score=0.9, faithfulness=None, answer_relevancy=None, latency_seconds=2.0, llm_calls=4, tool_calls=2,
                    retrieval_attempts=1, revisions=0, completed=True, fell_back_to_safe_answer=False, unnecessary_retrieval_retries=0)
        return [{**base, **over}, {**base, **over}]

    def test_metrics_that_were_not_run_are_reported_as_not_evaluated_never_zero(self):
        agg = aggregate(self.rows())
        self.assertIsNone(agg["avg_faithfulness_llm_judge"])
        self.assertIn("avg_faithfulness_llm_judge", agg["not_evaluated"])
        self.assertEqual(agg["avg_answer_similarity"], 0.8)

    def test_none_values_are_excluded_from_averages(self):
        rows = self.rows()
        rows[1]["answer_similarity"] = None  # abstained
        self.assertEqual(aggregate(rows)["avg_answer_similarity"], 0.8)

    def test_comparison_reports_deltas_and_direction_and_flags_missing_metrics(self):
        b, a = aggregate(self.rows()), aggregate(self.rows(retrieval_recall_at_k=0.5, llm_calls=6))
        c = compare(b, a)
        self.assertEqual(c["avg_retrieval_recall_at_k"]["delta"], -0.5)
        self.assertFalse(c["avg_retrieval_recall_at_k"]["agentic_better"])
        self.assertEqual(c["avg_llm_calls"]["delta"], 2.0)
        self.assertEqual(c["avg_faithfulness_llm_judge"]["note"], "not evaluated")

    def test_report_keeps_the_frontend_contract_and_both_arms(self):
        report = build_report({"baseline_rag": self.rows(), "agentic_rag": self.rows()}, {"path": "x"})
        self.assertEqual(report["primary_arm"], "agentic_rag")
        for key in ("avg_retrieval_recall_at_k", "avg_retrieval_precision_at_k", "avg_answer_similarity", "avg_groundedness_score", "avg_latency_seconds", "num_questions"):
            self.assertIn(key, report["system_evaluation"])
        self.assertIn("comparison", report)
        self.assertEqual(set(report["arms"]), {"baseline_rag", "agentic_rag"})


class ReportStorage(unittest.TestCase):
    def test_legacy_or_missing_reports_load_as_no_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "r.json"
            self.assertEqual(load_report(path), {"status": "no_data"})
            path.write_text(json.dumps({"system_evaluation": {"avg_retrieval_recall_at_k": 0.0}}), encoding="utf-8")
            self.assertEqual(load_report(path)["status"], "no_data")  # pre-verification report is not trusted
            path.write_text("not json", encoding="utf-8")
            self.assertEqual(load_report(path), {"status": "no_data"})

    def test_saved_reports_round_trip_with_the_schema_version(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "r.json"
            save_report({"system_evaluation": {"num_questions": 3}, "results": []}, path)
            loaded = load_report(path)
            self.assertEqual((loaded["schema_version"], loaded["system_evaluation"]["num_questions"]), (SCHEMA_VERSION, 3))


class GoldenBuilder(unittest.TestCase):
    long = [t + " " + t for t in DOC_TEXTS]  # >= 200 chars each

    def env(self, drafts):
        return Env({"build_golden.draft": drafts}, texts=self.long)

    def draft(self, **kw):
        base = dict(question="What does the law of conservation of mass state?", reference_answer="Mass can neither be created nor destroyed in a chemical reaction.",
                    expected_keywords=["mass", "created", "destroyed"], topic="Conservation")
        base.update(kw)
        return GoldenDraft(**base)

    def test_difficulty_plan_matches_the_40_35_25_split(self):
        plan = difficulty_plan(10)
        self.assertEqual((plan.count("simple"), plan.count("medium"), plan.count("high")), (4, 3, 3))
        for n in (1, 3, 7, 20):
            self.assertEqual(len(difficulty_plan(n)), n)

    def test_verified_drafts_become_items_with_real_source_pointers(self):
        env = self.env([self.draft()])
        result = build(env.llm, env.retrieval, env.scope, n=1)
        it = result["items"][0]
        self.assertEqual((it["source_document"], it["source_chunk"], it["source_page"], it["review_status"]), ("chem.pdf", 0, 1, "needs_human_review"))
        self.assertTrue(verify_item(env.retrieval, env.scope, it)["verified"])
        env.close()

    def test_drafts_that_cannot_be_verified_are_dropped(self):
        env = self.env([self.draft(expected_keywords=["quantum", "gravity", "neutrino"])])
        result = build(env.llm, env.retrieval, env.scope, n=1)
        self.assertEqual(result["items"], [])
        self.assertIn("keywords", result["dropped"][0]["reason"])
        env.close()

    def test_answers_the_chunk_does_not_support_are_dropped(self):
        env = self.env([self.draft(reference_answer="Volcanoes erupt molten magma across tectonic boundaries")])
        result = build(env.llm, env.retrieval, env.scope, n=1)
        self.assertIn("supported", result["dropped"][0]["reason"])
        env.close()

    def test_invalid_model_output_is_dropped_not_invented(self):
        env = self.env([None])
        self.assertEqual(build(env.llm, env.retrieval, env.scope, n=1)["items"], [])
        env.close()


class LangSmithIntegration(unittest.TestCase):
    def client(self, existing_ids=()):
        client = mock.MagicMock()
        client.read_dataset.return_value = mock.Mock(id="ds1")
        client.list_examples.return_value = [mock.Mock(metadata={"golden_id": i}) for i in existing_ids]
        return client

    def test_dataset_upload_contains_verified_fields_and_is_idempotent(self):
        client = self.client(existing_ids=[1])
        upload_to_langsmith(client, "ds", [item(1), item(2, chunk=1)])
        kwargs = client.create_examples.call_args.kwargs
        self.assertEqual(len(kwargs["inputs"]), 1)  # example 1 already exists
        self.assertEqual(kwargs["metadata"][0]["source_chunk"], 1)
        self.assertEqual(set(kwargs["outputs"][0]), {"reference_answer", "expected_keywords", "source_chunk", "source_page"})
        self.assertEqual(kwargs["metadata"][0]["source_document"], "chem.pdf")

    def test_dataset_is_created_when_missing(self):
        client = self.client()
        client.read_dataset.side_effect = RuntimeError("not found")
        client.create_dataset.return_value = mock.Mock(id="new")
        upload_to_langsmith(client, "ds", [item(1)])
        client.create_dataset.assert_called_once()

    def test_evaluators_score_real_outputs_and_mark_unrun_metrics_as_not_evaluated(self):
        evaluators = {f.__name__: f for f in make_evaluators(embedder)}
        self.assertNotIn("faithfulness", evaluators)  # judge not requested
        run = mock.Mock(error=None, outputs={"answer": NOT_SUPPORTED_MESSAGE, "first_attempt_chunks": [], "evidence_texts": [], "workflow": {"completed": True, "fell_back_to_safe_answer": True}})
        example = mock.Mock(outputs={"source_chunk": 0, "expected_keywords": ["mass"], "reference_answer": "x"}, inputs={"question": "q"})
        self.assertEqual(evaluators["recall_at_k"](run, example)["score"], 0.0)
        sim = evaluators["answer_similarity"](run, example)
        self.assertIsNone(sim["score"])
        self.assertEqual(sim["comment"], "abstained")
        self.assertEqual(evaluators["safe_fallback"](run, example)["score"], 1.0)

    def test_errored_runs_are_not_evaluated_instead_of_scored_as_zero(self):
        evaluators = {f.__name__: f for f in make_evaluators(embedder, llm=object(), judge=True)}
        example = mock.Mock(outputs={"source_chunk": 0, "expected_keywords": ["mass"], "reference_answer": "x"}, inputs={"question": "q"})
        for run in (mock.Mock(outputs=None, error="RuntimeError: 429"), mock.Mock(outputs={}, error=None)):
            for name, fn in evaluators.items():
                result = fn(run, example)
                self.assertIsNone(result["score"], name)
                self.assertIn("not evaluated", result["comment"], name)

    def test_the_experiment_target_retries_provider_errors_before_giving_up(self):
        state = {"n": 0}

        def flaky(prompt):
            state["n"] += 1
            if state["n"] == 1:
                raise LLMError(429, "quota")
            return "Mass is conserved."

        env = Env({"baseline_rag.generate": [flaky]})
        svc = EvaluationService(env.llm, env.retrieval, env.graph, embedder)
        seen = []

        def fake_evaluate(target, data, evaluators, experiment_prefix, metadata, max_concurrency):
            seen.append(target({"question": item()["question"]}))
            return mock.Mock(experiment_name="x")

        run_experiments(svc, env.scope, [item()], ["baseline_rag"], "p", client=self.client(), evaluate_fn=fake_evaluate, retries=2, backoff=0)
        self.assertEqual(seen[0]["answer"], "Mass is conserved.")
        self.assertEqual(state["n"], 2)
        env.close()

    def test_judge_evaluators_are_only_added_when_requested(self):
        names = {f.__name__ for f in make_evaluators(embedder, llm=object(), judge=True)}
        self.assertTrue({"faithfulness", "relevancy"} <= names)

    def test_experiments_are_skipped_without_a_key_and_upload_nothing(self):
        env = Env()
        svc = EvaluationService(env.llm, env.retrieval, env.graph, embedder)
        with mock.patch.dict("os.environ", {}, clear=True):
            result = run_experiments(svc, env.scope, [item()], ["baseline_rag"], "t")
        self.assertEqual(result["status"], "skipped")
        env.close()

    def test_one_experiment_is_created_per_arm_on_the_same_dataset(self):
        env = Env({"baseline_rag.generate": ["Mass is conserved."]})
        svc = EvaluationService(env.llm, env.retrieval, env.graph, embedder)
        captured = []

        def fake_evaluate(target, data, evaluators, experiment_prefix, metadata, max_concurrency):
            captured.append((experiment_prefix, data, metadata["arm"]))
            out = target({"question": item()["question"], "source_document": "chem.pdf"})  # the target really runs
            self.assertIn("answer", out)
            return mock.Mock(experiment_name=experiment_prefix + "-x")

        result = run_experiments(svc, env.scope, [item()], ["baseline_rag"], "pfx", client=self.client(), evaluate_fn=fake_evaluate)
        self.assertEqual(result["experiments"], {"baseline_rag": "pfx-baseline_rag-x"})
        self.assertEqual(captured, [("pfx-baseline_rag", "ai-tutor-guide-golden-verified", "baseline_rag")])
        env.close()


if __name__ == "__main__":
    unittest.main()
