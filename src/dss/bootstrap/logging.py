"""Supply cached application credentials to settings-independent observability."""

from functools import lru_cache

from src.dss.observability.logging_config import configure_logging as configure_handlers
from src.dss.settings import get_settings


@lru_cache(maxsize=1)
def secret_values() -> tuple[str, ...]:
    """Read lazily; invalidate alongside get_settings when the environment changes."""
    settings = get_settings()
    candidates = (
        settings.telegram_bot_token,
        settings.telegram_webhook_secret,
        settings.chat_api_key,
        settings.xai_api_key,
        settings.jina_api_key,
        settings.voyage_api_key,
        settings.sarvam_api_key,
        settings.bhashini_api_key,
        settings.bhashini_ulca_api_key,
    )
    # Short secrets corrupt ordinary words; longer overlapping secrets go first.
    unique = {value for value in candidates if len(value) >= 8}
    return tuple(sorted(unique, key=len, reverse=True))


def configure_logging(level_name: str) -> int:
    return configure_handlers(level_name, secrets=secret_values)
