"""Container API entrypoint with explicit long-running resource ownership."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.dss.bootstrap.logging import configure_logging
from src.dss.bootstrap.runtime import api_runtime
from src.dss.interfaces.api.dependencies import APIDependencies
from src.dss.interfaces.api.http import HTTPRoutes
from src.dss.settings import Settings, get_settings


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


def create_app(settings: Settings) -> FastAPI:
    dependencies: APIDependencies | None = None

    def current_dependencies() -> APIDependencies:
        if dependencies is None:
            raise RuntimeError("API lifespan has not started")
        return dependencies

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        nonlocal dependencies
        configure_logging(settings.log_level)
        async with api_runtime(settings) as runtime:
            dependencies = runtime.dependencies
            try:
                await runtime.start_local_worker()
                yield
            finally:
                dependencies = None

    app = FastAPI(
        title="Delhi Scheme Saathi", description="Voice-first Hindi chatbot for Delhi welfare schemes",
        version="0.1.0", lifespan=lifespan,
    )
    register_routes(app, HTTPRoutes(current_dependencies), settings)
    return app


app = create_app(get_settings())
