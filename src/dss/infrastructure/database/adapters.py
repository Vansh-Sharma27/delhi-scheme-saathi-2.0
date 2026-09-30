"""Pool-holding adapters for the database repository ports.

The Phase 2 ports (``SchemeRepository``, ``DocumentRepository``,
``OfficeRepository``, ``RejectionRuleRepository``) are class-shaped, but the
legacy repositories are module-level functions that take the pool as their
first argument. These adapters hold the pool and forward to the same
functions, which are byte-identical to their pre-move bodies, so no query
text, ordering, or fallback changed. The application layer can now depend on
the ports; Phase 5 threads these adapters through the service constructors
and Phase 6 wires them in the composition root.

The domain types (``Scheme``, ``SchemeMatch``, ``UserProfile``, ``Document``,
``Office``, ``RejectionRule``) still live in the legacy ``src.models`` tree
until Phase 4 and are referenced only under ``if TYPE_CHECKING:``, matching
the ports' own pattern, so the import-linter graph records no runtime
dependency on the legacy tree.

``haversine_distance`` stays on the office repo module: it is a pure helper
of the in-Python distance sort, not part of any port.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import asyncpg

from src.dss.application.ports.document_repository import DocumentRepository
from src.dss.application.ports.office_repository import OfficeRepository
from src.dss.application.ports.rejection_rule_repository import RejectionRuleRepository
from src.dss.application.ports.scheme_repository import SchemeRepository
from src.dss.infrastructure.database import (
    document_repo,
    office_repo,
    rejection_rule_repo,
    scheme_repo,
)

if TYPE_CHECKING:
    from src.dss.domain.schemes.rejection_rule import RejectionRule
    from src.models.document import Document
    from src.models.office import Office
    from src.models.scheme import Scheme, SchemeMatch
    from src.models.session import UserProfile


class PostgresSchemeRepository(SchemeRepository):
    """Scheme read access over an asyncpg pool."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def get_scheme_by_id(self, scheme_id: str) -> Scheme | None:
        return await scheme_repo.get_scheme_by_id(self._pool, scheme_id)

    async def get_schemes_by_life_event(
        self, life_event: str, limit: int = 10
    ) -> list[Scheme]:
        return await scheme_repo.get_schemes_by_life_event(
            self._pool, life_event, limit
        )

    async def get_all_schemes(self, active_only: bool = True) -> list[Scheme]:
        return await scheme_repo.get_all_schemes(self._pool, active_only)

    async def hybrid_search(
        self,
        life_event: str | None,
        profile: UserProfile,
        query_embedding: list[float] | None = None,
        limit: int = 5,
    ) -> list[SchemeMatch]:
        return await scheme_repo.hybrid_search(
            self._pool,
            life_event,
            profile,
            query_embedding,
            limit,
        )

    async def search_schemes_by_text(
        self, search_text: str, limit: int = 10
    ) -> list[Scheme]:
        return await scheme_repo.search_schemes_by_text(
            self._pool, search_text, limit
        )

    async def get_scheme_debug_rows(
        self, scheme_ids: list[str]
    ) -> list[dict[str, Any]]:
        return await scheme_repo.get_scheme_debug_rows(self._pool, scheme_ids)


class PostgresDocumentRepository(DocumentRepository):
    """Document read access over an asyncpg pool."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def get_document_by_id(self, doc_id: str) -> Document | None:
        return await document_repo.get_document_by_id(self._pool, doc_id)

    async def get_documents_by_ids(self, doc_ids: list[str]) -> list[Document]:
        return await document_repo.get_documents_by_ids(self._pool, doc_ids)

    async def get_all_documents(self) -> list[Document]:
        return await document_repo.get_all_documents(self._pool)

    async def get_documents_for_scheme(self, scheme_id: str) -> list[Document]:
        return await document_repo.get_documents_for_scheme(self._pool, scheme_id)

    async def search_documents(self, query: str, limit: int = 10) -> list[Document]:
        return await document_repo.search_documents(self._pool, query, limit)


class PostgresOfficeRepository(OfficeRepository):
    """Office read access over an asyncpg pool."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def get_office_by_id(self, office_id: str) -> Office | None:
        return await office_repo.get_office_by_id(self._pool, office_id)

    async def get_offices_by_district(
        self, district: str, limit: int = 10
    ) -> list[Office]:
        return await office_repo.get_offices_by_district(self._pool, district, limit)

    async def get_nearest_offices(
        self,
        latitude: float,
        longitude: float,
        limit: int = 5,
        office_type: str | None = None,
    ) -> list[Office]:
        return await office_repo.get_nearest_offices(
            self._pool, latitude, longitude, limit, office_type
        )

    async def get_offices_by_service(
        self,
        document_id: str,
        district: str | None = None,
        limit: int = 10,
    ) -> list[Office]:
        return await office_repo.get_offices_by_service(
            self._pool, document_id, district, limit
        )

    async def get_all_offices(self) -> list[Office]:
        return await office_repo.get_all_offices(self._pool)


class PostgresRejectionRuleRepository(RejectionRuleRepository):
    """Rejection rule read access over an asyncpg pool."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def get_rules_by_scheme(self, scheme_id: str) -> list[RejectionRule]:
        return await rejection_rule_repo.get_rules_by_scheme(self._pool, scheme_id)

    async def get_rules_by_ids(self, rule_ids: list[str]) -> list[RejectionRule]:
        return await rejection_rule_repo.get_rules_by_ids(self._pool, rule_ids)

    async def get_critical_rules(self, scheme_id: str) -> list[RejectionRule]:
        return await rejection_rule_repo.get_critical_rules(self._pool, scheme_id)

    async def get_all_rules(self) -> list[RejectionRule]:
        return await rejection_rule_repo.get_all_rules(self._pool)
