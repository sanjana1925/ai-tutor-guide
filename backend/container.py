"""Composition root: builds the real services once and hands them to the API layer."""
import os
from dataclasses import dataclass
from typing import Optional

import chromadb
from chromadb.utils import embedding_functions
from google import genai
from langchain_text_splitters import RecursiveCharacterTextSplitter

from backend import config
from backend.agents.memory import ConversationSummarizer
from backend.graph.state import Deps
from backend.graph.workflow import build_deps, build_workflow
from backend.services.chat_history_service import ChatHistoryService
from backend.services.learner_state_service import LearnerStateService
from backend.services.llm_service import LLM, GeminiLLM
from backend.services.retrieval_service import RetrievalService


@dataclass
class Container:
    llm: LLM
    retrieval: RetrievalService
    learner: LearnerStateService
    deps: Deps
    graph: object
    chat: ChatHistoryService
    memory: ConversationSummarizer


def build_container() -> Container:
    client = chromadb.PersistentClient(path=config.CHROMA_PATH)
    embedding_fn = embedding_functions.SentenceTransformerEmbeddingFunction(model_name=config.EMBEDDING_MODEL_NAME)
    collection = client.get_or_create_collection(name=config.COLLECTION_NAME, embedding_function=embedding_fn)
    retrieval = RetrievalService(collection, RecursiveCharacterTextSplitter(chunk_size=800, chunk_overlap=150))
    llm = GeminiLLM(genai.Client(api_key=os.environ.get("GEMINI_API_KEY")), config.ANSWER_MODEL)
    learner = LearnerStateService()
    deps = build_deps(llm, retrieval, learner)
    chat = ChatHistoryService(config.DB_PATH)
    return Container(
        llm=llm,
        retrieval=retrieval,
        learner=learner,
        deps=deps,
        graph=build_workflow(deps),
        chat=chat,
        memory=ConversationSummarizer(llm, chat),
    )


_container: Optional[Container] = None


def get_container() -> Container:
    global _container
    if _container is None:
        _container = build_container()
    return _container


def set_container(container: Optional[Container]) -> None:
    global _container
    _container = container
