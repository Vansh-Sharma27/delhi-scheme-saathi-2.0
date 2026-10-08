"""Port-driven matching agrees with a frozen, independent historical matcher."""

import ast
import subprocess
from pathlib import Path
from types import ModuleType
from unittest.mock import AsyncMock

import pytest

from src.dss.application.matching.scheme_matcher import SchemeMatcher
from src.dss.application.ports.embeddings import EmbeddingProvider
from src.dss.application.ports.scheme_repository import SchemeRepository
from src.dss.domain.profiles.profile import UserProfile
from src.dss.domain.schemes.scheme import EligibilityCriteria, Scheme, SchemeCandidate
from src.dss.infrastructure.embeddings.fallback_client import EMBEDDING_DIM


@pytest.fixture
def legacy() -> ModuleType:
    # Pin the oracle independently of both the working tree and future HEADs.
    source_ref = "9e2ffa377b5a788fa2ad649b8fc53b90cbeb2506:src/services/scheme_matcher.py"
    source = subprocess.check_output(
        ["git", "show", source_ref], cwd=Path(__file__).resolve().parents[1],
        encoding="utf-8",
    )
    module = ModuleType("historical_scheme_matcher")
    tree = ast.parse(source)
    # Remap imports only; the historical matching implementation stays independent.
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and node.module in {
            "src.integrations.embedding_client",
            "src.dss.infrastructure.embeddings.fallback_client",
            "src.db.scheme_repo",
        }:
            if node.module == "src.db.scheme_repo":
                node.module = "src.dss.infrastructure.database.scheme_repo"
            else:
                node.module = "src.dss.infrastructure.embeddings.fallback_client"
                node.names = [name for name in node.names if name.name != "get_embedding_client"]
    tree.body = [node for node in tree.body if not isinstance(node, ast.ImportFrom) or node.names]
    exec(compile(tree, source_ref, "exec"), module.__dict__)
    return module


@pytest.mark.parametrize("embedding", [None, [0.2], [0.2] * EMBEDDING_DIM])
async def test_constructed_matcher_matches_existing_pipeline(monkeypatch, embedding, legacy) -> None:
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
    assert legacy.match_schemes.__code__ is not SchemeMatcher.match_schemes.__code__
    assert legacy.match_schemes.__module__ == "historical_scheme_matcher"
    profile = UserProfile(gender="male", life_event="HOUSING")
    monkeypatch.setattr(legacy, "get_embedding_client", lambda: embeddings, raising=False)
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
