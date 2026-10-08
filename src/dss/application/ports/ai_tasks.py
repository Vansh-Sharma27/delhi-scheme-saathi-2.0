"""Typed AI task capabilities shared by independent application packages."""

from typing import Any, Protocol

from src.dss.domain.conversations.session import ConversationMemory, Session
from src.dss.domain.schemes.scheme import SchemeMatch


class AITasks(Protocol):
    def should_run_relevance_judge(self, matches: list[SchemeMatch]) -> bool: ...

    async def analyze_message(
        self, *, session: Session, user_message: str,
        conversation_history: list[dict[str, str]], system_prompt: str,
        session_language: str,
    ) -> dict[str, Any]: ...

    async def judge_scheme_relevance(
        self, *, session: Session, user_message: str,
        conversation_history: list[dict[str, str]],
        candidate_schemes: list[dict[str, Any]], session_language: str,
    ) -> dict[str, Any]: ...

    async def generate_response(
        self, *, session: Session, context: dict[str, Any],
        system_prompt: str, user_language: str,
    ) -> str: ...

    async def refresh_working_memory(
        self, session: Session, *, queue_lag_ms: float | None = None,
    ) -> ConversationMemory: ...
