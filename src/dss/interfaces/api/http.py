"""HTTP routes over typed, entrypoint-supplied dependencies."""

import logging
import secrets
from typing import Any, TypeVar

from fastapi import HTTPException, Query, Request

from src.dss.application.conversation.contracts import ChatRequest
from src.dss.application.conversation.validators import sanitize_input
from src.dss.interfaces.api.dependencies import APIDependencies
from src.dss.settings import CHAT_SESSION_PREFIX

logger = logging.getLogger(__name__)
T = TypeVar("T")


def require_repository(repository: T | None) -> T:
    if repository is None:
        raise HTTPException(status_code=503, detail="Database connection not available")
    return repository


class HTTPRoutes:
    def __init__(self, dependencies: APIDependencies) -> None:
        self.dependencies = dependencies

    async def health_check(self) -> dict[str, Any]:
        result: dict[str, Any] = {"status": "ok", "database": "disconnected", "schemes_count": 0}
        if self.dependencies.schemes is not None:
            try:
                count = await self.dependencies.schemes.count_active_schemes()
                result["database"] = "connected"
                result["schemes_count"] = count
            except Exception as exc:
                logger.error("Database health check failed: %s", exc)
                result["database"] = "error"
                result["status"] = "degraded"
        return result

    async def root(self) -> dict[str, str]:
        return {"name": "Delhi Scheme Saathi API", "version": "0.1.0", "docs": "/docs"}

    async def get_scheme(self, scheme_id: str) -> dict[str, Any]:
        schemes = require_repository(self.dependencies.schemes)
        documents = require_repository(self.dependencies.documents)
        rules = require_repository(self.dependencies.rules)
        scheme = await schemes.get_scheme_by_id(scheme_id)
        if not scheme:
            raise HTTPException(status_code=404, detail=f"Scheme {scheme_id} not found")
        related = await documents.get_documents_for_scheme(scheme_id)
        warnings = await rules.get_rules_by_scheme(scheme_id)
        return {"scheme": scheme.model_dump(), "documents": [d.model_dump() for d in related],
                "rejection_rules": [r.model_dump() for r in warnings]}

    async def list_schemes(
        self, life_event: str | None = None, limit: int = Query(default=10, ge=1, le=100),
    ) -> dict[str, Any]:
        repository = require_repository(self.dependencies.schemes)
        if life_event:
            schemes = await repository.get_schemes_by_life_event(life_event, limit)
        else:
            schemes = await repository.get_all_schemes()
            schemes = schemes[:limit]
        return {"schemes": [s.model_dump() for s in schemes], "total": len(schemes), "life_event": life_event}

    async def get_document(self, document_id: str) -> dict[str, Any]:
        documents = require_repository(self.dependencies.documents)
        offices = require_repository(self.dependencies.offices)
        document = await documents.get_document_by_id(document_id)
        if not document:
            raise HTTPException(status_code=404, detail=f"Document {document_id} not found")
        prerequisites = []
        if document.prerequisites:
            prerequisites = await documents.get_documents_by_ids(document.prerequisites)
        locations = await offices.get_offices_by_service(document_id)
        return {"document": document.model_dump(), "prerequisites": [d.model_dump() for d in prerequisites],
                "offices": [o.model_dump() for o in locations]}

    async def get_nearest_offices(
        self, lat: float | None = Query(default=None, ge=-90, le=90),
        lng: float | None = Query(default=None, ge=-180, le=180),
        district: str | None = None, office_type: str | None = None,
        limit: int = Query(default=5, ge=1, le=50),
    ) -> dict[str, Any]:
        repository = require_repository(self.dependencies.offices)
        if lat is not None and lng is not None:
            offices = await repository.get_nearest_offices(lat, lng, limit, office_type)
            query_type = "location"
        elif district:
            offices = await repository.get_offices_by_district(district, limit)
            query_type = "district"
        else:
            raise HTTPException(status_code=400, detail="Provide either lat+lng or district parameter")
        return {"offices": [o.model_dump() for o in offices], "total": len(offices),
                "query_type": query_type, "query_district": district,
                "query_location": (lat, lng) if lat and lng else None}

    async def list_life_events(self) -> dict[str, Any]:
        return {"life_events": await require_repository(self.dependencies.schemes).list_life_events()}

    async def telegram_webhook(self, request: Request) -> dict[str, str]:
        webhook_secret = self.dependencies.settings.telegram_webhook_secret
        if webhook_secret:
            token_header = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
            if token_header != webhook_secret:
                raise HTTPException(status_code=403, detail="Forbidden")
        update = await request.json()
        if not isinstance(update, dict):
            raise HTTPException(status_code=400, detail="Invalid payload")
        require_repository(self.dependencies.schemes)
        return await self.dependencies.telegram(update)

    async def chat_endpoint(self, payload: dict[str, Any], request: Request) -> dict[str, Any]:
        chat_api_key = self.dependencies.settings.chat_api_key
        if chat_api_key and not secrets.compare_digest(request.headers.get("X-API-Key", ""), chat_api_key):
            raise HTTPException(status_code=403, detail="Forbidden")
        require_repository(self.dependencies.schemes)
        user_id = str(payload.get("user_id", "test_user"))[:64]
        message = sanitize_input(payload.get("message", ""))
        if not message:
            raise HTTPException(status_code=400, detail="Message is required")
        response = await self.dependencies.chat(ChatRequest(
            user_id=f"{CHAT_SESSION_PREFIX}{user_id}", message=message,
        ))
        return {
            "response": response.text, "next_state": response.next_state,
            "schemes": [s.model_dump() if hasattr(s, "model_dump") else s for s in (response.schemes or [])],
            "documents": [d.model_dump() if hasattr(d, "model_dump") else d for d in (response.documents or [])],
            "rejection_warnings": [r.model_dump() if hasattr(r, "model_dump") else r for r in (response.rejection_warnings or [])],
        }
