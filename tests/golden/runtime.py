"""Golden scenarios through the canonical composition root and injected ports."""

import asyncio
from unittest.mock import AsyncMock

from src.dss.application.conversation.ai_orchestrator import (
    AIExecutionPolicy,
    AIOrchestrator,
    AITaskType,
)
from src.dss.application.conversation.contracts import ChatRequest
from src.dss.application.conversation.profile_fields import ProfileFields
from src.dss.application.conversation.views import SchemeViews
from src.dss.application.guidance.service import Guidance
from src.dss.application.matching.scheme_matcher import SchemeMatcher
from src.dss.application.ports.ai_tasks import AITasks
from src.dss.application.ports.embeddings import EmbeddingProvider
from src.dss.application.ports.llm import LLMProvider, ProviderExecutionResult
from src.dss.application.ports.office_repository import OfficeRepository
from src.dss.application.ports.rejection_rule_repository import RejectionRuleRepository
from src.dss.application.ports.scheme_repository import SchemeRepository
from src.dss.bootstrap.conversation import build_conversation
from src.dss.domain.schemes.scheme import SchemeCandidate
from src.dss.infrastructure.ai.fallback_client import FallbackLLMClient
from src.dss.infrastructure.ai.prompts.loader import (
    get_analysis_system_prompt,
    get_generate_response_prompt,
)
from src.dss.infrastructure.database.catalog import _load_catalog, get_canonical_life_events
from src.dss.infrastructure.embeddings.fallback_client import EMBEDDING_DIM
from src.dss.infrastructure.sessions.session_store import InMemorySessionStore
from src.dss.settings import Settings
from tests.golden.harness import (
    _DEFAULT_JUDGE_RESULT,
    _TIMEOUT_SECONDS,
    ScenarioResult,
    TurnRecord,
    _event_snapshot,
    _FixedClock,
    _model_dump,
)


async def run_scenario(scenario_id, user_id, turns, *, session_store=None):
    clock = _FixedClock()
    store = session_store if session_store is not None else InMemorySessionStore(clock)
    result = ScenarioResult(scenario_id=scenario_id)
    events = []
    llm = AsyncMock(spec=LLMProvider)
    ai = AIOrchestrator(
        llm, settings=Settings(_env_file=None),
        safe_analysis=FallbackLLMClient._safe_analysis_payload,
        safe_relevance=FallbackLLMClient._safe_relevance_payload,
        safe_generation=FallbackLLMClient._safe_generation_text,
        policies={AITaskType.ANALYZE_MESSAGE: AIExecutionPolicy(_TIMEOUT_SECONDS, "inline")},
        usage_sink=events.append,
    )
    schemes = AsyncMock(spec=SchemeRepository)
    offices = AsyncMock(spec=OfficeRepository)
    rules = AsyncMock(spec=RejectionRuleRepository)
    rules.get_rules_by_scheme.return_value = []
    offices.get_nearest_offices.return_value = []
    offices.get_offices_by_district.return_value = []
    response_ai = AsyncMock(spec=AITasks)
    responses = Guidance(response_ai, get_prompt=get_generate_response_prompt, safe_generation=FallbackLLMClient._safe_generation_text)
    views = SchemeViews(schemes, offices, rules, responses, AsyncMock(return_value=[]))
    embeddings = AsyncMock(spec=EmbeddingProvider)
    # Golden cases supply evaluated facts; independent SQL/evaluator tests remain authoritative.
    matcher = SchemeMatcher(
        schemes, embeddings, get_canonical_life_events, embedding_dimension=EMBEDDING_DIM,
        evaluate=lambda scheme, profile: next(
            match.eligibility_match for match in turn_spec.match_result if match.scheme is scheme
        ),
    )
    service = build_conversation(
        settings=Settings(_env_file=None), store=store, clock=clock, ai=ai,
        responses=responses, fields=ProfileFields(lambda: _load_catalog().values()),
        views=views, match_schemes=matcher.match_schemes,
        get_analysis_prompt=get_analysis_system_prompt, enqueue=AsyncMock(return_value=False),
    )
    for turn_spec in turns:
        start = len(events)
        cancelled = False
        if turn_spec.llm_timeout:
            async def slow(_turn=turn_spec, **kwargs):
                nonlocal cancelled
                try:
                    await asyncio.sleep(_TIMEOUT_SECONDS * 10)
                except asyncio.CancelledError:
                    cancelled = True
                    raise
                return ProviderExecutionResult(_turn.llm_analysis, None, False, 0)
            llm.analyze_message_with_meta.side_effect = slow
        else:
            llm.analyze_message_with_meta.side_effect = None
            llm.analyze_message_with_meta.return_value = ProviderExecutionResult(turn_spec.llm_analysis, None, False, 0)
        llm.judge_scheme_relevance_with_meta.return_value = ProviderExecutionResult(
            turn_spec.llm_judge if turn_spec.llm_judge is not None else _DEFAULT_JUDGE_RESULT,
            None, False, 0,
        )
        schemes.retrieve_candidates.return_value = [SchemeCandidate(scheme=m.scheme, similarity=m.similarity) for m in turn_spec.match_result]
        embeddings.get_embedding.side_effect = RuntimeError("embedding provider unavailable") if turn_spec.embedding_failure else None
        embeddings.get_embedding.return_value = [0.0] * EMBEDDING_DIM
        schemes.get_scheme_by_id.return_value = turn_spec.scheme_for_details
        response_ai.generate_response.return_value = turn_spec.llm_generate or ""
        response = await service.handle_message(ChatRequest(
            user_id=user_id, message=turn_spec.message, message_type=turn_spec.message_type,
            callback_data=turn_spec.callback_data,
        ))
        session = await store.get(user_id)
        record = TurnRecord(
            response_text=response.text, response_text_hindi=response.text_hindi,
            response_audio_url=response.audio_url,
            response_documents=[_model_dump(x) for x in response.documents],
            response_rejection_warnings=[_model_dump(x) for x in response.rejection_warnings],
            response_offices=[_model_dump(x) for x in response.offices],
            next_state=response.next_state or "", language=response.language,
            schemes=[_model_dump(x) for x in response.schemes], inline_keyboard=response.inline_keyboard,
            ai_events=[_event_snapshot(x) for x in events[start:]], llm_timeout_cancelled=cancelled,
        )
        if session is not None:
            record.session_user_id = session.user_id
            record.session_state = session.state.value
            record.session_profile = session.user_profile.model_dump(mode="json")
            record.session_messages = [m.model_dump(mode="json") for m in session.messages]
            record.session_working_memory = session.working_memory.model_dump(mode="json")
            record.session_discussed_schemes = list(session.discussed_schemes)
            record.session_selected_scheme_id = session.selected_scheme_id
            record.session_presented_schemes = list(session.presented_schemes)
            record.session_language_preference = session.language_preference
            record.session_language_locked = session.language_locked
            record.session_currently_asking = session.currently_asking
            record.session_skipped_fields = list(session.skipped_fields)
            record.session_awaiting_profile_change = session.awaiting_profile_change
            record.session_completed_turn_count = session.completed_turn_count
            record.session_last_memory_refresh_turn = session.last_memory_refresh_turn
            record.session_pending_memory_job = session.pending_memory_job
            record.session_created_at = session.created_at.isoformat()
            record.session_updated_at = session.updated_at.isoformat()
            record.session_metadata = dict(session.metadata)
        result.turns.append(record)
    return result
