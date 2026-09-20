"""Shared test scaffolding: a scripted fake LLM and an in-memory Chroma with a deterministic embedding.
No network, no model download, no LangSmith key needed."""
import hashlib
import os
import re
import shutil
import tempfile
import weakref
import uuid
from pathlib import Path
from typing import Any, Callable, Dict, List

os.environ["TUTOR_DISABLE_TRACING"] = "1"  # tests never upload traces, even if .env has a real key

import chromadb
from chromadb import EmbeddingFunction
from langchain_text_splitters import RecursiveCharacterTextSplitter

from backend.agents.schemas import CriticEvaluation, EvidenceEvaluation, SupervisorDecision, TutorOutput
from backend.agents.memory import ConversationSummarizer
from backend.graph.workflow import build_deps, build_workflow, run_request
from backend.services.chat_history_service import ChatHistoryService
from backend.services.learner_state_service import LearnerStateService
from backend.services.retrieval_service import RetrievalService, Scope


class HashEmbedding(EmbeddingFunction):
    """Deterministic bag-of-words hashing embedding (64-d), so similarity search works offline."""

    def __init__(self):
        pass

    def __call__(self, input):  # noqa: A002
        out = []
        for text in input:
            vec = [0.0] * 64
            for tok in re.findall(r"\w+", text.lower()):
                vec[int(hashlib.md5(tok.encode()).hexdigest(), 16) % 64] += 1.0
            norm = sum(v * v for v in vec) ** 0.5 or 1.0
            out.append([v / norm for v in vec])
        return out

    @staticmethod
    def name() -> str:
        return "hash-test-embedding"

    def get_config(self) -> Dict[str, Any]:
        return {}

    @staticmethod
    def build_from_config(config: Dict[str, Any]) -> "HashEmbedding":
        return HashEmbedding()


class FakeLLM:
    """script: {call_name: [item, ...]} consumed in order. An item is a schema instance, a dict for the
    schema, a string (text calls), None (invalid structured output) or a callable(prompt) -> any of those."""

    def __init__(self, script: Dict[str, List[Any]] = None):
        self.script = {k: list(v) for k, v in (script or {}).items()}
        self.calls: List[str] = []
        self.prompts: List[str] = []

    def _next(self, name: str, prompt: str, budget):
        budget.charge_llm()
        self.calls.append(name)
        self.prompts.append(prompt)
        queue = self.script.get(name)
        if not queue:
            raise AssertionError(f"unexpected LLM call: {name}")
        item = queue.pop(0) if len(queue) > 1 else queue[0]  # last item repeats
        return item(prompt) if callable(item) else item

    def text(self, prompt, system, *, budget, name):
        return self._next(name, prompt, budget)

    def structured(self, schema, prompt, system, *, budget, name):
        item = self._next(name, prompt, budget)
        if item is None or isinstance(item, schema):
            return item
        return schema(**item)


def supervisor(intent="qa", **kw) -> SupervisorDecision:
    base = dict(intent=intent, goal="explain_concept", needs_retrieval=intent == "qa", response_style="normal",
                next_action="retrieve", confidence=0.9, standalone_query="what is mass conservation", reasoning="test")
    base.update(kw)
    return SupervisorDecision(**base)


def evaluation(action="use_evidence", sufficient=True, relevant=True, coverage=0.9, **kw) -> EvidenceEvaluation:
    return EvidenceEvaluation(relevant=relevant, sufficient=sufficient, coverage=coverage,
                              missing_information=kw.pop("missing_information", []), recommended_action=action, **kw)


def tutor(action="answer", chunks=(0,), answer="Mass is conserved in a chemical reaction.", **kw) -> TutorOutput:
    return TutorOutput(action=action, answer=answer, used_chunk_indices=list(chunks), **kw)


def critic(action="finish", **kw) -> CriticEvaluation:
    base = dict(grounded=True, relevant=True, complete=True, unsupported_claims=[], missing_information=[],
                contradictions=[], revision_required=action != "finish", recommended_action=action)
    base.update(kw)
    return CriticEvaluation(**base)


DOC_TEXTS = [
    "The law of conservation of mass states that mass can neither be created nor destroyed in a chemical reaction.",
    "A balanced chemical equation has the same number of atoms of each element on both sides of the arrow.",
    "Exothermic reactions release heat along with the formation of products, while endothermic reactions absorb energy.",
    "Photosynthesis converts carbon dioxide and water into glucose and oxygen using sunlight.",
]


class Env:
    """A complete backend wired to fakes: in-memory Chroma, temp learner-state dir, scripted LLM."""

    def __init__(self, script=None, session="sess1", doc="chem.pdf", texts=None):
        client = chromadb.EphemeralClient()
        self.collection = client.get_or_create_collection(name=f"t_{uuid.uuid4().hex}", embedding_function=HashEmbedding())
        self.retrieval = RetrievalService(self.collection, RecursiveCharacterTextSplitter(chunk_size=800, chunk_overlap=100))
        self.tmp_path = tempfile.mkdtemp()
        self._finalizer = weakref.finalize(self, shutil.rmtree, self.tmp_path, True)
        self.learner = LearnerStateService(root=Path(self.tmp_path) / "states", legacy_root=Path(self.tmp_path) / "legacy")
        self.llm = FakeLLM(script)
        self.chat = ChatHistoryService(Path(self.tmp_path) / "chat.db")
        self.memory = ConversationSummarizer(self.llm, self.chat)
        self.deps = build_deps(self.llm, self.retrieval, self.learner)
        self.graph = build_workflow(self.deps)
        self.scope = Scope(session, doc)
        self.add_document(self.scope, texts or DOC_TEXTS)

    def add_document(self, scope: Scope, texts: List[str]):
        self.collection.add(
            documents=texts,
            ids=[uuid.uuid4().hex for _ in texts],
            metadatas=[{"source": scope.document_id, "session_id": scope.session_id, "chunk_index": i, "page": i + 1} for i in range(len(texts))],
        )

    def ask(self, message="what is mass conservation", **kw):
        return run_request(self.graph, message=message, session_id=self.scope.session_id, document_id=self.scope.document_id, **kw)

    def close(self):
        self._finalizer()

