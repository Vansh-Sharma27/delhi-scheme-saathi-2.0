"""Application use case for applying analyzed profile facts."""

from typing import Any

from src.dss.application.conversation.models import ProfileUpdate, TurnAnalysis
from src.dss.application.conversation.transition_policy import TransitionPolicy
from src.dss.domain.conversations.session import Session
from src.dss.domain.profiles.profile import UserProfile


class ProfileUpdateService:
    """Merge extracted facts and invalidate stale scheme context."""

    @staticmethod
    def apply(
        session: Session, analysis: TurnAnalysis, user_message: str, *, policies: Any
    ) -> tuple[Session, ProfileUpdate]:
        session_manager = policies.session_manager
        turn_policy = policies.turn_policy
        before_profile = session.user_profile
        if analysis.extracted_fields:
            session = session_manager.update_profile(
                session,
                UserProfile(
                    **{k: v for k, v in analysis.extracted_fields.items() if v is not None}
                ),
            )
        if turn_policy.should_update_life_event(
            session,
            analysis.detected_life_event,
            analysis.extracted_fields,
            analysis.action,
            user_message,
        ):
            session = session_manager.update_profile(
                session, UserProfile(life_event=analysis.detected_life_event)
            )
        update = ProfileUpdate(
            before_profile=before_profile,
            changed_fields=turn_policy.matching_field_changes(before_profile, session.user_profile),
        )
        if update.profile_changed:
            session = TransitionPolicy._clear_stale_scheme_state(
                session, analysis, update, policies=policies
            )
        return session, update
