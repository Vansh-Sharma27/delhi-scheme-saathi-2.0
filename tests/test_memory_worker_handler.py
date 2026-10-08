"""Tests for the SQS-based working-memory Lambda handler."""

import json
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

from src.dss.application.ports.work_queue import AIWorkType
from src.dss.bootstrap import memory_worker


def test_memory_worker_handler_processes_sqs_records(monkeypatch) -> None:
    """Worker Lambda should deserialize queue records and process them."""
    process_item = AsyncMock()
    event = {
        "Records": [
            {
                "messageId": "msg-1",
                "body": json.dumps(
                    {
                        "work_type": "refresh_working_memory",
                        "user_id": "user-123",
                        "turn_count": 7,
                    }
                ),
            }
        ]
    }

    @asynccontextmanager
    async def worker_runtime(settings):
        yield SimpleNamespace(process=process_item)

    monkeypatch.setattr(memory_worker, "worker_runtime", worker_runtime)
    result = memory_worker.handler(event, context=None)

    assert result == {"batchItemFailures": []}
    process_item.assert_awaited_once()
    item = process_item.await_args.args[0]
    assert item.work_type == AIWorkType.REFRESH_WORKING_MEMORY
    assert item.user_id == "user-123"
    assert item.turn_count == 7


def test_memory_worker_handler_reports_batch_failures(monkeypatch) -> None:
    """Failed records should be returned for SQS retry instead of crashing the batch."""
    process_item = AsyncMock(side_effect=RuntimeError("boom"))
    event = {
        "Records": [
            {
                "messageId": "msg-2",
                "body": json.dumps(
                    {
                        "work_type": "refresh_working_memory",
                        "user_id": "user-456",
                        "turn_count": 11,
                    }
                ),
            }
        ]
    }

    @asynccontextmanager
    async def worker_runtime(settings):
        yield SimpleNamespace(process=process_item)

    monkeypatch.setattr(memory_worker, "worker_runtime", worker_runtime)
    result = memory_worker.handler(event, context=None)

    process_item.assert_awaited_once()
    assert result == {"batchItemFailures": [{"itemIdentifier": "msg-2"}]}
