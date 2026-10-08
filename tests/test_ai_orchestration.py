"""Tests for the AI orchestration and working-memory layer."""

import asyncio
from unittest.mock import AsyncMock

import pytest

from src.dss.application.conversation.ai_orchestrator import (
    AIExecutionPolicy,
    AIOrchestrator,
    AITaskType,
    LLMUsageEvent,
)
from src.dss.application.ports.llm import LLMProvider, ProviderExecutionResult
from src.dss.infrastructure.ai.fallback_client import FallbackLLMClient
from src.dss.settings import Settings
from src.models.scheme import EligibilityCriteria, Scheme, SchemeMatch
from src.models.session import ConversationMemory, Message, Session, UserProfile


def _make_match(scheme_id: str, deterministic_score: float) -> SchemeMatch:
    """Create a minimal scheme match for gating tests."""
    return SchemeMatch(
        scheme=Scheme(
            id=scheme_id,
            name=f"Scheme {scheme_id}",
            name_hindi=f"योजना {scheme_id}",
            department="Dept",
            department_hindi="विभाग",
            level="state",
            eligibility=EligibilityCriteria(),
            life_events=["HOUSING"],
            description="Test scheme",
            description_hindi="परीक्षण योजना",
            documents_required=[],
        ),
        deterministic_score=deterministic_score,
    )


@pytest.mark.asyncio
async def test_generate_response_includes_working_memory_context() -> None:
    """Free-form response generation should inject working memory into the prompt context."""
    fake_llm = AsyncMock(spec=LLMProvider)
    fake_llm.generate_response_with_meta = AsyncMock(
        return_value=ProviderExecutionResult(
            output="Generated response",
            provider="bedrock",
            fallback_used=False,
            latency_ms=12.0,
        )
    )
    orchestrator = AIOrchestrator(
        llm_client=fake_llm,
        settings=Settings(_env_file=None),
        safe_analysis=FallbackLLMClient._safe_analysis_payload,
        safe_relevance=FallbackLLMClient._safe_relevance_payload,
        safe_generation=FallbackLLMClient._safe_generation_text,
    )
    session = Session(
        user_id="user-memory-context",
        working_memory=ConversationMemory(
            summary="User asked about housing help.",
            profile_facts=["Need area: HOUSING"],
        ),
    )

    response = await orchestrator.generate_response(
        session=session,
        context={"response_mode": "scheme_question_answer"},
        system_prompt="test",
        user_language="en",
    )

    assert response == "Generated response"
    context = fake_llm.generate_response_with_meta.await_args.kwargs["context"]
    assert context["working_memory"]["summary"] == "User asked about housing help."
    assert "Need area: HOUSING" in context["working_memory"]["profile_facts"]


@pytest.mark.asyncio
async def test_refresh_working_memory_builds_summary_and_scheme_context() -> None:
    """Background memory refresh should combine LLM summary with deterministic facts."""
    fake_llm = AsyncMock(spec=LLMProvider)
    fake_llm.summarize_conversation_with_meta = AsyncMock(
        return_value=ProviderExecutionResult(
            output="User wants housing support and needs the next eligibility step.",
            provider="bedrock",
            fallback_used=False,
            latency_ms=18.0,
        )
    )
    orchestrator = AIOrchestrator(
        llm_client=fake_llm,
        settings=Settings(_env_file=None),
        safe_analysis=FallbackLLMClient._safe_analysis_payload,
        safe_relevance=FallbackLLMClient._safe_relevance_payload,
        safe_generation=FallbackLLMClient._safe_generation_text,
    )
    session = Session(
        user_id="user-refresh-memory",
        user_profile=UserProfile(life_event="HOUSING", annual_income=300000),
        selected_scheme_id="SCH-1",
        discussed_schemes=["SCH-1", "SCH-2"],
        messages=[
            Message(role="user", content="I need housing help."),
            Message(role="assistant", content="Please share your annual family income."),
        ],
    )

    memory = await orchestrator.refresh_working_memory(session)

    assert memory.summary == "User wants housing support and needs the next eligibility step."
    assert "Need area: HOUSING" in memory.profile_facts
    assert "Annual income: ₹3 lakh" in memory.profile_facts
    assert memory.active_scheme_ids[0] == "SCH-1"


def test_should_run_relevance_judge_only_for_ambiguous_matches() -> None:
    """AI relevance judging should be reserved for ambiguous deterministic rankings."""
    orchestrator = AIOrchestrator(
        llm_client=AsyncMock(spec=LLMProvider),
        settings=Settings(_env_file=None),
        safe_analysis=FallbackLLMClient._safe_analysis_payload,
        safe_relevance=FallbackLLMClient._safe_relevance_payload,
        safe_generation=FallbackLLMClient._safe_generation_text,
    )

    assert orchestrator.should_run_relevance_judge(
        [_make_match("SCH-CLEAR", 0.97), _make_match("SCH-LOW", 0.60)]
    ) is False
    assert orchestrator.should_run_relevance_judge(
        [_make_match("SCH-A", 0.84), _make_match("SCH-B", 0.80)]
    ) is True


