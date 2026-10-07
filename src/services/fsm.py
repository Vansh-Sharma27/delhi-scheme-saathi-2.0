"""Temporary catalog defaults for legacy FSM callers."""

from src.dss.application.conversation import fsm
from src.dss.application.conversation.fsm import FSMTransitionError as FSMTransitionError
from src.dss.application.conversation.fsm import can_transition as can_transition
from src.dss.application.conversation.fsm import (
    get_state_prompt_context as get_state_prompt_context,
)
from src.dss.application.conversation.fsm import get_valid_transitions as get_valid_transitions
from src.dss.application.conversation.fsm import transition as transition
from src.dss.application.conversation.profile_fields import ProfileFields
from src.dss.domain.conversations.states import ConversationState
from src.dss.domain.profiles.profile import UserProfile
from src.dss.infrastructure.database.catalog import _load_catalog

_fields = ProfileFields(lambda: _load_catalog().values())


def should_auto_match(profile: UserProfile) -> bool:
    return fsm.should_auto_match(profile, fields=_fields)


def determine_next_state(
    current_state: ConversationState,
    profile: UserProfile,
    intent: str,
    has_schemes: bool | None = None,
    selected_scheme_id: str | None = None,
    has_selected_scheme: bool = False,
    action: str | None = None,
    requested_state: ConversationState | None = None,
) -> ConversationState:
    return fsm.determine_next_state(
        current_state, profile, intent, has_schemes, selected_scheme_id,
        has_selected_scheme, action, requested_state, fields=_fields,
    )
