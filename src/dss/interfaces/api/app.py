"""Register the shared HTTP surface without constructing an entrypoint."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.dss.interfaces.api.http import HTTPRoutes
from src.dss.settings import Settings


def register_routes(app: FastAPI, routes: HTTPRoutes, settings: Settings) -> None:
    app.add_middleware(
        CORSMiddleware, allow_origins=settings.cors_origins or ["http://localhost:3000"],
        allow_credentials=False, allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "Authorization"],
    )
    app.add_api_route("/health", routes.health_check, methods=["GET"])
    app.add_api_route("/", routes.root, methods=["GET"])
    app.add_api_route("/api/scheme/{scheme_id}", routes.get_scheme, methods=["GET"])
    app.add_api_route("/api/schemes", routes.list_schemes, methods=["GET"])
    app.add_api_route("/api/document/{document_id}", routes.get_document, methods=["GET"])
    app.add_api_route("/api/csc/nearest", routes.get_nearest_offices, methods=["GET"])
    app.add_api_route("/api/life-events", routes.list_life_events, methods=["GET"])
    app.add_api_route("/webhook/telegram", routes.telegram_webhook, methods=["POST"])
    app.add_api_route("/api/chat", routes.chat_endpoint, methods=["POST"])
