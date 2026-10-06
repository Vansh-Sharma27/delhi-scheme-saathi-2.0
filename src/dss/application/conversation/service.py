"""One-turn application pipeline: deterministic policies override the LLM."""

from typing import Any

from src.dss.application.conversation.commands import CommandHandler
from src.dss.application.conversation.contracts import ChatRequest, ChatResponse
from src.dss.application.conversation.language_policy import LanguagePolicy
from src.dss.application.conversation.models import TurnAnalysis
from src.dss.application.conversation.persistence import TurnPersistence
from src.dss.application.conversation.profile_update import ProfileUpdateService
from src.dss.application.conversation.transition_policy import TransitionPolicy
from src.dss.application.conversation.turn_analyzer import TurnAnalyzer
from src.dss.application.conversation.turn_renderer import TurnRenderer
from src.dss.domain.conversations.session import Session


class ConversationApplication:
    def __init__(
        self,
        *,
        dependencies: Any,
        policies: Any,
        analyzer: TurnAnalyzer,
        language_policy: LanguagePolicy,
        profile_updates: ProfileUpdateService,
        transitions: TransitionPolicy,
        renderer: TurnRenderer,
        commands: CommandHandler,
        persistence: TurnPersistence,
        session_store: Any,
        clock: Any,
    ) -> None:
        self.dependencies = dependencies
        self.policies = policies
        self.turn_analyzer = analyzer
        self.language_policy = language_policy
        self.profile_update_service = profile_updates
        self.transition_policy = transitions
        self.renderer = renderer
        self.commands = commands
        self.persistence = persistence
        self.session_store = session_store
        self.clock = clock

    async def handle_message(self, request: ChatRequest) -> ChatResponse:
        """Handle one incoming user message and return the reply."""
        session = await self.dependencies.session_manager.get_or_create_session(
            request.user_id,
            store=self.session_store,
            clock=self.clock,
        )

        # Telegram callback queries legitimately carry an empty message body;
        # their payload lives in callback_data. Dispatch them before applying
        # the text-only empty-message guard.
        if request.message_type == "callback" and request.callback_data:
            return await self.commands._handle_callback(session, request.callback_data)

        user_message = self.dependencies.sanitize_input(request.message)
        if not user_message:
            return ChatResponse(
                text="मुझे आपका संदेश समझ नहीं आया। कृपया दोबारा लिखें।",
                language=(
                    session.language_preference if session.language_preference != "auto" else "hi"
                ),
            )

        command = self.dependencies.intents.extract_supported_command(user_message)
        if command:
            return await self.commands._handle_command(session, command, user_message)

        analysis = await self.turn_analyzer.analyze(session, user_message)
        session, lang, language_changed = self.language_policy.resolve(
            session, analysis, policies=self.policies
        )

        early_reply = await self._handle_turn_reset(
            session,
            analysis,
            user_message=user_message,
            lang=lang,
            language_changed=language_changed,
        )
        if early_reply is not None:
            return early_reply

        session, profile_update = self.profile_update_service.apply(
            session, analysis, user_message, policies=self.policies
        )
        profile = session.user_profile

        next_state, requested_state = self.transition_policy.decide(
            session,
            analysis,
            profile_update,
            user_message,
            policies=self.policies,
        )

        result = await self.renderer.render(
            session=session,
            next_state=next_state,
            requested_state=requested_state,
            analysis=analysis,
            profile_update=profile_update,
            user_message=user_message,
            lang=lang,
        )

        response_text = result.text
        if (
            profile.life_event == "DEATH_IN_FAMILY"
            and "life_event" in profile_update.changed_fields
            and profile_update.before_profile.life_event is None
        ):
            response_text = self.dependencies.language.prepend_death_in_family_empathy(
                response_text, lang
            )

        return await self.persistence._finalize_turn(
            session=result.session,
            next_state=result.state,
            user_message=user_message,
            response_text=response_text,
            schemes=result.schemes,
            inline_keyboard=result.inline_keyboard,
            lang=lang,
        )

    async def _handle_turn_reset(
        self,
        session: Session,
        analysis: TurnAnalysis,
        *,
        user_message: str,
        lang: str,
        language_changed: bool,
    ) -> ChatResponse | None:
        reset = self.transition_policy.reset(
            session,
            analysis,
            lang,
            language_changed,
            policies=self.policies,
            responses=self.dependencies.response_generator,
        )
        if reset is None:
            return None
        session, response_text = reset
        return await self.persistence._build_command_response(
            session, user_message=user_message, response_text=response_text, language=lang
        )
