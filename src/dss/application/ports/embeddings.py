"""Port: embedding provider.

Canonical home for the embedding provider contract, moved here in Phase 2
from ``src/integrations/embedding_client.py`` so the application matching
layer can depend on the port and Phase 3 can relocate the Jina/Voyage
adapters behind it. The legacy module re-exports the protocol; the facade
is removed in Phase 6.

``EMBEDDING_DIM`` stays with the legacy adapter; it is an adapter-level
length guard (spec 10.4 frozen list), not part of the port contract.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class EmbeddingProvider(Protocol):
    """Provider contract for vector embeddings of scheme matching queries."""

    async def get_embedding(self, text: str) -> list[float] | None: ...
    async def get_embeddings_batch(self, texts: list[str]) -> list[list[float]]: ...
