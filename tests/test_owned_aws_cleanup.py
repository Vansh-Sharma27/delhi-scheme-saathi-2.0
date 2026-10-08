"""Owned SDK clients are released without making AWS requests."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, call

import pytest

from src.dss.bootstrap import runtime, sessions
from src.dss.infrastructure.queues.work_queue import SQSAIWorkQueue
from src.dss.infrastructure.sessions.session_store import DynamoDBSessionStore, InMemorySessionStore
from src.dss.settings import Settings


@pytest.fixture
def sdk(monkeypatch):
    dynamodb = Mock(spec=["close"])
    sqs = Mock(spec=["close"])
    resource = Mock(spec=["Table", "meta"])
    resource.meta = SimpleNamespace(client=dynamodb)
    resource_factory = Mock(return_value=resource)
    client_factory = Mock(return_value=sqs)
    monkeypatch.setattr("boto3.resource", resource_factory)
    monkeypatch.setattr("boto3.client", client_factory)
    return SimpleNamespace(
        dynamodb=dynamodb, sqs=sqs, resource=resource,
        resource_factory=resource_factory, client_factory=client_factory,
    )


@pytest.mark.parametrize("close_fails", [False, True])
async def test_adapters_close_owned_clients_once(sdk, close_fails):
    store = DynamoDBSessionStore("synthetic", region="ap-south-1")
    queue = SQSAIWorkQueue("synthetic-queue", "ap-south-1")
    sdk.resource_factory.assert_called_once_with("dynamodb", region_name="ap-south-1")
    sdk.client_factory.assert_called_once_with("sqs", region_name="ap-south-1")
    if close_fails:
        sdk.dynamodb.close.side_effect = OSError("close failed")
        sdk.sqs.close.side_effect = OSError("close failed")
        with pytest.raises(OSError, match="close failed"):
            store.close()
        with pytest.raises(OSError, match="close failed"):
            await queue.close()
    else:
        store.close()
        await queue.close()
    store.close()
    await queue.close()
    assert sdk.dynamodb.mock_calls == [call.close()]
    assert sdk.sqs.mock_calls == [call.close()]
    assert sdk.resource.mock_calls == [call.Table("synthetic")]


@pytest.mark.parametrize("close_fails", [False, True])
def test_table_construction_failure_closes_client_and_preserves_error(sdk, close_fails):
    error = RuntimeError("table construction failed")
    sdk.resource.Table.side_effect = error
    if close_fails:
        sdk.dynamodb.close.side_effect = OSError("close failed")
    with pytest.raises(RuntimeError) as caught:
        DynamoDBSessionStore("synthetic")
    assert caught.value is error
    sdk.dynamodb.close.assert_called_once_with()


@pytest.mark.parametrize("worker", [False, True])
def test_store_construction_failure_preserves_fallback_policy(sdk, worker):
    error = RuntimeError("table construction failed")
    sdk.resource.Table.side_effect = error
    settings = Settings(_env_file=None, session_table_name="synthetic", use_bedrock=False)
    if worker:
        with pytest.raises(RuntimeError) as caught:
            sessions.build_worker_session_store(settings)
        assert caught.value is error
    else:
        assert isinstance(sessions.build_session_store(settings), InMemorySessionStore)
    sdk.dynamodb.close.assert_called_once_with()


@pytest.mark.parametrize(
    ("kind", "failure"),
    [
        ("api", None), ("api", "body"), ("api", "queue"), ("api", "llm"),
        ("worker", None), ("worker", "body"), ("worker", "llm"),
    ],
)
async def test_runtime_releases_sdk_clients_on_exit_and_partial_construction(
    monkeypatch, sdk, kind, failure,
):
    settings = Settings(
        _env_file=None, session_table_name="synthetic", use_bedrock=False,
        ai_memory_queue_enabled=True, ai_memory_queue_backend="sqs",
        ai_memory_queue_url="synthetic-queue", sarvam_api_key="", bhashini_api_key="",
    )
    # Keep real store/queue builders and adapters; replace unrelated resources.
    monkeypatch.setattr(runtime, "open_pool", AsyncMock(side_effect=OSError("no database")))
    for name in ("FallbackLLMClient", "FallbackEmbeddingClient", "SarvamClient", "TelegramClient"):
        monkeypatch.setattr(runtime, name, Mock(return_value=AsyncMock()))
    monkeypatch.setattr(runtime, "build_ai", Mock(return_value=Mock()))
    error = RuntimeError("synthetic failure")
    if failure == "queue":
        sdk.client_factory.side_effect = error
    elif failure == "llm":
        monkeypatch.setattr(runtime, "FallbackLLMClient", Mock(side_effect=error))

    async def enter_runtime():
        factory = runtime.api_runtime if kind == "api" else runtime.worker_runtime
        async with factory(settings):
            sdk.dynamodb.close.assert_not_called()
            sdk.sqs.close.assert_not_called()
            if failure == "body":
                raise error

    if failure:
        with pytest.raises(RuntimeError) as caught:
            await enter_runtime()
        assert caught.value is error
    else:
        await enter_runtime()
    assert sdk.dynamodb.mock_calls == [call.close()]
    expected_sqs_calls = [call.close()] if kind == "api" and failure != "queue" else []
    assert sdk.sqs.mock_calls == expected_sqs_calls
    assert sdk.resource.mock_calls == [call.Table("synthetic")]


async def test_queue_cleanup_failure_still_closes_store(monkeypatch, sdk):
    settings = Settings(
        _env_file=None, session_table_name="synthetic", use_bedrock=False,
        ai_memory_queue_enabled=True, ai_memory_queue_backend="sqs",
        ai_memory_queue_url="synthetic-queue",
    )
    monkeypatch.setattr(runtime, "open_pool", AsyncMock(side_effect=OSError("no database")))
    monkeypatch.setattr(runtime, "FallbackLLMClient", Mock(side_effect=RuntimeError("construction")))
    sdk.sqs.close.side_effect = OSError("queue cleanup")
    with pytest.raises(OSError, match="queue cleanup"):
        async with runtime.api_runtime(settings):
            pytest.fail("construction should fail")
    sdk.sqs.close.assert_called_once_with()
    sdk.dynamodb.close.assert_called_once_with()
