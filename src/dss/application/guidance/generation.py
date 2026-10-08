"""Grounded response orchestration with injected generation callbacks."""

from collections.abc import Awaitable, Callable
from typing import Any

from src.dss.application.guidance.eligibility_rules import _build_eligibility_rule_text
from src.dss.application.guidance.presenters import (
    _build_matching_reason_context,
    _is_eligibility_question,
    _is_justification_question,
    _maybe_generate_eligibility_response,
    _maybe_generate_scheme_justification_response,
)
from src.dss.application.guidance.scheme_terms import _maybe_generate_scheme_term_response
from src.dss.application.ports.ai_tasks import AITasks
from src.dss.domain.conversations.session import Session
from src.dss.domain.eligibility.evaluator import calculate_eligibility_match
from src.dss.domain.eligibility.presentation_facts import _infer_income_segment, eligibility_facts
from src.dss.domain.profiles.profile import UserProfile
from src.dss.domain.schemes.scheme import Scheme


async def generate_response(
    session: Session,
    context: dict[str, Any],
    *,
    get_ai_orchestrator: Callable[[], AITasks],
    get_prompt: Callable[[], str],
) -> str:
    """Generate natural language response using LLM and database context.

    Context includes:
    - matched_schemes: list of scheme matches
    - current_scheme: selected scheme details
    - documents: required documents
    - rejection_warnings: applicable rules
    - nearest_offices: nearby CSCs
    """
    # Load response generation prompt
    try:
        system_prompt = get_prompt()
    except FileNotFoundError:
        system_prompt = "Generate a helpful response based on the context."

    # Add state-specific context
    context["conversation_state"] = session.state.value
    context["user_profile"] = session.user_profile.model_dump()
    context["language"] = session.language_preference

    # Generate response via LLM
    response = await get_ai_orchestrator().generate_response(
        session=session,
        context=context,
        system_prompt=system_prompt,
        user_language=session.language_preference,
    )

    return response


def _last_assistant_response(session: Session) -> str | None:
    """Return the most recent assistant reply for translation/rephrase follow-ups."""
    for message in reversed(session.messages):
        if message.role == "assistant" and message.content.strip():
            return message.content.strip()[:1200]
    return None


async def generate_scheme_question_response(
    session: Session,
    scheme: Scheme,
    profile: UserProfile,
    user_question: str,
    language: str,
    *,
    active_view: str | None = None,
    generate_response: Callable[[Session, dict[str, Any]], Awaitable[str]],
) -> str:
    """Answer a follow-up question about a selected scheme using grounded context."""
    term_response = _maybe_generate_scheme_term_response(
        scheme,
        profile,
        user_question,
        language,
        income_segment=_infer_income_segment(
            scheme.eligibility.income_by_category, profile.annual_income
        ),
    )
    if term_response:
        return term_response
    justification_response: str | None = None
    if _is_justification_question(user_question):
        justification_response = _maybe_generate_scheme_justification_response(
            scheme,
            profile,
            user_question,
            language,
            reasons=_build_matching_reason_context(
                scheme, profile, calculate_eligibility_match(scheme, profile)
            ),
        )
    if justification_response:
        return justification_response
    eligibility_response: str | None = None
    if _is_eligibility_question(user_question) and _build_eligibility_rule_text(scheme, language):
        eligibility_response = _maybe_generate_eligibility_response(
            scheme,
            profile,
            user_question,
            language,
            facts=eligibility_facts(scheme, profile),
        )
    if eligibility_response:
        return eligibility_response

    current_scheme = scheme.model_dump(mode="json")
    current_scheme["description"] = scheme.description[:1200]
    current_scheme["description_hindi"] = scheme.description_hindi[:1200]

    context = {
        "response_mode": "scheme_question_answer",
        "active_view": active_view or session.state.value,
        "user_question": user_question,
        "current_scheme": current_scheme,
        "last_assistant_response": _last_assistant_response(session),
        "matching_reasons": _build_matching_reason_context(
            scheme, profile, calculate_eligibility_match(scheme, profile)
        ),
        "answer_style_rules": [
            "Answer the exact question first.",
            "Do not repeat the full scheme card unless the user asked for a full overview.",
            "If the user asks why this scheme was suggested, cite only matching_reasons and current_scheme facts.",
            "If the user asks for a term meaning, explain it plainly and practically.",
            "If the user asks for the same information in another language, translate or restate the last_assistant_response when it is relevant.",
        ],
    }
    return await generate_response(session, context)
