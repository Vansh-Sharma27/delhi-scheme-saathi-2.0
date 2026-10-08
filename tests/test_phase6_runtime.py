"""Runtime ownership is explicit and partial construction releases resources."""

from unittest.mock import AsyncMock, Mock

import pytest

from src.dss.bootstrap import runtime
from src.dss.settings import Settings


async def test_api_runtime_does_not_start_worker_until_container_requests_it(monkeypatch) -> None:
    pool = AsyncMock()
    monkeypatch.setattr(runtime, "open_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(runtime, "verify_scheme_rows", AsyncMock())
    settings = Settings(_env_file=None, use_bedrock=False, session_table_name="dss-sessions", xai_api_key="")
    async with runtime.api_runtime(settings) as graph:
        assert graph.worker is None
        assert graph.memory.store is not None
        await graph.start_local_worker()
        task = graph.worker._task
        assert task is not None
        await graph.start_local_worker()
        assert graph.worker._task is task
    assert task.cancelled()
    pool.close.assert_awaited_once()


async def test_api_partial_construction_closes_open_pool(monkeypatch) -> None:
    pool = AsyncMock()
    monkeypatch.setattr(runtime, "open_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(runtime, "verify_scheme_rows", AsyncMock())
    monkeypatch.setattr(runtime, "build_session_store", Mock(side_effect=RuntimeError("synthetic")))
    with pytest.raises(RuntimeError, match="synthetic"):
        async with runtime.api_runtime(Settings(_env_file=None)):
            pytest.fail("construction should fail")
    pool.close.assert_awaited_once()


async def test_worker_runtime_avoids_pool_and_creates_fresh_ai_per_invocation(monkeypatch) -> None:
    pool = AsyncMock(side_effect=AssertionError("worker cannot open API pool"))
    monkeypatch.setattr(runtime, "open_pool", pool)
    monkeypatch.setattr(runtime, "build_worker_session_store", Mock(return_value=AsyncMock()))
    settings = Settings(_env_file=None)
    async with runtime.worker_runtime(settings) as first:
        first_ai = first.ai
        assert first.queue is None
    async with runtime.worker_runtime(settings) as second:
        assert second.ai is not first_ai
    pool.assert_not_called()
