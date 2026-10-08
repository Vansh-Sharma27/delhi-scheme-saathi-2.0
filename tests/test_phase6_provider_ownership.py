"""Provider construction is lazy and executor ownership is per runtime."""

import asyncio
from threading import Event, Thread
from unittest.mock import AsyncMock, Mock

import pytest

from src.dss.application.conversation.ai_orchestrator import (
    AIExecutionPolicy,
    AIOrchestrator,
    AITaskType,
)
from src.dss.infrastructure.ai.bedrock_client import BedrockLLMClient
from src.dss.infrastructure.ai.fallback_client import FallbackLLMClient
from src.dss.settings import Settings


async def test_composite_constructs_only_used_provider_and_closes_owned_clients() -> None:
    bedrock, grok = AsyncMock(), AsyncMock()
    bedrock.analyze_message.side_effect = RuntimeError("synthetic")
    grok.analyze_message.return_value = {"intent": "question"}
    build_bedrock, build_grok = Mock(return_value=bedrock), Mock(return_value=grok)
    client = FallbackLLMClient(
        Settings(_env_file=None, use_bedrock=True, xai_api_key="synthetic"),
        bedrock=build_bedrock, grok=build_grok,
    )
    build_bedrock.assert_not_called()
    build_grok.assert_not_called()
    result = await client.analyze_message_with_meta("housing", [], "GREETING", {}, "synthetic")
    assert result.output == {"intent": "question"}
    assert result.provider == "grok" and result.fallback_used
    await client.close()
    build_bedrock.assert_called_once()
    build_grok.assert_called_once()
    bedrock.close.assert_awaited_once()
    grok.close.assert_awaited_once()


async def test_bedrock_executors_are_instance_owned_and_keep_concurrency(monkeypatch) -> None:
    factory = Mock(return_value=Mock())
    monkeypatch.setattr("boto3.client", factory)
    settings = Settings(_env_file=None, ai_inline_concurrency=3, ai_background_concurrency=2)
    first, second = BedrockLLMClient(settings), BedrockLLMClient(settings)
    factory.assert_not_called()
    inline = first._executor("inline")
    background = first._executor("background")
    assert inline._max_workers == 3 and background._max_workers == 2
    assert inline is first._executor("inline")
    assert inline is not second._executor("inline")
    await first.close()
    await second.close()
    assert inline._shutdown and background._shutdown


@pytest.mark.parametrize("block_construction", [False, True])
@pytest.mark.parametrize("priority", ["inline", "background"])
def test_bedrock_timeout_and_runner_exit_do_not_wait_for_worker(
    monkeypatch, block_construction, priority,
) -> None:
    started, release, closed, returned = Event(), Event(), Event(), Event()
    failures = []
    calls = []
    settings = Settings(
        _env_file=None, use_bedrock=True, xai_api_key="",
        ai_inline_concurrency=1, ai_background_concurrency=1,
    )
    bedrock = BedrockLLMClient(settings)
    other = BedrockLLMClient(settings)

    def block():
        started.set()
        assert release.wait(5), "test must release the worker in finally"

    def converse(**kwargs):
        calls.append("converse")
        if not block_construction:
            block()
        return {"output": {"message": {"content": [{"text": "late response"}]}}}

    def close_runtime():
        assert release.is_set(), "client closed while worker was using it"
        closed.set()

    runtime = Mock(converse=Mock(side_effect=converse), close=Mock(side_effect=close_runtime))

    def build_runtime(*args, **kwargs):
        if block_construction:
            block()
        return runtime

    factory = Mock(side_effect=build_runtime)
    monkeypatch.setattr("boto3.client", factory)
    composite = FallbackLLMClient(settings, bedrock=lambda: bedrock)
    ai = AIOrchestrator(
        composite,
        settings=settings,
        safe_analysis=lambda language: {},
        safe_relevance=lambda candidates: {},
        safe_generation=lambda language: "safe fallback",
        policies={
            AITaskType.GENERATE_RESPONSE: AIExecutionPolicy(
                timeout_seconds=0.2, priority=priority,
            ),
        },
    )

    async def invoke():
        result = await ai._run_task(
            task_type=AITaskType.GENERATE_RESPONSE,
            session_id=None,
            prompt_chars=0,
            call=lambda task_priority: composite.generate_response_with_meta(
                {}, "test", priority=task_priority,
            ),
            safe_output=lambda: "safe fallback",
        )
        assert result == "safe fallback"
        assert started.is_set() and not release.is_set()
        queued_call = Mock()
        queued = asyncio.create_task(bedrock._run(priority, queued_call))
        await asyncio.sleep(0)
        await composite.close()
        await composite.close()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(queued, timeout=0.5)
        queued_call.assert_not_called()
        assert not closed.is_set()
        for next_priority in ("inline", "background"):
            with pytest.raises(RuntimeError, match="closed"):
                await bedrock.generate_response({}, "test", priority=next_priority)
        # Closing one owner does not shut down another owner's executor.
        assert await other._run("inline", lambda: "independent") == "independent"
        await other.close()

    def invocation_thread():
        try:
            with asyncio.Runner() as runner:
                runner.run(invoke())
        except BaseException as exc:
            failures.append(exc)
        finally:
            returned.set()

    thread = Thread(target=invocation_thread, daemon=True)
    thread.start()
    try:
        assert started.wait(2), "worker did not start"
        assert returned.wait(2), "close or Runner exit waited for blocked boto3"
        assert not failures
        assert not closed.is_set()
    finally:
        release.set()
        thread.join(timeout=3)
        # Also clean up when an assertion fails before invoke reaches close.
        asyncio.run(composite.close())
        asyncio.run(other.close())
        assert closed.wait(3), "deferred client cleanup never completed"
    assert not thread.is_alive()
    assert calls == ["converse"]
    factory.assert_called_once()
    runtime.close.assert_called_once()


async def test_bedrock_idle_close_is_synchronous_and_terminal(monkeypatch) -> None:
    factory = Mock()
    monkeypatch.setattr("boto3.client", factory)
    client = BedrockLLMClient(Settings(_env_file=None))
    await client.close()
    factory.assert_not_called()
    with pytest.raises(RuntimeError, match="closed"):
        await client.generate_response({}, "test")
    factory.assert_not_called()

    used = BedrockLLMClient(Settings(_env_file=None))
    runtime = Mock()
    used._client = runtime
    assert await used._run("inline", lambda: "done") == "done"
    await used.close()
    runtime.close.assert_called_once()
    assert used._client is None and not used._executors
    await used.close()
    runtime.close.assert_called_once()
