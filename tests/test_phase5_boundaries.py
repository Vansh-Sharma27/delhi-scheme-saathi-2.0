"""Phase 5 size, interface, and grounded-presentation regression checks."""

import ast
import subprocess
from contextlib import asynccontextmanager
from functools import lru_cache
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from src.dss.application.guidance import presenters
from src.dss.application.ports.scheme_repository import SchemeRepository
from src.dss.bootstrap import api, lambda_api
from src.dss.domain.eligibility.presentation_facts import EligibilityFacts
from src.dss.domain.profiles.profile import UserProfile
from src.dss.domain.schemes.scheme import EligibilityCriteria, Scheme
from src.dss.interfaces.api.dependencies import APIDependencies
from src.dss.interfaces.api.http import HTTPRoutes
from src.dss.interfaces.telegram.dispatch import TelegramHandler
from src.dss.settings import Settings
from src.services import response_generator

ROOT = Path(__file__).resolve().parents[1]


@lru_cache(maxsize=1)
def _original_responses() -> ModuleType:
    source = subprocess.check_output(
        ["git", "show", "a394923:src/services/response_generator.py"], cwd=ROOT
    ).decode("utf-8")
    module = ModuleType("phase5_original_responses")
    exec(compile(source, "<original-responses>", "exec"), module.__dict__)
    return module


def _scheme(eligibility: EligibilityCriteria) -> Scheme:
    return Scheme(
        id="phase5-synthetic",
        name="Widow support",
        name_hindi="Synthetic scheme",
        department="Synthetic department",
        department_hindi="Synthetic department",
        level="state",
        description="Support for widowed women",
        description_hindi="Synthetic description",
        eligibility=eligibility,
        life_events=["DEATH_IN_FAMILY"],
    )


@pytest.mark.parametrize("language", ["en", "hi", "hinglish"])
def test_grounded_presenters_match_original_responses(language: str) -> None:
    original = _original_responses()
    profiles = [
        UserProfile(),
        UserProfile(
            age=30,
            gender="female",
            category="SC",
            annual_income=200000,
            life_event="DEATH_IN_FAMILY",
            marital_status="widowed",
        ),
        UserProfile(age=70, gender="male", category="GENERAL", annual_income=900000),
    ]
    criteria = [
        EligibilityCriteria(),
        EligibilityCriteria(
            min_age=18, max_age=60, genders=["female"], caste_categories=["SC"], max_income=300000
        ),
        EligibilityCriteria(
            income_segments=["LIG", "MIG"],
            income_by_category={"MIG": 900000, "EWS": 300000, "LIG": 600000},
        ),
    ]
    for eligibility in criteria:
        scheme = _scheme(eligibility)
        for profile in profiles:
            for name, question in [
                ("_maybe_generate_eligibility_response", "Am I eligible?"),
                ("_maybe_generate_eligibility_response", "What documents do I need?"),
                ("_maybe_generate_scheme_justification_response", "Why this scheme?"),
                ("_maybe_generate_scheme_justification_response", "Hello"),
                ("_maybe_generate_scheme_term_response", "What is the LIG income band?"),
                ("_maybe_generate_scheme_term_response", "Hello"),
            ]:
                args = scheme, profile, question, language
                assert getattr(response_generator, name)(*args) == getattr(original, name)(*args)
            assert response_generator._build_matching_reason_context(scheme, profile) == (
                original._build_matching_reason_context(scheme, profile)
            )


def test_presenter_uses_supplied_facts_instead_of_evaluating_profile() -> None:
    scheme = _scheme(EligibilityCriteria(min_age=18))
    facts = EligibilityFacts({}, ["age"], [], ["age"], False)
    text = presenters._maybe_generate_eligibility_response(
        scheme, UserProfile(age=30), "Am I eligible?", "en", facts=facts
    )
    assert text is not None and "does not appear eligible" in text
    tree = ast.parse(Path(presenters.__file__).read_text(encoding="utf-8"))
    assert not any(
        isinstance(node, ast.Name) and node.id == "calculate_eligibility_match"
        for node in ast.walk(tree)
    )


def test_phase5_physical_line_limits() -> None:
    baseline = set(
        subprocess.check_output(["git", "ls-tree", "-r", "--name-only", "a394923"], cwd=ROOT)
        .decode()
        .splitlines()
    )
    for path in (ROOT / "src").rglob("*.py"):
        relative = path.relative_to(ROOT).as_posix()
        if relative not in baseline:
            assert len(path.read_text(encoding="utf-8").splitlines()) <= 500, relative
    for relative in [
        "src/dss/application/conversation/service.py",
        "src/services/conversation/service.py",
    ]:
        assert len((ROOT / relative).read_text(encoding="utf-8").splitlines()) < 300


def test_telegram_dispatch_is_owned_by_canonical_interface() -> None:
    notifier, speech, store, clock, conversation = (AsyncMock() for _ in range(5))
    dispatch = TelegramHandler(notifier, speech, store, clock, conversation)
    assert dispatch.handle.__module__ == "src.dss.interfaces.telegram.dispatch"
    assert dispatch.notifier is notifier
    assert dispatch.speech is speech
    assert dispatch.store is store
    assert dispatch.clock is clock
    assert dispatch.conversation is conversation


def test_http_routes_are_owned_by_interface() -> None:
    endpoints = [
        route.endpoint
        for route in api.app.routes
        if getattr(route, "path", "").startswith(("/api/", "/webhook/", "/health"))
    ]
    assert len(endpoints) == 8
    assert all(endpoint.__module__ == "src.dss.interfaces.api.http" for endpoint in endpoints)
    assert all(isinstance(endpoint.__self__, HTTPRoutes) for endpoint in endpoints)


def test_http_webhook_dispatch_uses_injected_dependency(monkeypatch) -> None:
    update = {"update_id": 123}
    dispatch = AsyncMock(return_value={"status": "ok"})
    settings = Settings(_env_file=None, telegram_webhook_secret="")
    dependencies = APIDependencies(
        settings, AsyncMock(spec=SchemeRepository), None, None, None, AsyncMock(), dispatch,
    )

    @asynccontextmanager
    async def isolated_runtime(runtime_settings):
        assert runtime_settings is settings
        yield SimpleNamespace(dependencies=dependencies, start_local_worker=AsyncMock())

    monkeypatch.setattr(api, "api_runtime", isolated_runtime)
    with TestClient(api.create_app(settings)) as client:
        response = client.post("/webhook/telegram", json=update)
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    dispatch.assert_awaited_once_with(update)


def test_lambda_handler_serves_relocated_health_route(monkeypatch) -> None:
    settings = Settings(_env_file=None)
    dependencies = APIDependencies(settings, None, None, None, None, AsyncMock(), AsyncMock())

    @asynccontextmanager
    async def isolated_runtime(runtime_settings):
        assert runtime_settings is settings
        yield SimpleNamespace(dependencies=dependencies)

    monkeypatch.setattr(lambda_api, "get_settings", lambda: settings)
    monkeypatch.setattr(lambda_api, "api_runtime", isolated_runtime)
    event = {
        "version": "2.0",
        "routeKey": "GET /health",
        "rawPath": "/health",
        "rawQueryString": "",
        "headers": {"host": "phase5.test"},
        "requestContext": {
            "http": {"method": "GET", "path": "/health", "sourceIp": "127.0.0.1"},
            "stage": "$default",
        },
        "isBase64Encoded": False,
    }
    response = lambda_api.handler(event, SimpleNamespace())
    assert response["statusCode"] == 200
    assert '"status":"ok"' in response["body"]
