"""Temporary alias for the canonical scheme-reference implementation."""

import sys

from src.dss.application.conversation import scheme_reference
from src.dss.application.conversation.scheme_reference import (
    store_presented_schemes as store_presented_schemes,
)

sys.modules[__name__] = scheme_reference
