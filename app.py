"""
Compatibility entry point. The application now lives in the `backend/` package:

    uvicorn app:app --reload            (unchanged command)
    uvicorn backend.main:app --reload   (equivalent)

The names below are re-exported because evaluate.py and older scripts import them from `app`.
"""
from backend.main import EMBEDDING_MODEL_NAME, app, generate_answer, retrieve_relevant_chunks  # noqa: F401
