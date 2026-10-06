"""HTTP handlers; legacy startup wiring is supplied by the entrypoint."""

import logging
import secrets
from typing import Any, cast

from fastapi import HTTPException, Query, Request

from src.dss.application.conversation.contracts import ChatRequest

logger = logging.getLogger(__name__)


class APIRoutes:
    def __init__(self, runtime: Any) -> None:
        self.runtime = runtime

    async def health_check(self) -> dict[str, Any]:
        """Health check endpoint returning database status and scheme count."""
        result: dict[str, Any] = {
            "status": "ok",
            "database": "disconnected",
            "schemes_count": 0,
        }

        if self.runtime.db_pool:
            try:
                async with self.runtime.db_pool.acquire() as conn:
                    # Check database connectivity and get scheme count
                    count = await conn.fetchval(
                        "SELECT COUNT(*) FROM schemes WHERE is_active = true"
                    )
                    result["database"] = "connected"
                    result["schemes_count"] = count or 0
            except Exception as e:
                logger.error("Database health check failed: %s", e)
                result["database"] = "error"
                result["status"] = "degraded"

        return result

    async def root(self) -> dict[str, str]:
        """Root endpoint with API info."""
        return {
            "name": "Delhi Scheme Saathi API",
            "version": "0.1.0",
            "docs": "/docs",
        }

    async def get_scheme(self, scheme_id: str) -> dict[str, Any]:
        """Get full scheme details by ID."""
        document_repo = self.runtime.repositories.document_repo
        rejection_rule_repo = self.runtime.repositories.rejection_rule_repo
        scheme_repo = self.runtime.repositories.scheme_repo

        pool = self.runtime.get_db_pool()
        scheme = await scheme_repo.get_scheme_by_id(pool, scheme_id)

        if not scheme:
            raise HTTPException(status_code=404, detail=f"Scheme {scheme_id} not found")

        # Get related documents and rejection rules
        documents = await document_repo.get_documents_for_scheme(pool, scheme_id)
        rejection_rules = await rejection_rule_repo.get_rules_by_scheme(pool, scheme_id)

        return {
            "scheme": scheme.model_dump(),
            "documents": [d.model_dump() for d in documents],
            "rejection_rules": [r.model_dump() for r in rejection_rules],
        }

    async def list_schemes(
        self,
        life_event: str | None = None,
        limit: int = Query(default=10, ge=1, le=100),
    ) -> dict[str, Any]:
        """List schemes, optionally filtered by life event."""
        scheme_repo = self.runtime.repositories.scheme_repo

        pool = self.runtime.get_db_pool()

        if life_event:
            schemes = await scheme_repo.get_schemes_by_life_event(pool, life_event, limit)
        else:
            schemes = await scheme_repo.get_all_schemes(pool)
            schemes = schemes[:limit]

        return {
            "schemes": [s.model_dump() for s in schemes],
            "total": len(schemes),
            "life_event": life_event,
        }

    async def get_document(self, document_id: str) -> dict[str, Any]:
        """Get document details with procurement guidance."""
        document_repo = self.runtime.repositories.document_repo
        office_repo = self.runtime.repositories.office_repo

        pool = self.runtime.get_db_pool()
        document = await document_repo.get_document_by_id(pool, document_id)

        if not document:
            raise HTTPException(status_code=404, detail=f"Document {document_id} not found")

        # Get prerequisite documents
        prereq_docs = []
        if document.prerequisites:
            prereq_docs = await document_repo.get_documents_by_ids(pool, document.prerequisites)

        # Get offices that issue this document
        offices = await office_repo.get_offices_by_service(pool, document_id)

        return {
            "document": document.model_dump(),
            "prerequisites": [d.model_dump() for d in prereq_docs],
            "offices": [o.model_dump() for o in offices],
        }

    async def get_nearest_offices(
        self,
        lat: float | None = Query(default=None, ge=-90, le=90),
        lng: float | None = Query(default=None, ge=-180, le=180),
        district: str | None = None,
        office_type: str | None = None,
        limit: int = Query(default=5, ge=1, le=50),
    ) -> dict[str, Any]:
        """Get nearest CSC/government offices."""
        office_repo = self.runtime.repositories.office_repo

        pool = self.runtime.get_db_pool()

        if lat is not None and lng is not None:
            offices = await office_repo.get_nearest_offices(pool, lat, lng, limit, office_type)
            query_type = "location"
        elif district:
            offices = await office_repo.get_offices_by_district(pool, district, limit)
            query_type = "district"
        else:
            raise HTTPException(
                status_code=400, detail="Provide either lat+lng or district parameter"
            )

        return {
            "offices": [o.model_dump() for o in offices],
            "total": len(offices),
            "query_type": query_type,
            "query_district": district,
            "query_location": (lat, lng) if lat and lng else None,
        }

    async def list_life_events(self) -> dict[str, Any]:
        """List all life event categories."""
        pool = self.runtime.get_db_pool()

        async with pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT key, display_name, display_name_hindi, aliases FROM life_events_taxonomy ORDER BY key"
            )

        return {
            "life_events": [
                {
                    "key": row["key"],
                    "display_name": row["display_name"],
                    "display_name_hindi": row["display_name_hindi"],
                    "aliases": list(row["aliases"] or []),
                }
                for row in rows
            ]
        }

    async def telegram_webhook(self, request: Request) -> dict[str, str]:
        """Handle incoming Telegram updates with secret token verification."""
        handle_telegram_update = self.runtime.telegram_handler.handle_telegram_update

        # Verify Telegram webhook secret token
        webhook_secret = self.runtime.get_settings().telegram_webhook_secret
        if webhook_secret:
            token_header = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
            if token_header != webhook_secret:
                raise HTTPException(status_code=403, detail="Forbidden")

        update = await request.json()
        if not isinstance(update, dict):
            raise HTTPException(status_code=400, detail="Invalid payload")

        pool = self.runtime.get_db_pool()
        return cast(dict[str, str], await handle_telegram_update(update, pool))

    async def chat_endpoint(self, payload: dict[str, Any], request: Request) -> dict[str, Any]:
        """Direct chat endpoint for testing without Telegram.

        Request: {"user_id": "test123", "message": "Namaste"}
        Response: {"response": "...", "next_state": "...", "schemes": [...]}

        ``user_id`` is caller-supplied and unauthenticated, so it is namespaced
        under ``CHAT_SESSION_PREFIX`` before it reaches the session store. Without
        that, passing a Telegram user's numeric ID here would open their live
        session and expose the profile extracted from it. Setting ``CHAT_API_KEY``
        additionally closes the endpoint to unknown callers.
        """
        conversation_service = self.runtime.conversation.ConversationService
        sanitize_input = self.runtime.sanitize_input

        chat_api_key = self.runtime.get_settings().chat_api_key
        if chat_api_key and not secrets.compare_digest(
            request.headers.get("X-API-Key", ""), chat_api_key
        ):
            raise HTTPException(status_code=403, detail="Forbidden")

        pool = self.runtime.get_db_pool()
        user_id = str(payload.get("user_id", "test_user"))[:64]
        message = sanitize_input(payload.get("message", ""))

        if not message:
            raise HTTPException(status_code=400, detail="Message is required")

        chat_request = ChatRequest(
            user_id=f"{self.runtime.CHAT_SESSION_PREFIX}{user_id}",
            message=message,
        )

        service = conversation_service(pool)
        response = await service.handle_message(chat_request)

        return {
            "response": response.text,
            "next_state": response.next_state,
            "schemes": [
                s.model_dump() if hasattr(s, "model_dump") else s for s in (response.schemes or [])
            ],
            "documents": [
                d.model_dump() if hasattr(d, "model_dump") else d
                for d in (response.documents or [])
            ],
            "rejection_warnings": [
                r.model_dump() if hasattr(r, "model_dump") else r
                for r in (response.rejection_warnings or [])
            ],
        }
