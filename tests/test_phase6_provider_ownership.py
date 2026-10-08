"""Provider construction is lazy and executor ownership is per runtime."""

from unittest.mock import AsyncMock, Mock

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
