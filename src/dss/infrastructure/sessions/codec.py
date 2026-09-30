"""Session persistence repair and deserialization."""

from datetime import UTC, datetime
from typing import Any, TypeVar

from src.dss.domain.conversations.clock import Clock
from src.dss.domain.conversations.session import ConversationMemory, Message, Session
from src.dss.domain.conversations.states import ConversationState
from src.dss.domain.profiles.profile import UserProfile

SessionType = TypeVar("SessionType", bound=Session)


def _normalize_persisted_state(
    raw_state: str | ConversationState | None,
    user_profile: dict[str, Any],
) -> ConversationState:
    """Map legacy persisted state values to the current 10-state FSM."""
    if isinstance(raw_state, ConversationState):
        return raw_state
    state_value = str(raw_state or ConversationState.GREETING.value)
    if state_value in ConversationState._value2member_map_:
        return ConversationState(state_value)
    legacy_map = {
        "MATCHING": ConversationState.SCHEME_MATCHING,
        "PRESENTING": ConversationState.SCHEME_PRESENTATION,
        "DETAILS": ConversationState.SCHEME_DETAILS,
        "APPLICATION": ConversationState.APPLICATION_HELP,
        "HANDOFF": ConversationState.CSC_HANDOFF,
    }
    if state_value == "UNDERSTANDING":
        return (
            ConversationState.PROFILE_COLLECTION
            if user_profile.get("life_event")
            else ConversationState.SITUATION_UNDERSTANDING
        )
    return legacy_map.get(state_value, ConversationState.GREETING)


def session_from_item(
    cls: type[SessionType], item: dict[str, Any], *, clock: Clock | None = None,
    profile_type: type[UserProfile] = UserProfile,
) -> SessionType:
    """Hydrate a session without changing legacy fallback order."""
    state = _normalize_persisted_state(item.get("state"), item.get("user_profile", {}))
    messages = [
        Message(
            role=m["role"], content=m["content"],
            timestamp=datetime.fromisoformat(m["timestamp"]) if isinstance(m["timestamp"], str) else m["timestamp"],
        )
        for m in item.get("messages", [])
    ]
    result = cls(
        user_id=item["user_id"], state=state,
        user_profile=profile_type(**item.get("user_profile", {})), messages=messages,
        working_memory=ConversationMemory(**(item.get("working_memory") or {"summary": item.get("conversation_summary")})),
        discussed_schemes=item.get("discussed_schemes", []),
        selected_scheme_id=item.get("selected_scheme_id"),
        language_preference=item.get("language_preference", "auto"),
        language_locked=item.get("language_locked", False),
        currently_asking=item.get("currently_asking", item.get("metadata", {}).get("currently_asking")),
        skipped_fields=item.get("skipped_fields", item.get("metadata", {}).get("skipped_fields", [])),
        awaiting_profile_change=item.get("awaiting_profile_change", item.get("metadata", {}).get("awaiting_profile_change", False)),
        presented_schemes=item.get("presented_schemes", item.get("metadata", {}).get("presented_schemes", [])),
        completed_turn_count=item.get("completed_turn_count", 0),
        last_memory_refresh_turn=item.get("last_memory_refresh_turn", 0),
        pending_memory_job=item.get("pending_memory_job", False),
        created_at=datetime.fromisoformat(item["created_at"]) if isinstance(item.get("created_at"), str) else (item.get("created_at") or (clock.now() if clock is not None else datetime.now(UTC))),
        updated_at=datetime.fromisoformat(item["updated_at"]) if isinstance(item.get("updated_at"), str) else (item.get("updated_at") or (clock.now() if clock is not None else datetime.now(UTC))),
        metadata=item.get("metadata", {}),
    )
    result.with_clock(clock)
    return result
