"""Port: document repository.

Defines the read surface over scheme application documents so the guidance
layer and the document-detail endpoint can depend on the port instead of
the infrastructure document repository. Its adapter holds the pool and
implements this port.

Document values are imported directly from the canonical domain model.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from src.dss.domain.schemes.document import Document


@runtime_checkable
class DocumentRepository(Protocol):
    """Read access to scheme application documents."""

    async def get_document_by_id(self, doc_id: str) -> Document | None: ...
    async def get_documents_by_ids(self, doc_ids: list[str]) -> list[Document]: ...
    async def get_all_documents(self) -> list[Document]: ...
    async def get_documents_for_scheme(self, scheme_id: str) -> list[Document]: ...
    async def search_documents(self, query: str, limit: int = 10) -> list[Document]: ...
