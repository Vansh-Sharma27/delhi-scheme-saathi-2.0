"""AI background work queue adapters.

Moved to ``src.dss.infrastructure.queues`` in Phase 3 behind the
``AIWorkQueue`` port defined in Phase 2 (the port module is the canonical home
of ``AIWorkItem``, ``AIWorkType``, and the ``AIWorkQueue`` protocol). The
legacy ``src.services.ai_background`` module keeps the application-side
worker functions and re-exports these names until Phase 6 removes the facade.

``serialize_work_item`` and ``deserialize_work_item`` move with the adapters
because they are the SQS payload codec: one side of the wire is
``SQSAIWorkQueue.enqueue``, the other is the memory worker handler. Keeping
them beside the adapter keeps the payload format in one module.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, datetime

import boto3

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

logger = logging.getLogger(__name__)


class InMemoryAIWorkQueue:
    """In-process queue for local development and tests."""

    def __init__(self) -> None:
        self._queue: asyncio.Queue[AIWorkItem] = asyncio.Queue()

    async def enqueue(self, item: AIWorkItem) -> None:
        await self._queue.put(item)

    async def dequeue(self) -> AIWorkItem | None:
        return await self._queue.get()

    async def ack(self, item: AIWorkItem) -> None:
        self._queue.task_done()

    async def close(self) -> None:
        return None


class SQSAIWorkQueue:
    """SQS-backed queue for shared background AI jobs across instances."""

    def __init__(self, queue_url: str, region: str) -> None:
        self._queue_url = queue_url
        self._client = boto3.client("sqs", region_name=region)

    async def enqueue(self, item: AIWorkItem) -> None:
        body = json.dumps(serialize_work_item(item))
        await asyncio.to_thread(
            self._client.send_message,
            QueueUrl=self._queue_url,
            MessageBody=body,
        )

    async def dequeue(self) -> AIWorkItem | None:
        response = await asyncio.to_thread(
            self._client.receive_message,
            QueueUrl=self._queue_url,
            MaxNumberOfMessages=1,
            WaitTimeSeconds=20,
            VisibilityTimeout=60,
        )
        messages = response.get("Messages", [])
        if not messages:
            return None

        raw_message = messages[0]
        body = json.loads(raw_message["Body"])
        return deserialize_work_item(
            body,
            receipt_handle=raw_message.get("ReceiptHandle"),
        )

    async def ack(self, item: AIWorkItem) -> None:
        if not item.receipt_handle:
            return
        await asyncio.to_thread(
            self._client.delete_message,
            QueueUrl=self._queue_url,
            ReceiptHandle=item.receipt_handle,
        )

    async def close(self) -> None:
        return None


def serialize_work_item(item: AIWorkItem) -> dict[str, str | int]:
    """Serialize a work item into a queue-safe payload."""
    return {
        "work_type": item.work_type.value,
        "user_id": item.user_id,
        "turn_count": item.turn_count,
        "enqueued_at": item.enqueued_at.isoformat(),
    }


def deserialize_work_item(
    payload: dict[str, object],
    *,
    receipt_handle: str | None = None,
    clock: Clock | None = None,
) -> AIWorkItem:
    """Deserialize a queue payload into a typed work item."""
    enqueued_at_raw = payload.get("enqueued_at")
    if isinstance(enqueued_at_raw, str):
        enqueued_at = datetime.fromisoformat(enqueued_at_raw)
    else:
        enqueued_at = clock.now() if clock is not None else datetime.now(UTC)

    return AIWorkItem(
        work_type=AIWorkType(str(payload["work_type"])),
        user_id=str(payload["user_id"]),
        turn_count=int(payload.get("turn_count", 0)),
        enqueued_at=enqueued_at,
        receipt_handle=receipt_handle,
    )
