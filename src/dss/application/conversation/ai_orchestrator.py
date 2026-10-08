"""Central orchestration layer for all live LLM usage."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, TypeVar, cast

from src.dss.application.conversation.memory import build_working_memory, working_memory_payload
from src.dss.application.ports.llm import LLMProvider, ProviderExecutionResult, TaskPriority
from src.dss.domain.conversations.session import ConversationMemory, Session
from src.dss.domain.schemes.scheme import SchemeMatch
from src.dss.observability.llm_usage import LLMUsageEvent as LLMUsageEvent
from src.dss.observability.llm_usage import log_llm_usage
from src.dss.settings import Settings

logger = logging.getLogger(__name__)

T = TypeVar("T")


class AITaskType(StrEnum):
    """Task classes for policy and telemetry."""

    ANALYZE_MESSAGE = "analyze_message"
    JUDGE_SCHEME_RELEVANCE = "judge_scheme_relevance"
    GENERATE_RESPONSE = "generate_response"
    REFRESH_WORKING_MEMORY = "refresh_working_memory"


@dataclass(frozen=True, slots=True)
class AIExecutionPolicy:
    """Execution controls for a specific AI task."""

    timeout_seconds: float
    priority: str


class AIOrchestrator:
    """Apply task policy, timeouts, and telemetry to shared LLM usage."""

    _POLICIES = {
        AITaskType.ANALYZE_MESSAGE: AIExecutionPolicy(timeout_seconds=8.0, priority="inline"),
        AITaskType.JUDGE_SCHEME_RELEVANCE: AIExecutionPolicy(
            timeout_seconds=3.0, priority="inline"
        ),
        AITaskType.GENERATE_RESPONSE: AIExecutionPolicy(timeout_seconds=8.0, priority="inline"),
        AITaskType.REFRESH_WORKING_MEMORY: AIExecutionPolicy(
            timeout_seconds=20.0,
            priority="background",
        ),
    }

    def __init__(
        self,
        llm_client: LLMProvider,
        *,
        settings: Settings,
        safe_analysis: Callable[[str], dict[str, Any]],
        safe_relevance: Callable[[list[dict[str, Any]]], dict[str, Any]],
        safe_generation: Callable[[str], str],
        policies: Mapping[AITaskType, AIExecutionPolicy] | None = None,
        usage_sink: Callable[[LLMUsageEvent], None] | None = None,
    ) -> None:
        self.settings = settings
        self.llm_client = llm_client
        self.safe_analysis = safe_analysis
        self.safe_relevance = safe_relevance
        self.safe_generation = safe_generation
        self._policies = dict(self._POLICIES)
        if policies:
            self._policies.update(policies)
        self._usage_sink = usage_sink

    @staticmethod
    def _estimate_prompt_chars(*parts: object) -> int:
        """Approximate prompt size without relying on provider token APIs."""
        total = 0
        for part in parts:
            if part in (None, "", [], {}, ()):
                continue
            total += len(json.dumps(part, ensure_ascii=False, default=str))
        return total

    def _log_usage(
        self,
        *,
        task_type: AITaskType,
        session_id: str | None,
        prompt_chars: int,
        result: ProviderExecutionResult[Any],
        queue_lag_ms: float | None = None,
    ) -> None:
        """Emit a structured usage log for observability."""
        event = LLMUsageEvent(
            task_type=task_type.value,
            session_id=session_id,
            provider=result.provider,
            fallback_used=result.fallback_used,
            latency_ms=round(result.latency_ms, 2),
            prompt_chars=prompt_chars,
            queue_lag_ms=queue_lag_ms,
            error=result.error,
        )
        if self._usage_sink is not None:
            self._usage_sink(event)
        log_llm_usage(event, logger)

    async def _run_task(
        self,
        *,
        task_type: AITaskType,
        session_id: str | None,
        prompt_chars: int,
        call: Callable[[str], asyncio.Future[ProviderExecutionResult[T]]] | Callable[[str], Any],
        safe_output: Callable[[], T],
        queue_lag_ms: float | None = None,
    ) -> T:
        """Run one orchestrated LLM task under policy controls."""
        policy = self._policies[task_type]
        try:
            async with asyncio.timeout(policy.timeout_seconds):
                result = await call(policy.priority)
        except TimeoutError:
            result = ProviderExecutionResult(
                output=safe_output(),
                provider=None,
                fallback_used=False,
                latency_ms=policy.timeout_seconds * 1000,
                error="timeout",
            )

        self._log_usage(
            task_type=task_type,
            session_id=session_id,
            prompt_chars=prompt_chars,
            result=result,
            queue_lag_ms=queue_lag_ms,
        )
        return result.output

    def should_run_relevance_judge(self, matches: list[SchemeMatch]) -> bool:
        """Only invoke LLM judging when deterministic ranking is ambiguous."""
        if not matches:
            return False

        top_score = matches[0].deterministic_score
        second_score = matches[1].deterministic_score if len(matches) > 1 else 0.0
        score_gap = top_score - second_score

        return (
            top_score <= self.settings.ai_relevance_min_deterministic_score
            or score_gap < self.settings.ai_relevance_score_gap_threshold
        )

    async def analyze_message(
        self,
        *,
        session: Session,
        user_message: str,
        conversation_history: list[dict[str, str]],
        system_prompt: str,
        session_language: str,
    ) -> dict[str, Any]:
        """Analyze the user's message with continuity-aware context."""
        user_profile = {
            **session.user_profile.model_dump(),
            "_currently_asking": session.currently_asking,
        }
        memory = working_memory_payload(session)
        prompt_chars = self._estimate_prompt_chars(
            user_message,
            conversation_history[-10:],
            user_profile,
            memory,
        )

        return await self._run_task(
            task_type=AITaskType.ANALYZE_MESSAGE,
            session_id=session.user_id,
            prompt_chars=prompt_chars,
            call=lambda priority: self.llm_client.analyze_message_with_meta(
                user_message=user_message,
                conversation_history=conversation_history,
                current_state=session.state.value,
                user_profile=user_profile,
                system_prompt=system_prompt,
                session_language=session_language,
                working_memory=memory,
                priority=cast(TaskPriority, priority),
            ),
            safe_output=lambda: self.safe_analysis(session_language),
        )

    async def judge_scheme_relevance(
        self,
        *,
        session: Session,
        user_message: str,
        conversation_history: list[dict[str, str]],
        candidate_schemes: list[dict[str, Any]],
        session_language: str,
    ) -> dict[str, Any]:
        """LLM gate for ambiguous deterministic scheme matches."""
        memory = working_memory_payload(session)
        prompt_chars = self._estimate_prompt_chars(
            user_message,
            conversation_history[-8:],
            session.user_profile.model_dump(),
            candidate_schemes,
            memory,
        )

        return await self._run_task(
            task_type=AITaskType.JUDGE_SCHEME_RELEVANCE,
            session_id=session.user_id,
            prompt_chars=prompt_chars,
            call=lambda priority: self.llm_client.judge_scheme_relevance_with_meta(
                user_message=user_message,
                conversation_history=conversation_history,
                current_state=session.state.value,
                user_profile=session.user_profile.model_dump(),
                candidate_schemes=candidate_schemes,
                session_language=session_language,
                working_memory=memory,
                priority=cast(TaskPriority, priority),
            ),
            safe_output=lambda: self.safe_relevance(candidate_schemes),
        )

    async def generate_response(
        self,
        *,
        session: Session,
        context: dict[str, Any],
        system_prompt: str,
        user_language: str,
    ) -> str:
        """Generate a free-form response with working memory attached."""
        enriched_context = dict(context)
        memory = working_memory_payload(session)
        if memory is not None:
            enriched_context["working_memory"] = memory

        prompt_chars = self._estimate_prompt_chars(
            enriched_context,
            system_prompt,
            user_language,
        )

        return await self._run_task(
            task_type=AITaskType.GENERATE_RESPONSE,
            session_id=session.user_id,
            prompt_chars=prompt_chars,
            call=lambda priority: self.llm_client.generate_response_with_meta(
                context=enriched_context,
                system_prompt=system_prompt,
                user_language=user_language,
                priority=cast(TaskPriority, priority),
            ),
            safe_output=lambda: self.safe_generation(user_language),
        )

    async def refresh_working_memory(
        self,
        session: Session,
        *,
        queue_lag_ms: float | None = None,
    ) -> ConversationMemory:
        """Refresh compact working memory from recent turns and summary state."""
        if not session.messages:
            return build_working_memory(session, session.working_memory.summary)

        messages = [
            {"role": message.role, "content": message.content} for message in session.messages
        ]
        prompt_chars = self._estimate_prompt_chars(messages, session.working_memory.summary)

        summary = await self._run_task(
            task_type=AITaskType.REFRESH_WORKING_MEMORY,
            session_id=session.user_id,
            prompt_chars=prompt_chars,
            queue_lag_ms=queue_lag_ms,
            call=lambda priority: self.llm_client.summarize_conversation_with_meta(
                messages=messages,
                current_summary=session.working_memory.summary,
                priority=cast(TaskPriority, priority),
            ),
            safe_output=lambda: session.working_memory.summary or "",
        )

        refreshed = build_working_memory(session, summary or session.working_memory.summary)
        if refreshed == session.working_memory:
            return session.working_memory
        return refreshed
