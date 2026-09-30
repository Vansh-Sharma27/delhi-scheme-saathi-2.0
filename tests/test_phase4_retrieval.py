"""Pin raw retrieval and evaluation ordering independently of golden mocks."""

from unittest.mock import AsyncMock

import pytest

from src.dss.domain.profiles.profile import UserProfile
from src.dss.infrastructure.database import scheme_repo
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
