"""Owned memory processing preserves clocks, pending markers and queue lifecycle."""

import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

from src.dss.application.conversation.background_memory import MemoryJobs
from src.dss.application.ports.ai_tasks import AITasks
from src.dss.application.ports.work_queue import AIWorkQueue
from src.dss.bootstrap.background import LocalMemoryWorker
from src.dss.domain.conversations.session import ConversationMemory, Session
from src.dss.infrastructure.queues.work_queue import InMemoryAIWorkQueue
from src.dss.infrastructure.sessions.session_store import InMemorySessionStore


class FixedClock:
    value = datetime(2026, 1, 1, tzinfo=UTC)

    def now(self):
        return self.value


async def test_memory_jobs_use_latest_session_and_injected_clock() -> None:
    clock = FixedClock()
    store = InMemorySessionStore(clock)
    queue = InMemoryAIWorkQueue()
    ai = AsyncMock(spec=AITasks)
    jobs = MemoryJobs(store, ai, clock, queue)
    assert await jobs.enqueue("synthetic", 2)
    item = await queue.dequeue()
    assert item.enqueued_at == clock.now()
    await store.save(Session(user_id="synthetic", pending_memory_job=True, completed_turn_count=4))
    clock.value += timedelta(seconds=3)
    ai.refresh_working_memory.return_value = ConversationMemory(summary="synthetic")
    await jobs.process(item)
    assert ai.refresh_working_memory.await_args.kwargs["queue_lag_ms"] == 3000
    saved = await store.get("synthetic")
    assert saved.last_memory_refresh_turn == 4
    assert saved.working_memory.summary == "synthetic"
    assert not saved.pending_memory_job
    await jobs.process(item)
    assert ai.refresh_working_memory.await_count == 1
    await store.save(saved.copy_with(pending_memory_job=True))
    ai.refresh_working_memory.side_effect = RuntimeError("synthetic")
    await jobs.process(item)
    assert not (await store.get("synthetic")).pending_memory_job
    assert not await MemoryJobs(store, ai, clock, None).enqueue("synthetic", 4)


async def test_local_worker_starts_once_acknowledges_failures_and_closes_once() -> None:
    queue = AsyncMock(spec=AIWorkQueue)
    acknowledged = asyncio.Event()
    queue.dequeue.return_value = object()
    queue.ack.side_effect = lambda item: acknowledged.set()
    process = AsyncMock(side_effect=RuntimeError("synthetic"))
    worker = LocalMemoryWorker(queue, process)
    await worker.start()
    task = worker._task
    await worker.start()
    assert worker._task is task
    await asyncio.wait_for(acknowledged.wait(), timeout=1)
    await worker.stop()
    await worker.stop()
    assert task.cancelled()
    assert worker._task is None
    queue.ack.assert_awaited_once()
    queue.close.assert_awaited_once()
