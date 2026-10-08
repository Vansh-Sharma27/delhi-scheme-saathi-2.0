"""Session operations with explicit persistence and clock dependencies."""

import logging
from datetime import UTC, datetime

from src.dss.application.ports.clock import Clock
from src.dss.application.ports.session_repository import SessionStore
from src.dss.domain.conversations.session import ConversationMemory, Session
from src.dss.domain.conversations.states import ConversationState
from src.dss.domain.profiles.profile import UserProfile

logger = logging.getLogger(__name__)


async def get_or_create_session(
    user_id: str,
    *,
    store: SessionStore,
    clock: Clock | None = None,
) -> Session:
    """Get an existing session or create one in the supplied store."""
    session = await store.get(user_id)

    if session is None:
        session = Session(
            user_id=user_id,
            state=ConversationState.GREETING,
            user_profile=UserProfile(),
            created_at=clock.now() if clock is not None else datetime.now(UTC),
            updated_at=clock.now() if clock is not None else datetime.now(UTC),
        ).with_clock(clock)
        await store.save(session)
        logger.info("Created new session for user %s", user_id)

    return session.with_clock(clock) if clock is not None else session


async def save_session(
    session: Session,
    *,
    store: SessionStore,
) -> None:
    """Save a session in the supplied store."""
    await store.save(session)


async def delete_session(
    user_id: str,
    *,
    store: SessionStore,
) -> None:
    """Delete a session from the supplied store, or the configured default."""
    await store.delete(user_id)


async def add_message(
    session: Session,
    role: str,
    content: str,
) -> Session:
    """Add a message to session history."""
    return session.add_message(role, content)


def update_profile(session: Session, new_profile: UserProfile) -> Session:
    """Update session with new profile (immutable merge)."""
    merged_profile = session.user_profile.merge_with(new_profile)
    return session.with_profile(merged_profile)


def update_state(session: Session, new_state: ConversationState) -> Session:
    """Update session state."""
    return session.with_state(new_state)


def add_discussed_scheme(session: Session, scheme_id: str) -> Session:
    """Add scheme to discussed list."""
    if scheme_id not in session.discussed_schemes:
        discussed = list(session.discussed_schemes)
        discussed.append(scheme_id)
        return session.copy_with(
            discussed_schemes=discussed,
        )
    return session


def select_scheme(session: Session, scheme_id: str) -> Session:
    """Set selected scheme and add to discussed."""
    session = add_discussed_scheme(session, scheme_id)
    return session.copy_with(
        selected_scheme_id=scheme_id,
    )


def set_language(session: Session, language: str, locked: bool | None = None) -> Session:
    """Set language preference."""
    updates: dict[str, str | bool] = {
        "language_preference": language,
    }
    if locked is not None:
        updates["language_locked"] = locked
    return session.copy_with(**updates)


def set_currently_asking(session: Session, field: str | None) -> Session:
    """Update which field is being asked in the current flow."""
    return session.copy_with(
        currently_asking=field,
    )


def set_skipped_fields(session: Session, skipped_fields: list[str]) -> Session:
    """Persist skipped profile fields."""
    return session.copy_with(
        skipped_fields=list(skipped_fields),
    )


def set_presented_schemes(
    session: Session,
    presented_schemes: list[dict[str, str]],
) -> Session:
    """Persist the last scheme list shown to the user."""
    return session.copy_with(
        presented_schemes=presented_schemes,
    )


def set_awaiting_profile_change(session: Session, awaiting: bool) -> Session:
    """Track whether matching should wait for meaningful profile changes."""
    return session.copy_with(
        awaiting_profile_change=awaiting,
    )


def clear_selection(session: Session) -> Session:
    """Clear the currently selected scheme."""
    return session.copy_with(
        selected_scheme_id=None,
    )


def get_conversation_history(
    session: Session,
    include_assistant: bool = True,
) -> list[dict[str, str]]:
    """Get conversation history as list of dicts."""
    messages = session.messages
    if not include_assistant:
        messages = [m for m in messages if m.role == "user"]

    return [{"role": m.role, "content": m.content} for m in messages]


def mark_turn_completed(session: Session) -> Session:
    """Increment completed turns after a full user-assistant exchange."""
    return session.copy_with(
        completed_turn_count=session.completed_turn_count + 1,
    )


def set_pending_memory_job(session: Session, pending: bool) -> Session:
    """Track whether a working-memory refresh job is already queued."""
    return session.copy_with(
        pending_memory_job=pending,
    )


def apply_working_memory(
    session: Session,
    memory: ConversationMemory,
    *,
    refreshed_turn: int | None = None,
) -> Session:
    """Persist refreshed working memory and clear queue markers."""
    return session.copy_with(
        working_memory=memory,
        last_memory_refresh_turn=(
            refreshed_turn
            if refreshed_turn is not None
            else session.completed_turn_count
        ),
        pending_memory_job=False,
    )


def reset_session(session: Session, preserve_language: bool = True) -> Session:
    """Reset session to initial state while optionally preserving language lock."""
    language_preference = session.language_preference if preserve_language else "auto"
    language_locked = session.language_locked if preserve_language else False
    return Session(
        user_id=session.user_id,
        state=ConversationState.GREETING,
        user_profile=UserProfile(),
        language_preference=language_preference,
        language_locked=language_locked,
        created_at=session.created_at,
        updated_at=session.now(),
    ).with_clock(session.clock)
