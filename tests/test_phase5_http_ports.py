"""HTTP repository-port migration preserves payloads, queries, and errors."""

import subprocess
from contextlib import asynccontextmanager
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from src.dss.application.ports.document_repository import DocumentRepository
from src.dss.application.ports.office_repository import OfficeRepository
from src.dss.application.ports.rejection_rule_repository import RejectionRuleRepository
from src.dss.application.ports.scheme_repository import SchemeRepository
from src.dss.infrastructure.database.adapters import PostgresSchemeRepository
from src.dss.interfaces.api.routes import APIRoutes


class QueryPool:
    def __init__(self, count=3) -> None:
        self.count = count
        self.queries = []
        self.rows = [
            {
                "key": "HOUSING",
                "display_name": "Synthetic",
                "display_name_hindi": "Synthetic",
                "aliases": None,
            }
        ]

    @asynccontextmanager
    async def acquire(self):
        yield self

    async def fetchval(self, query):
        self.queries.append(query)
        return self.count

    async def fetch(self, query):
        self.queries.append(query)
        return self.rows


@pytest.mark.parametrize("count", [None, 0, 3])
async def test_repository_keeps_health_and_taxonomy_queries(count) -> None:
    pool = QueryPool(count)
    repository = PostgresSchemeRepository(pool)
    assert await repository.count_active_schemes() == (count or 0)
    assert await repository.list_life_events() == [
        {
            "key": "HOUSING",
            "display_name": "Synthetic",
            "display_name_hindi": "Synthetic",
            "aliases": [],
        }
    ]
    assert pool.queries == [
        "SELECT COUNT(*) FROM schemes WHERE is_active = true",
        "SELECT key, display_name, display_name_hindi, aliases FROM life_events_taxonomy ORDER BY key",
    ]


@pytest.mark.parametrize(
    "method,arguments",
    [
        ("health_check", {}),
        ("list_life_events", {}),
        ("get_scheme", {"scheme_id": "synthetic"}),
        ("get_scheme", {"scheme_id": "missing"}),
        ("get_document", {"document_id": "synthetic"}),
        ("get_document", {"document_id": "missing"}),
        ("list_schemes", {"life_event": "HOUSING", "limit": 2}),
        ("list_schemes", {"life_event": None, "limit": 2}),
        ("get_nearest_offices", {"lat": 0.0, "lng": 0.0, "limit": 2}),
        ("get_nearest_offices", {"lat": None, "lng": None, "district": "synthetic", "limit": 2}),
        ("get_nearest_offices", {"lat": None, "lng": None, "limit": 2}),
    ],
)
async def test_http_payloads_and_errors_match_pre_port_handlers(method, arguments) -> None:
    source = subprocess.check_output(
        ["git", "show", "ff5ea64:src/dss/interfaces/api/routes.py"],
        cwd=Path(__file__).resolve().parents[1],
    ).decode("utf-8")
    original = ModuleType("original_http_routes")
    exec(compile(source, "<original-http>", "exec"), original.__dict__)
    pool = QueryPool()
    payload = SimpleNamespace(
        model_dump=lambda: {"id": "synthetic"}, prerequisites=["prerequisite"]
    )
    schemes = AsyncMock(spec=SchemeRepository)
    schemes.get_scheme_by_id.side_effect = lambda identifier: (
        None if identifier == "missing" else payload
    )
    schemes.get_schemes_by_life_event.return_value = [payload]
    schemes.get_all_schemes.return_value = [payload]
    schemes.count_active_schemes.return_value = 3
    schemes.list_life_events.return_value = [{**pool.rows[0], "aliases": []}]
    documents = AsyncMock(spec=DocumentRepository)
    documents.get_document_by_id.side_effect = lambda identifier: (
        None if identifier == "missing" else payload
    )
    documents.get_documents_for_scheme.return_value = [payload]
    documents.get_documents_by_ids.return_value = [payload]
    offices = AsyncMock(spec=OfficeRepository)
    offices.get_offices_by_service.return_value = [payload]
    offices.get_offices_by_district.return_value = [payload]
    offices.get_nearest_offices.return_value = [payload]
    rules = AsyncMock(spec=RejectionRuleRepository)
    rules.get_rules_by_scheme.return_value = [payload]

    def module_proxy(port):
        proxy = SimpleNamespace()
        for name in dir(port):
            if name.startswith("_") or not isinstance(getattr(port, name), AsyncMock):
                continue
            bound_method = getattr(port, name)

            async def forward(bound_pool, *args, _method=bound_method):
                assert bound_pool is pool
                return await _method(*args)

            setattr(proxy, name, forward)
        return proxy

    runtime = SimpleNamespace(
        db_pool=pool,
        get_db_pool=lambda: pool,
        scheme_repository=lambda _: schemes,
        document_repository=lambda _: documents,
        office_repository=lambda _: offices,
        rejection_rule_repository=lambda _: rules,
        repositories=SimpleNamespace(
            scheme_repo=module_proxy(schemes),
            document_repo=module_proxy(documents),
            office_repo=module_proxy(offices),
            rejection_rule_repo=module_proxy(rules),
        ),
    )
    outcomes = []
    for handlers in [original.APIRoutes(runtime), APIRoutes(runtime)]:
        try:
            outcomes.append(await getattr(handlers, method)(**arguments))
        except HTTPException as error:
            outcomes.append((error.status_code, error.detail))
    assert outcomes[0] == outcomes[1]
    if method == "get_nearest_offices" and arguments["lat"] == 0.0:
        assert outcomes[1]["query_location"] is None
