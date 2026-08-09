from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import Enum
from threading import RLock
from uuid import uuid4

from .events import EventBus, EventType


class TaskState(str, Enum):
    CREATED = "created"
    PLANNING = "planning"
    WAITING_APPROVAL = "waiting_approval"
    RUNNING = "running"
    VERIFYING = "verifying"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


TERMINAL_STATES = {
    TaskState.SUCCEEDED,
    TaskState.FAILED,
    TaskState.CANCELLED,
}


@dataclass(slots=True)
class TaskRecord:
    task_id: str
    task_type: str
    state: TaskState
    created_at: str
    updated_at: str

    def as_dict(self) -> dict[str, str]:
        result = asdict(self)
        result["state"] = self.state.value
        return result


class TaskManager:
    """
    Canonical OSIRIS task lifecycle.

    User prompts and private task payloads are deliberately not
    persisted here yet. Phase 2 first establishes lifecycle,
    identity, state transitions, and observability.
    """

    def __init__(self, events: EventBus) -> None:
        self._events = events
        self._tasks: dict[str, TaskRecord] = {}
        self._lock = RLock()

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def create(self, task_type: str) -> TaskRecord:
        task_type = task_type.strip()

        if not task_type:
            raise ValueError("task_type cannot be empty")

        now = self._now()

        task = TaskRecord(
            task_id=str(uuid4()),
            task_type=task_type,
            state=TaskState.CREATED,
            created_at=now,
            updated_at=now,
        )

        with self._lock:
            self._tasks[task.task_id] = task

        self._events.publish(
            EventType.TASK_CREATED,
            payload={
                "task_id": task.task_id,
                "task_type": task.task_type,
            },
        )

        return task

    def get(self, task_id: str) -> TaskRecord | None:
        with self._lock:
            return self._tasks.get(task_id)

    def transition(
        self,
        task_id: str,
        new_state: TaskState,
    ) -> TaskRecord:
        with self._lock:
            task = self._tasks.get(task_id)

            if task is None:
                raise KeyError(task_id)

            if task.state in TERMINAL_STATES:
                raise ValueError(
                    f"Task {task_id} is already terminal: "
                    f"{task.state.value}"
                )

            previous = task.state
            task.state = new_state
            task.updated_at = self._now()

        self._events.publish(
            EventType.TASK_STATE_CHANGED,
            payload={
                "task_id": task_id,
                "from": previous.value,
                "to": new_state.value,
            },
        )

        return task

    def all(self) -> list[TaskRecord]:
        with self._lock:
            return list(self._tasks.values())

    @property
    def count(self) -> int:
        with self._lock:
            return len(self._tasks)
