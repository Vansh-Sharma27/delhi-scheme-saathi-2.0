"""Lifecycle-independent construction of the typed conversation graph."""

from collections.abc import Awaitable, Callable

from src.dss.application.conversation import keyboards, scheme_reference, sessions, turn_policy
from src.dss.application.conversation.commands import CommandHandler
from src.dss.application.conversation.language_policy import LanguagePolicy
from src.dss.application.conversation.models import RenderResult
from src.dss.application.conversation.persistence import TurnPersistence
from src.dss.application.conversation.profile_fields import ProfileFields
from src.dss.application.conversation.profile_questions import ProfileQuestionRenderer
from src.dss.application.conversation.profile_update import ProfileUpdateService
from src.dss.application.conversation.service import ConversationApplication
from src.dss.application.conversation.transition_policy import TransitionPolicy
from src.dss.application.conversation.turn_analyzer import TurnAnalyzer
from src.dss.application.conversation.turn_renderer import TurnRenderer
from src.dss.application.conversation.view_formatting import (
    build_multi_beneficiary_scope_response,
    build_scheme_list_text,
)
from src.dss.application.conversation.views import SchemeViews
from src.dss.application.matching.matching_use_case import MatchingUseCase
from src.dss.application.ports.ai_tasks import AITasks
from src.dss.application.ports.clock import Clock
from src.dss.application.ports.matching import MatchSchemes
from src.dss.application.ports.responses import Responses
from src.dss.application.ports.session_repository import SessionStore
from src.dss.domain.conversations.session import Session
from src.dss.domain.profiles.profile import UserProfile
from src.dss.settings import Settings


def build_conversation(
    *, settings: Settings, store: SessionStore, clock: Clock,
    ai: AITasks, responses: Responses, fields: ProfileFields,
    views: SchemeViews, match_schemes: MatchSchemes,
    get_analysis_prompt: Callable[[], str], enqueue: Callable[[str, int], Awaitable[bool]],
) -> ConversationApplication:
    """Wire supplied instances without starting resources or resolving singletons."""
    matching = MatchingUseCase(
        ai, match_schemes=match_schemes,
        is_low_context=turn_policy.is_low_context_matching_turn,
        build_focus=turn_policy.build_matching_focus_text,
        get_history=sessions.get_conversation_history,
        build_scheme_list=build_scheme_list_text,
        generate_no_schemes=responses.generate_no_schemes_response,
        collection_state=turn_policy.collection_state_for_profile,
        format_keyboard=keyboards.format_inline_keyboard,
        store_presented=scheme_reference.store_presented_schemes,
        set_awaiting_profile_change=sessions.set_awaiting_profile_change,
        clear_selection=sessions.clear_selection,
        set_presented_schemes=sessions.set_presented_schemes,
        set_currently_asking=sessions.set_currently_asking,
    )

    async def run_matching(profile: UserProfile, text: str, session: Session, lang: str) -> RenderResult:
        result = await matching.run(profile, text, session, lang)
        return RenderResult(result.session, result.state, result.text, result.schemes, result.inline_keyboard)

    questions = ProfileQuestionRenderer(
        run_matching=run_matching, profile_extractor=fields, response_generator=responses,
        scope_response=build_multi_beneficiary_scope_response,
    )
    renderer = TurnRenderer(
        questions=questions, run_matching=run_matching, profile_extractor=fields,
        response_generator=responses, views=views, match_schemes=match_schemes,
        format_inline_keyboard=keyboards.format_inline_keyboard,
        format_presented_scheme_keyboard=keyboards.format_presented_scheme_keyboard,
    )
    persistence = TurnPersistence(
        responses=responses, settings=settings, session_store=store, enqueue=enqueue,
    )
    commands = CommandHandler(
        renderer, persistence, responses=responses, views=views, session_store=store,
    )
    return ConversationApplication(
        responses=responses,
        analyzer=TurnAnalyzer(ai, get_system_prompt=get_analysis_prompt),
        language_policy=LanguagePolicy(), profile_updates=ProfileUpdateService(),
        transitions=TransitionPolicy(fields), renderer=renderer, commands=commands,
        persistence=persistence, session_store=store, clock=clock,
    )
