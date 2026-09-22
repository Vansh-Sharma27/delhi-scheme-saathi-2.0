"""New adapter paths must remain usable throughout expand/migrate/contract."""

from src.dss.application.ports.embeddings import EmbeddingProvider
from src.dss.application.ports.llm import LLMProvider
from src.dss.application.ports.session_repository import SessionStore
from src.dss.application.ports.speech import SpeechProvider
from src.dss.application.ports.work_queue import AIWorkQueue
from src.dss.infrastructure.ai.fallback_client import FallbackLLMClient
from src.dss.infrastructure.embeddings.fallback_client import FallbackEmbeddingClient
from src.dss.infrastructure.embeddings.jina_client import JinaEmbeddingClient
from src.dss.infrastructure.queues.work_queue import InMemoryAIWorkQueue, SQSAIWorkQueue
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


def test_expanded_work_queues_expose_the_port() -> None:
    assert issubclass(InMemoryAIWorkQueue, AIWorkQueue)
    assert issubclass(SQSAIWorkQueue, AIWorkQueue)


def test_expanded_llm_composite_exposes_the_port() -> None:
    assert issubclass(FallbackLLMClient, LLMProvider)


def test_expanded_prompt_loader_matches_legacy_templates() -> None:
    from src.dss.infrastructure.ai.prompts.loader import load_prompt
    from src.prompts.loader import load_prompt as legacy_load

    for name in ("analysis_system_prompt", "generate_response", "system_prompt"):
        assert load_prompt(name) == legacy_load(name)
