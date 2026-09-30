"""Re-export facade for the LLM fallback composite moved in Phase 3.

Canonical home: ``src.dss.infrastructure.ai.fallback_client``. This module forwards the public names so existing imports keep working; it is deleted in Phase 6 (spec 2.1, 2.3 contract step). The port types re-export from ``src.dss.application.ports.llm``, their single canonical home since Phase 2. The singleton lives in the canonical module; callers that reset it for tests import the canonical module directly.
"""

from src.dss.application.ports.llm import (
    ProviderExecutionResult as ProviderExecutionResult,
)
from src.dss.application.ports.llm import (
    TaskPriority as TaskPriority,
)
from src.dss.infrastructure.ai.fallback_client import (
    FallbackLLMClient as FallbackLLMClient,
)
from src.dss.infrastructure.ai.fallback_client import (
    LLMClient as LLMClient,
)
from src.dss.infrastructure.ai.fallback_client import (
    get_llm_client as get_llm_client,
)
