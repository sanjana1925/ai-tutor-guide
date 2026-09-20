"""Tool layer safety (typed args, allowlists, budgets) and document/session isolation."""
import tempfile
import unittest
from pathlib import Path

from helpers import DOC_TEXTS, Env, critic, evaluation, supervisor, tutor

from backend.budget import Budget
from backend.graph.workflow import run_request
from backend.services.learner_state_service import LearnerStateService
from backend.services.retrieval_service import Scope
from backend.tools.base import ToolContext
from backend.domain.quiz_engine import LearnerState


class ToolSafety(unittest.TestCase):
    def setUp(self):
        self.env = Env()
        self.ctx = ToolContext(scope=self.env.scope, budget=Budget())
        self.registry = self.env.deps.registry

    def tearDown(self):
        self.env.close()

    def test_search_document_returns_typed_chunks(self):
        r = self.registry.run("search_document", self.ctx, {"query": "conservation of mass", "top_k": 2})
        self.assertTrue(r.ok)
        self.assertEqual(len(r.chunks), 2)
        self.assertEqual(set(r.chunks[0]), {"chunk_index", "text", "page", "distance"})
        self.assertEqual(r.chunks[0]["chunk_index"], 0)

    def test_unknown_tool_is_refused(self):
        r = self.registry.run("delete_everything", self.ctx, {})
        self.assertFalse(r.ok)
        self.assertIn("unknown or disallowed", r.error)

    def test_a_model_cannot_pass_a_session_or_document_id(self):
        for extra in ({"session_id": "sess2"}, {"document_id": "other.pdf"}, {"where": {"source": "other.pdf"}}):
            r = self.registry.run("search_document", self.ctx, {"query": "x", **extra})
            self.assertFalse(r.ok, extra)
            self.assertIn("invalid arguments", r.error)

    def test_invalid_arguments_are_rejected_before_execution(self):
        for args in ({"query": ""}, {"query": "x", "top_k": 99}, {"query": "x" * 501}, {}):
            self.assertFalse(self.registry.run("search_document", self.ctx, args).ok, args)
        self.assertEqual(self.ctx.budget.tool_calls, 0)  # rejected calls cost nothing

    def test_agents_only_get_their_allowlisted_tools(self):
        retrieval_registry = self.env.deps.retrieval_agent.registry
        self.assertNotIn("get_learning_history", retrieval_registry.names())
        r = retrieval_registry.run("get_learning_history", self.ctx, {})
        self.assertFalse(r.ok)
        planner_registry = self.env.deps.planner.registry
        self.assertNotIn("search_document", planner_registry.names())

    def test_tool_budget_is_enforced(self):
        ctx = ToolContext(scope=self.env.scope, budget=Budget(max_tool_calls=1))
        self.assertTrue(self.registry.run("search_document", ctx, {"query": "mass"}).ok)
        r = self.registry.run("search_document", ctx, {"query": "mass"})
        self.assertFalse(r.ok)
        self.assertEqual(r.error, "tool_call_budget_exceeded")

    def test_a_crashing_tool_returns_an_error_result_not_an_exception(self):
        self.env.retrieval.search = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom"))
        r = self.registry.run("search_document", self.ctx, {"query": "mass"})
        self.assertFalse(r.ok)
        self.assertIn("tool execution failed", r.error)

    def test_similar_and_neighbor_tools(self):
        similar = self.registry.run("search_similar_chunks", self.ctx, {"chunk_index": 0, "top_k": 2})
        self.assertTrue(similar.ok)
        self.assertNotIn(0, [c["chunk_index"] for c in similar.chunks])
        neighbors = self.registry.run("get_neighbor_chunks", self.ctx, {"chunk_index": 1})
        self.assertEqual([c["chunk_index"] for c in neighbors.chunks], [0, 2])
        self.assertFalse(self.registry.run("search_similar_chunks", self.ctx, {"chunk_index": 99}).ok)

    def test_metadata_tool_uses_page_numbers_when_present(self):
        r = self.registry.run("search_by_metadata", self.ctx, {"page": 2})
        self.assertEqual([c["chunk_index"] for c in r.chunks], [1])

    def test_metadata_tool_reports_missing_page_metadata(self):
        env = Env()
        env.collection.delete(where={"source": "chem.pdf"})
        env.collection.add(documents=["no pages here"], ids=["x"], metadatas=[{"source": "chem.pdf", "session_id": "sess1", "chunk_index": 0}])
        r = env.deps.registry.run("search_by_metadata", ToolContext(env.scope, Budget()), {"page": 1})
        self.assertFalse(r.ok)
        self.assertIn("no page metadata", r.error)
        env.close()

    def test_document_metadata_tool(self):
        r = self.registry.run("get_document_metadata", self.ctx, {})
        self.assertEqual((r.data["num_chunks"], r.data["indexed"], r.data["has_page_metadata"]), (4, True, True))


