"""Port: session repository.

Canonical home for the session repository contract, moved here in Phase 2
from `src/db/session_store.py` so the application conversation layer can
depend on the port and Phase 3 can relocate the in-memory and DynamoDB
adapters behind it. The legacy module re-exports the protocol; the facade
is removed in Phase 6.

Session values are imported directly from the canonical domain model.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from src.dss.domain.conversations.session import Session


@runtime_checkable
class SessionStore(Protocol):
    """Read and write access to conversation sessions keyed by user id."""

    async def get(self, user_id: str) -> Session | None: ...
    async def save(self, session: Session) -> None: ...
    async def delete(self, user_id: str) -> None: ...
