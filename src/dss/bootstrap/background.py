"""Queue selection and container-owned local worker lifecycle."""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from contextlib import suppress

from src.dss.application.ports.work_queue import AIWorkItem, AIWorkQueue
from src.dss.infrastructure.queues.work_queue import InMemoryAIWorkQueue, SQSAIWorkQueue
from src.dss.settings import Settings

logger = logging.getLogger(__name__)


def build_work_queue(settings: Settings) -> AIWorkQueue | None:
    if not settings.ai_memory_queue_enabled:
        return None
    if settings.ai_memory_queue_backend == "sqs" and settings.ai_memory_queue_url:
        return SQSAIWorkQueue(settings.ai_memory_queue_url, settings.aws_region)
    return InMemoryAIWorkQueue()


class LocalMemoryWorker:
    def __init__(
        self, queue: AIWorkQueue, process: Callable[[AIWorkItem], Awaitable[None]],
    ) -> None:
        self.queue: AIWorkQueue | None = queue
        self.process = process
        self._task: asyncio.Task[None] | None = None

    async def _run(self, queue: AIWorkQueue) -> None:
        while True:
            try:
                item = await queue.dequeue()
                if item is None:
                    continue
                try:
                    await self.process(item)
                finally:
                    await queue.ack(item)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.error("Unhandled error in background worker loop", exc_info=True)
                await asyncio.sleep(1)

    async def start(self) -> None:
        if self.queue is None:
            return
        if self._task is not None and not self._task.done():
            return
        self._task = asyncio.create_task(self._run(self.queue), name="ai-background-worker")
        logger.info("Started AI background worker")

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            with suppress(asyncio.CancelledError):
                await self._task
            self._task = None
        if self.queue is not None:
            await self.queue.close()
            self.queue = None
