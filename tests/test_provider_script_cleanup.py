"""Scripts own their constructed clients even when work or cleanup fails."""

from unittest.mock import AsyncMock

import pytest

from scripts import generate_embeddings, test_voice_integration
from src.dss.infrastructure.embeddings import fallback_client
from src.dss.settings import Settings


@pytest.mark.asyncio
@pytest.mark.parametrize("close_fails", [False, True])
async def test_embedding_script_closes_client_and_pool(monkeypatch, close_fails):
    import asyncpg
    import dotenv

    monkeypatch.setattr(dotenv, "load_dotenv", lambda: None)
    monkeypatch.setenv("DATABASE_URL", "postgresql://unused/test")
    monkeypatch.setenv("VOYAGE_API_KEY", "test-key")
    pool = AsyncMock()
    pool.fetch.side_effect = RuntimeError("fetch failed")
    client = AsyncMock()
    if close_fails:
        client.close.side_effect = RuntimeError("close failed")

    def build_client(settings):
        assert isinstance(settings, Settings)
        assert settings.voyage_api_key == "test-key"
        return client

    monkeypatch.setattr(asyncpg, "create_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(fallback_client, "FallbackEmbeddingClient", build_client)
    with pytest.raises(RuntimeError, match="close failed" if close_fails else "fetch failed"):
        await generate_embeddings.main()
    client.close.assert_awaited_once_with()
    pool.close.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_voice_script_closes_client_when_test_raises(monkeypatch):
    client = AsyncMock()
    monkeypatch.setattr(
        test_voice_integration, "test_voice_connection",
        AsyncMock(return_value=(client, "fake")),
    )
    monkeypatch.setattr(
        test_voice_integration, "test_language_detection",
        AsyncMock(side_effect=RuntimeError("voice failed")),
    )
    with pytest.raises(RuntimeError, match="voice failed"):
        await test_voice_integration.main()
    client.close.assert_awaited_once_with()
