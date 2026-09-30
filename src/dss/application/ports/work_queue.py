"""Port: AI background work queue.

Canonical home for the work queue contract and its payload types, moved
here in Phase 2 from `src/services/ai_background.py` (spec 6.1: "AIWorkQueue
already exists as a Protocol; reuse it"). The legacy module re-exports all
three names so existing imports (`memory_worker_handler`, tests) keep
working; the facade is removed in Phase 6.

`AIWorkItem` carries an explicit `enqueued_at` timestamp. Phase 3 enqueue and
deserialization helpers accept a Clock and pass its value here. Direct legacy
construction keeps its UTC wall-time default.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Protocol, runtime_checkable


class AIWorkType(StrEnum):
    """Background AI work types."""

    REFRESH_WORKING_MEMORY = "refresh_working_memory"


@dataclass(slots=True)
class AIWorkItem:
    """Background AI work payload."""

    work_type: AIWorkType
    user_id: str
    turn_count: int
    enqueued_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    receipt_handle: str | None = None


@runtime_checkable
class AIWorkQueue(Protocol):
    """Queue abstraction for async AI jobs."""

    async def enqueue(self, item: AIWorkItem) -> None: ...
    async def dequeue(self) -> AIWorkItem | None: ...
    async def ack(self, item: AIWorkItem) -> None: ...
    async def close(self) -> None: ...
