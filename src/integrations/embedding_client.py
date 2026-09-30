"""Re-export facade for the embedding adapters moved in Phase 3.

Canonical home: ``src.dss.infrastructure.embeddings.fallback_client``.
This module forwards the public names so existing imports keep working;
it is deleted in Phase 6 (spec 2.1, 2.3 contract step). The singleton
lives in the canonical module; callers that reset it for tests import
the canonical module directly.
"""

from src.dss.infrastructure.embeddings.fallback_client import (
    EMBEDDING_DIM as EMBEDDING_DIM,
)
from src.dss.infrastructure.embeddings.fallback_client import (
    VOYAGE_API_URL as VOYAGE_API_URL,
)
from src.dss.infrastructure.embeddings.fallback_client import (
    VOYAGE_MODEL as VOYAGE_MODEL,
)
from src.dss.infrastructure.embeddings.fallback_client import (
    EmbeddingClient as EmbeddingClient,
)
from src.dss.infrastructure.embeddings.fallback_client import (
    FallbackEmbeddingClient as FallbackEmbeddingClient,
)
from src.dss.infrastructure.embeddings.fallback_client import (
    get_embedding_client as get_embedding_client,
)
