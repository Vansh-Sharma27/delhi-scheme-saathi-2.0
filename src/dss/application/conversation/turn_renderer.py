"""Conversation application rendering."""

from collections.abc import Awaitable, Callable

from src.dss.application.conversation import scheme_reference, view_formatting
from src.dss.application.conversation import sessions as session_manager
from src.dss.application.conversation.models import ProfileUpdate, RenderResult, TurnAnalysis
from src.dss.application.conversation.profile_fields import ProfileFields
from src.dss.application.conversation.profile_questions import ProfileQuestionRenderer
from src.dss.application.conversation.views import SchemeViews
from src.dss.application.ports.matching import MatchSchemes
from src.dss.application.ports.responses import Responses
from src.dss.domain.conversations.session import Session
from src.dss.domain.conversations.states import ConversationState
from src.dss.domain.profiles.profile import UserProfile
from src.dss.domain.schemes.scheme import SchemeMatch

_SCHEME_VIEW_STATES = {
    ConversationState.SCHEME_DETAILS,
    ConversationState.DOCUMENT_GUIDANCE,
    ConversationState.REJECTION_WARNINGS,
    ConversationState.APPLICATION_HELP,
}


class TurnRenderer:
    """Render turns and language-switch snapshots using shared scheme views."""

    def __init__(
        self,
        *,
        questions: ProfileQuestionRenderer,
        run_matching: Callable[[UserProfile, str, Session, str], Awaitable[RenderResult]],
        profile_extractor: ProfileFields,
        response_generator: Responses,
        views: SchemeViews,
        match_schemes: MatchSchemes,
        format_inline_keyboard: Callable[[list[SchemeMatch], str], list[list[dict[str, str]]] | None],
        format_presented_scheme_keyboard: Callable[[list[dict[str, str]], str], list[list[dict[str, str]]] | None],
    ) -> None:
        self.questions = questions
        self._run_matching = run_matching
        self.profile_extractor = profile_extractor
        self.response_generator = response_generator
        self.views = views
        self.match_schemes = match_schemes
        self.format_inline_keyboard = format_inline_keyboard
        self.format_presented_scheme_keyboard = format_presented_scheme_keyboard

    async def render(
        self,
        *,
        session: Session,
        next_state: ConversationState,
        requested_state: ConversationState | None,
        analysis: TurnAnalysis,
        profile_update: ProfileUpdate,
        user_message: str,
        lang: str,
    ) -> RenderResult:
        """Legacy rendering implementation retained during extraction."""
        profile = session.user_profile

        if next_state == ConversationState.GREETING:
            if session.state == ConversationState.CSC_HANDOFF:
                session = session_manager.reset_session(session)
            return RenderResult(
                session,
                next_state,
                self.response_generator.generate_greeting_response(lang),
            )

        if next_state == ConversationState.SITUATION_UNDERSTANDING:
            return await self.questions._render_situation_understanding(
                session, analysis, user_message, lang
            )

        if next_state == ConversationState.PROFILE_COLLECTION:
            return await self.questions._render_profile_collection(
                session, analysis, profile_update, user_message, lang
            )

        if next_state == ConversationState.SCHEME_MATCHING:
            outcome = await self._run_matching(profile, user_message, session, lang)
            session = outcome.session
            # Clear field tracking only when we actually reached presentation;
            # the clarification and no-match paths still need it.
            if outcome.state == ConversationState.SCHEME_PRESENTATION:
                session = session_manager.set_currently_asking(session, None)
            return RenderResult(
                session,
                outcome.state,
                outcome.text,
                outcome.schemes,
                outcome.inline_keyboard,
            )

        if next_state == ConversationState.SCHEME_PRESENTATION:
            return await self._render_scheme_presentation(
                session, analysis, requested_state, user_message, lang
            )

        if next_state in _SCHEME_VIEW_STATES:
            return await self._render_scheme_view(session, analysis, next_state, user_message, lang)

        if next_state == ConversationState.CSC_HANDOFF:
            # The LLM reply is more natural when it has one; the office list
            # is the fallback for when it does not.
            text = analysis.llm_response_text or await self.views.build_handoff_text(
                profile, lang
            )
            return RenderResult(session, next_state, text)

        return RenderResult(
            session,
            next_state,
            self.response_generator.generate_greeting_response(lang),
        )

    async def _render_scheme_presentation(
        self,
        session: Session,
        analysis: TurnAnalysis,
        requested_state: ConversationState | None,
        user_message: str,
        lang: str,
    ) -> RenderResult:
        """Show the scheme list, or open the scheme the user just referenced."""
        profile = session.user_profile
        # An explicit back-to-list request must not immediately reopen the
        # previously selected scheme through the normal context fallback.
        if requested_state == ConversationState.SCHEME_PRESENTATION:
            session = session_manager.clear_selection(session)
            scheme_id = None
        else:
            scheme_id = (
                analysis.resolved_scheme_id
                or scheme_reference.default_scheme_from_session(session, requested_state)
            )

        if scheme_id:
            session = session_manager.select_scheme(session, scheme_id)
            if analysis.action == "answer_scheme_question":
                return RenderResult(
                    session,
                    ConversationState.SCHEME_DETAILS,
                    await self.views.build_scheme_question_answer_text(
                        session,
                        scheme_id,
                        profile,
                        user_message,
                        lang,
                        active_view=ConversationState.SCHEME_DETAILS.value,
                    ),
                )

            view_state = (
                requested_state
                if requested_state in _SCHEME_VIEW_STATES
                else ConversationState.SCHEME_DETAILS
            )
            return RenderResult(
                session,
                view_state,
                await self._build_scheme_view_text(
                    session, view_state, scheme_id, profile, user_message, lang, action=None
                ),
            )

        schemes = await self.match_schemes(
            profile=profile,
            query_text=user_message,
        )
        inline_keyboard = None
        if schemes:
            session = scheme_reference.store_presented_schemes(session, schemes)
            inline_keyboard = self.format_inline_keyboard(schemes, lang)
        return RenderResult(
            session,
            ConversationState.SCHEME_PRESENTATION,
            self.response_generator.generate_scheme_selection_response(lang),
            schemes,
            inline_keyboard,
        )

    async def _render_scheme_view(
        self,
        session: Session,
        analysis: TurnAnalysis,
        view_state: ConversationState,
        user_message: str,
        lang: str,
    ) -> RenderResult:
        """Render one of the four single-scheme self.views.

        All four need a scheme id first, and fall back to the list when there
        is none. Naming a different scheme while in application help means the
        user changed their mind, so they get that scheme's overview instead of
        application steps for something they have not seen.
        """
        profile = session.user_profile
        scheme_id = (
            analysis.resolved_scheme_id
            or scheme_reference.default_scheme_from_session(session, view_state)
        )

        if not scheme_id:
            return RenderResult(
                session,
                ConversationState.SCHEME_PRESENTATION,
                view_formatting.build_select_scheme_first_text(lang),
            )

        switched_scheme = scheme_id != session.selected_scheme_id
        if switched_scheme:
            session = session_manager.select_scheme(session, scheme_id)

        if view_state == ConversationState.APPLICATION_HELP and switched_scheme:
            return RenderResult(
                session,
                ConversationState.SCHEME_DETAILS,
                await self.views.build_scheme_details_text(scheme_id, profile, lang),
            )

        return RenderResult(
            session,
            view_state,
            await self._build_scheme_view_text(
                session,
                view_state,
                scheme_id,
                profile,
                user_message,
                lang,
                action=analysis.action,
            ),
        )

    async def _build_scheme_view_text(
        self,
        session: Session,
        view_state: ConversationState,
        scheme_id: str,
        profile: UserProfile,
        user_message: str,
        lang: str,
        *,
        action: str | None,
    ) -> str:
        """Dispatch to the renderer for one scheme view."""
        if action == "answer_scheme_question":
            return await self.views.build_scheme_question_answer_text(
                session, scheme_id, profile, user_message, lang
            )
        if view_state == ConversationState.DOCUMENT_GUIDANCE:
            return await self.views.build_document_guidance_text(session, scheme_id, lang)
        if view_state == ConversationState.REJECTION_WARNINGS:
            return await self.views.build_rejection_warnings_text(scheme_id, profile, lang)
        if view_state == ConversationState.APPLICATION_HELP:
            return await self.views.build_application_help_text(session, scheme_id, lang)
        return await self.views.build_scheme_details_text(scheme_id, profile, lang)

    async def snapshot(
        self,
        session: Session,
        lang: str,
    ) -> tuple[str, list[list[dict[str, str]]] | None]:
        """Render the user's current context in a chosen language."""
        profile = session.user_profile
        state = session.state

        if state == ConversationState.GREETING:
            return self.response_generator.generate_greeting_response(lang), None

        if state in {
            ConversationState.SITUATION_UNDERSTANDING,
            ConversationState.PROFILE_COLLECTION,
        }:
            next_question = self.profile_extractor.get_next_question(
                profile,
                lang,
                session.skipped_fields,
            )
            if next_question:
                return next_question, None
            if state == ConversationState.SITUATION_UNDERSTANDING or not profile.life_event:
                return self.response_generator.generate_clarification_response(
                    "life_event", lang
                ), None
            return self.response_generator.generate_help_response(lang), None

        if state == ConversationState.SCHEME_PRESENTATION:
            selection_text = view_formatting.build_presented_scheme_selection_text(
                session.presented_schemes,
                lang,
            )
            if selection_text:
                return selection_text, self.format_presented_scheme_keyboard(
                    session.presented_schemes,
                    lang,
                )
            return self.response_generator.generate_scheme_selection_response(lang), None

        if state in _SCHEME_VIEW_STATES and session.selected_scheme_id:
            return await self._build_scheme_view_text(
                session,
                state,
                session.selected_scheme_id,
                profile,
                "",
                lang,
                action=None,
            ), None

        if state == ConversationState.CSC_HANDOFF:
            return await self.views.build_handoff_text(profile, lang), None

        return self.response_generator.generate_help_response(lang), None
