"""Phase 3 expand: expose the existing Jina adapter at its new path."""

from src.integrations.jina_client import (
    EMBEDDING_DIM as EMBEDDING_DIM,
)
from src.integrations.jina_client import (
    JINA_API_URL as JINA_API_URL,
)
from src.integrations.jina_client import (
    JINA_MODEL as JINA_MODEL,
)
from src.integrations.jina_client import (
    EmbeddingResult as EmbeddingResult,
)
from src.integrations.jina_client import (
    JinaEmbeddingClient as JinaEmbeddingClient,
)
from src.integrations.jina_client import (
    configure_jina_client as configure_jina_client,
)
from src.integrations.jina_client import (
    get_jina_client as get_jina_client,
)
