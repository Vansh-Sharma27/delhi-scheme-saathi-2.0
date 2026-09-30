"""Port: scheme repository.

Defines the read surface over schemes so the matching layer and the
scheme-detail endpoint can depend on the port instead of the
`src.db.scheme_repo` function module. The functions there are module-level
and take a pool as the first argument, so no existing class satisfies a
class-shaped protocol; Phase 3 wraps them in an adapter class that holds
the pool and implements this port.

Raw retrieval returns SchemeCandidate values for application-side evaluation.
The legacy hybrid_search method remains until Phase 6. Domain types are
runtime imports, visible to the full import-linter graph.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from src.dss.domain.profiles.profile import UserProfile
from src.dss.domain.schemes.scheme import Scheme, SchemeCandidate, SchemeMatch


@runtime_checkable
class SchemeRepository(Protocol):
    """Read access to schemes and the hybrid matching pipeline."""

    async def get_scheme_by_id(self, scheme_id: str) -> Scheme | None: ...
    async def get_schemes_by_life_event(
        self, life_event: str, limit: int = 10
    ) -> list[Scheme]: ...
    async def get_all_schemes(self, active_only: bool = True) -> list[Scheme]: ...
    async def hybrid_search(
        self,
        life_event: str | None,
        profile: UserProfile,
        query_embedding: list[float] | None = None,
        limit: int = 5,
    ) -> list[SchemeMatch]: ...
    async def retrieve_candidates(
        self,
        life_event: str | None,
        profile: UserProfile,
        query_embedding: list[float] | None = None,
        limit: int = 5,
    ) -> list[SchemeCandidate]: ...
    async def search_schemes_by_text(
        self, search_text: str, limit: int = 10
    ) -> list[Scheme]: ...
    async def get_scheme_debug_rows(
        self, scheme_ids: list[str]
    ) -> list[dict[str, Any]]: ...
