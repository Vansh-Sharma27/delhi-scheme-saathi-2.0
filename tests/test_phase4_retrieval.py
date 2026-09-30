"""Pin raw retrieval and evaluation ordering independently of golden mocks."""

from unittest.mock import AsyncMock

import pytest

from src.dss.domain.profiles.profile import UserProfile
from src.dss.domain.schemes.scheme import EligibilityCriteria, Scheme, SchemeCandidate
from src.dss.infrastructure.database import scheme_repo
from src.services import scheme_matcher
from tests.test_scheme_matcher import _CapturingPool


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
