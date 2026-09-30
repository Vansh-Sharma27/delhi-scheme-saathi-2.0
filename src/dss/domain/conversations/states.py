"""Conversation vocabulary, including persisted legacy aliases."""

from enum import Enum


# Not StrEnum: str(state) must keep the "ConversationState.X" form, and the
# legacy aliases below rely on plain Enum value aliasing.
class ConversationState(str, Enum):  # noqa: UP042
    """FSM states for the explicit 10-state conversation flow."""

    GREETING = "GREETING"
    SITUATION_UNDERSTANDING = "SITUATION_UNDERSTANDING"
    PROFILE_COLLECTION = "PROFILE_COLLECTION"
    SCHEME_MATCHING = "SCHEME_MATCHING"
    SCHEME_PRESENTATION = "SCHEME_PRESENTATION"
    SCHEME_DETAILS = "SCHEME_DETAILS"
    DOCUMENT_GUIDANCE = "DOCUMENT_GUIDANCE"
    REJECTION_WARNINGS = "REJECTION_WARNINGS"
    APPLICATION_HELP = "APPLICATION_HELP"
    CSC_HANDOFF = "CSC_HANDOFF"

    # Legacy aliases retained for compatibility with older code paths/tests.
    UNDERSTANDING = "PROFILE_COLLECTION"
    MATCHING = "SCHEME_MATCHING"
    PRESENTING = "SCHEME_PRESENTATION"
    DETAILS = "SCHEME_DETAILS"
    APPLICATION = "APPLICATION_HELP"
    HANDOFF = "CSC_HANDOFF"
