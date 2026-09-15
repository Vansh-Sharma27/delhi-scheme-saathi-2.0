"""New adapter paths must remain usable throughout expand/migrate/contract."""

from src.dss.application.ports.embeddings import EmbeddingProvider
from src.dss.infrastructure.embeddings.fallback_client import FallbackEmbeddingClient
from src.dss.infrastructure.embeddings.jina_client import JinaEmbeddingClient


def test_expanded_embedding_adapters_expose_the_port() -> None:
    assert issubclass(FallbackEmbeddingClient, EmbeddingProvider)
    assert issubclass(JinaEmbeddingClient, EmbeddingProvider)
