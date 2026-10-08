"""New adapter paths must remain usable throughout expand/migrate/contract."""

from pathlib import Path

import pytest

from src.dss.application.ports.embeddings import EmbeddingProvider
from src.dss.application.ports.llm import LLMProvider
from src.dss.application.ports.session_repository import SessionStore
from src.dss.application.ports.speech import SpeechProvider
from src.dss.application.ports.work_queue import AIWorkQueue
from src.dss.infrastructure.ai.bedrock_client import BedrockLLMClient
from src.dss.infrastructure.ai.fallback_client import FallbackLLMClient
from src.dss.infrastructure.ai.grok_client import GrokLLMClient
from src.dss.infrastructure.ai.prompts import loader
from src.dss.infrastructure.embeddings.fallback_client import FallbackEmbeddingClient
from src.dss.infrastructure.embeddings.jina_client import JinaEmbeddingClient
from src.dss.infrastructure.queues.work_queue import InMemoryAIWorkQueue, SQSAIWorkQueue
from src.dss.infrastructure.sessions.session_store import DynamoDBSessionStore, InMemorySessionStore
from src.dss.infrastructure.speech.bhashini import BhashiniClient
from src.dss.infrastructure.speech.sarvam import SarvamClient


@pytest.mark.parametrize("adapter,module", [
    (BedrockLLMClient, "ai.bedrock_client"),
    (GrokLLMClient, "ai.grok_client"),
    (FallbackLLMClient, "ai.fallback_client"),
    (FallbackEmbeddingClient, "embeddings.fallback_client"),
    (JinaEmbeddingClient, "embeddings.jina_client"),
    (SarvamClient, "speech.sarvam"),
    (BhashiniClient, "speech.bhashini"),
])
def test_provider_adapters_are_owned_by_infrastructure(adapter, module) -> None:
    assert adapter.__module__ == f"src.dss.infrastructure.{module}"


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


def test_prompt_loader_owns_and_reads_canonical_templates() -> None:
    prompts_dir = (
        Path(__file__).resolve().parents[1] / "src/dss/infrastructure/ai/prompts"
    )
    assert loader.load_prompt.__module__ == "src.dss.infrastructure.ai.prompts.loader"
    assert loader.PROMPTS_DIR.resolve() == prompts_dir
    for name in ("analysis_system_prompt", "generate_response", "system_prompt"):
        expected = (prompts_dir / f"{name}.txt").read_text(encoding="utf-8")
        assert expected.strip()
        assert loader.load_prompt(name) == expected
    assert loader.get_analysis_system_prompt() == loader.load_prompt("analysis_system_prompt")
    assert loader.get_system_prompt() == loader.get_analysis_system_prompt()
    assert loader.get_generate_response_prompt() == loader.load_prompt("generate_response")
    with pytest.raises(FileNotFoundError, match="Prompt template not found: missing_template"):
        loader.load_prompt("missing_template")


def test_expanded_repositories_share_the_canonical_functions() -> None:
    from src.dss.infrastructure.database import (
        document_repo as documents,
    )
    from src.dss.infrastructure.database import (
        office_repo as offices,
    )
    from src.dss.infrastructure.database import (
        rejection_rule_repo as rules,
    )
    from src.dss.infrastructure.database import (
        scheme_repo as schemes,
    )

    assert documents.get_document_by_id.__module__ == documents.__name__
    assert offices.get_nearest_offices.__module__ == offices.__name__
    assert rules.get_rules_by_scheme.__module__ == rules.__name__
    assert schemes.hybrid_search.__module__ == schemes.__name__
