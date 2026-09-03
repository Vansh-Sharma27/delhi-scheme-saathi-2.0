"""Port: document repository.

Defines the read surface over scheme application documents so the guidance
layer and the document-detail endpoint can depend on the port instead of
the `src.db.document_repo` function module. The functions there are
module-level and take a pool as the first argument, so no existing class
satisfies a class-shaped protocol; Phase 3 wraps them in an adapter class
that holds the pool and implements this port.

`Document` still lives in `src/models/document.py` and is referenced here
only under `if TYPE_CHECKING:`. The import-linter graph drops TYPE_CHECKING
imports, so this port has no runtime dependency on the legacy tree. Phase
4 moves `Document` into `src.dss.domain.schemes` and the reference resolves
there.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from src.models.document import Document


@runtime_checkable
class DocumentRepository(Protocol):
    """Read access to scheme application documents."""

    async def get_document_by_id(self, doc_id: str) -> Document | None: ...
    async def get_documents_by_ids(self, doc_ids: list[str]) -> list[Document]: ...
    async def get_all_documents(self) -> list[Document]: ...
    async def get_documents_for_scheme(self, scheme_id: str) -> list[Document]: ...
    async def search_documents(self, query: str, limit: int = 10) -> list[Document]: ...
