"""Canonical logging construction preserves redaction without settings imports."""

import io
import logging
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.dss.bootstrap import logging as bootstrap_logging
from src.dss.bootstrap.logging import secret_values
from src.dss.observability.logging_config import RedactingFilter, install_redaction
from src.dss.settings import Settings, get_settings


def test_propagated_record_and_traceback_are_redacted() -> None:
    secret = "synthetic-long-token"
    output = io.StringIO()
    handler = logging.StreamHandler(output)
    install_redaction(handler, lambda: (secret,))
    install_redaction(handler, lambda: (secret,))
    assert len([f for f in handler.filters if isinstance(f, RedactingFilter)]) == 1
    parent = logging.getLogger("phase6-redaction")
    child = logging.getLogger("phase6-redaction.child")
    previous = parent.level
    parent.addHandler(handler)
    parent.setLevel(logging.ERROR)
    try:
        try:
            raise ValueError(f"url/{secret}")
        except ValueError:
            child.exception("Failed %s", secret)
        assert secret not in output.getvalue()
        assert output.getvalue().count("***REDACTED***") == 2
    finally:
        parent.removeHandler(handler)
        parent.setLevel(previous)


def test_secret_provider_is_lazy_cached_and_longest_first(monkeypatch) -> None:
    get_settings.cache_clear()
    secret_values.cache_clear()
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "synthetic-long-token")
    monkeypatch.setenv("CHAT_API_KEY", "synthetic-long")
    monkeypatch.setenv("SARVAM_API_KEY", "abc")
    try:
        first = secret_values()
        assert first.index("synthetic-long-token") < first.index("synthetic-long")
        assert "abc" not in first
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "replacement-token")
        get_settings.cache_clear()
        assert secret_values() is first
        secret_values.cache_clear()
        assert "replacement-token" in secret_values()
    finally:
        secret_values.cache_clear()
        get_settings.cache_clear()


@pytest.mark.asyncio
async def test_custom_app_settings_redact_constructor_logs_across_runtimes(monkeypatch) -> None:
    from src.dss.bootstrap import api

    global_settings = Settings.model_construct(telegram_bot_token="synthetic-global-token")
    first = Settings.model_construct(telegram_bot_token="synthetic-first-token")
    second = Settings.model_construct(telegram_bot_token="synthetic-second-token")
    monkeypatch.setattr(bootstrap_logging, "get_settings", lambda: global_settings)
    secret_values.cache_clear()
    assert secret_values() == (global_settings.telegram_bot_token,)
    output = io.StringIO()
    handler = logging.StreamHandler(output)
    root = logging.getLogger()
    previous_level = root.level
    monkeypatch.setattr(root, "handlers", [handler])
    logger = logging.getLogger("constructor-redaction.child")

    @asynccontextmanager
    async def fake_runtime(settings):
        try:
            raise ValueError(settings.telegram_bot_token)
        except ValueError:
            logger.exception("constructing %s", settings.telegram_bot_token)
        yield SimpleNamespace(dependencies=None, start_local_worker=AsyncMock())

    monkeypatch.setattr(api, "api_runtime", fake_runtime)
    try:
        first_app = api.create_app(first)
        second_app = api.create_app(second)
        async with (
            first_app.router.lifespan_context(first_app),
            second_app.router.lifespan_context(second_app),
        ):
            logger.error("older runtime still active: %s", first.telegram_bot_token)
        rendered = output.getvalue()
        assert first.telegram_bot_token not in rendered
        assert second.telegram_bot_token not in rendered
        assert rendered.count("***REDACTED***") == 5
        assert len([f for f in handler.filters if isinstance(f, RedactingFilter)]) == 1
    finally:
        root.setLevel(previous_level)
        secret_values.cache_clear()


def test_reconfiguration_replaces_provider_and_retains_flat_secret_union() -> None:
    handler = logging.StreamHandler()

    def first():
        return ("synthetic-overlap", "abc")

    def second():
        return ("synthetic-overlap-long", "synthetic-new-token")

    install_redaction(handler, first)
    installed = handler.filters[0]
    for _ in range(20):
        install_redaction(handler, second)
    assert handler.filters == [installed]
    assert isinstance(installed, RedactingFilter)
    assert installed.secrets is second
    record = logging.LogRecord(
        "test", logging.ERROR, __file__, 1,
        "abc %s %s %s", (first()[0], *second()), None,
    )
    record.exc_text = "cached exception: synthetic-overlap-long"
    installed.filter(record)
    assert record.getMessage() == "abc " + " ".join(["***REDACTED***"] * 3)
    assert record.exc_text == "cached exception: ***REDACTED***"