class DocumentIsolation(unittest.TestCase):
    def setUp(self):
        self.env = Env()
        self.svc = self.env.retrieval
        self.a = Scope("sess1", "chem.pdf")  # the default doc
        self.b = Scope("sess2", "chem.pdf")  # same filename, different session
        self.c = Scope("sess1", "bio.pdf")  # same session, different document
        self.env.add_document(self.b, ["Session two secret: the answer is 42 in this document."])
        self.env.add_document(self.c, ["Mitochondria are the powerhouse of the cell."])

    def tearDown(self):
        self.env.close()

    def test_search_never_crosses_sessions_or_documents(self):
        texts_a = [c["text"] for c in self.svc.search(self.a, "secret answer 42 mitochondria", 8)]
        self.assertTrue(all(t in DOC_TEXTS for t in texts_a))
        self.assertEqual([c["text"] for c in self.svc.search(self.b, "mass", 8)], ["Session two secret: the answer is 42 in this document."])
        self.assertEqual([c["text"] for c in self.svc.search(self.c, "mass", 8)], ["Mitochondria are the powerhouse of the cell."])

    def test_every_read_method_is_scoped(self):
        self.assertEqual(self.svc.count(self.a), 4)
        self.assertEqual(self.svc.count(self.b), 1)
        self.assertEqual(len(self.svc.get_texts(self.c)), 1)
        self.assertEqual([c["text"] for c in self.svc.get_by_indices(self.b, [0, 1, 2])], ["Session two secret: the answer is 42 in this document."])
        self.assertEqual(self.svc.neighbors(self.b, 0), [])
        self.assertEqual(self.svc.by_page(self.c, 3), [])

    def test_deleting_one_document_leaves_the_others_untouched(self):
        self.svc.delete(self.b)
        self.assertEqual(self.svc.count(self.b), 0)
        self.assertEqual((self.svc.count(self.a), self.svc.count(self.c)), (4, 1))

    def test_scope_requires_both_identifiers(self):
        with self.assertRaises(ValueError):
            Scope("", "chem.pdf")
        with self.assertRaises(ValueError):
            Scope("sess1", "")

    def test_a_full_request_only_sees_its_own_documents_evidence(self):
        env = Env({"supervisor_agent.decide": [supervisor()], "evidence_evaluator.evaluate": [evaluation()],
                   "tutor_agent.write": [tutor(chunks=(0,))], "critic_agent.review": [critic()]})
        env.add_document(Scope("sess2", "chem.pdf"), ["Session two secret: the answer is 42 in this document."])
        final, _ = run_request(env.graph, message="secret answer 42", session_id="sess1", document_id="chem.pdf")
        seen = " ".join(c["text"] for c in final["evidence"])
        self.assertNotIn("Session two secret", seen)
        env.close()

    def test_learner_state_is_separate_per_document_in_one_session(self):
        # Regression: state used to be one file per session, so switching documents overwrote progress.
        with tempfile.TemporaryDirectory() as tmp:
            svc = LearnerStateService(root=Path(tmp) / "s", legacy_root=Path(tmp) / "legacy")
            s1, s2 = svc.get(Scope("u", "a.pdf")), svc.get(Scope("u", "b.pdf"))
            s1.total_attempted, s1.total_correct = 5, 4
            svc.save(s1)
            s2.total_attempted = 9
            svc.save(s2)
            fresh = LearnerStateService(root=Path(tmp) / "s", legacy_root=Path(tmp) / "legacy")
            self.assertEqual(fresh.get(Scope("u", "a.pdf")).total_attempted, 5)
            self.assertEqual(fresh.get(Scope("u", "b.pdf")).total_attempted, 9)

    def test_legacy_state_file_is_still_loaded_but_only_for_its_own_document(self):
        with tempfile.TemporaryDirectory() as tmp:
            legacy = Path(tmp) / "legacy"
            legacy.mkdir()
            state = LearnerState(session_id="u", filename="a.pdf", total_attempted=7)
            (legacy / "learner_state_u.json").write_text(state.model_dump_json(), encoding="utf-8")
            svc = LearnerStateService(root=Path(tmp) / "s", legacy_root=legacy)
            self.assertEqual(svc.get(Scope("u", "a.pdf")).total_attempted, 7)
            self.assertEqual(svc.get(Scope("u", "other.pdf")).total_attempted, 0)

    def test_reset_only_clears_the_requested_document(self):
        with tempfile.TemporaryDirectory() as tmp:
            svc = LearnerStateService(root=Path(tmp) / "s", legacy_root=Path(tmp) / "legacy")
            for name in ("a.pdf", "b.pdf"):
                s = svc.get(Scope("u", name))
                s.total_attempted = 3
                svc.save(s)
            svc.reset(Scope("u", "a.pdf"))
            fresh = LearnerStateService(root=Path(tmp) / "s", legacy_root=Path(tmp) / "legacy")
            self.assertEqual((fresh.get(Scope("u", "a.pdf")).total_attempted, fresh.get(Scope("u", "b.pdf")).total_attempted), (0, 3))


if __name__ == "__main__":
    unittest.main()
