"""Memory refresh scheduling and processing over instance-owned ports."""

import logging

from src.dss.application.conversation import sessions
from src.dss.application.ports.ai_tasks import AITasks
from src.dss.application.ports.clock import Clock
from src.dss.application.ports.session_repository import SessionStore
from src.dss.application.ports.work_queue import AIWorkItem, AIWorkQueue, AIWorkType

logger = logging.getLogger(__name__)


class MemoryJobs:
    def __init__(
        self, store: SessionStore, ai: AITasks, clock: Clock,
        queue: AIWorkQueue | None,
    ) -> None:
        self.store = store
        self.ai = ai
        self.clock = clock
        self.queue = queue

    async def enqueue(self, user_id: str, turn_count: int) -> bool:
        if self.queue is None:
            return False
        await self.queue.enqueue(AIWorkItem(
            work_type=AIWorkType.REFRESH_WORKING_MEMORY,
            user_id=user_id, turn_count=turn_count, enqueued_at=self.clock.now(),
        ))
        return True

    async def process(self, item: AIWorkItem) -> None:
        session = await self.store.get(item.user_id)
        if session is None:
            return
        if item.work_type != AIWorkType.REFRESH_WORKING_MEMORY:
            return
        if not session.pending_memory_job:
            return
        session.with_clock(self.clock)
        queue_lag_ms = max(0.0, (self.clock.now() - item.enqueued_at).total_seconds() * 1000)
        try:
            memory = await self.ai.refresh_working_memory(session, queue_lag_ms=queue_lag_ms)
            session = sessions.apply_working_memory(
                session, memory, refreshed_turn=session.completed_turn_count,
            )
        except Exception as exc:
            logger.error(
                "Background memory refresh failed for user=%s turn=%s: %s",
                item.user_id, item.turn_count, exc, exc_info=True,
            )
            session = sessions.set_pending_memory_job(session, False)
        else:
            session = sessions.set_pending_memory_job(session, False)
        await self.store.save(session)
