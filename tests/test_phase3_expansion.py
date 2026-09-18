"""New adapter paths must remain usable throughout expand/migrate/contract."""

from src.dss.application.ports.embeddings import EmbeddingProvider
from src.dss.application.ports.session_repository import SessionStore
from src.dss.application.ports.speech import SpeechProvider
from src.dss.infrastructure.embeddings.fallback_client import FallbackEmbeddingClient
from src.dss.infrastructure.embeddings.jina_client import JinaEmbeddingClient
from src.dss.infrastructure.sessions.session_store import DynamoDBSessionStore, InMemorySessionStore
from src.dss.infrastructure.speech.bhashini import BhashiniClient
from src.dss.infrastructure.speech.sarvam import SarvamClient


def test_expanded_embedding_adapters_expose_the_port() -> None:
    assert issubclass(FallbackEmbeddingClient, EmbeddingProvider)
    assert issubclass(JinaEmbeddingClient, EmbeddingProvider)


def test_expanded_speech_adapters_expose_the_port() -> None:
    assert issubclass(SarvamClient, SpeechProvider)
    assert issubclass(BhashiniClient, SpeechProvider)


def test_expanded_session_stores_expose_the_port() -> None:
    assert issubclass(InMemorySessionStore, SessionStore)
    assert issubclass(DynamoDBSessionStore, SessionStore)
