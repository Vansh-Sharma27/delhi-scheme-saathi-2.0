"""Persist completed turns and schedule memory refresh."""

import logging
from collections.abc import Awaitable, Callable

from src.dss.application.conversation import sessions as session_manager
from src.dss.application.conversation.contracts import ChatResponse
from src.dss.application.conversation.language_policy import LanguagePolicy
from src.dss.application.conversation.memory import should_refresh_working_memory
from src.dss.application.ports.responses import Responses
from src.dss.application.ports.session_repository import SessionStore
from src.dss.domain.conversations.session import Session
from src.dss.domain.conversations.states import ConversationState
from src.dss.domain.schemes.scheme import SchemeMatch
from src.dss.settings import Settings

logger = logging.getLogger(__name__)


class TurnPersistence:
    def __init__(
        self, *, responses: Responses, settings: Settings, session_store: SessionStore,
        enqueue: Callable[[str, int], Awaitable[bool]],
    ) -> None:
        self.responses = responses
        self.settings = settings
        self.session_store = session_store
        self.enqueue = enqueue

    async def _finalize_turn(
        self,
        *,
        session: Session,
        next_state: ConversationState,
        user_message: str,
        response_text: str,
        schemes: list[SchemeMatch],
        inline_keyboard: list[list[dict[str, str]]] | None,
        lang: str,
    ) -> ChatResponse:
        """Enforce the response language, persist the turn, and build the reply."""
        response_text = await LanguagePolicy.enforce(
            session,
            response_text,
            lang,
            responses=self.responses,
        )
        session = session_manager.update_state(session, next_state)
        await self._save_completed_turn(
            session,
            user_message=user_message,
            response_text=response_text,
        )

        return ChatResponse(
            text=response_text,
            schemes=schemes,
            inline_keyboard=inline_keyboard,
            next_state=next_state.value,
            language=lang,
        )

    async def _save_completed_turn(
        self,
        session: Session,
        *,
        user_message: str,
        response_text: str,
    ) -> Session:
        """Persist a completed user-assistant turn and enqueue memory refresh if due."""
        session = await session_manager.add_message(session, "user", user_message)
        session = await session_manager.add_message(
            session, "assistant", response_text
        )
        session = session_manager.mark_turn_completed(session)

        refresh_due = should_refresh_working_memory(
            session,
            trigger_turns=self.settings.ai_memory_refresh_turns,
            trigger_tokens=self.settings.ai_memory_refresh_token_threshold,
        )
        if refresh_due:
            session = session_manager.set_pending_memory_job(session, True)

        await session_manager.save_session(session, store=self.session_store)

        if not refresh_due:
            return session

        if await self.enqueue(session.user_id, session.completed_turn_count):
            return session

        # The job never made it onto the queue, so clear the marker; leaving it
        # set would block every future refresh for this user.
        logger.warning(
            "Memory refresh queue unavailable for user=%s turn=%s",
            session.user_id,
            session.completed_turn_count,
        )
        session = session_manager.set_pending_memory_job(session, False)
        await session_manager.save_session(session, store=self.session_store)
        return session

    async def _build_command_response(
        self,
        session: Session,
        *,
        user_message: str,
        response_text: str,
        language: str,
        inline_keyboard: list[list[dict[str, str]]] | None = None,
    ) -> ChatResponse:
        """Persist a deterministic turn and return a response."""
        await self._save_completed_turn(
            session,
            user_message=user_message,
            response_text=response_text,
        )
        return ChatResponse(
            text=response_text,
            next_state=session.state.value,
            language=language,
            inline_keyboard=inline_keyboard,
        )
