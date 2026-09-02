"""Port: large language model provider.

Canonical home for the LLM provider contract. Moved here in Phase 2 from
``src/integrations/llm_client.py`` so the application layer can depend on the
port and Phase 3 can relocate the Bedrock/Grok adapters behind it without
the application importing infrastructure. The legacy module re-exports
these names so existing imports keep working; the facade is removed in
Phase 6.

The protocol covers both the plain methods (``analyze_message`` etc.) and
the ``*_with_meta`` variants, because the AI orchestrator (spec 7.5, an
application service) consumes the latter for telemetry. Adapters that only
implement the plain four (``BedrockLLMClient``, ``GrokLLMClient``) are not
expected to satisfy the full protocol; the composite ``FallbackLLMClient``
is the port-facing adapter and implements all eight.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Generic, Literal, Protocol, TypeVar

TaskPriority = Literal["inline", "background"]
T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class ProviderExecutionResult(Generic[T]):
    """Result of a provider execution with metadata for observability."""

    output: T
    provider: str | None
    fallback_used: bool
    latency_ms: float
    error: str | None = None


class LLMProvider(Protocol):
    """Provider contract for LLM-backed analysis, generation, and judging.

    The ``*_with_meta`` variants return a :class:`ProviderExecutionResult`
    carrying provider/fallback/latency metadata the orchestrator emits as
    ``llm_usage`` telemetry. The plain variants return the bare payload.
    """

    async def analyze_message(
        self,
        user_message: str,
        conversation_history: list[dict[str, str]],
        current_state: str,
        user_profile: dict[str, Any],
        system_prompt: str,
        session_language: str = "hi",
        working_memory: dict[str, Any] | None = None,
        priority: TaskPriority = "inline",
    ) -> dict[str, Any]: ...

    async def analyze_message_with_meta(
        self,
        user_message: str,
        conversation_history: list[dict[str, str]],
        current_state: str,
        user_profile: dict[str, Any],
        system_prompt: str,
        session_language: str = "hi",
        working_memory: dict[str, Any] | None = None,
        priority: TaskPriority = "inline",
    ) -> ProviderExecutionResult[dict[str, Any]]: ...

    async def generate_response(
        self,
        context: dict[str, Any],
        system_prompt: str,
        user_language: str = "hi",
        priority: TaskPriority = "inline",
    ) -> str: ...

    async def generate_response_with_meta(
        self,
        context: dict[str, Any],
        system_prompt: str,
        user_language: str = "hi",
        priority: TaskPriority = "inline",
    ) -> ProviderExecutionResult[str]: ...

    async def summarize_conversation(
        self,
        messages: list[dict[str, str]],
        current_summary: str | None = None,
        priority: TaskPriority = "background",
    ) -> str: ...

    async def summarize_conversation_with_meta(
        self,
        messages: list[dict[str, str]],
        current_summary: str | None = None,
        priority: TaskPriority = "background",
    ) -> ProviderExecutionResult[str]: ...

    async def judge_scheme_relevance(
        self,
        user_message: str,
        conversation_history: list[dict[str, str]],
        current_state: str,
        user_profile: dict[str, Any],
        candidate_schemes: list[dict[str, Any]],
        session_language: str = "hi",
        working_memory: dict[str, Any] | None = None,
        priority: TaskPriority = "inline",
    ) -> dict[str, Any]: ...

    async def judge_scheme_relevance_with_meta(
        self,
        user_message: str,
        conversation_history: list[dict[str, str]],
        current_state: str,
        user_profile: dict[str, Any],
        candidate_schemes: list[dict[str, Any]],
        session_language: str = "hi",
        working_memory: dict[str, Any] | None = None,
        priority: TaskPriority = "inline",
    ) -> ProviderExecutionResult[dict[str, Any]]: ...
