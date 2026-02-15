"""Background task manager with WebSocket progress broadcasting."""
import asyncio
import uuid
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Coroutine, Optional
from fastapi import WebSocket


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class TaskRecord:
    id: str
    kind: str
    status: TaskStatus = TaskStatus.PENDING
    progress: float = 0.0
    message: str = ""
    result: Any = None
    error: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)


class TaskManager:
    def __init__(self):
        self._tasks: dict[str, TaskRecord] = {}
        self._subscribers: dict[str, list[WebSocket]] = {}
        self._lock = asyncio.Lock()

    def create_task(
        self,
        kind: str,
        coro_fn: Callable[["TaskManager", str], Coroutine],
    ) -> str:
        task_id = uuid.uuid4().hex[:12]
        record = TaskRecord(id=task_id, kind=kind)
        self._tasks[task_id] = record
        asyncio.create_task(self._run(task_id, coro_fn))
        return task_id

    async def _run(self, task_id: str, coro_fn):
        record = self._tasks[task_id]
        record.status = TaskStatus.RUNNING
        record.updated_at = time.time()
        try:
            result = await coro_fn(self, task_id)
            record.status = TaskStatus.COMPLETED
            record.progress = 1.0
            record.result = result
        except Exception as e:
            record.status = TaskStatus.FAILED
            record.error = str(e)
        finally:
            record.updated_at = time.time()
            await self._broadcast(task_id)

    async def update_progress(self, task_id: str, progress: float, message: str = ""):
        if task_id in self._tasks:
            rec = self._tasks[task_id]
            rec.progress = progress
            rec.message = message
            rec.updated_at = time.time()
            await self._broadcast(task_id)

    def get_task(self, task_id: str) -> Optional[TaskRecord]:
        return self._tasks.get(task_id)

    async def subscribe(self, task_id: str, ws: WebSocket):
        if task_id not in self._subscribers:
            self._subscribers[task_id] = []
        self._subscribers[task_id].append(ws)

    async def unsubscribe(self, task_id: str, ws: WebSocket):
        if task_id in self._subscribers:
            self._subscribers[task_id] = [
                s for s in self._subscribers[task_id] if s is not ws
            ]

    async def _broadcast(self, task_id: str):
        rec = self._tasks.get(task_id)
        if not rec:
            return
        msg = {
            "type": "progress",
            "taskId": rec.id,
            "status": rec.status.value,
            "progress": rec.progress,
            "message": rec.message,
        }
        if rec.status == TaskStatus.COMPLETED:
            msg["result"] = rec.result
        if rec.status == TaskStatus.FAILED:
            msg["error"] = rec.error
        dead = []
        for ws in self._subscribers.get(task_id, []):
            try:
                await ws.send_json(msg)
            except Exception:
                dead.append(ws)
        for ws in dead:
            await self.unsubscribe(task_id, ws)
