"""Port-driven matching agrees with the independently retained legacy path."""

from unittest.mock import AsyncMock

import pytest

from src.dss.application.matching.scheme_matcher import SchemeMatcher
from src.dss.application.ports.embeddings import EmbeddingProvider
from src.dss.application.ports.scheme_repository import SchemeRepository
from src.dss.domain.profiles.profile import UserProfile
from src.dss.domain.schemes.scheme import EligibilityCriteria, Scheme, SchemeCandidate
from src.dss.infrastructure.embeddings.fallback_client import EMBEDDING_DIM
from src.services import scheme_matcher as legacy


@pytest.mark.parametrize("embedding", [None, [0.2], [0.2] * EMBEDDING_DIM])
async def test_constructed_matcher_matches_existing_pipeline(monkeypatch, embedding) -> None:
    candidates = [SchemeCandidate(scheme=Scheme(
        id=sid, name=sid, name_hindi=sid, department="synthetic", department_hindi="synthetic",
        level="state", description="synthetic", description_hindi="synthetic",
        eligibility=EligibilityCriteria(genders=[gender]), life_events=[event], benefits_amount=benefit,
    )) for sid, gender, event, benefit in [
        ("off-topic", "male", "EDUCATION", 1000000),
        ("fails", "female", "HOUSING", 1000000),
        ("small", "male", "HOUSING", 1000),
        ("large", "male", "HOUSING", 500000),
    ]]
    repository = AsyncMock(spec=SchemeRepository)
    repository.retrieve_candidates.return_value = candidates
    embeddings = AsyncMock(spec=EmbeddingProvider)
    embeddings.get_embedding.return_value = embedding
    matcher = SchemeMatcher(repository, embeddings, lambda sid: [], embedding_dimension=EMBEDDING_DIM)
    profile = UserProfile(gender="male", life_event="HOUSING")
    monkeypatch.setattr(legacy, "get_embedding_client", lambda: embeddings)
    monkeypatch.setattr(legacy, "retrieve_candidates", AsyncMock(return_value=candidates))
    monkeypatch.setattr(legacy, "get_canonical_life_events", lambda sid: [])
    expected = await legacy.match_schemes(None, profile, "housing", 1)
    actual = await matcher.match_schemes(profile=profile, query_text="housing", limit=1)
    assert actual == expected
    assert [match.scheme.id for match in actual] == ["large"]
    assert repository.retrieve_candidates.await_args.kwargs["limit"] == 10
    assert repository.retrieve_candidates.await_args.kwargs["query_embedding"] == (
        embedding if embedding and len(embedding) == EMBEDDING_DIM else None
    )
