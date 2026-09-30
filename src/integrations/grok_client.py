"""Re-export facade for the Grok LLM adapter moved in Phase 3.

Canonical home: ``src.dss.infrastructure.ai.grok_client``. This module forwards the public names so existing imports keep working; it is deleted in Phase 6 (spec 2.1, 2.3 contract step). Tests that swap the adapter class patch the canonical module, where the fallback composite's lazy imports now resolve.
"""

from src.dss.infrastructure.ai.grok_client import (
    GrokLLMClient as GrokLLMClient,
)
