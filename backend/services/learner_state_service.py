"""
Learner-state persistence (deterministic Python).

State is stored per (session, document). The previous layout kept one file per session, so
switching documents overwrote the other document's progress. Legacy files are still read.
"""
import hashlib
import json
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Dict, Iterator, Tuple

from backend import config
from backend.domain.quiz_engine import LearnerState
from backend.services.retrieval_service import Scope


class LearnerStateService:
    def __init__(self, root: Path = config.DATA_DIR / "learner_states", legacy_root: Path = config.DATA_DIR):
        self._root = Path(root)
        self._legacy_root = Path(legacy_root)
        self._cache: Dict[Tuple[str, str], LearnerState] = {}
        self._locks: Dict[Tuple[str, str], threading.RLock] = {}
        self._guard = threading.Lock()

    @staticmethod
    def _key(scope: Scope) -> Tuple[str, str]:
        return (scope.session_id, scope.document_id)

    def _path(self, scope: Scope) -> Path:
        digest = hashlib.sha256(scope.document_id.encode("utf-8")).hexdigest()[:16]
        return self._root / f"{scope.session_id}__{digest}.json"

    def _legacy_path(self, scope: Scope) -> Path:
        return self._legacy_root / f"learner_state_{scope.session_id}.json"

    @contextmanager
    def locked(self, scope: Scope) -> Iterator[None]:
        """Serialises quiz turns for one learner+document so answers can't be double-graded."""
        with self._guard:
            lock = self._locks.setdefault(self._key(scope), threading.RLock())
        with lock:
            yield

    def _load_file(self, path: Path, scope: Scope):
        if not path.exists():
            return None
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if raw.get("filename") == scope.document_id and raw.get("session_id") == scope.session_id:
                return LearnerState(**raw)
        except Exception:  # noqa: BLE001 - corrupt state file: start fresh rather than fail the request
            return None
        return None

    def get(self, scope: Scope) -> LearnerState:
        key = self._key(scope)
        if key in self._cache:
            return self._cache[key]
        state = self._load_file(self._path(scope), scope) or self._load_file(self._legacy_path(scope), scope)
        if state is None:
            state = LearnerState(session_id=scope.session_id, filename=scope.document_id)
        self._cache[key] = state
        return state

    def save(self, state: LearnerState) -> None:
        scope = Scope(state.session_id, state.filename)
        self._cache[self._key(scope)] = state
        try:
            self._root.mkdir(parents=True, exist_ok=True)
            self._path(scope).write_text(json.dumps(state.model_dump(), indent=2), encoding="utf-8")
        except OSError:
            pass

    def reset(self, scope: Scope) -> None:
        self._cache.pop(self._key(scope), None)
        for path in (self._path(scope), self._legacy_path(scope)):
            if path.exists() and (path == self._path(scope) or self._load_file(path, scope) is not None):
                try:
                    path.unlink()
                except OSError:
                    pass
