"""Tests for application startup behavior."""

import json
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from src.dss.application.conversation.contracts import ChatRequest, ChatResponse
from src.dss.application.ports.scheme_repository import SchemeRepository
from src.dss.application.ports.work_queue import AIWorkQueue
from src.dss.bootstrap import api, runtime
from src.dss.infrastructure.database.scheme_repo import get_scheme_debug_rows
from src.dss.infrastructure.queues.work_queue import InMemoryAIWorkQueue
from src.dss.interfaces.api.dependencies import APIDependencies
from src.dss.interfaces.api.http import HTTPRoutes
from src.dss.settings import CHAT_SESSION_PREFIX, Settings


class _FakeRequest:
    """Minimal stand-in exposing only what the chat endpoint reads."""

    def __init__(self, headers: dict[str, str] | None = None) -> None:
        self.headers = headers or {}


def _chat_dependencies(captured: dict[str, str], api_key: str = "") -> APIDependencies:
    async def chat(request: ChatRequest) -> ChatResponse:
        captured["user_id"] = request.user_id
        return ChatResponse(text="ok", next_state="GREETING")

    return APIDependencies(
        Settings(_env_file=None, chat_api_key=api_key),
        AsyncMock(spec=SchemeRepository), None, None, None, chat, AsyncMock(),
    )


@pytest.fixture
def owned_runtime(monkeypatch):
    """Exercise real resource ownership with network clients replaced at construction."""
    settings = Settings(
        _env_file=None, use_bedrock=False, session_table_name="dss-sessions",
        ai_memory_queue_enabled=True, ai_memory_queue_backend="in_memory",
        sarvam_api_key="", bhashini_api_key="", chat_api_key="",
    )
    connection = AsyncMock()
    connection.fetchval.return_value = 7
    connection.fetch.return_value = []
    pool = Mock()
    pool.acquire.return_value = _AcquireContext(connection)
    pool.close = AsyncMock()
    open_pool = AsyncMock(return_value=pool)
    monkeypatch.setattr(runtime, "open_pool", open_pool)
    queue = InMemoryAIWorkQueue()
    monkeypatch.setattr(queue, "close", AsyncMock())
    build_queue = Mock(return_value=queue)
    monkeypatch.setattr(runtime, "build_work_queue", build_queue)
    clients = []
    for name in ("FallbackLLMClient", "FallbackEmbeddingClient", "SarvamClient", "TelegramClient"):
        client = AsyncMock()
        clients.append(client)
        monkeypatch.setattr(runtime, name, Mock(return_value=client))
    monkeypatch.setattr(runtime, "build_ai", Mock(return_value=AsyncMock()))
    monkeypatch.setattr(runtime, "build_conversation", Mock(return_value=SimpleNamespace(
        handle_message=AsyncMock(return_value=ChatResponse(text="ok")),
    )))
    graphs = []

    @asynccontextmanager
    async def capture_runtime(settings):
        async with runtime.api_runtime(settings) as graph:
            graphs.append(graph)
            yield graph

    monkeypatch.setattr(api, "api_runtime", capture_runtime)
    monkeypatch.setattr(api, "configure_logging", Mock())
    return SimpleNamespace(
        settings=settings, pool=pool, open_pool=open_pool, queue=queue,
        build_queue=build_queue, clients=clients, graphs=graphs,
    )


class _FakeConn:
    def __init__(self, rows):
        self._rows = rows

    async def fetch(self, query, scheme_ids):  # type: ignore[no-untyped-def]
        return self._rows


class _AcquireContext:
    def __init__(self, conn):
        self._conn = conn

    async def __aenter__(self):
        return self._conn

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _FakePool:
    def __init__(self, rows):
        self._rows = rows

    def acquire(self):
        return _AcquireContext(_FakeConn(self._rows))


@pytest.mark.asyncio
async def test_get_scheme_debug_rows_handles_partial_rows() -> None:
    """Debug-row verification should work on lightweight SELECT payloads."""
    pool = _FakePool(
        [
            {
                "id": "SCH-DELHI-001",
                "name": "PMAY-U 2.0",
                "life_events": ["HOUSING"],
                "eligibility": {
                    "categories": ["EWS", "LIG", "MIG"],
                    "income_by_category": {
                        "EWS": 300000,
                        "LIG": 600000,
                        "MIG": 900000,
                    },
                },
            }
        ]
    )

    rows = await get_scheme_debug_rows(pool, ["SCH-DELHI-001"])

    assert rows == [
        {
            "id": "SCH-DELHI-001",
            "name": "PMAY-U 2.0",
            "life_events": ["HOUSING"],
            "canonical_life_events": ["CHILDBIRTH", "HOUSING", "MARRIAGE"],
            "life_events_match": False,
            "raw_categories": ["EWS", "LIG", "MIG"],
            "caste_categories": [],
            "income_segments": ["EWS", "LIG", "MIG"],
            "income_by_category": {
                "EWS": 300000,
                "LIG": 600000,
                "MIG": 900000,
            },
        }
    ]


