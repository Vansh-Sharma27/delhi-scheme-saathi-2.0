"""The interactive profile command must not print personal field values."""

from unittest.mock import AsyncMock, MagicMock

from scripts import test_conversation_flow as cli
from src.db import connection, session_store
from src.dss.domain.conversations.session import Session
from src.dss.domain.profiles.profile import UserProfile
from src.services import conversation, session_manager


async def test_profile_command_reports_presence_without_personal_values(monkeypatch, capsys) -> None:
    profile = UserProfile(age=47, gender="female", category="SC", annual_income=123456)
    session = Session(user_id="synthetic-cli-user", user_profile=profile)
    inputs = iter(["/profile", "/quit"])
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))
    monkeypatch.setattr(cli, "load_dotenv", lambda: None)
    monkeypatch.setattr(connection, "init_pool", AsyncMock(return_value=object()))
    monkeypatch.setattr(connection, "close_pool", AsyncMock())
    monkeypatch.setattr(session_store, "configure_session_store", MagicMock())
    monkeypatch.setattr(conversation, "ConversationService", MagicMock())
    monkeypatch.setattr(session_manager, "get_or_create_session", AsyncMock(return_value=session))

    await cli.main()

    output = capsys.readouterr().out
    assert "Age: provided" in output
    assert "Gender: provided" in output
    assert "Category: provided" in output
    assert "Income: provided" in output
    assert "Life Event: missing" in output
    assert "female" not in output
    assert "123456" not in output
    assert "Age: 47" not in output
    assert "Category: SC" not in output
