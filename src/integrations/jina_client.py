"""Re-export facade for the Jina embedding adapter moved in Phase 3.

Canonical home: ``src.dss.infrastructure.embeddings.jina_client``. This module
forwards the public names so existing imports keep working; it is deleted in
Phase 6 (spec 2.1, 2.3 contract step). The singleton lives in the canonical
module; callers that reset it for tests import the canonical module directly.
"""

from src.dss.infrastructure.embeddings.jina_client import (
    EMBEDDING_DIM as EMBEDDING_DIM,
)
from src.dss.infrastructure.embeddings.jina_client import (
    JINA_API_URL as JINA_API_URL,
)
from src.dss.infrastructure.embeddings.jina_client import (
    JINA_MODEL as JINA_MODEL,
)
from src.dss.infrastructure.embeddings.jina_client import (
    EmbeddingResult as EmbeddingResult,
)
from src.dss.infrastructure.embeddings.jina_client import (
    JinaEmbeddingClient as JinaEmbeddingClient,
)
from src.dss.infrastructure.embeddings.jina_client import (
    configure_jina_client as configure_jina_client,
)
from src.dss.infrastructure.embeddings.jina_client import (
    get_jina_client as get_jina_client,
)
