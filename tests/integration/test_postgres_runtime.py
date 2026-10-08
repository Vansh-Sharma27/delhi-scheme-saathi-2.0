"""Opt-in tests against an explicitly provisioned, isolated PostgreSQL test DB.

Apply scripts/init-db/01-schema.sql and run scripts.ensure_seed_data first.
Set DSS_INTEGRATION_DATABASE_URL to that DB; DATABASE_URL is never a fallback.
Only connection-local temporary scheme rows and synthetic in-memory sessions
are written. No provider keys, AWS backends, or embedding services are needed.
"""

import importlib
import json
import os
from pathlib import Path
from urllib.parse import urlsplit

import asyncpg
import httpx
import pytest
from fastapi import FastAPI

from src.dss.application.matching.scheme_matcher import SchemeMatcher
from src.dss.bootstrap.runtime import api_runtime
from src.dss.domain.conversations.session import Session
from src.dss.domain.profiles.profile import UserProfile
from src.dss.infrastructure.database.adapters import PostgresSchemeRepository
from src.dss.infrastructure.database.catalog import get_canonical_life_events
from src.dss.infrastructure.embeddings.fallback_client import FallbackEmbeddingClient
from src.dss.interfaces.api.app import register_routes
from src.dss.interfaces.api.http import HTTPRoutes
from src.dss.settings import Settings

pytestmark = pytest.mark.skipif(
    not os.environ.get("DSS_INTEGRATION_DATABASE_URL"),
    reason="Set DSS_INTEGRATION_DATABASE_URL to an isolated, seeded pgvector test DB",
)


@pytest.fixture
def settings(monkeypatch):
    url = os.environ["DSS_INTEGRATION_DATABASE_URL"]
    parsed = urlsplit(url)
    assert parsed.scheme in {"postgres", "postgresql"} and parsed.hostname and parsed.path.strip("/"), (
        "DSS_INTEGRATION_DATABASE_URL must explicitly identify the isolated test database"
    )
    # Ignore developer/CI provider credentials and backend switches, including .env.
    for name in Settings.model_fields:
        monkeypatch.delenv(name.upper(), raising=False)
        monkeypatch.delenv(name.lower(), raising=False)
    return Settings(
        _env_file=None, database_url=url, xai_api_key="", use_bedrock=False,
        jina_api_key="", voyage_api_key="", sarvam_api_key="",
        bhashini_api_key="", bhashini_user_id="", bhashini_ulca_api_key="",
        telegram_bot_token="", telegram_webhook_secret="", chat_api_key="",
        session_table_name="dss-sessions", ai_memory_queue_enabled=False,
        ai_memory_queue_backend="in_memory", ai_memory_queue_url="",
    )


@pytest.fixture
def seed():
    data = Path(__file__).resolve().parents[2] / "data"
    return {
        name: json.loads((data / f"all_{name}.json").read_text(encoding="utf-8"))
        for name in ("schemes", "documents", "offices", "rejection_rules")
    }


