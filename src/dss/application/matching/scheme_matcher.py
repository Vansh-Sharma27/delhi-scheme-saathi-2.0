"""Deterministic retrieval, evaluation, topic filtering and ranking over ports."""

import logging
from collections.abc import Callable

from src.dss.application.ports.embeddings import EmbeddingProvider
from src.dss.application.ports.scheme_repository import SchemeRepository
from src.dss.domain.eligibility.evaluator import calculate_eligibility_match
from src.dss.domain.profiles.profile import UserProfile
from src.dss.domain.schemes.scheme import Scheme, SchemeMatch

logger = logging.getLogger(__name__)


class SchemeMatcher:
    def __init__(
        self, schemes: SchemeRepository, embeddings: EmbeddingProvider,
        canonical_events: Callable[[str], list[str]], *, embedding_dimension: int,
        evaluate: Callable[[Scheme, UserProfile], dict[str, bool]] = calculate_eligibility_match,
    ) -> None:
        self.schemes = schemes
        self.embeddings = embeddings
        self.canonical_events = canonical_events
        self.embedding_dimension = embedding_dimension
        self.evaluate = evaluate

    def is_topic_consistent(self, scheme: Scheme, requested_life_event: str | None) -> bool:
        if not requested_life_event:
            return True
        canonical_life_events = self.canonical_events(scheme.id)
        if canonical_life_events:
            return requested_life_event in canonical_life_events
        return requested_life_event in scheme.life_events

    async def match_schemes(
        self, *, profile: UserProfile, query_text: str | None = None, limit: int = 5,
    ) -> list[SchemeMatch]:
        logger.info(
            "Starting deterministic scheme matching for life_event=%s age=%s category=%s income=%s",
            profile.life_event, profile.age, profile.category, profile.annual_income,
        )
        query_embedding = None
        if query_text:
            try:
                embedding = await self.embeddings.get_embedding(query_text)
                if embedding and len(embedding) == self.embedding_dimension:
                    query_embedding = embedding
                elif embedding:
                    logger.warning(
                        "Skipping vector ranking: expected %s-dim embedding, received %s",
                        self.embedding_dimension, len(embedding),
                    )
                else:
                    logger.warning("Skipping vector ranking: embedding unavailable from all providers")
            except Exception as exc:
                logger.warning("Failed to get query embedding: %s", exc)
        fetch_limit = max(limit * 3, 10)
        candidates = await self.schemes.retrieve_candidates(
            life_event=profile.life_event, profile=profile,
            query_embedding=query_embedding, limit=fetch_limit,
        )
        matches = [
            SchemeMatch(
                scheme=candidate.scheme, similarity=candidate.similarity,
                eligibility_match=self.evaluate(candidate.scheme, profile),
            )
            for candidate in candidates
        ]
        if matches:
            filtered = []
            for match in matches:
                if not self.is_topic_consistent(match.scheme, profile.life_event):
                    logger.info(
                        "Filtered out scheme %s for topic mismatch: requested=%s canonical_life_events=%s runtime_life_events=%s",
                        match.scheme.id, profile.life_event,
                        self.canonical_events(match.scheme.id), match.scheme.life_events,
                    )
                    continue
                failing_fields = [
                    field for field, is_match in match.eligibility_match.items() if is_match is False
                ]
                if failing_fields:
                    logger.info(
                        "Filtered out scheme %s after deterministic checks: failed=%s life_events=%s",
                        match.scheme.id, ",".join(failing_fields), match.scheme.life_events,
                    )
                    continue
                filtered.append(match)
            matches = rank_schemes(filtered)[:limit]
        logger.info(
            "Deterministic scheme matches complete: life_event=%s matched_ids=%s",
            profile.life_event, [match.scheme.id for match in matches],
        )
        return matches

    async def get_schemes_for_life_event(self, life_event: str, limit: int = 5) -> list[SchemeMatch]:
        schemes = await self.schemes.get_schemes_by_life_event(life_event, limit)
        return [SchemeMatch(scheme=scheme, similarity=0.0, eligibility_match={}) for scheme in schemes]


def rank_schemes(matches: list[SchemeMatch]) -> list[SchemeMatch]:
    """Re-rank schemes by a combined score."""
    def _compute_score(match: SchemeMatch) -> float:
        # Base similarity score
        result = match.similarity * 0.4

        # Eligibility match bonus
        if match.eligibility_match:
            match_rate = sum(match.eligibility_match.values()) / len(match.eligibility_match)
            result += match_rate * 0.4

        # Benefits amount bonus (normalized)
        if match.scheme.benefits_amount:
            # Normalize to 0-1 range (assuming max 10 lakh)
            normalized_benefit = min(match.scheme.benefits_amount / 1000000, 1.0)
            result += normalized_benefit * 0.2

        return result

    ranked: list[SchemeMatch] = []
    for match in matches:
        ranked.append(
            match.model_copy(update={"deterministic_score": _compute_score(match)})
        )
    return sorted(ranked, key=lambda match: match.deterministic_score, reverse=True)
