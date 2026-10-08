"""The CLI owns its canonical graph and never prints personal profile values."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from scripts import test_conversation_flow as cli
from src.dss.bootstrap import conversation, runtime
from src.dss.domain.conversations.session import Session
from src.dss.domain.profiles.profile import UserProfile
from src.dss.infrastructure.ai import fallback_client as llm_client
from src.dss.infrastructure.embeddings import fallback_client as embedding_client
from src.dss.infrastructure.sessions import session_store
from src.dss.settings import Settings


@pytest.fixture
def owned_cli(monkeypatch):
    monkeypatch.setattr(cli, "load_dotenv", lambda: None)
    settings = Settings(_env_file=None, use_bedrock=False)
    monkeypatch.setattr("src.dss.settings.Settings", lambda: settings)
    pool = SimpleNamespace(close=AsyncMock())
    open_pool = AsyncMock(return_value=pool)
    monkeypatch.setattr(runtime, "open_pool", open_pool)
    llm, embeddings = AsyncMock(), AsyncMock()
    llm_factory = Mock(return_value=llm)
    embedding_factory = Mock(return_value=embeddings)
    monkeypatch.setattr(llm_client, "FallbackLLMClient", llm_factory)
    monkeypatch.setattr(embedding_client, "FallbackEmbeddingClient", embedding_factory)
    store = session_store.InMemorySessionStore()
    monkeypatch.setattr(session_store, "InMemorySessionStore", Mock(return_value=store))
    build = Mock(wraps=conversation.build_conversation)
    monkeypatch.setattr(conversation, "build_conversation", build)
    # Fail immediately if the CLI acquires API-only resources or global state.
    for module, name in (
        (runtime, "api_runtime"),
        (runtime, "build_work_queue"),
        (runtime, "build_session_store"),
        (runtime, "LocalMemoryWorker"),
        (runtime, "TelegramClient"),
        (runtime, "SarvamClient"),
        (runtime, "BhashiniClient"),
        (session_store, "configure_session_store"),
        (session_store, "get_session_store"),
    ):
        monkeypatch.setattr(module, name, Mock(side_effect=AssertionError(name)))
    return SimpleNamespace(
        pool=pool, open_pool=open_pool, llm=llm, embeddings=embeddings,
        llm_factory=llm_factory, embedding_factory=embedding_factory,
        store=store, build=build, settings=settings,
    )


def assert_closed(resources):
    for resource in (resources.pool, resources.llm, resources.embeddings):
        resource.close.assert_awaited_once_with()


@pytest.mark.parametrize("life_event", [None, "EDUCATION"])
async def test_profile_command_reports_presence_without_personal_values(monkeypatch, capsys, owned_cli, life_event) -> None:
    profile = UserProfile(
        life_event=life_event, age=47, gender="female", category="SC", annual_income=123456,
    )
    session = Session(user_id="cli-test-user", user_profile=profile)
    await owned_cli.store.save(session)
    inputs = iter(["/profile", "/quit"])
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))

    await cli.main()

    output = capsys.readouterr().out
    assert "Age: provided" in output
    assert "Gender: provided" in output
    assert "Category: provided" in output
    assert "Income: provided" in output
    assert f"Life Event: {'provided' if life_event else 'missing'}" in output
    assert "EDUCATION" not in output
    assert "female" not in output
    assert "123456" not in output
    assert "Age: 47" not in output
    assert "Category: SC" not in output
    assert f"Completeness: {profile.completeness_score}/10" in output
    assert_closed(owned_cli)


async def test_client_close_failure_still_closes_other_resources(monkeypatch, owned_cli):
    monkeypatch.setattr("builtins.input", lambda _: "/quit")
    owned_cli.embeddings.close.side_effect = RuntimeError("synthetic close failure")
    with pytest.raises(RuntimeError, match="synthetic close failure"):
        await cli.main()
    assert_closed(owned_cli)


async def test_commands_use_the_conversation_store_without_background_work(monkeypatch, capsys, owned_cli):
    inputs = iter(["  ", " /start ", "/PROFILE", "/RESET", "/profile", "/QUIT"])
    seen = []

    def read_input(prompt):
        seen.append(owned_cli.store._sessions.get("cli-test-user"))
        assert prompt == "👤 You: "
        return next(inputs)

    monkeypatch.setattr("builtins.input", read_input)
    await cli.main()

    output = capsys.readouterr().out
    assert "✅ Database connected" in output
    assert "🤖 Bot: Ready! Type 'Namaste' to start." in output
    assert "🔄 Session reset. Type 'Namaste' to start fresh." in output
    assert "Goodbye!" in output
    assert "👋 Session ended." in output
    assert seen[0] is None and seen[1] is None
    assert seen[2].completed_turn_count == 1
    assert seen[4] is None
    assert seen[5].completed_turn_count == 0
    graph = owned_cli.build.call_args.kwargs
    assert graph["store"] is owned_cli.store
    assert graph["enqueue"].__self__.queue is None
    assert await graph["enqueue"]("cli-test-user", 8) is False
    assert not (await owned_cli.store.get("cli-test-user")).pending_memory_job
    owned_cli.open_pool.assert_awaited_once_with(owned_cli.settings)
    assert_closed(owned_cli)


@pytest.mark.parametrize("exit_error", [EOFError, KeyboardInterrupt, asyncio.CancelledError])
async def test_input_exit_closes_owned_resources(monkeypatch, capsys, owned_cli, exit_error):
    monkeypatch.setattr("builtins.input", Mock(side_effect=exit_error))
    if exit_error is EOFError:
        await cli.main()
    else:
        with pytest.raises(exit_error):
            await cli.main()
    assert "👋 Session ended." in capsys.readouterr().out
    assert_closed(owned_cli)


async def test_database_failure_exits_before_construction(monkeypatch, capsys, owned_cli):
    owned_cli.open_pool.side_effect = OSError("synthetic database failure")
    read_input = Mock(side_effect=AssertionError("must not prompt"))
    monkeypatch.setattr("builtins.input", read_input)
    await cli.main()
    output = capsys.readouterr().out
    assert "❌ Database connection failed: synthetic database failure" in output
    assert "Make sure PostgreSQL is running with the scheme data" in output
    assert "Ready!" not in output
    read_input.assert_not_called()
    owned_cli.build.assert_not_called()
    owned_cli.llm_factory.assert_not_called()
    owned_cli.embedding_factory.assert_not_called()
    owned_cli.pool.close.assert_not_awaited()


@pytest.mark.parametrize("failure", ["llm", "embeddings", "graph"])
async def test_partial_construction_closes_acquired_resources(owned_cli, failure):
    target = {
        "llm": owned_cli.llm_factory,
        "embeddings": owned_cli.embedding_factory,
        "graph": owned_cli.build,
    }[failure]
    target.side_effect = RuntimeError("synthetic construction failure")
    with pytest.raises(RuntimeError, match="synthetic construction failure"):
        await cli.main()
    owned_cli.pool.close.assert_awaited_once_with()
    if failure != "llm":
        owned_cli.llm.close.assert_awaited_once_with()
    else:
        owned_cli.llm.close.assert_not_awaited()
    if failure == "graph":
        owned_cli.embeddings.close.assert_awaited_once_with()
    else:
        owned_cli.embeddings.close.assert_not_awaited()


async def test_message_errors_continue_and_render_response(monkeypatch, capsys, owned_cli):
    handler = AsyncMock(side_effect=[
        RuntimeError("synthetic turn failure"),
        SimpleNamespace(
            text="synthetic reply",
            schemes=[SimpleNamespace(scheme=SimpleNamespace(name_hindi="synthetic scheme"))],
            inline_keyboard=[[{"text": "button", "callback_data": "test"}]],
        ),
    ])
    owned_cli.build.side_effect = lambda **kwargs: SimpleNamespace(handle_message=handler)
    inputs = iter(["first", "second", "/quit"])
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))
    await cli.main()
    output = capsys.readouterr().out
    assert "❌ Error: synthetic turn failure" in output
    assert "🤖 Bot: synthetic reply" in output
    assert "📋 Matched Schemes:" in output
    assert "• synthetic scheme" in output
    assert "[Keyboard buttons would appear here]" in output
    assert [call.args[0].message for call in handler.await_args_list] == ["first", "second"]
    assert all(call.args[0].user_id == "cli-test-user" for call in handler.await_args_list)
    assert_closed(owned_cli)
