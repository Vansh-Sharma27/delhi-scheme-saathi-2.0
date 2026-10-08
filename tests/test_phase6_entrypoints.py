"""Four-surface lifecycle separation: cold/warm calls and container-only worker."""

from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

from fastapi.testclient import TestClient

from src.dss.bootstrap import api, lambda_api, memory_worker
from src.dss.interfaces.api.dependencies import APIDependencies
from src.dss.settings import Settings


def test_container_and_lambda_have_distinct_resource_lifetimes(monkeypatch) -> None:
    settings = Settings(_env_file=None)
    starts, closes, workers = [], [], []

    @asynccontextmanager
    async def fake_runtime(settings):
        marker = object()
        starts.append(marker)
        worker = AsyncMock()
        workers.append(worker)
        try:
            yield SimpleNamespace(dependencies=APIDependencies(
                settings, None, None, None, None, AsyncMock(), AsyncMock(),
            ), start_local_worker=worker)
        finally:
            closes.append(marker)

    monkeypatch.setattr(api, "api_runtime", fake_runtime)
    monkeypatch.setattr(lambda_api, "api_runtime", fake_runtime)
    with TestClient(api.create_app(settings)) as client:
        assert client.get("/health").json()["database"] == "disconnected"
        assert closes == []
        workers[0].assert_awaited_once()
    assert closes == starts
    event = {
        "version": "2.0", "routeKey": "GET /health", "rawPath": "/health",
        "rawQueryString": "", "headers": {"host": "synthetic.test"},
        "requestContext": {"http": {"method": "GET", "path": "/health", "sourceIp": "127.0.0.1"}, "stage": "$default"},
        "isBase64Encoded": False,
    }
    for _ in range(2):
        assert lambda_api.handler(event, SimpleNamespace())["statusCode"] == 200
    assert closes == starts and len(starts) == 3
    for worker in workers[1:]:
        worker.assert_not_called()


def test_worker_repeated_invocations_close_resources_and_report_failures(monkeypatch) -> None:
    processors, closed = [], []

    @asynccontextmanager
    async def fake_runtime(settings):
        process = AsyncMock()
        processors.append(process)
        try:
            yield SimpleNamespace(process=process)
        finally:
            closed.append(process)

    monkeypatch.setattr(memory_worker, "worker_runtime", fake_runtime)
    event = {"Records": [{"messageId": "bad", "body": "invalid-json"}, {"messageId": "good", "body": '{"work_type":"refresh_working_memory","user_id":"synthetic","turn_count":2}'}]}
    for _ in range(2):
        assert memory_worker.handler(event, None) == {"batchItemFailures": [{"itemIdentifier": "bad"}]}
    assert closed == processors and len(processors) == 2
    for process in processors:
        process.assert_awaited_once()
