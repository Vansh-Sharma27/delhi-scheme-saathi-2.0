"""Tests for Telegram Bot API client helpers."""

from unittest.mock import AsyncMock

import pytest

from src.dss.infrastructure.telegram import DEFAULT_BOT_COMMANDS, TelegramClient
from src.dss.settings import Settings


class _FakeResponse:
    """Minimal HTTPX-like response for Telegram client tests."""

    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self) -> None:
        """Pretend the HTTP response was successful."""

    def json(self):
        """Return the fake Telegram payload."""
        return self._payload


@pytest.mark.asyncio
async def test_set_my_commands_posts_default_commands() -> None:
    """Default Telegram commands should be posted to setMyCommands."""
    client = TelegramClient(Settings(_env_file=None, telegram_bot_token="test-token"))

    real_http_client = client._client
    mock_http_client = AsyncMock()
    mock_http_client.post = AsyncMock(return_value=_FakeResponse({"ok": True, "result": True}))
    client._client = mock_http_client
    await real_http_client.aclose()

    result = await client.set_my_commands()

    assert result["ok"] is True
    mock_http_client.post.assert_awaited_once_with(
        "https://api.telegram.org/bottest-token/setMyCommands",
        json={"commands": DEFAULT_BOT_COMMANDS},
    )


@pytest.mark.asyncio
async def test_get_my_commands_uses_telegram_endpoint() -> None:
    """Fetching registered Telegram commands should hit getMyCommands."""
    client = TelegramClient(Settings(_env_file=None, telegram_bot_token="test-token"))

    real_http_client = client._client
    mock_http_client = AsyncMock()
    mock_http_client.get = AsyncMock(
        return_value=_FakeResponse(
            {"ok": True, "result": [{"command": "help", "description": "Learn"}]}
        )
    )
    client._client = mock_http_client
    await real_http_client.aclose()

    result = await client.get_my_commands()

    assert result["result"][0]["command"] == "help"
    mock_http_client.get.assert_awaited_once_with(
        "https://api.telegram.org/bottest-token/getMyCommands"
    )
