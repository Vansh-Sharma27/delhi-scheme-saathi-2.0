"""Background queue and worker for non-urgent AI tasks.

The queue adapters (``InMemoryAIWorkQueue``, ``SQSAIWorkQueue``) and the SQS
payload codec (``serialize_work_item``, ``deserialize_work_item``) moved to
``src.dss.infrastructure.queues.work_queue`` in Phase 3 and are re-exported
below so existing imports keep working; the re-exports are removed in Phase 6.
This module keeps the application-side wiring: the configured-queue singleton,
the default-queue factory, the memory-refresh enqueue helper, the background
worker loop, and the work-item processor. Constructor injection replaces the
singletons in Phase 6.
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import suppress
from datetime import UTC, datetime

from src.dss.application.ports.clock import Clock
from src.dss.application.ports.work_queue import (
    AIWorkItem as AIWorkItem,
)
from src.dss.application.ports.work_queue import (
    AIWorkQueue as AIWorkQueue,
)
from src.dss.application.ports.work_queue import (
    AIWorkType as AIWorkType,
)
from src.dss.infrastructure.queues.work_queue import (
    InMemoryAIWorkQueue as InMemoryAIWorkQueue,
)
from src.dss.infrastructure.queues.work_queue import (
    SQSAIWorkQueue as SQSAIWorkQueue,
)
from src.dss.infrastructure.queues.work_queue import (
    deserialize_work_item as deserialize_work_item,
)
from src.dss.infrastructure.queues.work_queue import (
    serialize_work_item as serialize_work_item,
)
from src.dss.infrastructure.sessions.session_store import get_session_store
from src.dss.settings import get_settings

logger = logging.getLogger(__name__)

_ai_work_queue: AIWorkQueue | None = None
_worker_task: asyncio.Task[None] | None = None


def configure_ai_work_queue(queue: AIWorkQueue | None) -> None:
    """Set the active AI work queue."""
    global _ai_work_queue
    _ai_work_queue = queue


def get_ai_work_queue() -> AIWorkQueue | None:
    """Return the configured AI work queue."""
    return _ai_work_queue


def create_default_ai_work_queue() -> AIWorkQueue | None:
    """Create queue from settings."""
    settings = get_settings()
    if not settings.ai_memory_queue_enabled:
        return None
    if settings.ai_memory_queue_backend == "sqs" and settings.ai_memory_queue_url:
        return SQSAIWorkQueue(settings.ai_memory_queue_url, settings.aws_region)
    return InMemoryAIWorkQueue()


async def enqueue_memory_refresh(
    user_id: str, turn_count: int, *, clock: Clock | None = None
) -> bool:
    """Enqueue a working-memory refresh for a session."""
    queue = get_ai_work_queue()
    if queue is None:
        return False
    await queue.enqueue(
        AIWorkItem(
            work_type=AIWorkType.REFRESH_WORKING_MEMORY,
            user_id=user_id,
            turn_count=turn_count,
            enqueued_at=clock.now() if clock is not None else datetime.now(UTC),
        )
    )
    return True


async def process_work_item(item: AIWorkItem, *, clock: Clock | None = None) -> None:
    """Execute a background AI work item."""
    from src.services import session_manager
    from src.services.ai_orchestrator import get_ai_orchestrator

    store = get_session_store()
    session = await store.get(item.user_id)
    if session is None:
        return
    if item.work_type != AIWorkType.REFRESH_WORKING_MEMORY:
        return
    if not session.pending_memory_job:
        return
    if clock is not None:
        session.with_clock(clock)
    queue_lag_ms = max(
        0.0,
        ((clock.now() if clock is not None else datetime.now(UTC)) - item.enqueued_at).total_seconds() * 1000,
    )

    try:
        memory = await get_ai_orchestrator().refresh_working_memory(
            session,
            queue_lag_ms=queue_lag_ms,
        )
        session = session_manager.apply_working_memory(
            session,
            memory,
            refreshed_turn=session.completed_turn_count,
        )
    except Exception as exc:
        logger.error(
            "Background memory refresh failed for user=%s turn=%s: %s",
            item.user_id,
            item.turn_count,
            exc,
            exc_info=True,
        )
        session = session_manager.set_pending_memory_job(session, False)
    else:
        session = session_manager.set_pending_memory_job(session, False)

    await store.save(session)


async def _worker_loop(queue: AIWorkQueue) -> None:
    """Continuously process background AI jobs."""
    while True:
        try:
            item = await queue.dequeue()
            if item is None:
                continue
            try:
                await process_work_item(item)
            finally:
                await queue.ack(item)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.error("Unhandled error in background worker loop", exc_info=True)
            await asyncio.sleep(1)  # brief pause before retrying


async def start_ai_background_worker() -> None:
    """Start the background AI worker if a queue is configured."""
    global _worker_task

    queue = get_ai_work_queue()
    if queue is None:
        return

    # Restart if the task completed or was cancelled (silent death guard).
    if _worker_task is not None and not _worker_task.done():
        return

    _worker_task = asyncio.create_task(_worker_loop(queue), name="ai-background-worker")
    logger.info("Started AI background worker")


async def stop_ai_background_worker() -> None:
    """Stop the background AI worker and close queue resources."""
    global _worker_task

    if _worker_task is not None:
        _worker_task.cancel()
        with suppress(asyncio.CancelledError):
            await _worker_task
        _worker_task = None

    queue = get_ai_work_queue()
    if queue is not None:
        await queue.close()
    configure_ai_work_queue(None)