async def test_container_all_read_routes_and_errors(settings, seed):
    from src.dss.bootstrap.api import create_app

    app = create_app(settings)
    async with app.router.lifespan_context(app), httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://integration.test",
    ) as client:
        response = await client.get("/")
        assert response.status_code == 200
        assert response.json() == {
            "name": "Delhi Scheme Saathi API", "version": "0.1.0", "docs": "/docs",
        }
        active = [s for s in seed["schemes"] if s.get("is_active", True)]
        response = await client.get("/health")
        assert response.status_code == 200
        assert response.json() == {
            "status": "ok", "database": "connected", "schemes_count": len(active),
        }
        response = await client.get("/api/schemes", params={"limit": 100})
        assert response.status_code == 200
        body = response.json()
        assert body["total"] == len(active) and body["life_event"] is None
        assert {s["id"]: s["name"] for s in body["schemes"]} == {
            s["id"]: s["name"] for s in active
        }
        response = await client.get("/api/schemes", params={"limit": 1})
        assert response.status_code == 200
        assert response.json()["total"] == len(response.json()["schemes"]) == 1

        response = await client.get("/api/schemes", params={"life_event": "HOUSING"})
        assert response.status_code == 200
        body = response.json()
        assert body["life_event"] == "HOUSING"
        assert {s["id"] for s in body["schemes"]} == {
            s["id"] for s in active if "HOUSING" in s["life_events"]
        }
        assert body["total"] == len(body["schemes"]) > 0
        response = await client.get("/api/schemes?life_event=DSS_TEST_UNKNOWN")
        assert response.status_code == 200
        assert response.json() == {"schemes": [], "total": 0, "life_event": "DSS_TEST_UNKNOWN"}

        scheme = next(s for s in active if s["id"] == "SCH-DELHI-001")
        response = await client.get(f"/api/scheme/{scheme['id']}")
        assert response.status_code == 200
        body = response.json()
        assert body["scheme"]["name"] == scheme["name"]
        assert body["scheme"]["benefits_amount"] == scheme["benefits_amount"]
        assert {d["id"] for d in body["documents"]} == set(scheme["documents_required"])
        assert {r["id"] for r in body["rejection_rules"]} == {
            r["id"] for r in seed["rejection_rules"] if r["scheme_id"] == scheme["id"]
        }
        assert body["documents"] and body["rejection_rules"]

        document = next(d for d in seed["documents"] if d["id"] == "DOC-INCOME-CERT")
        response = await client.get(f"/api/document/{document['id']}")
        assert response.status_code == 200
        body = response.json()
        assert body["document"]["name"] == document["name"]
        assert {d["id"] for d in body["prerequisites"]} == set(document["prerequisites"])
        expected_offices = sorted(
            [o for o in seed["offices"] if document["id"] in o["services"]],
            key=lambda o: (o["type"], o["name"]),
        )[:10]
        assert [o["id"] for o in body["offices"]] == [o["id"] for o in expected_offices]
        assert body["prerequisites"] and body["offices"]

        office = next(o for o in seed["offices"] if o["id"] == "OFF-CSC-DWARKA-001")
        response = await client.get("/api/csc/nearest", params={
            "lat": office["latitude"], "lng": office["longitude"], "office_type": "CSC", "limit": 3,
        })
        assert response.status_code == 200
        body = response.json()
        assert body["query_type"] == "location" and body["query_district"] is None
        assert body["query_location"] == [office["latitude"], office["longitude"]]
        assert body["total"] == len(body["offices"]) == min(
            3, sum(o["type"] == "CSC" for o in seed["offices"])
        )
        assert body["offices"][0]["id"] == office["id"]
        assert body["offices"][0]["distance_km"] == 0
        assert all(o["type"] == "CSC" for o in body["offices"])
        distances = [o["distance_km"] for o in body["offices"]]
        assert distances == sorted(distances)
        response = await client.get("/api/csc/nearest", params={"district": office["district"], "limit": 50})
        assert response.status_code == 200
        body = response.json()
        assert body["query_type"] == "district" and body["query_location"] is None
        assert body["query_district"] == office["district"]
        assert {o["id"] for o in body["offices"]} == {
            o["id"] for o in seed["offices"] if o["district"] == office["district"]
        }
        assert body["total"] == len(body["offices"]) > 0

        response = await client.get("/api/life-events")
        assert response.status_code == 200
        events = response.json()["life_events"]
        assert len(events) == 10
        assert [e["key"] for e in events] == sorted(e["key"] for e in events)
        assert next(e for e in events if e["key"] == "HOUSING") == {
            "key": "HOUSING", "display_name": "Housing & Property",
            "display_name_hindi": "आवास एवं संपत्ति",
            "aliases": ["buying_home", "constructing_home", "renting_home", "property_purchase"],
        }
        for path, status, detail in (
            ("/api/scheme/DSS-TEST-MISSING", 404, "Scheme DSS-TEST-MISSING not found"),
            ("/api/document/DSS-TEST-MISSING", 404, "Document DSS-TEST-MISSING not found"),
            ("/api/csc/nearest", 400, "Provide either lat+lng or district parameter"),
            ("/api/csc/nearest?lat=28", 400, "Provide either lat+lng or district parameter"),
        ):
            response = await client.get(path)
            assert response.status_code == status, path
            assert response.json() == {"detail": detail}
        for path, field in (
            ("/api/schemes?limit=0", "limit"), ("/api/schemes?limit=101", "limit"),
            ("/api/schemes?limit=abc", "limit"),
            ("/api/csc/nearest?lat=91&lng=77", "lat"),
            ("/api/csc/nearest?lat=28&lng=181", "lng"),
            ("/api/csc/nearest?district=Delhi&limit=51", "limit"),
        ):
            response = await client.get(path)
            assert response.status_code == 422, path
            assert response.json()["detail"][0]["loc"] == ["query", field]


