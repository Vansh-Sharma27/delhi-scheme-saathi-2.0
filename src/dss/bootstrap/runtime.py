"""Owned API and memory-worker resources for explicit entrypoint lifetimes."""

import logging
from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager
from dataclasses import dataclass
from functools import partial

import asyncpg

from src.dss.application.conversation.ai_orchestrator import AIOrchestrator
from src.dss.application.conversation.background_memory import MemoryJobs
from src.dss.application.conversation.profile_fields import ProfileFields
from src.dss.application.conversation.views import SchemeViews
from src.dss.application.guidance.documents import resolve_documents_for_scheme
from src.dss.application.guidance.service import Guidance
from src.dss.application.matching.scheme_matcher import SchemeMatcher
from src.dss.application.ports.work_queue import AIWorkQueue
from src.dss.bootstrap.background import LocalMemoryWorker, build_work_queue
from src.dss.bootstrap.conversation import build_conversation
from src.dss.bootstrap.sessions import build_session_store, build_worker_session_store
from src.dss.infrastructure.ai.fallback_client import FallbackLLMClient
from src.dss.infrastructure.ai.prompts.loader import (
    get_analysis_system_prompt,
    get_generate_response_prompt,
)
from src.dss.infrastructure.database.adapters import (
    PostgresDocumentRepository,
    PostgresOfficeRepository,
    PostgresRejectionRuleRepository,
    PostgresSchemeRepository,
)
from src.dss.infrastructure.database.catalog import _load_catalog, get_canonical_life_events
from src.dss.infrastructure.embeddings.fallback_client import EMBEDDING_DIM, FallbackEmbeddingClient
from src.dss.infrastructure.queues.work_queue import InMemoryAIWorkQueue
from src.dss.infrastructure.sessions.clock import SystemClock
from src.dss.infrastructure.sessions.session_store import DynamoDBSessionStore
from src.dss.infrastructure.speech.bhashini import BhashiniClient
from src.dss.infrastructure.speech.sarvam import SarvamClient
from src.dss.infrastructure.telegram import TelegramClient
from src.dss.interfaces.api.dependencies import APIDependencies
from src.dss.interfaces.telegram.dispatch import TelegramHandler
from src.dss.settings import Settings

logger = logging.getLogger(__name__)


def build_ai(settings: Settings, client: FallbackLLMClient) -> AIOrchestrator:
    return AIOrchestrator(
        client, settings=settings,
        safe_analysis=FallbackLLMClient._safe_analysis_payload,
        safe_relevance=FallbackLLMClient._safe_relevance_payload,
        safe_generation=FallbackLLMClient._safe_generation_text,
    )


@dataclass
class APIRuntime:
    dependencies: APIDependencies
    memory: MemoryJobs
    queue: AIWorkQueue | None
    worker: LocalMemoryWorker | None = None

    async def start_local_worker(self) -> None:
        if isinstance(self.queue, InMemoryAIWorkQueue):
            if self.worker is None:
                self.worker = LocalMemoryWorker(self.queue, self.memory.process)
            await self.worker.start()

    async def stop_local_worker(self) -> None:
        if self.worker is not None:
            await self.worker.cancel()


async def open_pool(settings: Settings) -> asyncpg.Pool:
    return await asyncpg.create_pool(settings.database_url, min_size=2, max_size=10, command_timeout=30)


async def verify_scheme_rows(pool: asyncpg.Pool) -> None:
    try:
        rows = await PostgresSchemeRepository(pool).get_scheme_debug_rows(["SCH-DELHI-001", "SCH-DELHI-006"])
        for row in rows:
            log_method = logger.warning if not row["life_events_match"] else logger.info
            log_method(
                "Verified scheme row %s db_life_events=%s canonical_life_events=%s caste_categories=%s income_segments=%s",
                row["id"], row["life_events"], row["canonical_life_events"],
                row["caste_categories"], row["income_segments"],
            )
    except Exception as exc:
        logger.warning("Scheme verification logging failed: %s", exc)


@asynccontextmanager
async def api_runtime(settings: Settings) -> AsyncIterator[APIRuntime]:
    """Open one graph, clean partial construction, and never start a local worker."""
    async with AsyncExitStack() as cleanup:
        pool = None
        try:
            pool = await open_pool(settings)
        except Exception as exc:
            logger.error("Failed to initialize database: %s", exc)
        else:
            cleanup.push_async_callback(pool.close)
            await verify_scheme_rows(pool)
        clock = SystemClock()
        store = build_session_store(settings, clock=clock)
        if isinstance(store, DynamoDBSessionStore):
            cleanup.callback(store.close)
        queue = build_work_queue(settings)
        if queue is not None:
            cleanup.push_async_callback(queue.close)
        llm = FallbackLLMClient(settings)
        cleanup.push_async_callback(llm.close)
        ai = build_ai(settings, llm)
        memory = MemoryJobs(store, ai, clock, queue)
        embeddings = FallbackEmbeddingClient(settings)
        cleanup.push_async_callback(embeddings.close)
        speech = (
            SarvamClient(settings=settings) if settings.sarvam_api_key or not settings.bhashini_api_key
            else BhashiniClient(settings=settings)
        )
        cleanup.push_async_callback(speech.close)
        notifier = TelegramClient(settings)
        cleanup.push_async_callback(notifier.close)
        responses = Guidance(ai, get_prompt=get_generate_response_prompt, safe_generation=llm._safe_generation_text)
        schemes = PostgresSchemeRepository(pool) if pool is not None else None
        documents = PostgresDocumentRepository(pool) if pool is not None else None
        offices = PostgresOfficeRepository(pool) if pool is not None else None
        rules = PostgresRejectionRuleRepository(pool) if pool is not None else None

        if schemes is not None and documents is not None and offices is not None and rules is not None:
            views = SchemeViews(schemes, offices, rules, responses, partial(resolve_documents_for_scheme, documents))
            matcher = SchemeMatcher(schemes, embeddings, get_canonical_life_events, embedding_dimension=EMBEDDING_DIM)
            conversation = build_conversation(
                settings=settings, store=store, clock=clock, ai=ai, responses=responses,
                fields=ProfileFields(lambda: _load_catalog().values()), views=views,
                match_schemes=matcher.match_schemes, get_analysis_prompt=get_analysis_system_prompt,
                enqueue=memory.enqueue,
            ).handle_message
        else:
            from src.dss.application.conversation.contracts import ChatRequest, ChatResponse

            async def unavailable(request: ChatRequest) -> ChatResponse:
                raise RuntimeError("Database connection not available")

            conversation = unavailable
        telegram = TelegramHandler(notifier, speech, store, clock, conversation)
        runtime = APIRuntime(APIDependencies(
            settings, schemes, documents, offices, rules, conversation, telegram.handle,
        ), memory, queue)
        cleanup.push_async_callback(runtime.stop_local_worker)
        yield runtime


@asynccontextmanager
async def worker_runtime(settings: Settings) -> AsyncIterator[MemoryJobs]:
    """Own async AI resources for one SQS invocation without API resources."""
    async with AsyncExitStack() as cleanup:
        clock = SystemClock()
        store = build_worker_session_store(settings, clock=clock)
        if isinstance(store, DynamoDBSessionStore):
            cleanup.callback(store.close)
        llm = FallbackLLMClient(settings)
        cleanup.push_async_callback(llm.close)
        yield MemoryJobs(store, build_ai(settings, llm), clock, None)
