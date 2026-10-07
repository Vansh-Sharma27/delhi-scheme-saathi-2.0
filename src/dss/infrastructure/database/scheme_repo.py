"""Scheme repository with 3-stage hybrid search.

Moved to ``src.dss.infrastructure.database`` in Phase 3; the legacy
``src.db.scheme_repo`` module re-exports these names until Phase 6 removes
the facade. The pool-holding adapter classes implementing the Phase 2
repository ports live in ``src.dss.infrastructure.database.adapters``.
"""

import logging
from typing import Any, cast

import asyncpg

from src.dss.domain.eligibility.evaluator import INCOME_SEGMENT_ORDER as INCOME_SEGMENT_ORDER
from src.dss.domain.eligibility.evaluator import (
    _infer_income_segment as _infer_income_segment,
)
from src.dss.domain.eligibility.evaluator import (
    _lookup_case_insensitive as _lookup_case_insensitive,
)
from src.dss.domain.eligibility.evaluator import (
    calculate_eligibility_match as calculate_eligibility_match,
)
from src.dss.domain.profiles.profile import UserProfile
from src.dss.domain.schemes.scheme import EligibilityCriteria, Scheme, SchemeCandidate, SchemeMatch
from src.dss.infrastructure.database.catalog import (
    get_canonical_life_events,
    get_canonical_scheme_ids_for_life_event,
)
from src.dss.infrastructure.database.scheme_codec import scheme_from_row

logger = logging.getLogger(__name__)


async def count_active_schemes(pool: asyncpg.Pool) -> int:
    """Preserve the health endpoint's active-scheme count query."""
    async with pool.acquire() as conn:
        count = await conn.fetchval("SELECT COUNT(*) FROM schemes WHERE is_active = true")
    return cast(int, count or 0)


async def list_life_events(pool: asyncpg.Pool) -> list[dict[str, Any]]:
    """Read the taxonomy in the same order and shape as the HTTP endpoint."""
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT key, display_name, display_name_hindi, aliases FROM life_events_taxonomy ORDER BY key"
        )
    return [
        {
            "key": row["key"],
            "display_name": row["display_name"],
            "display_name_hindi": row["display_name_hindi"],
            "aliases": list(row["aliases"] or []),
        }
        for row in rows
    ]


