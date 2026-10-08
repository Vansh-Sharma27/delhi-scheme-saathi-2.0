"""Clock threading preserves session timestamps, TTL, and queue lag."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, Mock

import pytest

from src.dss.application.conversation import sessions as session_manager
from src.dss.application.conversation.background_memory import MemoryJobs
from src.dss.application.ports.ai_tasks import AITasks
from src.dss.application.ports.session_repository import SessionStore
from src.dss.application.ports.work_queue import AIWorkQueue
from src.dss.infrastructure.queues.work_queue import deserialize_work_item, serialize_work_item
from src.dss.infrastructure.sessions.session_store import DynamoDBSessionStore, InMemorySessionStore
from src.models.session import ConversationMemory, ConversationState, Session, UserProfile


class FixedClock:
    def __init__(self) -> None:
        self.value = datetime(2026, 1, 1, 12, tzinfo=UTC)

    def now(self) -> datetime:
        return self.value


@pytest.mark.asyncio
async def test_clock_survives_session_mutations_storage_and_reset() -> None:
    clock = FixedClock()
    store = InMemorySessionStore(clock=clock)
    session = await session_manager.get_or_create_session("synthetic", store=store, clock=clock)
    created = session.created_at
    assert session.updated_at == created == clock.now()
    for i in range(14):
        clock.value += timedelta(seconds=1)
        session = await session_manager.add_message(session, "user", str(i))
        assert session.messages[-1].timestamp == session.updated_at == clock.now()
    assert len(session.messages) == 12

    changes = [
        lambda s: s.copy_with(language_locked=True),
        lambda s: session_manager.update_state(s, ConversationState.SCHEME_DETAILS),
        lambda s: session_manager.update_profile(s, UserProfile(age=30)),
        lambda s: session_manager.select_scheme(s, "S1"),
        lambda s: session_manager.set_language(s, "en", locked=True),
        lambda s: session_manager.set_currently_asking(s, "age"),
        lambda s: session_manager.set_skipped_fields(s, ["category"]),
        lambda s: session_manager.set_presented_schemes(s, [{"id": "S1"}]),
        lambda s: session_manager.set_awaiting_profile_change(s, True),
        session_manager.clear_selection,
        session_manager.mark_turn_completed,
        lambda s: session_manager.set_pending_memory_job(s, True),
        lambda s: session_manager.apply_working_memory(s, ConversationMemory(summary="synthetic")),
        session_manager.reset_session,
    ]
    for change in changes:
        clock.value += timedelta(seconds=1)
        session = change(session)
        assert session.clock is clock
        assert session.updated_at == clock.now()
        assert session.created_at == created

    explicit = created - timedelta(days=1)
    session = session.copy_with(updated_at=explicit)
    item = session.to_dynamodb_item()
    assert item["ttl"] == int(explicit.timestamp()) + 7 * 86400
    assert "clock" not in item and "_clock" not in session.model_dump()
    await store.save(session)
    loaded = await store.get(session.user_id)
    assert loaded is not None and loaded.clock is clock
    assert loaded.updated_at == clock.now()
    clock.value += timedelta(seconds=1)
    assert loaded.copy_with().updated_at == clock.now()


@pytest.mark.asyncio
async def test_dynamodb_clock_fallback_preserves_stored_timestamp_and_ttl(monkeypatch: pytest.MonkeyPatch) -> None:
    clock = FixedClock()
    table = Mock()
    resource = Mock()
    resource.Table.return_value = table
    monkeypatch.setattr("boto3.resource", Mock(return_value=resource))
    store = DynamoDBSessionStore("synthetic", clock=clock)
    table.get_item.return_value = {"Item": {"user_id": "synthetic"}}
    session = await store.get("synthetic")
    assert session is not None and session.clock is clock
    assert session.created_at == session.updated_at == clock.now()
    timestamp = session.updated_at
    clock.value += timedelta(days=1)
    await store.save(session)
    item = table.put_item.call_args.kwargs["Item"]
    assert item["ttl"] == int(timestamp.timestamp()) + 7 * 86400
    assert item["updated_at"] == timestamp.isoformat()
    table.get_item.return_value = {"Item": item}
    loaded = await store.get("synthetic")
    assert loaded is not None and loaded.updated_at == timestamp


@pytest.mark.asyncio
async def test_queue_clock_drives_enqueue_fallback_and_worker_lag() -> None:
    clock = FixedClock()
    queue = AsyncMock(spec=AIWorkQueue)
    store = AsyncMock(spec=SessionStore)
    orchestrator = AsyncMock(spec=AITasks)
    jobs = MemoryJobs(store=store, ai=orchestrator, clock=clock, queue=queue)
    assert await jobs.enqueue("synthetic", 2)
    item = queue.enqueue.call_args.args[0]
    assert item.enqueued_at == clock.now()
    payload = serialize_work_item(item)
    assert deserialize_work_item(payload, clock=clock).enqueued_at == item.enqueued_at
    del payload["enqueued_at"]
    assert deserialize_work_item(payload, clock=clock).enqueued_at == clock.now()

    session = Session(user_id="synthetic", pending_memory_job=True, completed_turn_count=2)
    store.get.return_value = session
    orchestrator.refresh_working_memory.return_value = ConversationMemory(summary="synthetic")
    clock.value += timedelta(seconds=3)
    await jobs.process(item)
    assert orchestrator.refresh_working_memory.call_args.kwargs["queue_lag_ms"] == 3000
    saved = store.save.call_args.args[0]
    assert saved.updated_at == clock.now() and not saved.pending_memory_job
    orchestrator.refresh_working_memory.side_effect = RuntimeError("synthetic failure")
    await jobs.process(item)
    assert not store.save.call_args.args[0].pending_memory_job
