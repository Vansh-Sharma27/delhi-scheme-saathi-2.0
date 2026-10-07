"""Structured LLM usage events and logging."""

import json
import logging
from dataclasses import asdict, dataclass


@dataclass(frozen=True, slots=True)
class LLMUsageEvent:
    """Structured telemetry for one orchestrated LLM task."""

    task_type: str
    session_id: str | None
    provider: str | None
    fallback_used: bool
    latency_ms: float
    prompt_chars: int
    queue_lag_ms: float | None = None
    error: str | None = None


def log_llm_usage(event: LLMUsageEvent, logger: logging.Logger) -> None:
    logger.info("llm_usage %s", json.dumps(asdict(event), ensure_ascii=False))