async def test_chat_commands_persist_only_in_api_namespace(settings):
    async with api_runtime(settings) as runtime:
        assert runtime.dependencies.schemes is not None
        store = runtime.memory.store
        user_id = "dss-integration-synthetic-user"
        await store.save(Session(user_id=user_id, language_preference="en", metadata={"sentinel": True}))
        untouched = (await store.get(user_id)).model_dump()
        app = FastAPI()
        register_routes(app, HTTPRoutes(runtime.dependencies), settings)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://integration.test",
        ) as client:
            replies = []
            for turn, command in enumerate(("/start", "/language"), start=1):
                response = await client.post("/api/chat", json={"user_id": user_id, "message": command})
                assert response.status_code == 200
                body = response.json()
                assert set(body) == {"response", "next_state", "schemes", "documents", "rejection_warnings"}
                assert body["response"] and body["next_state"] == "GREETING"
                assert body["schemes"] == body["documents"] == body["rejection_warnings"] == []
                replies.append(body["response"])
                saved = await store.get(f"api:{user_id}")
                assert saved is not None and saved.completed_turn_count == turn
                assert [m.content for m in saved.messages if m.role == "user"] == ["/start", "/language"][:turn]
                assert [m.content for m in saved.messages if m.role == "assistant"] == replies
                assert (await store.get(user_id)).model_dump() == untouched
            assert replies[0] != replies[1]
            response = await client.post("/api/chat", json={"user_id": user_id, "message": "   "})
            assert response.status_code == 400
            assert response.json() == {"detail": "Message is required"}
            assert (await store.get(f"api:{user_id}")).completed_turn_count == 2


class FixedEmbeddings:
    async def get_embedding(self, text):
        assert text == "synthetic integration query"
        return [1.0] + [0.0] * 1023

    async def get_embeddings_batch(self, texts):
        return [await self.get_embedding(text) for text in texts]


