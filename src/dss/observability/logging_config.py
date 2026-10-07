"""Handler-attached credential redaction with an injected secret provider."""

from __future__ import annotations

import logging
from collections.abc import Callable

LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
REDACTED = "***REDACTED***"
SecretProvider = Callable[[], tuple[str, ...]]


def redact(text: str, secrets: tuple[str, ...]) -> str:
    """Replace supplied secrets, already ordered longest first."""
    for secret in secrets:
        text = text.replace(secret, REDACTED)
    return text


class RedactingFilter(logging.Filter):
    """Redact interpolated messages and exception text before handler emission."""

    def __init__(self, secrets: SecretProvider) -> None:
        super().__init__()
        self.secrets = secrets

    def filter(self, record: logging.LogRecord) -> bool:
        secrets = self.secrets()
        if not secrets:
            return True
        message = record.getMessage()
        redacted = redact(message, secrets)
        if redacted != message:
            record.msg = redacted
            record.args = ()
        if record.exc_info and not record.exc_text:
            record.exc_text = logging.Formatter().formatException(record.exc_info)
        if record.exc_text:
            record.exc_text = redact(record.exc_text, secrets)
        return True


def install_redaction(handler: logging.Handler, secrets: SecretProvider) -> None:
    """Attach once to the handler so propagated module records are filtered."""
    if not any(isinstance(existing, RedactingFilter) for existing in handler.filters):
        handler.addFilter(RedactingFilter(secrets))


def configure_logging(level_name: str, *, secrets: SecretProvider) -> int:
    """Configure existing Lambda handlers as well as newly installed handlers."""
    level = getattr(logging, level_name.upper(), logging.INFO)
    logging.basicConfig(level=level, format=LOG_FORMAT)
    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    formatter = logging.Formatter(LOG_FORMAT)
    for handler in root_logger.handlers:
        handler.setLevel(level)
        if handler.formatter is None:
            handler.setFormatter(formatter)
        install_redaction(handler, secrets)
    return level
