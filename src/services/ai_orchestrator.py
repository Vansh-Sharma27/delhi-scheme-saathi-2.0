"""Live compatibility alias for application AI orchestration."""

import sys

from src.config import get_settings
from src.dss.application.conversation import ai_orchestrator as _implementation
from src.dss.application.conversation.ai_orchestrator import AIExecutionPolicy as AIExecutionPolicy
from src.dss.application.conversation.ai_orchestrator import AIOrchestrator as AIOrchestrator
from src.dss.application.conversation.ai_orchestrator import AITaskType as AITaskType
from src.dss.application.conversation.ai_orchestrator import LLMUsageEvent as LLMUsageEvent
from src.dss.application.conversation.ai_orchestrator import (
    configure_ai_orchestrator as configure_ai_orchestrator,
)
from src.dss.application.conversation.ai_orchestrator import (
    get_ai_orchestrator as get_ai_orchestrator,
)

_implementation.get_settings = get_settings
sys.modules[__name__] = _implementation
