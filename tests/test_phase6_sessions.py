"""Explicit session dependencies isolate independently constructed applications."""

from datetime import UTC, datetime

from src.dss.application.conversation import sessions
from src.dss.infrastructure.sessions.session_store import InMemorySessionStore


class FixedClock:
    def now(self) -> datetime:
        return datetime(2026, 1, 1, tzinfo=UTC)


async def test_session_operations_use_only_the_supplied_store() -> None:
    clock = FixedClock()
    first = InMemorySessionStore(clock)
    second = InMemorySessionStore(clock)
    session = await sessions.get_or_create_session("synthetic", store=first, clock=clock)
    assert session.clock is clock
    assert session.created_at == session.updated_at == clock.now()
    assert await second.get("synthetic") is None
    changed = sessions.set_language(session, "en", locked=True)
    await sessions.save_session(changed, store=first)
    loaded = await first.get("synthetic")
    assert loaded.language_locked and loaded.language_preference == "en"
    await sessions.delete_session("synthetic", store=second)
    assert await first.get("synthetic") is not None
    await sessions.delete_session("synthetic", store=first)
    assert await first.get("synthetic") is None
