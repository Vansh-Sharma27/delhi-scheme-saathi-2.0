"""Temporary constructor compatibility for legacy AI consumers."""

from collections.abc import Callable, Mapping

from src.dss.application.conversation.ai_orchestrator import AIExecutionPolicy as AIExecutionPolicy
from src.dss.application.conversation.ai_orchestrator import AIOrchestrator as ApplicationAI
from src.dss.application.conversation.ai_orchestrator import AITaskType as AITaskType
from src.dss.application.conversation.ai_orchestrator import LLMUsageEvent as LLMUsageEvent
from src.dss.application.ports.llm import LLMProvider
from src.dss.infrastructure.ai.fallback_client import FallbackLLMClient, get_llm_client
from src.dss.settings import get_settings


class AIOrchestrator(ApplicationAI):
    def __init__(
        self,
        llm_client: LLMProvider | None = None,
        *,
        policies: Mapping[AITaskType, AIExecutionPolicy] | None = None,
        usage_sink: Callable[[LLMUsageEvent], None] | None = None,
    ) -> None:
        super().__init__(
            llm_client=llm_client or get_llm_client(),
            settings=get_settings(),
            safe_analysis=FallbackLLMClient._safe_analysis_payload,
            safe_relevance=FallbackLLMClient._safe_relevance_payload,
            safe_generation=FallbackLLMClient._safe_generation_text,
            policies=policies,
            usage_sink=usage_sink,
        )


_ai_orchestrator: AIOrchestrator | None = None


def configure_ai_orchestrator(orchestrator: AIOrchestrator | None) -> None:
    global _ai_orchestrator
    _ai_orchestrator = orchestrator


def get_ai_orchestrator() -> AIOrchestrator:
    global _ai_orchestrator
    if _ai_orchestrator is None:
        _ai_orchestrator = AIOrchestrator()
    return _ai_orchestrator
