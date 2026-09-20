"""LangSmith: traces are created, agent runs are named, metadata/tags are attached, tool calls and
failures are visible. Uses a recording Client - no real LangSmith key or network needed."""
import json
import os
import unittest
from types import SimpleNamespace
from unittest import mock

import langsmith as ls
from langsmith import tracing_context

from helpers import Env, critic, evaluation, supervisor, tutor

from backend.graph.workflow import build_deps, build_workflow, run_request
from backend.observability.langsmith import configure_tracing, hash_id, sanitize_metadata
from backend.services.llm_service import GeminiLLM


class RecordingClient(ls.Client):
    def __init__(self):
        super().__init__(api_key="test", api_url="http://localhost:9", auto_batch_tracing=False)
        self.created, self.updated = [], {}

    def create_run(self, *a, **kw):
        self.created.append(kw)

    def update_run(self, run_id, **kw):
        self.updated[str(run_id)] = kw

    # helpers
    def named(self, name):
        return [r for r in self.created if r["name"] == name]

    def parent_name(self, run):
        by_id = {str(r["id"]): r for r in self.created}
        return by_id.get(str(run.get("parent_run_id")), {}).get("name")

    def final_tags(self, run):
        return set(self.updated.get(str(run["id"]), {}).get("tags") or run.get("tags") or [])

    def final_meta(self, run):
        return (self.updated.get(str(run["id"]), {}).get("extra") or run.get("extra") or {}).get("metadata", {})


def fake_gemini(usage=True, responses=None):
    responses = responses or {
        "SupervisorDecision": supervisor().model_dump_json(),
        "EvidenceEvaluation": evaluation().model_dump_json(),
        "TutorOutput": tutor().model_dump_json(),
        "CriticEvaluation": critic().model_dump_json(),
    }

    class Models:
        def generate_content(self, model, contents, config):
            u = SimpleNamespace(prompt_token_count=10, candidates_token_count=5, total_token_count=15) if usage else None
            schema = config.response_schema
            text = responses[schema.__name__] if schema is not None else "A long enough plain-text answer for the guide agent."
            return SimpleNamespace(text=text, usage_metadata=u)

    return SimpleNamespace(models=Models())


def traced_run(usage=True, env=None, **request):
    env = env or Env()
    deps = build_deps(GeminiLLM(fake_gemini(usage), "gemini-test"), env.retrieval, env.learner)
    graph = build_workflow(deps)
    client = RecordingClient()
    with tracing_context(enabled=True, client=client):
        final, budget = run_request(graph, **{"message": "what is mass conservation", "session_id": "sess1", "document_id": "chem.pdf", **request})
    return client, final, budget


