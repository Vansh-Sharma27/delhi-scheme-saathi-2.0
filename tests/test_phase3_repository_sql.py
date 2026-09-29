"""Pin SQL and argument order outside the mocked golden repository boundary."""

from unittest.mock import AsyncMock, Mock

import pytest

from src.dss.infrastructure.database import document_repo, office_repo, rejection_rule_repo


def capturing_pool():
    connection = AsyncMock()
    connection.fetch.return_value = []
    connection.fetchrow.return_value = None
    context = AsyncMock()
    context.__aenter__.return_value = connection
    pool = Mock()
    pool.acquire.return_value = context
    return pool, connection


def assert_query(mock, query, *parameters):
    actual, *args = mock.await_args.args
    assert " ".join(actual.split()) == " ".join(query.split())
    assert args == list(parameters)


@pytest.mark.asyncio
async def test_document_queries_and_empty_input() -> None:
    pool, connection = capturing_pool()
    assert await document_repo.get_document_by_id(pool, "D1") is None
    assert_query(connection.fetchrow, "SELECT * FROM documents WHERE id = $1", "D1")
    assert await document_repo.get_documents_by_ids(pool, ["D1", "D2"]) == []
    assert_query(connection.fetch, "SELECT * FROM documents WHERE id = ANY($1)", ["D1", "D2"])
    connection.fetch.reset_mock()
    assert await document_repo.get_documents_by_ids(pool, []) == []
    connection.fetch.assert_not_awaited()
    await document_repo.get_all_documents(pool)
    assert_query(connection.fetch, "SELECT * FROM documents ORDER BY name")
    await document_repo.search_documents(pool, "income", 3)
    assert_query(connection.fetch, "SELECT * FROM documents WHERE name ILIKE $1 OR name_hindi ILIKE $1 ORDER BY name LIMIT $2", "%income%", 3)
    connection.fetch.reset_mock()
    assert await document_repo.get_documents_for_scheme(pool, "S1") == []
    assert_query(connection.fetchrow, "SELECT documents_required FROM schemes WHERE id = $1", "S1")
    connection.fetch.assert_not_awaited()
    connection.fetchrow.return_value = {"documents_required": ["D2", "D1"]}
    await document_repo.get_documents_for_scheme(pool, "S1")
    assert_query(connection.fetch, "SELECT * FROM documents WHERE id = ANY($1)", ["D2", "D1"])


@pytest.mark.asyncio
async def test_office_query_filters_placeholders_and_distance_order(monkeypatch: pytest.MonkeyPatch) -> None:
    pool, connection = capturing_pool()
    assert await office_repo.get_office_by_id(pool, "O1") is None
    assert_query(connection.fetchrow, "SELECT * FROM offices WHERE id = $1", "O1")
    await office_repo.get_offices_by_district(pool, "North", 3)
    assert_query(connection.fetch, "SELECT * FROM offices WHERE district ILIKE $1 ORDER BY type, name LIMIT $2", "%North%", 3)
    await office_repo.get_offices_by_service(pool, "D1", limit=4)
    assert_query(connection.fetch, "SELECT * FROM offices WHERE $1 = ANY(services) ORDER BY type, name LIMIT $2", "D1", 4)
    await office_repo.get_offices_by_service(pool, "D1", "North", 4)
    assert_query(connection.fetch, "SELECT * FROM offices WHERE $1 = ANY(services) AND district ILIKE $2 ORDER BY type, name LIMIT $3", "D1", "%North%", 4)
    await office_repo.get_all_offices(pool)
    assert_query(connection.fetch, "SELECT * FROM offices ORDER BY district, name")
    await office_repo.get_nearest_offices(pool, 28.6, 77.2)
    assert_query(connection.fetch, "SELECT * FROM offices WHERE latitude IS NOT NULL AND longitude IS NOT NULL")
    connection.fetch.return_value = [
        {"id": "far", "latitude": 29.0, "longitude": 77.2},
        {"id": "near", "latitude": 28.6, "longitude": 77.2},
    ]
    monkeypatch.setattr(office_repo.Office, "from_db_row", lambda row, distance_km: (row["id"], distance_km))
    result = await office_repo.get_nearest_offices(pool, 28.6, 77.2, 1, "CSC")
    assert_query(connection.fetch, "SELECT * FROM offices WHERE latitude IS NOT NULL AND longitude IS NOT NULL AND type = $1", "CSC")
    assert result == [("near", 0.0)]


@pytest.mark.asyncio
async def test_rejection_queries_pin_severity_order_and_empty_input() -> None:
    pool, connection = capturing_pool()
    severity = "CASE severity WHEN 'critical' THEN 0 WHEN 'high' THEN 1 WHEN 'warning' THEN 2 END"
    await rejection_rule_repo.get_rules_by_scheme(pool, "S1")
    assert_query(connection.fetch, f"SELECT * FROM rejection_rules WHERE scheme_id = $1 ORDER BY {severity}, rule_type", "S1")
    await rejection_rule_repo.get_rules_by_ids(pool, ["R1"])
    assert_query(connection.fetch, f"SELECT * FROM rejection_rules WHERE id = ANY($1) ORDER BY {severity}", ["R1"])
    connection.fetch.reset_mock()
    assert await rejection_rule_repo.get_rules_by_ids(pool, []) == []
    connection.fetch.assert_not_awaited()
    await rejection_rule_repo.get_critical_rules(pool, "S1")
    assert_query(connection.fetch, "SELECT * FROM rejection_rules WHERE scheme_id = $1 AND severity = 'critical' ORDER BY rule_type", "S1")
    await rejection_rule_repo.get_all_rules(pool)
    assert_query(connection.fetch, f"SELECT * FROM rejection_rules ORDER BY scheme_id, {severity}")
