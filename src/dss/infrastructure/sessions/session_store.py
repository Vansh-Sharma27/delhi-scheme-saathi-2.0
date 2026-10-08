"""Session store - in-memory for MVP, DynamoDB for production.

Implements the ``SessionStore`` port with in-memory and DynamoDB adapters.

In-memory saves accept an injected Clock, defaulting to SystemClock. DynamoDB
reads use an optional clock only for missing timestamps. TTL remains derived
from updated_at plus seven days, and DynamoDB saves never restamp the session.
"""

from contextlib import suppress

from src.dss.application.ports.clock import Clock
from src.dss.application.ports.session_repository import (
    SessionStore as SessionStore,
)
from src.dss.domain.conversations.session import Session
from src.dss.infrastructure.sessions.clock import SystemClock
from src.dss.infrastructure.sessions.codec import session_from_item


class InMemorySessionStore:
    """In-memory session store for local development."""

    def __init__(self, clock: Clock | None = None) -> None:
        self._sessions: dict[str, Session] = {}
        self._clock: Clock = clock if clock is not None else SystemClock()

    async def get(self, user_id: str) -> Session | None:
        """Get session by user ID."""
        session = self._sessions.get(user_id)
        return session.model_copy(deep=True).with_clock(session.clock) if session else None

    async def save(self, session: Session) -> None:
        """Save or update session."""
        updated = session.copy_with(updated_at=self._clock.now())
        self._sessions[session.user_id] = updated

    async def delete(self, user_id: str) -> None:
        """Delete session."""
        self._sessions.pop(user_id, None)

    def clear(self) -> None:
        """Clear all sessions (for testing)."""
        self._sessions.clear()


class DynamoDBSessionStore:
    """DynamoDB session store for AWS deployment (Phase 6)."""

    def __init__(
        self, table_name: str, region: str = "ap-south-1", *, clock: Clock | None = None
    ) -> None:
        import boto3
        self._table_name = table_name
        self._clock = clock
        self._dynamodb = boto3.resource("dynamodb", region_name=region)
        self._closed = False
        try:
            self._table = self._dynamodb.Table(table_name)
        except BaseException:
            # Preserve the construction error even if releasing the client fails.
            with suppress(Exception):
                self.close()
            raise

    def close(self) -> None:
        """Release the owned SDK client's connections at most once."""
        if not self._closed:
            self._closed = True
            self._dynamodb.meta.client.close()

    async def get(self, user_id: str) -> Session | None:
        """Get session by user ID."""
        import asyncio

        def _get():
            response = self._table.get_item(
                Key={"user_id": user_id},
                ConsistentRead=True,
            )
            return response.get("Item")

        item = await asyncio.get_running_loop().run_in_executor(None, _get)
        if item:
            return session_from_item(Session, item, clock=self._clock)
        return None

    async def save(self, session: Session) -> None:
        """Save or update session."""
        import asyncio

        item = session.to_dynamodb_item()

        def _put():
            self._table.put_item(Item=item)

        await asyncio.get_running_loop().run_in_executor(None, _put)

    async def delete(self, user_id: str) -> None:
        """Delete session."""
        import asyncio

        def _delete():
            self._table.delete_item(Key={"user_id": user_id})

        await asyncio.get_running_loop().run_in_executor(None, _delete)
