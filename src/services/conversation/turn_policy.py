"""Temporary catalog defaults for legacy turn-policy callers."""

from src.dss.application.conversation import turn_policy
from src.dss.application.conversation.profile_fields import ProfileFields
from src.dss.application.conversation.turn_policy import (
    MATCH_RELEVANT_FIELDS as MATCH_RELEVANT_FIELDS,
)
from src.dss.application.conversation.turn_policy import (
    SCHEME_CONTEXT_ACTIONS as SCHEME_CONTEXT_ACTIONS,
)
from src.dss.application.conversation.turn_policy import (
    build_matching_focus_text as build_matching_focus_text,
)
from src.dss.application.conversation.turn_policy import (
    collection_state_for_profile as collection_state_for_profile,
)
from src.dss.application.conversation.turn_policy import (
    contextual_field_value as contextual_field_value,
)
from src.dss.application.conversation.turn_policy import (
    is_low_context_matching_turn as is_low_context_matching_turn,
)
from src.dss.application.conversation.turn_policy import (
    matching_field_changes as matching_field_changes,
)
from src.dss.application.conversation.turn_policy import (
    requested_scheme_view as requested_scheme_view,
)
from src.dss.application.conversation.turn_policy import (
    sanitize_extracted_fields as sanitize_extracted_fields,
)
from src.dss.application.conversation.turn_policy import (
    should_answer_scheme_question as should_answer_scheme_question,
)
from src.dss.application.conversation.turn_policy import (
    should_preserve_scheme_context_action as should_preserve_scheme_context_action,
)
from src.dss.application.conversation.turn_policy import (
    should_update_life_event as should_update_life_event,
)
from src.dss.domain.conversations.session import Session
from src.dss.domain.conversations.states import ConversationState
from src.dss.domain.profiles.profile import UserProfile
from src.dss.infrastructure.database.catalog import _load_catalog

_fields = ProfileFields(lambda: _load_catalog().values())


def should_refresh_matches_after_profile_change(
    *, session: Session, profile: UserProfile, matching_inputs_changed: bool,
    action: str | None, requested_state: ConversationState | None,
) -> bool:
    return turn_policy.should_refresh_matches_after_profile_change(
        session=session, profile=profile, matching_inputs_changed=matching_inputs_changed,
        action=action, requested_state=requested_state, fields=_fields,
    )
