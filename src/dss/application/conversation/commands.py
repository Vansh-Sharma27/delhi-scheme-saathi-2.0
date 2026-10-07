"""Deterministic commands and inline-keyboard callbacks."""

from typing import Any

from src.dss.application.conversation.contracts import ChatResponse
from src.dss.application.conversation.language_policy import LanguagePolicy
from src.dss.application.conversation.persistence import TurnPersistence
from src.dss.domain.conversations.session import Session
from src.dss.domain.conversations.states import ConversationState

_CALLBACK_LANGUAGE_PREFIX = "lang:"
_CALLBACK_SCHEME_PREFIX = "scheme:"


class CommandHandler:
    def __init__(
        self,
        pool: Any,
        renderer: Any,
        persistence: TurnPersistence,
        *,
        dependencies: Any,
        session_store: Any,
    ) -> None:
        self.pool = pool
        self.renderer = renderer
        self.dependencies = dependencies
        self.session_store = session_store
        self._build_command_response = persistence._build_command_response

    async def _handle_command(
        self,
        session: Session,
        command: str,
        user_message: str,
    ) -> ChatResponse:
        """Answer /start, /help and /language without calling the LLM."""
        if command == "start":
            session = self.dependencies.session_manager.reset_session(session)
            lang = session.language_preference if session.language_preference != "auto" else "hi"
            return await self._build_command_response(
                session,
                user_message=user_message,
                response_text=self.dependencies.response_generator.generate_greeting_response(lang),
                language=lang,
            )

        if command == "help":
            response_text = self.dependencies.response_generator.generate_help_response(
                session.language_preference,
                has_active_scheme=bool(
                    session.selected_scheme_id
                    and session.state in self.dependencies.scheme_reference.SCHEME_CONTEXT_STATES
                ),
            )
        else:
            response_text = (
                self.dependencies.response_generator.generate_language_selection_response(
                    session.language_preference
                )
            )

        return await self._build_command_response(
            session,
            user_message=user_message,
            response_text=response_text,
            language=self.dependencies.language.command_response_language(session),
            inline_keyboard=self.dependencies.format_language_keyboard(session.language_preference),
        )

    async def _handle_callback(
        self,
        session: Session,
        callback_data: str,
    ) -> ChatResponse:
        """Handle a tap on an inline keyboard button."""
        lang = session.language_preference if session.language_preference != "auto" else "hi"

        if callback_data.startswith(_CALLBACK_LANGUAGE_PREFIX):
            return await self._handle_language_callback(
                session,
                callback_data.removeprefix(_CALLBACK_LANGUAGE_PREFIX),
                lang,
            )

        if callback_data.startswith(_CALLBACK_SCHEME_PREFIX):
            return await self._handle_scheme_callback(
                session,
                callback_data.removeprefix(_CALLBACK_SCHEME_PREFIX),
                lang,
            )

        return ChatResponse(
            text="अमान्य चयन।" if lang == "hi" else "Invalid selection.",
            language=lang,
        )

    async def _handle_language_callback(
        self,
        session: Session,
        requested_language: str,
        lang: str,
    ) -> ChatResponse:
        """Switch language and re-render the user's current context in it."""
        if requested_language not in self.dependencies.language.SUPPORTED_LANGUAGES:
            return ChatResponse(
                text="अमान्य भाषा चयन।" if lang == "hi" else "Invalid language selection.",
                language=lang,
            )

        session = self.dependencies.session_manager.set_language(
            session, requested_language, locked=True
        )
        state_text, inline_keyboard = await self.renderer.snapshot(
            session,
            requested_language,
        )
        response_text = (
            self.dependencies.response_generator.generate_language_changed_response(
                requested_language,
                has_active_scheme=bool(
                    session.selected_scheme_id
                    and session.state in self.dependencies.scheme_reference.SCHEME_CONTEXT_STATES
                ),
            )
            + "\n\n"
            + state_text
        )
        response_text = await LanguagePolicy.enforce(
            session,
            response_text,
            requested_language,
            responses=self.dependencies.response_generator,
        )

        session = await self.dependencies.session_manager.add_message(
            session, "assistant", response_text
        )
        await self.dependencies.session_manager.save_session(session, store=self.session_store)

        return ChatResponse(
            text=response_text,
            next_state=session.state.value,
            language=requested_language,
            inline_keyboard=inline_keyboard,
        )

    async def _handle_scheme_callback(
        self,
        session: Session,
        scheme_id: str,
        lang: str,
    ) -> ChatResponse:
        """Open the scheme behind a tapped button."""
        session = self.dependencies.session_manager.select_scheme(session, scheme_id)
        session = self.dependencies.session_manager.update_state(
            session, ConversationState.SCHEME_DETAILS
        )

        response_text = await self.dependencies.views.build_scheme_details_text(
            self.pool, scheme_id, session.user_profile, lang
        )
        response_text = await LanguagePolicy.enforce(
            session,
            response_text,
            lang,
            responses=self.dependencies.response_generator,
        )

        session = await self.dependencies.session_manager.add_message(
            session, "assistant", response_text
        )
        await self.dependencies.session_manager.save_session(session, store=self.session_store)

        return ChatResponse(
            text=response_text,
            next_state=ConversationState.SCHEME_DETAILS.value,
            language=lang,
        )
