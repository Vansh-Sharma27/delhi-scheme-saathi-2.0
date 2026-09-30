"""Port: time source.

Session helpers and background work accept this time source in Phase 3.
DynamoDB TTL remains derived from the session's updated_at plus seven days;
it does not read the current time. Injecting the clock makes timestamp updates
and memory-refresh lag deterministic without changing that expiry rule.

The port returns a timezone-aware datetime. An adapter wrapping
`datetime.now(UTC)` is the production implementation and lands in Phase 3.
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol, runtime_checkable


@runtime_checkable
class Clock(Protocol):
    """Provider of the current UTC time."""

    def now(self) -> datetime:
        """Return the current time as a timezone-aware UTC datetime."""
        ...
