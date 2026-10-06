"""Live compatibility alias for the Telegram interface until Phase 6."""

import sys

from src.config import get_settings
from src.dss.infrastructure.speech.bhashini import get_bhashini_client
from src.dss.interfaces.telegram import handler as _implementation
from src.integrations.telegram import get_telegram_client
from src.services import session_manager
from src.services.conversation import ConversationService, language

_implementation.get_settings = get_settings
_implementation.get_telegram_client = get_telegram_client
_implementation.ConversationService = ConversationService
_implementation.session_manager = session_manager
_implementation.language = language
_implementation.get_bhashini_client = get_bhashini_client
sys.modules[__name__] = _implementation
