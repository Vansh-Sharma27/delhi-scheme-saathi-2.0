"""Persist completed turns and schedule memory refresh."""

import logging
from typing import Any

from src.dss.application.conversation.contracts import ChatResponse
from src.dss.application.conversation.language_policy import LanguagePolicy
from src.dss.domain.conversations.session import Session
from src.dss.domain.conversations.states import ConversationState
from src.dss.domain.schemes.scheme import SchemeMatch

logger = logging.getLogger(__name__)


class TurnPersistence:
    def __init__(self, *, dependencies: Any, settings: Any, session_store: Any, clock: Any) -> None:
        self.dependencies = dependencies
        self.settings = settings
        self.session_store = session_store
        self.clock = clock

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
            responses=self.dependencies.response_generator,
        )
        session = self.dependencies.session_manager.update_state(session, next_state)
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
        session = await self.dependencies.session_manager.add_message(session, "user", user_message)
        session = await self.dependencies.session_manager.add_message(
            session, "assistant", response_text
        )
        session = self.dependencies.session_manager.mark_turn_completed(session)

        refresh_due = self.dependencies.should_refresh_working_memory(
            session,
            trigger_turns=self.settings.ai_memory_refresh_turns,
            trigger_tokens=self.settings.ai_memory_refresh_token_threshold,
        )
        if refresh_due:
            session = self.dependencies.session_manager.set_pending_memory_job(session, True)

        await self.dependencies.session_manager.save_session(session, store=self.session_store)

        if not refresh_due:
            return session

        if await self.dependencies.enqueue_memory_refresh(
            session.user_id, session.completed_turn_count, clock=self.clock
        ):
            return session

        # The job never made it onto the queue, so clear the marker; leaving it
        # set would block every future refresh for this user.
        logger.warning(
            "Memory refresh queue unavailable for user=%s turn=%s",
            session.user_id,
            session.completed_turn_count,
        )
        session = self.dependencies.session_manager.set_pending_memory_job(session, False)
        await self.dependencies.session_manager.save_session(session, store=self.session_store)
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
