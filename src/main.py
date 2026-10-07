"""Delhi Scheme Saathi - FastAPI Application.

Voice-first Hindi chatbot helping Delhi residents discover
and apply for government welfare schemes.
"""

import logging
import sys
from contextlib import asynccontextmanager

import asyncpg
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from src.config import get_settings
from src.dss.application.ports.document_repository import DocumentRepository
from src.dss.application.ports.office_repository import OfficeRepository
from src.dss.application.ports.rejection_rule_repository import RejectionRuleRepository
from src.dss.application.ports.scheme_repository import SchemeRepository
from src.dss.infrastructure.database.adapters import (
    PostgresDocumentRepository,
    PostgresOfficeRepository,
    PostgresRejectionRuleRepository,
    PostgresSchemeRepository,
)
from src.dss.interfaces.api.routes import APIRoutes
from src.dss.settings import CHAT_SESSION_PREFIX as CHAT_SESSION_PREFIX
from src.services import conversation as conversation
from src.utils.logging_config import configure_logging
from src.utils.validators import sanitize_input as sanitize_input
from src.webhook import handler

# Configure logging
settings = get_settings()
configure_logging(settings.log_level)
logger = logging.getLogger(__name__)

# Database connection pool (initialized on startup)
db_pool: asyncpg.Pool | None = None


async def init_db_pool() -> asyncpg.Pool:
    """Initialize the database connection pool."""
    return await asyncpg.create_pool(
        settings.database_url,
        min_size=2,
        max_size=10,
        command_timeout=30,
    )


async def close_db_pool() -> None:
    """Close the database connection pool."""
    global db_pool
    if db_pool:
        await db_pool.close()
        db_pool = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager for startup/shutdown."""
    global db_pool
    logger.info("Starting Delhi Scheme Saathi...")

    # Initialize database pool
    try:
        db_pool = await init_db_pool()
        logger.info("Database connection pool initialized")
    except Exception as e:
        logger.error("Failed to initialize database: %s", e)
        db_pool = None
    else:
        try:
            from src.db.scheme_repo import get_scheme_debug_rows

            scheme_debug_rows = await get_scheme_debug_rows(
                db_pool,
                ["SCH-DELHI-001", "SCH-DELHI-006"],
            )
            for row in scheme_debug_rows:
                log_method = logger.warning if not row["life_events_match"] else logger.info
                log_method(
                    "Verified scheme row %s db_life_events=%s canonical_life_events=%s caste_categories=%s income_segments=%s",
                    row["id"],
                    row["life_events"],
                    row["canonical_life_events"],
                    row["caste_categories"],
                    row["income_segments"],
                )
        except Exception as e:
            logger.warning("Scheme verification logging failed: %s", e)

    # Configure session store based on environment
    _configure_session_store()
    await _configure_ai_background_runtime()

    yield

    # Cleanup
    logger.info("Shutting down...")
    await _shutdown_ai_background_runtime()
    await close_db_pool()


def _configure_session_store() -> None:
    """Configure session store based on environment.

    Uses DynamoDB when SESSION_TABLE_NAME is set (production/Lambda),
    otherwise uses in-memory store (local development).
    """
    from src.db.session_store import (
        DynamoDBSessionStore,
        InMemorySessionStore,
        configure_session_store,
    )

    settings = get_settings()

    # Use DynamoDB when running in production (USE_BEDROCK=true or non-default table name)
    if settings.session_table_name and (
        settings.use_bedrock or settings.session_table_name != "dss-sessions"
    ):
        # DynamoDB configured (production)
        try:
            store = DynamoDBSessionStore(
                table_name=settings.session_table_name,
                region=settings.aws_region,
            )
            configure_session_store(store)
            logger.info("Session store: DynamoDB (%s)", settings.session_table_name)
        except Exception as e:
            logger.warning("DynamoDB init failed, using in-memory: %s", e)
            configure_session_store(InMemorySessionStore())
    else:
        # Local development - use in-memory store
        configure_session_store(InMemorySessionStore())
        logger.info("Session store: In-memory (local development)")


async def _configure_ai_background_runtime() -> None:
    """Configure and start the background AI worker."""
    from src.services.ai_background import (
        InMemoryAIWorkQueue,
        configure_ai_work_queue,
        create_default_ai_work_queue,
        start_ai_background_worker,
    )

    queue = create_default_ai_work_queue()
    configure_ai_work_queue(queue)
    if queue is None:
        logger.info("AI background queue: disabled")
        return

    if isinstance(queue, InMemoryAIWorkQueue):
        await start_ai_background_worker()
        logger.info("AI background queue: %s (in-process worker started)", queue.__class__.__name__)
        return

    logger.info("AI background queue: %s (external worker expected)", queue.__class__.__name__)


async def _shutdown_ai_background_runtime() -> None:
    """Stop the background AI worker and release queue resources."""
    from src.services.ai_background import stop_ai_background_worker

    await stop_ai_background_worker()


# Create FastAPI app
app = FastAPI(
    title="Delhi Scheme Saathi",
    description="Voice-first Hindi chatbot for Delhi welfare schemes",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS middleware — restrict to known origins in production
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins or ["http://localhost:3000"],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "Authorization"],
)


def get_db_pool() -> asyncpg.Pool:
    """Get the database connection pool.

    Raises HTTPException if pool is not initialized.
    """
    if not db_pool:
        raise HTTPException(status_code=503, detail="Database connection not available")
    return db_pool


# =============================================================================
# REST API Endpoints
# =============================================================================


# =============================================================================
# Telegram Webhook
# =============================================================================


# =============================================================================
# Chat API (for testing without Telegram)
# =============================================================================


# Phase 5 supplies live dependencies here; Phase 6 builds the composition root.


telegram_handler = handler


def scheme_repository(pool: asyncpg.Pool) -> SchemeRepository:
    return PostgresSchemeRepository(pool)


def document_repository(pool: asyncpg.Pool) -> DocumentRepository:
    return PostgresDocumentRepository(pool)


def office_repository(pool: asyncpg.Pool) -> OfficeRepository:
    return PostgresOfficeRepository(pool)


def rejection_rule_repository(pool: asyncpg.Pool) -> RejectionRuleRepository:
    return PostgresRejectionRuleRepository(pool)


_routes = APIRoutes(sys.modules[__name__])
health_check = _routes.health_check
app.add_api_route("/health", health_check, methods=["GET"])
root = _routes.root
app.add_api_route("/", root, methods=["GET"])
get_scheme = _routes.get_scheme
app.add_api_route("/api/scheme/{scheme_id}", get_scheme, methods=["GET"])
list_schemes = _routes.list_schemes
app.add_api_route("/api/schemes", list_schemes, methods=["GET"])
get_document = _routes.get_document
app.add_api_route("/api/document/{document_id}", get_document, methods=["GET"])
get_nearest_offices = _routes.get_nearest_offices
app.add_api_route("/api/csc/nearest", get_nearest_offices, methods=["GET"])
list_life_events = _routes.list_life_events
app.add_api_route("/api/life-events", list_life_events, methods=["GET"])
telegram_webhook = _routes.telegram_webhook
app.add_api_route("/webhook/telegram", telegram_webhook, methods=["POST"])
chat_endpoint = _routes.chat_endpoint
app.add_api_route("/api/chat", chat_endpoint, methods=["POST"])
