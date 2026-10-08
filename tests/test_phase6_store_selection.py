"""Store selection preserves the different API/script and worker predicates."""

import subprocess
import sys
from unittest.mock import Mock

import pytest

from src.dss.bootstrap import sessions
from src.dss.infrastructure.sessions.session_store import InMemorySessionStore
from src.dss.settings import Settings


@pytest.mark.parametrize("table,bedrock,dynamo", [
    ("", False, False), ("", True, False),
    ("dss-sessions", False, False), ("dss-sessions", True, True),
    ("synthetic-table", False, True), ("synthetic-table", True, True),
])
def test_api_and_script_store_predicate(monkeypatch, table, bedrock, dynamo) -> None:
    shared = Mock()
    factory = Mock(return_value=shared)
    monkeypatch.setattr(sessions, "DynamoDBSessionStore", factory)
    settings = Settings(_env_file=None, session_table_name=table, use_bedrock=bedrock)
    result = sessions.build_session_store(settings)
    assert (result is shared) is dynamo
    if dynamo:
        factory.assert_called_once_with(table_name=table, region=settings.aws_region, clock=None)
    else:
        assert isinstance(result, InMemorySessionStore)
        factory.assert_not_called()


def test_api_init_failure_falls_back_but_worker_failure_propagates(monkeypatch) -> None:
    settings = Settings(_env_file=None, session_table_name="synthetic-table")
    monkeypatch.setattr(sessions, "DynamoDBSessionStore", Mock(side_effect=RuntimeError("synthetic")))
    assert isinstance(sessions.build_session_store(settings), InMemorySessionStore)
    with pytest.raises(RuntimeError, match="synthetic"):
        sessions.build_worker_session_store(settings)
    with pytest.raises(RuntimeError, match="SESSION_TABLE_NAME is required"):
        sessions.build_worker_session_store(Settings(_env_file=None, session_table_name=""))


def test_fork_import_does_not_construct_web_application() -> None:
    result = subprocess.run(
        [sys.executable, "-c", "import sys; import scripts.fork_session; assert 'src.dss.bootstrap.api' not in sys.modules; assert 'src.dss.bootstrap.lambda_api' not in sys.modules; assert 'fastapi' not in sys.modules"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
