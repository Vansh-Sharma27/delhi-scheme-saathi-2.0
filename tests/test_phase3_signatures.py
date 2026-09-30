"""Pin parameter names, kinds, and defaults across adapter boundaries."""

import inspect

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


def test_provider_signatures_preserve_port_parameters() -> None:
    for adapter, port in (
        (FallbackLLMClient, LLMProvider),
        (FallbackEmbeddingClient, EmbeddingProvider),
        (JinaEmbeddingClient, EmbeddingProvider),
        (SarvamClient, SpeechProvider),
        (BhashiniClient, SpeechProvider),
        (InMemorySessionStore, SessionStore),
        (DynamoDBSessionStore, SessionStore),
        (InMemoryAIWorkQueue, AIWorkQueue),
        (SQSAIWorkQueue, AIWorkQueue),
    ):
        for name, method in vars(port).items():
            if name.startswith("_") or not inspect.isfunction(method):
                continue
            expected = list(inspect.signature(method).parameters.values())[1:]
            actual = list(inspect.signature(getattr(adapter, name)).parameters.values())[1:]
            assert [(p.name, p.kind, p.default) for p in actual[:len(expected)]] == [
                (p.name, p.kind, p.default) for p in expected
            ], (adapter.__name__, name)
            assert all(p.default is not inspect.Parameter.empty for p in actual[len(expected):])