@pytest.mark.asyncio
async def test_get_scheme_debug_rows_handles_stringified_eligibility() -> None:
    """Debug-row verification should accept JSON-string eligibility payloads."""
    pool = _FakePool(
        [
            {
                "id": "SCH-DELHI-006",
                "name": "Education Loan Scheme - Delhi",
                "life_events": ["EDUCATION"],
                "eligibility": json.dumps(
                    {
                        "categories": ["SC", "ST", "OBC"],
                        "max_income": 800000,
                    }
                ),
            }
        ]
    )

    rows = await get_scheme_debug_rows(pool, ["SCH-DELHI-006"])

    assert rows == [
        {
            "id": "SCH-DELHI-006",
            "name": "Education Loan Scheme - Delhi",
            "life_events": ["EDUCATION"],
            "canonical_life_events": ["EDUCATION"],
            "life_events_match": True,
            "raw_categories": ["SC", "ST", "OBC"],
            "caste_categories": ["SC", "ST", "OBC"],
            "income_segments": [],
            "income_by_category": {},
        }
    ]


@pytest.mark.asyncio
async def test_lifespan_keeps_db_pool_when_verification_logging_fails(owned_runtime) -> None:
    """Startup verification failures should not mark the database as disconnected."""
    resources = owned_runtime
    app = api.create_app(resources.settings)
    routes = next(route.endpoint.__self__ for route in app.routes if route.path == "/health")
    with patch.object(
        runtime.PostgresSchemeRepository, "get_scheme_debug_rows",
        AsyncMock(side_effect=KeyError("name_hindi")),
    ) as verify:
        async with app.router.lifespan_context(app):
            graph = resources.graphs[0]
            assert graph.dependencies.schemes._pool is resources.pool
            assert await routes.health_check() == {
                "status": "ok", "database": "connected", "schemes_count": 7,
            }
            assert graph.worker is not None
            task = graph.worker._task
            assert task is not None
            resources.pool.close.assert_not_awaited()

    verify.assert_awaited_once_with(["SCH-DELHI-001", "SCH-DELHI-006"])
    resources.open_pool.assert_awaited_once_with(resources.settings)
    resources.build_queue.assert_called_once_with(resources.settings)
    assert task.cancelled()
    assert graph.worker._task is None
    with pytest.raises(RuntimeError, match="API lifespan has not started"):
        _ = routes.dependencies
    resources.pool.close.assert_awaited_once()
    resources.queue.close.assert_awaited_once()
    for client in resources.clients:
        client.close.assert_awaited_once()


def test_lifespan_handles_pool_initialization_failure(owned_runtime) -> None:
    resources = owned_runtime
    resources.open_pool.side_effect = OSError("database unavailable")
    with TestClient(api.create_app(resources.settings)) as client:
        health = client.get("/health")
        assert health.status_code == 200
        assert health.json() == {
            "status": "ok", "database": "disconnected", "schemes_count": 0,
        }
        response = client.post("/api/chat", json={"message": "Namaste"})
        assert response.status_code == 503
        assert response.json() == {"detail": "Database connection not available"}
        graph = resources.graphs[0]
        assert graph.dependencies.schemes is None
        assert graph.worker is not None
        task = graph.worker._task
        assert task is not None

    resources.open_pool.assert_awaited_once_with(resources.settings)
    resources.pool.close.assert_not_awaited()
    assert task.cancelled()
    assert graph.worker._task is None
    resources.queue.close.assert_awaited_once()
    for client in resources.clients:
        client.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_configure_ai_background_runtime_starts_in_memory_worker(owned_runtime) -> None:
    """Local in-memory queue should start the in-process worker."""
    resources = owned_runtime
    async with runtime.api_runtime(resources.settings) as graph:
        assert graph.queue is resources.queue
        assert graph.memory.queue is resources.queue
        assert graph.worker is None
        await graph.start_local_worker()
        assert graph.worker is not None
        assert graph.worker.queue is resources.queue
        task = graph.worker._task
        assert task is not None
        assert not task.done()
        await graph.start_local_worker()
        assert graph.worker._task is task

    resources.build_queue.assert_called_once_with(resources.settings)
    assert task.cancelled()
    assert graph.worker._task is None
    resources.queue.close.assert_awaited_once()
    resources.pool.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_configure_ai_background_runtime_skips_worker_for_external_queue(owned_runtime) -> None:
    """Shared queues like SQS should not start an in-process poller in the web app."""
    resources = owned_runtime
    external_queue = AsyncMock(spec=AIWorkQueue)
    resources.build_queue.return_value = external_queue
    with patch.object(runtime, "LocalMemoryWorker") as worker:
        async with runtime.api_runtime(resources.settings) as graph:
            assert graph.queue is external_queue
            assert graph.memory.queue is external_queue
            await graph.start_local_worker()
            assert graph.worker is None
        worker.assert_not_called()

    resources.build_queue.assert_called_once_with(resources.settings)
    external_queue.close.assert_awaited_once()
    resources.pool.close.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("user_id", "expected"),
    [
        ("780045592", "api:780045592"),
        ("api:780045592", "api:api:780045592"),
        ("x" * 80, "api:" + "x" * 64),
    ],
)
async def test_chat_endpoint_namespaces_caller_supplied_user_id(
    user_id: str, expected: str
) -> None:
    """Always prefix after truncation, including already-prefixed caller IDs."""
    captured: dict[str, str] = {}

    routes = HTTPRoutes(_chat_dependencies(captured))
    await routes.chat_endpoint(
        {"user_id": user_id, "message": "Namaste"}, _FakeRequest()
    )

    assert captured["user_id"] != user_id
    assert captured["user_id"] == expected


