"""Conversation application rendering."""

from collections.abc import Awaitable, Callable
from types import ModuleType

from src.dss.application.conversation import profile_extractor
from src.dss.application.conversation.models import ProfileUpdate, RenderResult, TurnAnalysis
from src.dss.application.conversation.profile_fields import ProfileFields
from src.dss.domain.conversations.session import Session
from src.dss.domain.conversations.states import ConversationState
from src.dss.domain.profiles.profile import UserProfile
from src.dss.domain.schemes.scheme import SchemeMatch


class ProfileQuestionRenderer:
    """Render collection questions, validation feedback, and skipped fields."""

    def __init__(
        self,
        *,
        run_matching: Callable[[UserProfile, str, Session, str], Awaitable[RenderResult]],
        profile_extractor: ProfileFields,
        response_generator: ModuleType,
        session_manager: ModuleType,
        views: ModuleType,
        intents: ModuleType,
        language: ModuleType,
    ) -> None:
        self._run_matching = run_matching
        self.profile_extractor = profile_extractor
        self.response_generator = response_generator
        self.session_manager = session_manager
        self.views = views
        self.intents = intents
        self.language = language

    async def _render_situation_understanding(
        self,
        session: Session,
        analysis: TurnAnalysis,
        user_message: str,
        lang: str,
    ) -> RenderResult:
        """Ask what the user needs, or move on once the topic is known."""
        profile = session.user_profile

        if not profile.life_event:
            text = (
                analysis.llm_response_text
                or self.response_generator.generate_clarification_response("life_event", lang)
            )
            session = self.session_manager.set_currently_asking(session, "life_event")
            return RenderResult(session, ConversationState.SITUATION_UNDERSTANDING, text)

        if self.profile_extractor.is_complete_for_matching(profile):
            outcome = await self._run_matching(profile, user_message, session, lang)
            return RenderResult(
                outcome.session,
                outcome.state,
                outcome.text,
                outcome.schemes,
                outcome.inline_keyboard,
            )

        text = self.profile_extractor.get_next_question(
            profile, lang, session.skipped_fields
        ) or self.response_generator.generate_clarification_response("age", lang)
        session = self.session_manager.set_currently_asking(
            session,
            self.profile_extractor.get_next_missing_field(profile, session.skipped_fields),
        )
        return RenderResult(session, ConversationState.PROFILE_COLLECTION, text)

    async def _render_profile_collection(
        self,
        session: Session,
        analysis: TurnAnalysis,
        profile_update: ProfileUpdate,
        user_message: str,
        lang: str,
    ) -> RenderResult:
        """Collect the next profile field, handling skips and bad answers."""
        profile = session.user_profile

        if not profile.life_event:
            session = self.session_manager.set_currently_asking(session, "life_event")
            return RenderResult(
                session,
                ConversationState.SITUATION_UNDERSTANDING,
                self.response_generator.generate_clarification_response("life_event", lang),
            )

        previously_asking = session.currently_asking
        # The last search came back empty, the profile is as complete as it
        # gets, and this turn added nothing new — running matching again would
        # only produce the same empty result.
        no_new_matches_possible = (
            session.awaiting_profile_change
            and not profile_update.profile_changed
            and self.profile_extractor.is_complete_for_matching(profile)
        )

        if analysis.action in {"ask_field_reason", "clarify_field"} and previously_asking:
            text = (
                self.response_generator.generate_field_reason_response(previously_asking, lang)
                if analysis.action == "ask_field_reason"
                else self.response_generator.generate_field_help_response(previously_asking, lang)
            )
            session = self.session_manager.set_currently_asking(session, previously_asking)
            return RenderResult(session, ConversationState.PROFILE_COLLECTION, text)

        if analysis.action == "skip_field" and previously_asking:
            return await self._render_skipped_field(
                session,
                previously_asking,
                user_message,
                lang,
                no_new_matches_possible=no_new_matches_possible,
            )

        return await self._render_field_question(
            session,
            analysis,
            profile_update,
            user_message,
            lang,
            previously_asking=previously_asking,
            no_new_matches_possible=no_new_matches_possible,
        )

    async def _render_skipped_field(
        self,
        session: Session,
        skipped_field: str,
        user_message: str,
        lang: str,
        *,
        no_new_matches_possible: bool,
    ) -> RenderResult:
        """Record a skipped field and ask the next one, or match with what we have."""
        profile = session.user_profile
        skipped = list(session.skipped_fields)
        if skipped_field not in skipped:
            skipped.append(skipped_field)
        session = self.session_manager.set_skipped_fields(session, skipped)

        next_unskipped = self.profile_extractor.get_next_missing_field(profile, skipped)
        if next_unskipped:
            session = self.session_manager.set_currently_asking(session, next_unskipped)
            return RenderResult(
                session,
                ConversationState.PROFILE_COLLECTION,
                self.profile_extractor.get_next_question(profile, lang, skipped) or "",
            )

        if no_new_matches_possible:
            session = self.session_manager.set_currently_asking(session, None)
            return RenderResult(
                session,
                ConversationState.PROFILE_COLLECTION,
                self.response_generator.generate_no_schemes_response(lang),
            )

        outcome = await self._run_matching(profile, user_message, session, lang)
        session = self.session_manager.set_currently_asking(outcome.session, None)
        return RenderResult(
            session,
            outcome.state,
            outcome.text,
            outcome.schemes,
            outcome.inline_keyboard,
        )

    async def _render_field_question(
        self,
        session: Session,
        analysis: TurnAnalysis,
        profile_update: ProfileUpdate,
        user_message: str,
        lang: str,
        *,
        previously_asking: str | None,
        no_new_matches_possible: bool,
    ) -> RenderResult:
        """Normal collection turn: validate the answer, then ask the next field."""
        profile = session.user_profile
        next_question = self.profile_extractor.get_next_question(
            profile, lang, session.skipped_fields
        )
        next_field = self.profile_extractor.get_next_missing_field(profile, session.skipped_fields)
        scope_followup = self.intents.is_multi_beneficiary_scope_followup(
            user_message, previously_asking
        )

        validation_error = None
        if previously_asking and previously_asking not in analysis.extracted_fields:
            is_valid, error_type = profile_extractor.validate_field_response(
                previously_asking, user_message, analysis.extracted_fields
            )
            if not is_valid and error_type:
                validation_error = error_type

        # An explicit language switch mid-question is answered by re-asking
        # the same question in the new language, not by moving on.
        translated_reask = (
            analysis.explicit_language is not None
            and previously_asking is not None
            and not analysis.extracted_fields
            and not analysis.detected_life_event
        )

        state = ConversationState.PROFILE_COLLECTION
        schemes: list[SchemeMatch] = []
        inline_keyboard = None

        if validation_error:
            text = profile_extractor.get_validation_re_prompt(
                previously_asking, validation_error, lang
            )
        elif scope_followup:
            text = self.views.build_multi_beneficiary_scope_response(lang)
        elif translated_reask:
            text = (
                self.profile_extractor.get_next_question(profile, lang, session.skipped_fields)
                or ""
            )
        elif self._should_use_llm_reply(
            analysis,
            previously_asking=previously_asking,
            next_question=next_question,
            validation_error=validation_error,
            user_message=user_message,
            profile_changed=profile_update.profile_changed,
        ):
            text = analysis.llm_response_text
        elif next_question:
            text = next_question
        elif no_new_matches_possible:
            text = self.response_generator.generate_no_schemes_response(lang)
        else:
            # Every field is filled but the FSM did not route to matching.
            outcome = await self._run_matching(profile, user_message, session, lang)
            session, state, text = outcome.session, outcome.state, outcome.text
            schemes, inline_keyboard = outcome.schemes, outcome.inline_keyboard

        # Track the field being asked so the next turn can interpret a bare
        # answer in context.
        if validation_error or translated_reask:
            session = self.session_manager.set_currently_asking(session, previously_asking)
        elif scope_followup:
            session = self.session_manager.set_currently_asking(session, "life_event")
        else:
            session = self.session_manager.set_currently_asking(session, next_field)

        return RenderResult(session, state, text, schemes, inline_keyboard)

    def _should_use_llm_reply(
        self,
        analysis: TurnAnalysis,
        *,
        previously_asking: str | None,
        next_question: str | None,
        validation_error: str | None,
        user_message: str,
        profile_changed: bool,
    ) -> bool:
        """Decide whether the LLM's own wording can be used for this turn.

        Its reply is generated before the rule-based layers run, so it can be
        stale: re-asking for a field we just captured, wandering off the
        pending question, or flipping husband/wife relative to what the user
        said.
        """
        if not analysis.llm_response_text:
            return False

        captured_pending_field = (
            profile_changed
            and previously_asking
            and previously_asking in analysis.extracted_fields
            and next_question
        )
        if captured_pending_field:
            return False

        still_waiting_for_field = (
            previously_asking
            and previously_asking not in analysis.extracted_fields
            and analysis.action
            not in {
                "ask_field_reason",
                "clarify_field",
                "skip_field",
                "change_language",
                "start_over",
                "request_handoff",
            }
            and not validation_error
        )
        if still_waiting_for_field:
            return False

        return not self.language.response_conflicts_with_spouse_reference(
            user_message,
            analysis.llm_response_text,
        )
