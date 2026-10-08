"""Constructed Telegram handling uses the same supplied session store as chat."""

from unittest.mock import AsyncMock

from src.dss.application.conversation.contracts import ChatResponse
from src.dss.application.ports.notifier import Notifier
from src.dss.application.ports.speech import SpeechProvider
from src.dss.infrastructure.sessions.session_store import InMemorySessionStore
from src.dss.interfaces.telegram.dispatch import TelegramHandler
from tests.test_phase6_sessions import FixedClock


async def test_telegram_dispatch_reads_injected_store_and_preserves_callback() -> None:
    notifier = AsyncMock(spec=Notifier)
    speech = AsyncMock(spec=SpeechProvider)
    store, clock = InMemorySessionStore(), FixedClock()
    conversation = AsyncMock(return_value=ChatResponse(text="synthetic", language="en"))
    handler = TelegramHandler(notifier, speech, store, clock, conversation)
    result = await handler.handle({"update_id": 1, "callback_query": {
        "id": "synthetic-callback", "from": {"id": 123}, "data": "lang:en",
        "message": {"chat": {"id": 123}, "text": "Choose language"},
    }})
    assert result == {"status": "ok"}
    assert await store.get("123") is not None
    assert conversation.await_args.args[0].callback_data == "lang:en"
    notifier.answer_callback_query.assert_awaited_once_with("synthetic-callback")
    notifier.send_text.assert_awaited_once_with(123, "synthetic")