async def get_scheme_by_id(pool: asyncpg.Pool, scheme_id: str) -> Scheme | None:
    """Get a single scheme by ID."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM schemes WHERE id = $1 AND is_active = true",
            scheme_id
        )
        if row:
            return scheme_from_row(Scheme, row)
    return None


async def get_schemes_by_life_event(
    pool: asyncpg.Pool,
    life_event: str,
    limit: int = 10
) -> list[Scheme]:
    """Get schemes matching a life event."""
    canonical_ids = get_canonical_scheme_ids_for_life_event(life_event)
    async with pool.acquire() as conn:
        if canonical_ids:
            rows = await conn.fetch(
                """
                SELECT * FROM schemes
                WHERE is_active = true AND id = ANY($1::text[])
                ORDER BY benefits_amount DESC NULLS LAST
                LIMIT $2
                """,
                canonical_ids,
                limit,
            )
        else:
            rows = await conn.fetch(
                """
                SELECT * FROM schemes
                WHERE is_active = true AND $1 = ANY(life_events)
                ORDER BY benefits_amount DESC NULLS LAST
                LIMIT $2
                """,
                life_event,
                limit
            )
        return [scheme_from_row(Scheme, row) for row in rows]


async def get_all_schemes(pool: asyncpg.Pool, active_only: bool = True) -> list[Scheme]:
    """Get all schemes."""
    async with pool.acquire() as conn:
        query = "SELECT * FROM schemes"
        if active_only:
            query += " WHERE is_active = true"
        query += " ORDER BY name"
        rows = await conn.fetch(query)
        return [scheme_from_row(Scheme, row) for row in rows]


async def retrieve_candidates(
    pool: asyncpg.Pool,
    life_event: str | None,
    profile: UserProfile,
    query_embedding: list[float] | None = None,
    limit: int = 5
) -> list[SchemeCandidate]:
    """Retrieve SQL-filtered candidates in the existing vector/benefit order."""
    async with pool.acquire() as conn:
        # Build dynamic query based on available filters
        params: list[Any] = []
        conditions = ["is_active = true"]
        param_idx = 1

        # Stage 1: Life event filter
        if life_event:
            canonical_ids = get_canonical_scheme_ids_for_life_event(life_event)
            if canonical_ids:
                conditions.append(f"id = ANY(${param_idx}::text[])")
                params.append(canonical_ids)
            else:
                conditions.append(f"${param_idx} = ANY(life_events)")
                params.append(life_event)
            param_idx += 1

        # Stage 2: Eligibility filters
        if profile.age is not None:
            # Age within range (NULL means no restriction)
            conditions.append(f"""
                ((eligibility->>'min_age')::int IS NULL OR (eligibility->>'min_age')::int <= ${param_idx})
                AND ((eligibility->>'max_age')::int IS NULL OR (eligibility->>'max_age')::int >= ${param_idx})
            """)
            params.append(profile.age)
            param_idx += 1

        if profile.annual_income is not None:
            # Income below max (NULL means no restriction)
            conditions.append(f"""
                (eligibility->>'max_income')::int IS NULL
                OR (eligibility->>'max_income')::int >= ${param_idx}
            """)
            params.append(profile.annual_income)
            param_idx += 1

        # Stage 3: Vector similarity (if embedding provided)
        if query_embedding and len(query_embedding) > 0:
            # Pass embedding as a parameterized value to avoid SQL injection
            embedding_str = "[" + ",".join(map(str, query_embedding)) + "]"
            params.append(embedding_str)
            order_by = f"description_embedding <=> ${param_idx}::vector"
            similarity_select = f", 1 - (description_embedding <=> ${param_idx}::vector) as similarity"
            param_idx += 1
        else:
            order_by = "benefits_amount DESC NULLS LAST"
            similarity_select = ", 0.0 as similarity"

        where_clause = " AND ".join(conditions)
        query = f"""
            SELECT *{similarity_select}
            FROM schemes
            WHERE {where_clause}
            ORDER BY {order_by}
            LIMIT ${param_idx}
        """
        params.append(limit)

        rows = await conn.fetch(query, *params)

        # Retrieval returns raw candidates; evaluation belongs to the caller.
        results = []
        for row in rows:
            scheme = scheme_from_row(Scheme, row)
            # Handle None similarity value
            sim_value = row.get("similarity")
            similarity = float(sim_value) if sim_value is not None else 0.0

            results.append(SchemeCandidate(
                scheme=scheme,
                similarity=similarity,
            ))

        return results


async def hybrid_search(
    pool: asyncpg.Pool,
    life_event: str | None,
    profile: UserProfile,
    query_embedding: list[float] | None = None,
    limit: int = 5,
) -> list[SchemeMatch]:
    """Legacy evaluated retrieval, retained until Phase 6."""
    candidates = await retrieve_candidates(pool, life_event, profile, query_embedding, limit)
    return [
        SchemeMatch(scheme=c.scheme, similarity=c.similarity, eligibility_match=_calculate_eligibility_match(c.scheme, profile))
        for c in candidates
    ]


def _calculate_eligibility_match(scheme: Scheme, profile: UserProfile) -> dict[str, bool]:
    """Backward-compatible private alias."""
    return calculate_eligibility_match(scheme, profile)


async def search_schemes_by_text(
    pool: asyncpg.Pool,
    search_text: str,
    limit: int = 10
) -> list[Scheme]:
    """Simple text search in scheme names and descriptions."""
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT * FROM schemes
            WHERE is_active = true
              AND (
                name ILIKE $1 OR name_hindi ILIKE $1
                OR description ILIKE $1 OR description_hindi ILIKE $1
                OR $2 = ANY(tags)
              )
            ORDER BY benefits_amount DESC NULLS LAST
            LIMIT $3
            """,
            f"%{search_text}%",
            search_text.lower(),
            limit
        )
        return [scheme_from_row(Scheme, row) for row in rows]


async def get_scheme_debug_rows(
    pool: asyncpg.Pool,
    scheme_ids: list[str],
) -> list[dict[str, Any]]:
    """Fetch lightweight verification data for specific scheme rows."""
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, name, life_events, eligibility
            FROM schemes
            WHERE id = ANY($1::text[])
            ORDER BY id
            """,
            scheme_ids,
        )

    debug_rows: list[dict[str, Any]] = []
    for row in rows:
        eligibility = EligibilityCriteria.from_db(row.get("eligibility") or {})
        db_life_events = list(row.get("life_events") or [])
        canonical_life_events = get_canonical_life_events(row["id"])
        debug_rows.append(
            {
                "id": row["id"],
                "name": row["name"],
                "life_events": db_life_events,
                "canonical_life_events": canonical_life_events,
                "life_events_match": not canonical_life_events
                or sorted(db_life_events) == sorted(canonical_life_events),
                "raw_categories": eligibility.categories,
                "caste_categories": eligibility.caste_categories,
                "income_segments": eligibility.income_segments,
                "income_by_category": eligibility.income_by_category,
            }
        )

    if len(debug_rows) != len(scheme_ids):
        missing = sorted(set(scheme_ids) - {row["id"] for row in debug_rows})
        logger.warning("Missing scheme verification rows for: %s", ", ".join(missing))

    return debug_rows
