"""Dependency injection for FastAPI."""
import asyncio
import sys
from pathlib import Path
from functools import lru_cache

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.knowledge_base.db import Database
from src.knowledge_base.vector_store import VectorStore
from src.llm.router import LLMRouter
from api.task_manager import TaskManager

_db: Database | None = None
_vs: VectorStore | None = None
_router: LLMRouter | None = None
_task_manager: TaskManager | None = None
_db_lock = asyncio.Lock()


def get_db() -> Database:
    global _db
    if _db is None:
        import sqlite3
        _db = Database()
        # Patch connection for thread safety in async context
        _original_conn = Database.conn.fget

        @property
        def _safe_conn(self) -> sqlite3.Connection:
            if self._conn is None:
                self._conn = sqlite3.connect(
                    str(self.db_path), check_same_thread=False
                )
                self._conn.row_factory = sqlite3.Row
                self._conn.execute("PRAGMA journal_mode=WAL")
                self._conn.execute("PRAGMA foreign_keys=ON")
            return self._conn

        Database.conn = _safe_conn
        _db.initialize()
    return _db


def get_vs() -> VectorStore:
    global _vs
    if _vs is None:
        _vs = VectorStore()
    return _vs


def get_router() -> LLMRouter:
    global _router
    if _router is None:
        _router = LLMRouter(db=get_db())
    return _router


def get_task_manager() -> TaskManager:
    global _task_manager
    if _task_manager is None:
        _task_manager = TaskManager()
    return _task_manager


def get_db_lock() -> asyncio.Lock:
    return _db_lock