@pytest.mark.asyncio
async def test_analyze_message_enforces_deadline_cancels_and_records_timeout() -> None:
    """A real expired deadline must cancel work and emit timeout telemetry."""
    fake_llm = AsyncMock(spec=LLMProvider)
    cancelled = asyncio.Event()
    events: list[LLMUsageEvent] = []

    async def slow_analysis(**_kwargs: object) -> ProviderExecutionResult[dict[str, object]]:
        try:
            await asyncio.sleep(1)
        except asyncio.CancelledError:
            cancelled.set()
            raise
        return ProviderExecutionResult(
            output={"intent": "should-not-complete"},
            provider=None,
            fallback_used=False,
            latency_ms=1000.0,
        )

    fake_llm.analyze_message_with_meta = AsyncMock(side_effect=slow_analysis)
    orchestrator = AIOrchestrator(
        llm_client=fake_llm,
        settings=Settings(_env_file=None),
        safe_analysis=FallbackLLMClient._safe_analysis_payload,
        safe_relevance=FallbackLLMClient._safe_relevance_payload,
        safe_generation=FallbackLLMClient._safe_generation_text,
        policies={
            AITaskType.ANALYZE_MESSAGE: AIExecutionPolicy(
                timeout_seconds=0.01,
                priority="inline",
            )
        },
        usage_sink=events.append,
    )
    session = Session(user_id="timeout-user")

    output = await orchestrator.analyze_message(
        session=session,
        user_message="I need housing",
        conversation_history=[],
        system_prompt="test",
        session_language="en",
    )

    assert cancelled.is_set()
    assert output["intent"] == "unknown"
    assert len(events) == 1
    assert events[0].task_type == AITaskType.ANALYZE_MESSAGE.value
    assert events[0].error == "timeout"
    assert events[0].latency_ms == 10.0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("task", "provider_method", "kwargs", "payload", "priority"),
    [
        (
            "analyze_message", "analyze_message",
            {"user_message": "housing", "conversation_history": [],
             "system_prompt": "test", "session_language": "en"},
            {"intent": "question"}, "inline",
        ),
        (
            "judge_scheme_relevance", "judge_scheme_relevance",
            {"user_message": "housing", "conversation_history": [],
             "candidate_schemes": [], "session_language": "en"},
            {"overall_confidence": 0.5}, "inline",
        ),
        (
            "generate_response", "generate_response",
            {"context": {}, "system_prompt": "test", "user_language": "en"},
            "Generated response", "inline",
        ),
        (
            "refresh_working_memory", "summarize_conversation",
            {"queue_lag_ms": 7.0}, "Housing summary", "background",
        ),
    ],
)
async def test_tasks_use_provider_metadata_despite_plain_method_override(
    task, provider_method, kwargs, payload, priority,
) -> None:
    """All tasks use the metadata port even when a plain method exists on the instance."""
    provider = AsyncMock(spec=LLMProvider)
    plain = AsyncMock(side_effect=AssertionError("Plain provider method called"))
    setattr(provider, provider_method, plain)
    metadata = getattr(provider, f"{provider_method}_with_meta")
    metadata.return_value = ProviderExecutionResult(
        output=payload, provider="grok", fallback_used=True, latency_ms=12.34,
        error="provider diagnostic",
    )
    events: list[LLMUsageEvent] = []
    orchestrator = AIOrchestrator(
        llm_client=provider,
        settings=Settings(_env_file=None),
        safe_analysis=FallbackLLMClient._safe_analysis_payload,
        safe_relevance=FallbackLLMClient._safe_relevance_payload,
        safe_generation=FallbackLLMClient._safe_generation_text,
        usage_sink=events.append,
    )
    session = Session(
        user_id="metadata-user", messages=[Message(role="user", content="housing")],
    )

    output = await getattr(orchestrator, task)(session=session, **kwargs)

    assert (output.summary if isinstance(output, ConversationMemory) else output) == payload
    plain.assert_not_awaited()
    metadata.assert_awaited_once()
    assert metadata.await_args.kwargs["priority"] == priority
    assert len(events) == 1
    assert events[0].task_type == task
    assert events[0].session_id == session.user_id
    assert events[0].provider == "grok"
    assert events[0].fallback_used is True
    assert events[0].latency_ms == 12.34
    assert events[0].error == "provider diagnostic"
    assert events[0].queue_lag_ms == kwargs.get("queue_lag_ms")
