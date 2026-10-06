"""Response generation service."""

import logging
from typing import Any

from src.dss.application.guidance import generation, localization, presenters, scheme_terms
from src.dss.application.guidance.currency import _format_currency as _format_currency
from src.dss.application.guidance.eligibility_rules import (
    _build_eligibility_rule_text as _build_eligibility_rule_text,
)
from src.dss.application.guidance.eligibility_rules import (
    _eligibility_field_label as _eligibility_field_label,
)
from src.dss.application.guidance.generation import (
    _last_assistant_response as _last_assistant_response,
)
from src.dss.application.guidance.localization import (
    LANGUAGE_NORMALIZATION_PROMPT as LANGUAGE_NORMALIZATION_PROMPT,
)
from src.dss.application.guidance.localization import (
    _count_devanagari_tokens as _count_devanagari_tokens,
)
from src.dss.application.guidance.localization import (
    _count_hinglish_markers as _count_hinglish_markers,
)
from src.dss.application.guidance.localization import _count_latin_tokens as _count_latin_tokens
from src.dss.application.guidance.localization import (
    _needs_grounded_translation as _needs_grounded_translation,
)
from src.dss.application.guidance.localization import (
    _needs_language_normalization as _needs_language_normalization,
)
from src.dss.application.guidance.localization import _pick_language_text as _pick_language_text
from src.dss.application.guidance.presenters import (
    ELIGIBILITY_QUESTION_PATTERNS as ELIGIBILITY_QUESTION_PATTERNS,
)
from src.dss.application.guidance.presenters import (
    JUSTIFICATION_QUESTION_PATTERNS as JUSTIFICATION_QUESTION_PATTERNS,
)
from src.dss.application.guidance.presenters import (
    _is_eligibility_question as _is_eligibility_question,
)
from src.dss.application.guidance.presenters import (
    _is_justification_question as _is_justification_question,
)
from src.dss.application.guidance.templates import (
    generate_application_guidance as generate_application_guidance,
)
from src.dss.application.guidance.templates import (
    generate_clarification_response as generate_clarification_response,
)
from src.dss.application.guidance.templates import (
    generate_farewell_response as generate_farewell_response,
)
from src.dss.application.guidance.templates import (
    generate_field_help_response as generate_field_help_response,
)
from src.dss.application.guidance.templates import (
    generate_field_reason_response as generate_field_reason_response,
)
from src.dss.application.guidance.templates import (
    generate_greeting_response as generate_greeting_response,
)
from src.dss.application.guidance.templates import generate_help_response as generate_help_response
from src.dss.application.guidance.templates import (
    generate_language_changed_response as generate_language_changed_response,
)
from src.dss.application.guidance.templates import (
    generate_language_selection_response as generate_language_selection_response,
)
from src.dss.application.guidance.templates import (
    generate_no_schemes_response as generate_no_schemes_response,
)
from src.dss.application.guidance.templates import (
    generate_scheme_selection_response as generate_scheme_selection_response,
)
from src.dss.domain.conversations.session import Session
from src.dss.domain.eligibility.evaluator import calculate_eligibility_match
from src.dss.domain.eligibility.presentation_facts import (
    _infer_income_segment as _infer_income_segment,
)
from src.dss.domain.eligibility.presentation_facts import eligibility_facts
from src.dss.domain.profiles.profile import UserProfile
from src.dss.domain.schemes.scheme import Scheme
from src.services.ai_orchestrator import get_ai_orchestrator

logger = logging.getLogger(__name__)


async def ensure_response_language(
    session: Session,
    text: str,
    language: str,
) -> str:
    return await localization.ensure_response_language(
        session, text, language, rewrite=_rewrite_response_language
    )


async def _rewrite_response_language(
    session: Session,
    text: str,
    language: str,
) -> str:
    return await localization._rewrite_response_language(
        session, text, language, get_ai_orchestrator=get_ai_orchestrator
    )


async def translate_grounded_text_if_needed(
    session: Session,
    text: str,
    language: str,
) -> str:
    return await localization.translate_grounded_text_if_needed(
        session, text, language, rewrite=_rewrite_response_language
    )


async def generate_response(
    session: Session,
    context: dict[str, Any],
) -> str:
    return await generation.generate_response(
        session, context, get_ai_orchestrator=get_ai_orchestrator
    )


async def generate_scheme_question_response(
    session: Session,
    scheme: Scheme,
    profile: UserProfile,
    user_question: str,
    language: str,
    *,
    active_view: str | None = None,
) -> str:
    return await generation.generate_scheme_question_response(
        session,
        scheme,
        profile,
        user_question,
        language,
        active_view=active_view,
        generate_response=generate_response,
    )


def _build_matching_reason_context(scheme: Scheme, profile: UserProfile) -> list[str]:
    return presenters._build_matching_reason_context(
        scheme, profile, calculate_eligibility_match(scheme, profile)
    )


def _maybe_generate_scheme_term_response(
    scheme: Scheme, profile: UserProfile, user_question: str, language: str
) -> str | None:
    return scheme_terms._maybe_generate_scheme_term_response(
        scheme,
        profile,
        user_question,
        language,
        income_segment=_infer_income_segment(
            scheme.eligibility.income_by_category, profile.annual_income
        ),
    )


def _maybe_generate_eligibility_response(
    scheme: Scheme, profile: UserProfile, user_question: str, language: str
) -> str | None:
    if not _is_eligibility_question(user_question) or not _build_eligibility_rule_text(
        scheme, language
    ):
        return None
    return presenters._maybe_generate_eligibility_response(
        scheme, profile, user_question, language, facts=eligibility_facts(scheme, profile)
    )


def _maybe_generate_scheme_justification_response(
    scheme: Scheme, profile: UserProfile, user_question: str, language: str
) -> str | None:
    if not _is_justification_question(user_question):
        return None
    return presenters._maybe_generate_scheme_justification_response(
        scheme,
        profile,
        user_question,
        language,
        reasons=_build_matching_reason_context(scheme, profile),
    )
