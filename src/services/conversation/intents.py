"""Temporary alias for canonical deterministic intent policy."""

import sys

from src.dss.application.conversation import intents

sys.modules[__name__] = intents
