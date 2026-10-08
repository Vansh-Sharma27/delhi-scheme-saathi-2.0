"""Typed HTTP construction preserves namespace, authorization and availability."""

from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.dss.application.conversation.contracts import ChatResponse
from src.dss.application.ports.scheme_repository import SchemeRepository
from src.dss.interfaces.api.dependencies import APIDependencies
from src.dss.interfaces.api.http import HTTPRoutes
from src.dss.settings import Settings


@pytest.mark.parametrize("connected", [False, True])
def test_typed_http_auth_precedes_database_check_and_namespaces_ids(connected) -> None:
    chat = AsyncMock(return_value=ChatResponse(text="synthetic"))
    schemes = AsyncMock(spec=SchemeRepository) if connected else None
    routes = HTTPRoutes(APIDependencies(
        Settings(_env_file=None, chat_api_key="synthetic-key"), schemes, None, None, None,
        chat, AsyncMock(),
    ))
    app = FastAPI()
    app.add_api_route("/api/chat", routes.chat_endpoint, methods=["POST"])
    client = TestClient(app)
    assert client.post("/api/chat", json={"message": "hello"}).status_code == 403
    response = client.post("/api/chat", headers={"X-API-Key": "synthetic-key"}, json={"user_id": "123", "message": " hello "})
    assert response.status_code == (200 if connected else 503)
    if connected:
        request = chat.await_args.args[0]
        assert request.user_id == "api:123" and request.message == "hello"
    else:
        chat.assert_not_called()
