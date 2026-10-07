"""AI task policy has no dependency on importing legacy wiring first."""

import asyncio
from unittest.mock import AsyncMock

from src.dss.application.conversation.ai_orchestrator import (
    AIExecutionPolicy,
    AIOrchestrator,
    AITaskType,
)
from src.dss.application.ports.llm import LLMProvider
from src.dss.domain.conversations.session import Session
from src.dss.settings import Settings


async def test_injected_timeout_fallbacks_are_instance_local() -> None:
    provider = AsyncMock(spec=LLMProvider)
    cancelled = asyncio.Event()

    async def slow(**kwargs):
        try:
            await asyncio.sleep(1)
        finally:
            cancelled.set()

    provider.analyze_message_with_meta.side_effect = slow
    events = []
    ai = AIOrchestrator(
        provider, settings=Settings(_env_file=None),
        safe_analysis=lambda language: {"language": language, "injected": True},
        safe_relevance=lambda candidates: {}, safe_generation=lambda language: "safe",
        policies={AITaskType.ANALYZE_MESSAGE: AIExecutionPolicy(0.01, "inline")},
        usage_sink=events.append,
    )
    result = await ai.analyze_message(
        session=Session(user_id="synthetic"), user_message="housing",
        conversation_history=[], system_prompt="synthetic", session_language="en",
    )
    assert result == {"language": "en", "injected": True}
    assert cancelled.is_set()
    assert events[0].error == "timeout"
    assert events[0].latency_ms == 10.0
    provider.analyze_message.assert_not_called()
