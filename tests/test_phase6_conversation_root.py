"""The canonical graph runs without legacy wiring or module-global dependencies."""

from unittest.mock import AsyncMock

from src.dss.application.conversation.contracts import ChatRequest
from src.dss.application.conversation.profile_fields import ProfileFields
from src.dss.application.conversation.views import SchemeViews
from src.dss.application.guidance.service import Guidance
from src.dss.application.ports.ai_tasks import AITasks
from src.dss.application.ports.matching import MatchSchemes
from src.dss.bootstrap.conversation import build_conversation
from src.dss.infrastructure.sessions.session_store import InMemorySessionStore
from src.dss.settings import Settings
from tests.test_phase6_sessions import FixedClock


async def test_constructed_graph_persists_commands_and_keeps_stores_isolated() -> None:
    ai = AsyncMock(spec=AITasks)
    clock = FixedClock()
    first, second = InMemorySessionStore(clock), InMemorySessionStore(clock)
    responses = Guidance(ai, get_prompt=lambda: "synthetic", safe_generation=lambda lang: "safe")
    service = build_conversation(
        settings=Settings(_env_file=None), store=first, clock=clock, ai=ai,
        responses=responses, fields=ProfileFields(lambda: []),
        views=AsyncMock(spec=SchemeViews), match_schemes=AsyncMock(spec=MatchSchemes),
        get_analysis_prompt=lambda: "synthetic", enqueue=AsyncMock(return_value=False),
    )
    response = await service.handle_message(ChatRequest(user_id="synthetic", message="/start"))
    assert response.text == responses.generate_greeting_response("hi")
    saved = await first.get("synthetic")
    assert saved.completed_turn_count == 1
    assert len(saved.messages) == 2
    assert saved.clock is clock
    assert await second.get("synthetic") is None
    ai.analyze_message.assert_not_called()
