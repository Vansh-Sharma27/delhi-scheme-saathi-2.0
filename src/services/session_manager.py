"""Temporary store defaults for legacy callers of canonical session operations."""

from src.dss.application.conversation import sessions
from src.dss.application.conversation.sessions import add_discussed_scheme as add_discussed_scheme
from src.dss.application.conversation.sessions import add_message as add_message
from src.dss.application.conversation.sessions import apply_working_memory as apply_working_memory
from src.dss.application.conversation.sessions import clear_selection as clear_selection
from src.dss.application.conversation.sessions import (
    get_conversation_history as get_conversation_history,
)
from src.dss.application.conversation.sessions import mark_turn_completed as mark_turn_completed
from src.dss.application.conversation.sessions import reset_session as reset_session
from src.dss.application.conversation.sessions import select_scheme as select_scheme
from src.dss.application.conversation.sessions import (
    set_awaiting_profile_change as set_awaiting_profile_change,
)
from src.dss.application.conversation.sessions import set_currently_asking as set_currently_asking
from src.dss.application.conversation.sessions import set_language as set_language
from src.dss.application.conversation.sessions import (
    set_pending_memory_job as set_pending_memory_job,
)
from src.dss.application.conversation.sessions import set_presented_schemes as set_presented_schemes
from src.dss.application.conversation.sessions import set_skipped_fields as set_skipped_fields
from src.dss.application.conversation.sessions import update_profile as update_profile
from src.dss.application.conversation.sessions import update_state as update_state
from src.dss.application.ports.clock import Clock
from src.dss.application.ports.session_repository import SessionStore
from src.dss.domain.conversations.session import Session
from src.dss.infrastructure.sessions.session_store import get_session_store


async def get_or_create_session(
    user_id: str, *, store: SessionStore | None = None, clock: Clock | None = None,
) -> Session:
    return await sessions.get_or_create_session(user_id, store=store or get_session_store(), clock=clock)


async def save_session(session: Session, *, store: SessionStore | None = None) -> None:
    await sessions.save_session(session, store=store or get_session_store())


async def delete_session(user_id: str, *, store: SessionStore | None = None) -> None:
    await sessions.delete_session(user_id, store=store or get_session_store())
