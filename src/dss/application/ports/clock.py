"""Port: time source.

Introduces a clock abstraction so session expiry, memory-refresh lag, and
the DynamoDB TTL computation in `Session.to_dynamodb_item` can be made
deterministic in tests (spec 6.1). Today those paths call `datetime.now(UTC)`
directly. Phase 2 defines the port and a fake; Phase 3 threads an injected
clock through the session helpers, which is the behavioural change the spec
flags as needing deliberate golden regeneration (spec Phase 3 caution).

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
