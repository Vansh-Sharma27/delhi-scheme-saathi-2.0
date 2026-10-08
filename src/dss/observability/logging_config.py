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
        self._retained: set[str] = set()

    def update_secrets(self, secrets: SecretProvider) -> None:
        # ponytail: retain distinct old credentials for this handler's lifetime so
        # overlapping runtimes stay covered. No provider chains or runtime objects;
        # storage grows only with distinct rotations, reclaimed with the handler.
        self._retained.update(value for value in self.secrets() if len(value) >= 8)
        self.secrets = secrets

    def filter(self, record: logging.LogRecord) -> bool:
        secrets = tuple(sorted(
            self._retained | {value for value in self.secrets() if len(value) >= 8},
            key=len, reverse=True,
        ))
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
    """Attach once; refresh the provider without losing older runtime secrets."""
    for existing in handler.filters:
        if isinstance(existing, RedactingFilter):
            existing.update_secrets(secrets)
            break
    else:
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
