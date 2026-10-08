"""Constructed response generation and localization over typed AI tasks."""

from collections.abc import Callable
from typing import Any

from src.dss.application.guidance import generation, localization, templates
from src.dss.application.ports.ai_tasks import AITasks
from src.dss.domain.conversations.session import Session
from src.dss.domain.profiles.profile import UserProfile
from src.dss.domain.schemes.scheme import Scheme


class Guidance:
    def __init__(
        self, ai: AITasks, *, get_prompt: Callable[[], str],
        safe_generation: Callable[[str], str],
    ) -> None:
        self.ai = ai
        self.get_prompt = get_prompt
        self.safe_generation = safe_generation

    async def generate_response(self, session: Session, context: dict[str, Any]) -> str:
        return await generation.generate_response(
            session, context, get_ai_orchestrator=lambda: self.ai, get_prompt=self.get_prompt,
        )

    async def _rewrite_response_language(self, session: Session, text: str, language: str) -> str:
        return await localization._rewrite_response_language(
            session, text, language, get_ai_orchestrator=lambda: self.ai,
            safe_generation_text=self.safe_generation,
        )

    async def ensure_response_language(self, session: Session, text: str, language: str) -> str:
        return await localization.ensure_response_language(
            session, text, language, rewrite=self._rewrite_response_language,
        )

    async def translate_grounded_text_if_needed(
        self, session: Session, text: str, language: str,
    ) -> str:
        return await localization.translate_grounded_text_if_needed(
            session, text, language, rewrite=self._rewrite_response_language,
        )

    async def generate_scheme_question_response(
        self, session: Session, scheme: Scheme, profile: UserProfile,
        user_question: str, language: str, *, active_view: str | None = None,
    ) -> str:
        return await generation.generate_scheme_question_response(
            session, scheme, profile, user_question, language,
            active_view=active_view, generate_response=self.generate_response,
        )

    generate_greeting_response = staticmethod(templates.generate_greeting_response)
    generate_help_response = staticmethod(templates.generate_help_response)
    generate_language_selection_response = staticmethod(templates.generate_language_selection_response)
    generate_language_changed_response = staticmethod(templates.generate_language_changed_response)
    generate_clarification_response = staticmethod(templates.generate_clarification_response)
    generate_no_schemes_response = staticmethod(templates.generate_no_schemes_response)
    generate_farewell_response = staticmethod(templates.generate_farewell_response)
    generate_scheme_selection_response = staticmethod(templates.generate_scheme_selection_response)
    generate_field_reason_response = staticmethod(templates.generate_field_reason_response)
    generate_field_help_response = staticmethod(templates.generate_field_help_response)
    generate_application_guidance = staticmethod(templates.generate_application_guidance)
