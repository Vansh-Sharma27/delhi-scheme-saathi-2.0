"""Live compatibility alias for the Telegram interface until Phase 6."""

import sys

from src.dss.application.ports.speech import SpeechProvider
from src.dss.infrastructure.speech.bhashini import get_bhashini_client
from src.dss.infrastructure.speech.sarvam import get_sarvam_client
from src.dss.interfaces.telegram import handler as _implementation
from src.dss.settings import get_settings
from src.integrations.telegram import get_telegram_client
from src.services import session_manager
from src.services.conversation import ConversationService, language

_implementation.get_settings = get_settings
_implementation.get_telegram_client = get_telegram_client
_implementation.ConversationService = ConversationService
_implementation.session_manager = session_manager
_implementation.language = language
_implementation.get_bhashini_client = get_bhashini_client
_implementation.get_sarvam_client = get_sarvam_client


def _select_voice_client() -> SpeechProvider:
    """Retain provider selection in legacy wiring until Phase 6."""
    settings = _implementation.get_settings()
    if settings.sarvam_api_key:
        return _implementation.get_sarvam_client()
    if settings.bhashini_api_key:
        return _implementation.get_bhashini_client()
    return _implementation.get_sarvam_client()


_implementation._get_voice_client = _select_voice_client
sys.modules[__name__] = _implementation
