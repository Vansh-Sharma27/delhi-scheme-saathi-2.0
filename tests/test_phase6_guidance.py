"""Constructed guidance uses its own AI and preserves grounded fallbacks."""

from unittest.mock import AsyncMock

from src.dss.application.guidance.service import Guidance
from src.dss.application.ports.ai_tasks import AITasks
from src.dss.domain.conversations.session import Session


async def test_guidance_uses_injected_ai_and_keeps_grounded_text_on_safe_output() -> None:
    ai = AsyncMock(spec=AITasks)
    ai.generate_response.return_value = "safe"
    guidance = Guidance(ai, get_prompt=lambda: "synthetic", safe_generation=lambda lang: "safe")
    session = Session(user_id="synthetic", language_preference="en")
    text = "योजना की जानकारी"
    assert await guidance.ensure_response_language(session, text, "en") == text
    assert ai.generate_response.await_args.kwargs["context"]["source_text"] == text
    ai.generate_response.return_value = "constructed response"
    assert await guidance.generate_response(session, {}) == "constructed response"
    assert ai.generate_response.await_args.kwargs["system_prompt"] == "synthetic"
    assert ai.generate_response.await_args.kwargs["context"]["conversation_state"] == "GREETING"