class TraceStructure(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client, cls.final, cls.budget = traced_run()

    def test_a_trace_is_created_with_a_named_root_run(self):
        roots = self.client.named("agent_request")
        self.assertEqual(len(roots), 1)
        self.assertIsNone(roots[0].get("parent_run_id"))

    def test_important_agent_runs_have_meaningful_names(self):
        names = {r["name"] for r in self.client.created}
        for expected in ["supervisor_agent", "retrieval_agent", "evidence_evaluator", "tutor_agent", "critic_agent", "output_guardrail"]:
            self.assertIn(expected, names)
        generic = [n for n in names if n.startswith("RunnableSequence") or n == "LangGraph"]
        self.assertEqual(generic, [])

    def test_tool_calls_appear_under_the_retrieval_agent_with_arguments(self):
        for tool in ("get_document_metadata", "search_document"):
            runs = self.client.named(tool)
            self.assertEqual(len(runs), 1, tool)
            self.assertEqual(runs[0]["run_type"], "tool")
            self.assertEqual(self.client.parent_name(runs[0]), "retrieval_agent")
        search = self.client.named("search_document")[0]
        self.assertIn("query", json.dumps(search["inputs"]))
        result = self.client.updated[str(search["id"])]["outputs"]
        self.assertIn("conservation of mass", json.dumps(result))  # the retrieved evidence is visible

    def test_llm_calls_are_named_after_the_agent_step_and_nested_under_the_agent(self):
        expected = {"supervisor_agent.decide": "supervisor_agent", "evidence_evaluator.evaluate": "evidence_evaluator",
                    "tutor_agent.write": "tutor_agent", "critic_agent.review": "critic_agent"}
        for llm_name, parent in expected.items():
            run = self.client.named(llm_name)[0]
            self.assertEqual(run["run_type"], "llm")
            self.assertEqual(self.client.parent_name(run), parent)
            self.assertEqual(self.client.final_meta(run)["ls_model_name"], "gemini-test")

    def test_token_usage_is_recorded_only_when_the_provider_returns_it(self):
        run = self.client.named("tutor_agent.write")[0]
        self.assertEqual(self.client.updated[str(run["id"])]["outputs"]["usage_metadata"]["total_tokens"], 15)
        client, _, _ = traced_run(usage=False)
        run = client.named("tutor_agent.write")[0]
        self.assertNotIn("usage_metadata", client.updated[str(run["id"])]["outputs"])

    def test_routing_decisions_are_visible_as_runs(self):
        self.assertTrue(self.client.named("route_after_evidence"))
        self.assertTrue(self.client.named("route_after_critic"))


class TraceMetadataAndTags(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client, cls.final, cls.budget = traced_run()

    def test_root_run_carries_workflow_and_intent_tags_added_after_the_supervisor_decides(self):
        root = self.client.named("agent_request")[0]
        tags = self.client.final_tags(root)
        for tag in ("ai-tutor-guide", "workflow:qa", "intent:qa", "rag"):
            self.assertIn(tag, tags)

    def test_root_metadata_has_session_document_and_intent(self):
        meta = self.client.final_meta(self.client.named("agent_request")[0])
        self.assertEqual(meta["document_id"], "chem.pdf")
        self.assertEqual(meta["intent"], "qa")
        self.assertEqual(meta["workflow_type"], "qa")
        self.assertEqual(meta["decision_source"], "llm")
        self.assertIn("session_id", meta)

    def test_raw_session_id_is_never_sent(self):
        everything = json.dumps([self.client.final_meta(r) for r in self.client.created], default=str)
        self.assertNotIn('"sess1"', everything)
        self.assertEqual(self.client.final_meta(self.client.named("agent_request")[0])["session_id"], hash_id("sess1"))

    def test_agent_runs_carry_step_metadata(self):
        retrieval = self.client.named("retrieval_agent")[0]
        self.assertEqual(self.client.final_meta(retrieval)["retrieval_attempt"], 1)
        self.assertIn("retrieval", self.client.final_tags(retrieval))
        evaluator = self.client.named("evidence_evaluator")[0]
        self.assertEqual(self.client.final_meta(evaluator)["evidence_action"], "use_evidence")

    def test_revision_attempt_is_recorded_when_the_critic_sends_the_draft_back(self):
        env = Env()
        responses = {
            "SupervisorDecision": supervisor().model_dump_json(),
            "EvidenceEvaluation": evaluation().model_dump_json(),
            "TutorOutput": tutor().model_dump_json(),
        }
        critics = iter([critic("revise", complete=False, missing_information=["x"]).model_dump_json(), critic().model_dump_json()])

        class Models:
            def generate_content(self, model, contents, config):
                name = config.response_schema.__name__
                text = next(critics) if name == "CriticEvaluation" else responses[name]
                return SimpleNamespace(text=text, usage_metadata=None)

        deps = build_deps(GeminiLLM(SimpleNamespace(models=Models()), "m"), env.retrieval, env.learner)
        client = RecordingClient()
        with tracing_context(enabled=True, client=client):
            run_request(build_workflow(deps), message="q", session_id="sess1", document_id="chem.pdf")
        tutors = client.named("tutor_agent")
        self.assertEqual(len(tutors), 2)
        self.assertEqual(client.final_meta(tutors[1])["revision_attempt"], 1)
        self.assertIn("revision", client.final_tags(tutors[1]))

    def test_sensitive_keys_are_stripped_from_metadata(self):
        clean = sanitize_metadata({"api_key": "secret", "Authorization": "x", "user_token": "t", "intent": "qa", "n": 3})
        self.assertEqual(clean, {"intent": "qa", "n": 3})

    def test_long_values_are_truncated(self):
        self.assertLessEqual(len(sanitize_metadata({"note": "x" * 5000})["note"]), 200)

    def test_explicit_mode_tags_are_available_from_the_start(self):
        env = Env()
        deps = build_deps(GeminiLLM(fake_gemini(), "m"), env.retrieval, env.learner)
        graph = build_workflow(deps)
        client = RecordingClient()
        with tracing_context(enabled=True, client=client):
            run_request(graph, message="Key points", session_id="sess1", document_id="chem.pdf", mode_override="key_points")
        self.assertIn("workflow:guide-mode", set(client.named("agent_request")[0]["tags"]))


class FailuresRemainObservable(unittest.TestCase):
    def test_a_failing_tool_is_recorded_as_an_errored_run_and_the_request_still_ends_safely(self):
        env = Env()
        env.retrieval.search = mock.Mock(side_effect=RuntimeError("chroma down"))
        deps = build_deps(GeminiLLM(fake_gemini(), "m"), env.retrieval, env.learner)
        client = RecordingClient()
        with tracing_context(enabled=True, client=client):
            final, _ = run_request(build_workflow(deps), message="q", session_id="sess1", document_id="chem.pdf")
        search_runs = client.named("search_document")
        self.assertTrue(search_runs)
        self.assertIn("chroma down", client.updated[str(search_runs[0]["id"])].get("error", ""))
        self.assertTrue(final["reply"])

    def test_a_crashing_agent_is_tagged_as_an_error_in_its_run(self):
        env = Env()
        deps = build_deps(GeminiLLM(fake_gemini(), "m"), env.retrieval, env.learner)
        deps.retrieval_agent.step = mock.Mock(side_effect=RuntimeError("bug"))
        client = RecordingClient()
        with tracing_context(enabled=True, client=client):
            final, _ = run_request(build_workflow(deps), message="q", session_id="sess1", document_id="chem.pdf")
        node = client.named("retrieval_agent")[0]
        self.assertIn("error", client.final_tags(node))
        self.assertEqual(client.final_meta(node)["stop_reason"], "internal_error")
        self.assertEqual(final["stop_reason"], "internal_error")

    def test_budget_stops_are_tagged(self):
        from backend.budget import Budget

        client, final, _ = traced_run(budget=Budget(max_llm_calls=1))
        tagged = [r for r in client.created if "budget-exceeded" in client.final_tags(r)]
        self.assertTrue(tagged)

    def test_tracing_disabled_records_nothing(self):
        env = Env()
        deps = build_deps(GeminiLLM(fake_gemini(), "m"), env.retrieval, env.learner)
        client = RecordingClient()
        with tracing_context(enabled=False, client=client):
            run_request(build_workflow(deps), message="q", session_id="sess1", document_id="chem.pdf")
        self.assertEqual(client.created, [])


class Configuration(unittest.TestCase):
    def _run(self, env):
        with mock.patch.dict(os.environ, env, clear=True):
            return configure_tracing(), dict(os.environ)

    def test_current_langsmith_variables_enable_tracing_with_default_project(self):
        status, environ = self._run({"LANGSMITH_TRACING": "true", "LANGSMITH_API_KEY": "k"})
        self.assertTrue(status["enabled"])
        self.assertEqual(status["project"], "ai-tutor-guide")

    def test_legacy_langchain_variables_are_still_accepted(self):
        status, environ = self._run({"LANGCHAIN_TRACING_V2": "true", "LANGCHAIN_API_KEY": "k", "LANGCHAIN_PROJECT": "old"})
        self.assertTrue(status["enabled"])
        self.assertEqual(environ["LANGSMITH_API_KEY"], "k")
        self.assertEqual(status["project"], "old")

    def test_tracing_is_disabled_when_the_key_is_missing(self):
        status, environ = self._run({"LANGSMITH_TRACING": "true"})
        self.assertFalse(status["enabled"])
        self.assertEqual(environ["LANGSMITH_TRACING"], "false")

    def test_status_never_contains_the_api_key(self):
        status, _ = self._run({"LANGSMITH_TRACING": "true", "LANGSMITH_API_KEY": "super-secret"})
        self.assertNotIn("super-secret", json.dumps(status))


if __name__ == "__main__":
    unittest.main()
