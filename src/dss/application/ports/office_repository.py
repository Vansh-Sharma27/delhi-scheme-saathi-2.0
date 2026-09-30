"""Port: office repository.

Defines the read surface over government offices and CSCs so the guidance
layer and the nearest-office endpoint can depend on the port instead of
the `src/db/office_repo` function module. The functions there are
module-level and take a pool as the first argument, so no existing class
satisfies a class-shaped protocol; Phase 3 wraps them in an adapter class
that holds the pool and implements this port.

`haversine_distance` is a pure helper used only inside `get_nearest_offices`
and is not part of the port; it stays with the adapter.

`Office` still lives in `src/models/office.py` and is referenced here only
under `if TYPE_CHECKING:`. The import-linter graph drops TYPE_CHECKING
imports, so this port has no runtime dependency on the legacy tree. Phase
4 moves `Office` into `src.dss.domain.schemes` and the reference resolves
there.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from src.dss.domain.schemes.office import Office


@runtime_checkable
class OfficeRepository(Protocol):
    """Read access to government offices and CSCs."""

    async def get_office_by_id(self, office_id: str) -> Office | None: ...
    async def get_offices_by_district(
        self, district: str, limit: int = 10
    ) -> list[Office]: ...
    async def get_nearest_offices(
        self,
        latitude: float,
        longitude: float,
        limit: int = 5,
        office_type: str | None = None,
    ) -> list[Office]: ...
    async def get_offices_by_service(
        self,
        document_id: str,
        district: str | None = None,
        limit: int = 10,
    ) -> list[Office]: ...
    async def get_all_offices(self) -> list[Office]: ...