async def test_real_vector_matching_and_no_provider_fallback(settings):
    # ponytail: one real pooled connection keeps a temporary table across acquires;
    # closing it drops all synthetic rows without touching the seeded catalog.
    async with asyncpg.create_pool(
        settings.database_url, min_size=1, max_size=1, command_timeout=30,
    ) as pool:
        async with pool.acquire() as conn:
            await conn.execute("CREATE TEMP TABLE schemes (LIKE public.schemes INCLUDING DEFAULTS)")
            for scheme_id, amount, vector, eligibility, event, active in (
                ("DSS-TEST-CLOSE", 100, [1.0, 0.0], {"max_income": 100000}, "DSS_TEST", True),
                ("DSS-TEST-FAR", 200, [0.0, 1.0], {"max_income": 100000}, "DSS_TEST", True),
                ("DSS-TEST-AGE", 300, [1.0, 0.0], {"min_age": 60}, "DSS_TEST", True),
                ("DSS-TEST-GENDER", 400, [1.0, 0.0], {"genders": ["female"]}, "DSS_TEST", True),
                ("DSS-TEST-TOPIC", 500, [1.0, 0.0], {}, "OTHER_TEST", True),
                ("DSS-TEST-INACTIVE", 600, [1.0, 0.0], {}, "DSS_TEST", False),
            ):
                await conn.execute(
                    """INSERT INTO schemes
                       (id, name, name_hindi, department, department_hindi, level,
                        description, description_hindi, eligibility, benefits_amount,
                        description_embedding, life_events, is_active)
                       VALUES ($1, $1, $1, 'test', 'test', 'state', 'test', 'test',
                               $2::jsonb, $3, $4::vector, $5::text[], $6)""",
                    scheme_id, json.dumps(eligibility), amount,
                    json.dumps(vector + [0.0] * 1022), [event], active,
                )
        repository = PostgresSchemeRepository(pool)
        profile = UserProfile(age=30, gender="male", annual_income=50000, life_event="DSS_TEST")
        matcher = SchemeMatcher(repository, FixedEmbeddings(), get_canonical_life_events, embedding_dimension=1024)
        matches = await matcher.match_schemes(profile=profile, query_text="synthetic integration query")
        assert [m.scheme.id for m in matches] == ["DSS-TEST-CLOSE", "DSS-TEST-FAR"]
        assert [m.similarity for m in matches] == pytest.approx([1.0, 0.0])
        assert all(all(m.eligibility_match.values()) for m in matches)
        assert matches[0].deterministic_score > matches[1].deterministic_score
        assert len(await matcher.match_schemes(profile=profile, query_text="synthetic integration query", limit=1)) == 1

        provider = FallbackEmbeddingClient(settings)
        try:
            assert await provider.get_embedding("synthetic integration query") is None
            matcher = SchemeMatcher(repository, provider, get_canonical_life_events, embedding_dimension=1024)
            matches = await matcher.match_schemes(profile=profile, query_text="synthetic integration query")
            assert [m.scheme.id for m in matches] == ["DSS-TEST-FAR", "DSS-TEST-CLOSE"]
            assert [m.similarity for m in matches] == [0.0, 0.0]
            assert await matcher.match_schemes(
                profile=profile.model_copy(update={"annual_income": 100001}),
                query_text="synthetic integration query",
            ) == []
        finally:
            await provider.close()


def test_lambda_cold_then_warm_invocations_use_real_database(settings, seed, monkeypatch):
    from src.dss.bootstrap import lambda_api

    # Reload the entrypoint for a cold module, then reuse it across warm calls.
    lambda_api = importlib.reload(lambda_api)
    monkeypatch.setattr(lambda_api, "get_settings", lambda: settings)
    count = sum(s.get("is_active", True) for s in seed["schemes"])
    for path, status in (
        ("/health", 200), ("/api/scheme/SCH-DELHI-001", 200),
        ("/api/scheme/DSS-TEST-MISSING", 404), ("/health", 200),
    ):
        result = lambda_api.handler({
            "version": "2.0", "routeKey": f"GET {path}", "rawPath": path,
            "rawQueryString": "", "headers": {"host": "integration.test"},
            "requestContext": {
                "http": {"method": "GET", "path": path, "sourceIp": "127.0.0.1"},
                "stage": "$default",
            }, "isBase64Encoded": False,
        }, None)
        assert result["statusCode"] == status
        body = json.loads(result["body"])
        if path == "/health":
            assert body == {"status": "ok", "database": "connected", "schemes_count": count}
        elif status == 404:
            assert body == {"detail": "Scheme DSS-TEST-MISSING not found"}
        else:
            assert body["scheme"]["id"] == "SCH-DELHI-001"
            assert body["documents"] and body["rejection_rules"]
