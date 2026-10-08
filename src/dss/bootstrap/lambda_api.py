"""Lambda API with per-invocation async resources and no container lifespan."""

import asyncio
from typing import Any

from fastapi import FastAPI
from mangum import Mangum
from starlette.types import Receive, Scope, Send

from src.dss.bootstrap.api import register_routes
from src.dss.bootstrap.logging import configure_logging
from src.dss.bootstrap.runtime import api_runtime
from src.dss.interfaces.api.http import HTTPRoutes
from src.dss.settings import Settings, get_settings


class InvocationAPI:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        async with api_runtime(self.settings) as runtime:
            app = FastAPI(
                title="Delhi Scheme Saathi", description="Voice-first Hindi chatbot for Delhi welfare schemes",
                version="0.1.0",
            )
            register_routes(app, HTTPRoutes(runtime.dependencies), self.settings)
            await app(scope, receive, send)


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    settings = get_settings()
    configure_logging(settings.log_level)
    with asyncio.Runner() as runner:
        asyncio.set_event_loop(runner.get_loop())
        return Mangum(InvocationAPI(settings), lifespan="off")(event, context)
