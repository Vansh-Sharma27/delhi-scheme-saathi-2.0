"""Temporary language exports during caller migration."""

from src.dss.application.conversation.language import DEVANAGARI_FIRST as DEVANAGARI_FIRST
from src.dss.application.conversation.language import DEVANAGARI_LAST as DEVANAGARI_LAST
from src.dss.application.conversation.language import DEVANAGARI_THRESHOLD as DEVANAGARI_THRESHOLD
from src.dss.application.conversation.language import SUPPORTED_LANGUAGES as SUPPORTED_LANGUAGES
from src.dss.application.conversation.language import (
    command_response_language as command_response_language,
)
from src.dss.application.conversation.language import count_markers as count_markers
from src.dss.application.conversation.language import (
    detect_explicit_language_request as detect_explicit_language_request,
)
from src.dss.application.conversation.language import devanagari_ratio as devanagari_ratio
from src.dss.application.conversation.language import infer_text_language as infer_text_language
from src.dss.application.conversation.language import (
    looks_like_low_context_field_reply as looks_like_low_context_field_reply,
)
from src.dss.application.conversation.language import normalize_language as normalize_language
from src.dss.application.conversation.language import (
    preferred_turn_language as preferred_turn_language,
)
from src.dss.application.conversation.language import (
    prepend_death_in_family_empathy as prepend_death_in_family_empathy,
)
from src.dss.application.conversation.language import (
    response_conflicts_with_spouse_reference as response_conflicts_with_spouse_reference,
)
from src.dss.application.conversation.language import response_has_empathy as response_has_empathy
from src.dss.application.conversation.language import (
    should_preserve_unlocked_session_language as should_preserve_unlocked_session_language,
)
from src.dss.application.conversation.language import text_variant as text_variant
