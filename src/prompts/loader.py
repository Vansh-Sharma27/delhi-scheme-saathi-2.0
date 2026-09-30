"""Re-export facade for the prompt loader moved in Phase 3.

Canonical home: ``src.dss.infrastructure.ai.prompts.loader``. This module
forwards the loader functions so existing imports keep working; it is
deleted in Phase 6 (spec 2.1, 2.3 contract step). The prompt ``.txt`` files
moved together with the loader (spec 7.4), so ``PROMPTS_DIR`` resolves beside
them at the canonical path and no prompt content changed.
"""

from src.dss.infrastructure.ai.prompts.loader import (
    PROMPTS_DIR as PROMPTS_DIR,
)
from src.dss.infrastructure.ai.prompts.loader import (
    get_analysis_system_prompt as get_analysis_system_prompt,
)
from src.dss.infrastructure.ai.prompts.loader import (
    get_generate_response_prompt as get_generate_response_prompt,
)
from src.dss.infrastructure.ai.prompts.loader import (
    get_system_prompt as get_system_prompt,
)
from src.dss.infrastructure.ai.prompts.loader import (
    load_prompt as load_prompt,
)
