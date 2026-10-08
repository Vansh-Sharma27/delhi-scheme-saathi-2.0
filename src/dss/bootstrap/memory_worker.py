"""SQS batch entrypoint with invocation-owned AI resources."""

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from src.dss.application.ports.work_queue import AIWorkItem
from src.dss.bootstrap.logging import configure_logging
from src.dss.bootstrap.runtime import worker_runtime
from src.dss.infrastructure.queues.work_queue import deserialize_work_item
from src.dss.settings import get_settings

logger = logging.getLogger(__name__)


async def process_event(
    event: dict[str, Any], process: Callable[[AIWorkItem], Awaitable[None]],
) -> dict[str, list[dict[str, str]]]:
    batch_failures: list[dict[str, str]] = []
    for record in event.get("Records", []):
        message_id = record.get("messageId")
        try:
            payload = json.loads(record["body"])
            item = deserialize_work_item(payload)
            await process(item)
        except Exception as exc:
            logger.error("Memory worker failed for message_id=%s: %s", message_id, exc, exc_info=True)
            if message_id:
                batch_failures.append({"itemIdentifier": message_id})
    return {"batchItemFailures": batch_failures}


async def handle_event(event: dict[str, Any]) -> dict[str, list[dict[str, str]]]:
    settings = get_settings()
    configure_logging(settings.log_level, settings=settings)
    async with worker_runtime(settings) as jobs:
        return await process_event(event, jobs.process)


def handler(event: dict[str, Any], context: Any) -> dict[str, list[dict[str, str]]]:
    return asyncio.run(handle_event(event))
