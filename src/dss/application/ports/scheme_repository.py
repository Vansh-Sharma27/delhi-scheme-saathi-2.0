"""Port: scheme repository.

Defines the read surface over schemes so the matching layer and the
scheme-detail endpoint can depend on the port instead of the
`src.db.scheme_repo` function module. The functions there are module-level
and take a pool as the first argument, so no existing class satisfies a
class-shaped protocol; Phase 3 wraps them in an adapter class that holds
the pool and implements this port.

The six methods mirror the legacy repo's public read surface, including
`hybrid_search` (the 3-stage pipeline spec 7.3 says is the riskiest item in
the migration) and `search_schemes_by_text` which has no live callers today
but is part of the documented read surface. `get_scheme_debug_rows` returns
plain dicts, so it needs no domain-type reference.

`Scheme`, `SchemeMatch`, and `UserProfile` still live in the legacy
`src.models` tree and are referenced here only under `if TYPE_CHECKING:`.
The import-linter graph drops TYPE_CHECKING imports, so this port has no
runtime dependency on the legacy tree. Phase 4 moves `Scheme` and
`SchemeMatch` into `src.dss.domain.schemes` and `UserProfile` into
`src.dss.domain.profiles`, and these references resolve there.
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
