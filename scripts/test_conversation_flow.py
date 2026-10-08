#!/usr/bin/env python3
"""Interactive CLI test for conversation flow.

Simulates Telegram interaction via command line.
Usage: python -m scripts.test_conversation_flow
"""

import asyncio
import os
import sys
from contextlib import AsyncExitStack
from functools import partial

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv


async def main():
    """Run interactive conversation test."""
    load_dotenv()

    print("=" * 60)
    print("Delhi Scheme Saathi - Conversation Test CLI")
    print("=" * 60)
    print("Type your messages to simulate Telegram chat.")
    print("Commands: /reset - restart, /profile - show profile, /quit - exit")
    print("-" * 60)

    # Check for required environment variables
    if not os.getenv("XAI_API_KEY"):
        print("⚠️  XAI_API_KEY not set - LLM features will use fallbacks")
    if not os.getenv("DATABASE_URL"):
        print("⚠️  DATABASE_URL not set - using default localhost")

    # Import after env is loaded
    from src.dss.application.conversation import sessions
    from src.dss.application.conversation.background_memory import MemoryJobs
    from src.dss.application.conversation.contracts import ChatRequest
    from src.dss.application.conversation.profile_fields import ProfileFields
    from src.dss.application.conversation.views import SchemeViews
    from src.dss.application.guidance.documents import resolve_documents_for_scheme
    from src.dss.application.guidance.service import Guidance
    from src.dss.application.matching.scheme_matcher import SchemeMatcher
    from src.dss.bootstrap.conversation import build_conversation
    from src.dss.bootstrap.runtime import build_ai, open_pool
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
    from src.dss.infrastructure.embeddings.fallback_client import (
        EMBEDDING_DIM,
        FallbackEmbeddingClient,
    )
    from src.dss.infrastructure.sessions.clock import SystemClock
    from src.dss.infrastructure.sessions.session_store import InMemorySessionStore
    from src.dss.settings import Settings

    settings = Settings()

    # Initialize database
    try:
        pool = await open_pool(settings)
    except Exception as e:
        print(f"❌ Database connection failed: {e}")
        print("   Make sure PostgreSQL is running with the scheme data")
        return

    cleanup = AsyncExitStack()
    cleanup.push_async_callback(pool.close)
    try:
        print("✅ Database connected")
        clock = SystemClock()
        store = InMemorySessionStore(clock=clock)
        llm = FallbackLLMClient(settings)
        cleanup.push_async_callback(llm.close)
        embeddings = FallbackEmbeddingClient(settings)
        cleanup.push_async_callback(embeddings.close)
        ai = build_ai(settings, llm)
        # ponytail: the interactive CLI has no background queue or worker.
        memory = MemoryJobs(store, ai, clock, queue=None)
        responses = Guidance(
            ai, get_prompt=get_generate_response_prompt, safe_generation=llm._safe_generation_text,
        )
        schemes = PostgresSchemeRepository(pool)
        documents = PostgresDocumentRepository(pool)
        views = SchemeViews(
            schemes, PostgresOfficeRepository(pool), PostgresRejectionRuleRepository(pool),
            responses, partial(resolve_documents_for_scheme, documents),
        )
        matcher = SchemeMatcher(
            schemes, embeddings, get_canonical_life_events, embedding_dimension=EMBEDDING_DIM,
        )
        conversation = build_conversation(
            settings=settings, store=store, clock=clock, ai=ai, responses=responses,
            fields=ProfileFields(lambda: _load_catalog().values()), views=views,
            match_schemes=matcher.match_schemes, get_analysis_prompt=get_analysis_system_prompt,
            enqueue=memory.enqueue,
        )
        user_id = "cli-test-user"
        print("\n🤖 Bot: Ready! Type 'Namaste' to start.\n")

        while True:
            try:
                user_input = input("👤 You: ").strip()
            except EOFError:
                break

            if not user_input:
                continue

            # Handle commands
            if user_input.lower() == "/quit":
                print("Goodbye!")
                break

            if user_input.lower() == "/reset":
                await sessions.delete_session(user_id, store=store)
                print("🔄 Session reset. Type 'Namaste' to start fresh.\n")
                continue

            if user_input.lower() == "/profile":
                session = await sessions.get_or_create_session(user_id, store=store, clock=clock)
                profile = session.user_profile
                print("📋 Current Profile:")
                print(f"   State: {session.state.value}")
                for label, field in (
                    ("Life Event", "life_event"),
                    ("Age", "age"),
                    ("Gender", "gender"),
                    ("Category", "category"),
                    ("Income", "annual_income"),
                ):
                    status = "provided" if getattr(profile, field) is not None else "missing"
                    print(f"   {label}: {status}")
                print(f"   Completeness: {profile.completeness_score}/10")
                print()
                continue

            # Process message
            request = ChatRequest(
                user_id=user_id,
                message=user_input,
                message_type="text",
            )

            try:
                response = await conversation.handle_message(request)
                print(f"\n🤖 Bot: {response.text}")

                if response.schemes:
                    print("\n📋 Matched Schemes:")
                    for match in response.schemes:
                        scheme = match.scheme
                        print(f"   • {scheme.name_hindi}")

                if response.inline_keyboard:
                    print("\n   [Keyboard buttons would appear here]")

                print()

            except Exception as e:
                print(f"\n❌ Error: {e}\n")

    finally:
        await cleanup.aclose()
        print("\n👋 Session ended.")


if __name__ == "__main__":
    asyncio.run(main())
