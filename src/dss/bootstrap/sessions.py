"""Script-callable session-store construction using the existing backend predicate."""

import logging

from src.dss.application.ports.clock import Clock
from src.dss.application.ports.session_repository import SessionStore
from src.dss.infrastructure.sessions.session_store import DynamoDBSessionStore, InMemorySessionStore
from src.dss.settings import Settings

logger = logging.getLogger(__name__)


def build_session_store(settings: Settings, *, clock: Clock | None = None) -> SessionStore:
    """Select the API/script store without importing or starting a web application."""
    if settings.session_table_name and (
        settings.use_bedrock or settings.session_table_name != "dss-sessions"
    ):
        try:
            store = DynamoDBSessionStore(
                table_name=settings.session_table_name, region=settings.aws_region, clock=clock,
            )
            logger.info("Session store: DynamoDB (%s)", settings.session_table_name)
            return store
        except Exception as exc:
            logger.warning("DynamoDB init failed, using in-memory: %s", exc)
            return InMemorySessionStore(clock=clock)
    logger.info("Session store: In-memory (local development)")
    return InMemorySessionStore(clock=clock)


def build_worker_session_store(settings: Settings, *, clock: Clock | None = None) -> SessionStore:
    """The SQS worker requires a shared table and never falls back to process memory."""
    if not settings.session_table_name:
        raise RuntimeError("SESSION_TABLE_NAME is required for memory worker Lambda")
    return DynamoDBSessionStore(
        table_name=settings.session_table_name, region=settings.aws_region, clock=clock,
    )
