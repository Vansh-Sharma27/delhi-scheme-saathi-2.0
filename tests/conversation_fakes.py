"""Per-test conversation graph with explicit, independently scriptable fake ports."""

from unittest.mock import AsyncMock

from src.dss.application.conversation.ai_orchestrator import AIOrchestrator
from src.dss.application.conversation.profile_fields import ProfileFields
from src.dss.application.conversation.views import SchemeViews
from src.dss.application.guidance.service import Guidance
from src.dss.application.ports.ai_tasks import AITasks
from src.dss.application.ports.llm import LLMProvider, ProviderExecutionResult
from src.dss.application.ports.office_repository import OfficeRepository
from src.dss.application.ports.rejection_rule_repository import RejectionRuleRepository
from src.dss.application.ports.scheme_repository import SchemeRepository
from src.dss.bootstrap.conversation import build_conversation
from src.dss.infrastructure.ai.fallback_client import FallbackLLMClient
from src.dss.infrastructure.ai.prompts.loader import (
    get_analysis_system_prompt,
    get_generate_response_prompt,
)
from src.dss.infrastructure.database.catalog import _load_catalog
from src.dss.infrastructure.sessions.clock import SystemClock
from src.dss.infrastructure.sessions.session_store import InMemorySessionStore
from src.dss.settings import Settings


class ConversationFixture:
    def __init__(self):
        self.clock = SystemClock()
        self.store = InMemorySessionStore(self.clock)
        self.llm = AsyncMock(spec=LLMProvider)
        self.llm.generate_response.return_value = ""
        self.llm.judge_scheme_relevance.return_value = {}
        provider = AsyncMock(spec=LLMProvider)

        async def analyze(**kwargs):
            return ProviderExecutionResult(await self.llm.analyze_message(**kwargs), None, False, 0)

        async def judge(**kwargs):
            return ProviderExecutionResult(await self.llm.judge_scheme_relevance(**kwargs), None, False, 0)

        async def generate(**kwargs):
            return ProviderExecutionResult(await self.llm.generate_response(**kwargs), None, False, 0)

        async def summarize(**kwargs):
            return ProviderExecutionResult(await self.llm.summarize_conversation(**kwargs), None, False, 0)

        provider.analyze_message_with_meta.side_effect = analyze
        provider.judge_scheme_relevance_with_meta.side_effect = judge
        provider.generate_response_with_meta.side_effect = generate
        provider.summarize_conversation_with_meta.side_effect = summarize
        settings = Settings(_env_file=None)
        self.ai = AIOrchestrator(
            provider, settings=settings,
            safe_analysis=FallbackLLMClient._safe_analysis_payload,
            safe_relevance=FallbackLLMClient._safe_relevance_payload,
            safe_generation=FallbackLLMClient._safe_generation_text,
        )
        response_ai = AsyncMock(spec=AITasks)
        response_ai.generate_response.return_value = ""
        self.responses = Guidance(response_ai, get_prompt=get_generate_response_prompt, safe_generation=FallbackLLMClient._safe_generation_text)
        self.schemes = AsyncMock(spec=SchemeRepository)
        self.schemes.get_scheme_by_id.return_value = None
        self.offices = AsyncMock(spec=OfficeRepository)
        self.offices.get_nearest_offices.return_value = []
        self.offices.get_offices_by_district.return_value = []
        self.rules = AsyncMock(spec=RejectionRuleRepository)
        self.rules.get_rules_by_scheme.return_value = []
        self.views = SchemeViews(self.schemes, self.offices, self.rules, self.responses, AsyncMock(return_value=[]))
        self.match_schemes = AsyncMock(return_value=[])

        async def match(**kwargs):
            return await self.match_schemes(**kwargs)

        self.application = build_conversation(
            settings=settings, store=self.store, clock=self.clock, ai=self.ai,
            responses=self.responses, fields=ProfileFields(lambda: _load_catalog().values()),
            views=self.views, match_schemes=match, get_analysis_prompt=get_analysis_system_prompt,
            enqueue=AsyncMock(return_value=False),
        )
        self.handle_message = self.application.handle_message
