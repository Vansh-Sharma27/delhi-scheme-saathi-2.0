"""Phase 3 expand: expose the existing embedding adapter at its new path."""

from src.integrations.embedding_client import (
    EMBEDDING_DIM as EMBEDDING_DIM,
)
from src.integrations.embedding_client import (
    VOYAGE_API_URL as VOYAGE_API_URL,
)
from src.integrations.embedding_client import (
    VOYAGE_MODEL as VOYAGE_MODEL,
)
from src.integrations.embedding_client import (
    EmbeddingClient as EmbeddingClient,
)
from src.integrations.embedding_client import (
    FallbackEmbeddingClient as FallbackEmbeddingClient,
)
from src.integrations.embedding_client import (
    get_embedding_client as get_embedding_client,
)
