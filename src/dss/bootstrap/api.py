"""Container API entrypoint with explicit long-running resource ownership."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from src.dss.bootstrap.logging import configure_logging
from src.dss.bootstrap.runtime import api_runtime
from src.dss.interfaces.api.app import register_routes
from src.dss.interfaces.api.dependencies import APIDependencies
from src.dss.interfaces.api.http import HTTPRoutes
from src.dss.settings import Settings, get_settings


def create_app(settings: Settings) -> FastAPI:
    dependencies: APIDependencies | None = None

    def current_dependencies() -> APIDependencies:
        if dependencies is None:
            raise RuntimeError("API lifespan has not started")
        return dependencies

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        nonlocal dependencies
        configure_logging(settings.log_level, settings=settings)
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
