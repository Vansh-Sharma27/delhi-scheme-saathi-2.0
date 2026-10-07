"""Canonical logging construction preserves redaction without settings imports."""

import io
import logging

from src.dss.bootstrap.logging import secret_values
from src.dss.observability.logging_config import RedactingFilter, install_redaction
from src.dss.settings import get_settings


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
