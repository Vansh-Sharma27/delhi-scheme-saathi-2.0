"""Port: scheme repository.

Defines the read surface over schemes so the matching layer and the
scheme-detail endpoint can depend on the port instead of a pool-bound
implementation detail. The adapter holds the pool and implements this port.

Raw retrieval returns SchemeCandidate values for application-side evaluation.
Domain types are runtime imports, visible to the full import-linter graph.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from src.dss.domain.profiles.profile import UserProfile
from src.dss.domain.schemes.scheme import Scheme, SchemeCandidate


@runtime_checkable
class SchemeRepository(Protocol):
    """Read access to schemes and raw matching candidates."""

    async def get_scheme_by_id(self, scheme_id: str) -> Scheme | None: ...
    async def get_schemes_by_life_event(
        self, life_event: str, limit: int = 10
    ) -> list[Scheme]: ...
    async def get_all_schemes(self, active_only: bool = True) -> list[Scheme]: ...
    async def count_active_schemes(self) -> int: ...
    async def list_life_events(self) -> list[dict[str, Any]]: ...
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
