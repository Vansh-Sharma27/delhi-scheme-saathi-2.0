"""Temporary typed bridge preserving legacy view patch points during migration."""

import asyncpg

from src.dss.application.conversation.views import SchemeViews
from src.dss.domain.conversations.session import Session
from src.dss.domain.profiles.profile import UserProfile
from src.services.conversation import views


class LegacySchemeViews(SchemeViews):
    def __init__(self, pool: asyncpg.Pool) -> None:
        self.pool = pool

    async def build_scheme_details_text(self, scheme_id: str, profile: UserProfile, language: str) -> str:
        return await views.build_scheme_details_text(self.pool, scheme_id, profile, language)

    async def build_document_guidance_text(self, session: Session, scheme_id: str, language: str) -> str:
        return await views.build_document_guidance_text(self.pool, session, scheme_id, language)

    async def build_rejection_warnings_text(self, scheme_id: str, profile: UserProfile, language: str) -> str:
        return await views.build_rejection_warnings_text(self.pool, scheme_id, profile, language)

    async def build_application_help_text(self, session: Session, scheme_id: str, language: str) -> str:
        return await views.build_application_help_text(self.pool, session, scheme_id, language)

    async def build_scheme_question_answer_text(
        self, session: Session, scheme_id: str, profile: UserProfile,
        user_question: str, language: str, *, active_view: str | None = None,
    ) -> str:
        return await views.build_scheme_question_answer_text(
            self.pool, session, scheme_id, profile, user_question, language, active_view=active_view,
        )

    async def build_handoff_text(self, profile: UserProfile, language: str) -> str:
        return await views.build_handoff_text(self.pool, profile, language)
