"""Application policy for choosing the next conversation state."""

from typing import Any

from src.dss.application.conversation import fsm, intents, scheme_reference, turn_policy
from src.dss.application.conversation import sessions as session_manager
from src.dss.application.conversation.models import ProfileUpdate, TurnAnalysis
from src.dss.application.conversation.profile_fields import ProfileFields
from src.dss.domain.conversations.session import Session
from src.dss.domain.conversations.states import ConversationState


class TransitionPolicy:
    """Resolve scheme navigation and profile-collection state transitions."""

    def __init__(self, fields: ProfileFields) -> None:
        self.fields = fields

    def decide(
        self,
        session: Session,
        analysis: TurnAnalysis,
        update: ProfileUpdate,
        user_message: str,
    ) -> tuple[ConversationState, ConversationState | None]:
        profile = session.user_profile
        requested_state = turn_policy.requested_scheme_view(
            user_message,
            analysis.action,
            session.state,
            resolved_scheme_id=analysis.resolved_scheme_id,
            active_scheme_id=session.selected_scheme_id,
        )
        if (
            analysis.explicit_topic_switch
            and requested_state in scheme_reference.SCHEME_CONTEXT_STATES
        ):
            requested_state = None
        next_state = fsm.determine_next_state(
            current_state=session.state,
            profile=profile,
            intent=analysis.intent,
            selected_scheme_id=analysis.resolved_scheme_id,
            has_selected_scheme=bool(session.selected_scheme_id),
            action=analysis.action,
            requested_state=requested_state,
            fields=self.fields,
        )
        if (
            next_state == ConversationState.SCHEME_MATCHING
            and session.awaiting_profile_change
            and not update.profile_changed
        ):
            next_state = turn_policy.collection_state_for_profile(profile)
        if turn_policy.should_refresh_matches_after_profile_change(
            session=session,
            profile=profile,
            matching_inputs_changed=update.matching_inputs_changed,
            action=analysis.action,
            requested_state=requested_state,
            fields=self.fields,
        ):
            next_state = ConversationState.SCHEME_MATCHING
        if (
            next_state == ConversationState.SCHEME_DETAILS
            and session.state
            in {
                ConversationState.SCHEME_DETAILS,
                ConversationState.DOCUMENT_GUIDANCE,
                ConversationState.REJECTION_WARNINGS,
            }
            and intents.is_affirmative(user_message)
        ):
            next_state = ConversationState.APPLICATION_HELP
        return next_state, requested_state

    @staticmethod
    def _clear_stale_scheme_state(
        session: Session, analysis: TurnAnalysis, update: ProfileUpdate
    ) -> Session:
        session = session_manager.set_awaiting_profile_change(session, False)
        session = session_manager.set_skipped_fields(
            session, [f for f in session.skipped_fields if f not in update.changed_fields]
        )
        if "life_event" in update.changed_fields and update.before_profile.life_event is not None:
            session = session_manager.clear_selection(session)
            session = session_manager.set_presented_schemes(session, [])
            session = session_manager.set_currently_asking(session, None)
            session = session_manager.set_skipped_fields(session, [])
        elif (
            update.matching_inputs_changed
            and session.selected_scheme_id
            and not turn_policy.should_preserve_scheme_context_action(analysis.action)
        ):
            session = session_manager.clear_selection(session)
            session = session_manager.set_presented_schemes(session, [])
        return session

    @staticmethod
    def reset(
        session: Session,
        analysis: TurnAnalysis,
        lang: str,
        language_changed: bool,
        *,
        responses: Any,
    ) -> tuple[Session, str] | None:
        if (
            language_changed
            and session.state == ConversationState.GREETING
            and not analysis.detected_life_event
            and not analysis.extracted_fields
        ):
            return session, responses.generate_greeting_response(lang)
        if analysis.action == "start_over":
            session = session_manager.reset_session(session, preserve_language=True)
            return session, responses.generate_greeting_response(lang)
        if analysis.intent == "goodbye" or analysis.action == "goodbye":
            text = responses.generate_farewell_response(lang)
            session = session_manager.reset_session(session, preserve_language=True)
            return session, text
        return None
