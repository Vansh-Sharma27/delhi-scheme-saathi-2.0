"""Pin raw retrieval and evaluation ordering independently of golden mocks."""

import ast
import subprocess
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from src.dss.domain.profiles.profile import UserProfile
from src.dss.domain.schemes.scheme import EligibilityCriteria, Scheme, SchemeCandidate
from src.dss.infrastructure.database import scheme_repo
from src.services import scheme_matcher
from tests.test_scheme_matcher import _CapturingPool


def test_retrieval_query_body_is_original_ast() -> None:
    original = subprocess.check_output(["git", "show", "e7f8ae0:src/dss/infrastructure/database/scheme_repo.py"], text=True)
    current = Path(scheme_repo.__file__).read_text(encoding="utf-8")
    def query_body(source: str, name: str) -> list[str]:
        function = next(n for n in ast.parse(source).body if isinstance(n, ast.AsyncFunctionDef) and n.name == name)
        acquire = next(n for n in function.body if isinstance(n, ast.AsyncWith))
        result = []
        for node in acquire.body:
            result.append(ast.dump(node))
            if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "rows" for t in node.targets):
                break
        return result
    assert query_body(original, "hybrid_search") == query_body(current, "retrieve_candidates")


@pytest.mark.asyncio
@pytest.mark.parametrize("canonical", [True, False])
@pytest.mark.parametrize("vector", [None, [0.25, -0.5]])
async def test_raw_retrieval_parameter_positions(monkeypatch: pytest.MonkeyPatch, canonical: bool, vector: list[float] | None) -> None:
    monkeypatch.setattr(scheme_repo, "get_canonical_scheme_ids_for_life_event", lambda event: ["synthetic"] if canonical else [])
    connection = AsyncMock()
    connection.fetch.return_value = []
    await scheme_repo.retrieve_candidates(_CapturingPool(connection), "HOUSING", UserProfile(age=30, annual_income=200000), vector, 11)
    query, *params = connection.fetch.await_args.args
    assert params[:3] == [["synthetic"] if canonical else "HOUSING", 30, 200000]
    assert params[-1] == 11
    assert ("id = ANY($1::text[])" in query) is canonical
    assert ("$1 = ANY(life_events)" in query) is not canonical
    if vector:
        assert params[3] == "[0.25,-0.5]"
        assert "ORDER BY description_embedding <=> $4::vector" in query
        assert "LIMIT $5" in query
    else:
        assert "ORDER BY benefits_amount DESC NULLS LAST" in query
        assert "LIMIT $4" in query


@pytest.mark.asyncio
async def test_raw_retrieval_preserves_sql_and_legacy_evaluation(monkeypatch: pytest.MonkeyPatch) -> None:
    row = {"id": "synthetic", "name": "Synthetic", "name_hindi": "Synthetic", "department": "Synthetic", "department_hindi": "Synthetic", "level": "state", "description": "Synthetic", "description_hindi": "Synthetic", "eligibility": {"genders": ["female"]}, "similarity": None}
    connection = AsyncMock()
    connection.fetch.return_value = [row]
    pool = _CapturingPool(connection)
    profile = UserProfile(age=30, gender="male", annual_income=100000)
    calls = []
    original = scheme_repo._calculate_eligibility_match
    def evaluate(scheme, user):
        calls.append(scheme.id)
        return original(scheme, user)
    monkeypatch.setattr(scheme_repo, "_calculate_eligibility_match", evaluate)
    candidates = await scheme_repo.retrieve_candidates(pool, None, profile, None, 7)
    query, *params = connection.fetch.await_args.args
    assert "ORDER BY benefits_amount DESC NULLS LAST" in query
    assert params == [30, 100000, 7]
    assert calls == []
    assert candidates[0].similarity == 0.0
    assert not hasattr(candidates[0], "eligibility_match")
    matches = await scheme_repo.hybrid_search(pool, None, profile, None, 7)
    assert calls == ["synthetic"]
    assert matches[0].eligibility_match == {"age": True, "gender": False, "income": True}


@pytest.mark.asyncio
async def test_matching_operation_order(monkeypatch: pytest.MonkeyPatch) -> None:
    events = []
    def make(sid, gender, benefit):
        return Scheme(id=sid, name=sid, name_hindi=sid, department="Synthetic", department_hindi="Synthetic", level="state", description="Synthetic", description_hindi="Synthetic", eligibility=EligibilityCriteria(genders=[gender]), life_events=["HOUSING"], benefits_amount=benefit)
    candidates = [SchemeCandidate(scheme=make("off-topic", "male", 1000000)), SchemeCandidate(scheme=make("fails", "female", 1000000)), SchemeCandidate(scheme=make("small", "male", 1000)), SchemeCandidate(scheme=make("large", "male", 500000))]
    async def retrieve(**kwargs):
        events.append("retrieve")
        assert kwargs["limit"] == 10
        return candidates
    original_evaluate = scheme_matcher.calculate_eligibility_match
    def evaluate(scheme, profile):
        events.append("evaluate:" + scheme.id)
        return original_evaluate(scheme, profile)
    def topic(scheme, requested):
        events.append("topic:" + scheme.id)
        return scheme.id != "off-topic"
    original_rank = scheme_matcher.rank_schemes
    def rank(matches):
        events.append("rank")
        assert [m.scheme.id for m in matches] == ["small", "large"]
        return original_rank(matches)
    monkeypatch.setattr(scheme_matcher, "retrieve_candidates", retrieve)
    monkeypatch.setattr(scheme_matcher, "calculate_eligibility_match", evaluate)
    monkeypatch.setattr(scheme_matcher, "is_topic_consistent", topic)
    monkeypatch.setattr(scheme_matcher, "rank_schemes", rank)
    matches = await scheme_matcher.match_schemes(None, UserProfile(gender="male", life_event="HOUSING"), limit=1)
    assert [m.scheme.id for m in matches] == ["large"]
    assert events == ["retrieve", "evaluate:off-topic", "evaluate:fails", "evaluate:small", "evaluate:large", "topic:off-topic", "topic:fails", "topic:small", "topic:large", "rank"]
