"""Compatibility wiring for the application conversation pipeline."""

import sys

import asyncpg

from src.db.session_store import SessionStore, get_session_store
from src.dss.application.conversation import language as language
from src.dss.application.conversation import scheme_reference, turn_policy
from src.dss.application.conversation.commands import CommandHandler
from src.dss.application.conversation.keyboards import (
    format_inline_keyboard,
    format_presented_scheme_keyboard,
)
from src.dss.application.conversation.keyboards import (
    format_language_keyboard as format_language_keyboard,
)
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
from src.dss.application.conversation.validators import sanitize_input as sanitize_input
from src.dss.application.matching import scheme_relevance
from src.dss.application.matching.matching_use_case import MatchingUseCase
from src.dss.application.ports.clock import Clock
from src.dss.domain.conversations.session import Session
from src.dss.domain.profiles.profile import UserProfile
from src.dss.domain.schemes.scheme import SchemeMatch
from src.dss.infrastructure.ai.prompts.loader import get_analysis_system_prompt
from src.dss.infrastructure.database.catalog import _load_catalog
from src.dss.settings import get_settings
from src.models.api import ChatRequest, ChatResponse
from src.services import (
    response_generator,
    scheme_matcher,
    session_manager,
)
from src.services.ai_background import enqueue_memory_refresh as enqueue_memory_refresh
from src.services.ai_orchestrator import AIOrchestrator, get_ai_orchestrator
from src.services.conversation import views
from src.services.conversation_memory import (
    should_refresh_working_memory as should_refresh_working_memory,
)


class ConversationService:
    """Compatibility entrypoint supplying legacy collaborators until Phase 6."""

    def __init__(
        self,
        db_pool: asyncpg.Pool,
        *,
        ai_orchestrator: AIOrchestrator | None = None,
        session_store: SessionStore | None = None,
        clock: Clock | None = None,
    ) -> None:
        self.pool = db_pool
        self.settings = get_settings()
        self.ai = ai_orchestrator or get_ai_orchestrator()
        self.session_store = session_store or get_session_store()
        self.clock = clock
        self.fields = ProfileFields(lambda: _load_catalog().values())
        self.turn_analyzer = TurnAnalyzer(
            self.ai, get_system_prompt=get_analysis_system_prompt
        )
        self.language_policy = LanguagePolicy()
        self.profile_update_service = ProfileUpdateService()
        self.transition_policy = TransitionPolicy(self.fields)
        # Keep the raw client reachable for existing tests and narrow mocks.
        self.llm = self.ai.llm_client
        self.matching = MatchingUseCase(
            self.pool,
            self.ai,
            match_schemes=self._match_schemes,
            is_low_context=turn_policy.is_low_context_matching_turn,
            build_focus=turn_policy.build_matching_focus_text,
            get_history=session_manager.get_conversation_history,
            build_candidate_payload=scheme_relevance.build_candidate_payload,
            apply_relevance=scheme_relevance.apply_relevance_judgement,
            build_scheme_list=views.build_scheme_list_text,
            generate_no_schemes=response_generator.generate_no_schemes_response,
            collection_state=turn_policy.collection_state_for_profile,
            format_keyboard=self._format_matching_keyboard,
            store_presented=scheme_reference.store_presented_schemes,
            set_awaiting_profile_change=session_manager.set_awaiting_profile_change,
            clear_selection=session_manager.clear_selection,
            set_presented_schemes=session_manager.set_presented_schemes,
            set_currently_asking=session_manager.set_currently_asking,
        )
        questions = ProfileQuestionRenderer(
            run_matching=self._run_matching,
            profile_extractor=self.fields,
            response_generator=response_generator,
            scope_response=views.build_multi_beneficiary_scope_response,
        )
        self.renderer = TurnRenderer(
            self.pool,
            questions=questions,
            run_matching=self._run_matching,
            profile_extractor=self.fields,
            response_generator=response_generator,
            session_manager=session_manager,
            views=views,
            scheme_reference=scheme_reference,
            scheme_matcher=scheme_matcher,
            format_inline_keyboard=self._format_matching_keyboard,
            format_presented_scheme_keyboard=format_presented_scheme_keyboard,
        )

        # ponytail: live module patch points survive until Phase 6 constructor injection.
        dependencies = sys.modules[__name__]
        persistence = TurnPersistence(
            dependencies=dependencies,
            settings=self.settings,
            session_store=self.session_store,
            clock=self.clock,
        )
        commands = CommandHandler(
            self.pool,
            self.renderer,
            persistence,
            dependencies=dependencies,
            session_store=self.session_store,
        )
        self.application = ConversationApplication(
            responses=response_generator,
            analyzer=self.turn_analyzer,
            language_policy=self.language_policy,
            profile_updates=self.profile_update_service,
            transitions=self.transition_policy,
            renderer=self.renderer,
            commands=commands,
            persistence=persistence,
            session_store=self.session_store,
            clock=self.clock,
        )

    async def handle_message(self, request: ChatRequest) -> ChatResponse:
        return await self.application.handle_message(request)

    async def _run_matching(
        self,
        profile: UserProfile,
        user_message: str,
        session: Session,
        lang: str,
    ) -> RenderResult:
        """Compatibility delegate for the application matching use case."""
        result = await self.matching.run(profile, user_message, session, lang)
        return RenderResult(
            result.session,
            result.state,
            result.text,
            result.schemes,
            result.inline_keyboard,
        )

    @staticmethod
    def _format_matching_keyboard(
        schemes: list[SchemeMatch], lang: str
    ) -> list[list[dict[str, str]]] | None:
        """Keep the legacy keyboard patch point live during extraction."""
        return format_inline_keyboard(schemes, lang)

    async def _match_schemes(
        self,
        *,
        pool: asyncpg.Pool,
        profile: UserProfile,
        query_text: str | None,
    ) -> list[SchemeMatch]:
        """Keep the legacy patch point live while matching moves to application."""
        return await scheme_matcher.match_schemes(
            pool=pool,
            profile=profile,
            query_text=query_text,
        )