@pytest.mark.asyncio
async def test_chat_endpoint_rejects_wrong_api_key() -> None:
    """With CHAT_API_KEY set, a bad or missing header must not reach the service."""
    captured: dict[str, str] = {}

    routes = HTTPRoutes(_chat_dependencies(captured, "expected-key"))
    for headers in ({}, {"X-API-Key": "wrong-key"}):
        with pytest.raises(HTTPException) as excinfo:
            await routes.chat_endpoint(
                {"user_id": "tester", "message": "Namaste"}, _FakeRequest(headers)
            )
        assert excinfo.value.status_code == 403

    assert captured == {}


@pytest.mark.asyncio
async def test_chat_endpoint_accepts_correct_api_key() -> None:
    """The matching header still gets through to the conversation service."""
    captured: dict[str, str] = {}

    routes = HTTPRoutes(_chat_dependencies(captured, "expected-key"))
    result = await routes.chat_endpoint(
        {"user_id": "tester", "message": "Namaste"},
        _FakeRequest({"X-API-Key": "expected-key"}),
    )

    assert result["response"] == "ok"
    assert captured["user_id"] == f"{CHAT_SESSION_PREFIX}tester"


def test_chat_route_binds_body_and_namespaces_over_http(monkeypatch) -> None:
    """Cover the routed path, not just a direct call.

    The endpoint takes both a JSON body and the Request object; a signature
    change can keep direct calls working while breaking FastAPI's body binding.
    """
    captured: dict[str, str] = {}
    dependencies = _chat_dependencies(captured)
    start_worker = AsyncMock()

    @asynccontextmanager
    async def fake_runtime(settings):
        assert settings is dependencies.settings
        yield SimpleNamespace(dependencies=dependencies, start_local_worker=start_worker)

    monkeypatch.setattr(api, "api_runtime", fake_runtime)
    monkeypatch.setattr(api, "configure_logging", Mock())
    with TestClient(api.create_app(dependencies.settings)) as client:
        response = client.post(
            "/api/chat", json={"user_id": "780045592", "message": "Namaste"}
        )

    assert response.status_code == 200
    assert response.json()["response"] == "ok"
    assert response.json() == {
        "response": "ok", "next_state": "GREETING", "schemes": [],
        "documents": [], "rejection_warnings": [],
    }
    assert captured["user_id"] == "api:780045592"
    start_worker.assert_awaited_once()


@pytest.mark.parametrize(
    ("configured", "allowed_origin"),
    [("", "http://localhost:3000"), (" https://example.test, ", "https://example.test")],
)
def test_create_app_cors_policy(configured: str, allowed_origin: str) -> None:
    settings = Settings(_env_file=None, cors_allowed_origins=configured)
    client = TestClient(api.create_app(settings))
    response = client.options("/api/chat", headers={
        "Origin": allowed_origin,
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "Content-Type, Authorization",
    })
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == allowed_origin
    assert response.headers["access-control-allow-methods"] == "GET, POST"
    assert "access-control-allow-credentials" not in response.headers
    allowed_headers = response.headers["access-control-allow-headers"].lower()
    assert "content-type" in allowed_headers
    assert "authorization" in allowed_headers
    rejected = client.options("/api/chat", headers={
        "Origin": "https://untrusted.test",
        "Access-Control-Request-Method": "POST",
    })
    assert rejected.status_code == 400
    assert "access-control-allow-origin" not in rejected.headers
