"""Re-export facade for the Bedrock LLM adapter moved in Phase 3.

Canonical home: ``src.dss.infrastructure.ai.bedrock_client``. This module forwards the public names so existing imports keep working; it is deleted in Phase 6 (spec 2.1, 2.3 contract step). Tests that swap the adapter class patch the canonical module, where the fallback composite's lazy imports now resolve.
"""

from src.dss.infrastructure.ai.bedrock_client import (
    NOVA_MODEL_ID as NOVA_MODEL_ID,
)
from src.dss.infrastructure.ai.bedrock_client import (
    BedrockLLMClient as BedrockLLMClient,
)
