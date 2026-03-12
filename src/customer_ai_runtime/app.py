from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request

from customer_ai_runtime.api.routes import router
from customer_ai_runtime.application.container import Container, build_container
from customer_ai_runtime.core.config import get_settings
from customer_ai_runtime.core.errors import AppError
from customer_ai_runtime.core.logging import configure_logging
from customer_ai_runtime.core.responses import error_response


def create_app(container: Container | None = None, route_prefix: str = "") -> FastAPI:
    settings = container.settings if container else get_settings()
    configure_logging(settings.log_level)
    resolved_container = container or build_container(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        await resolved_container.plugin_registry.startup()
        try:
            yield
        finally:
            await resolved_container.plugin_registry.shutdown()

    app = FastAPI(title="Customer AI Runtime", version="0.1.0", lifespan=lifespan)
    app.state.container = resolved_container
    app.include_router(router, prefix=route_prefix)

    @app.exception_handler(AppError)
    async def app_error_handler(_: Request, exc: AppError):
        return error_response(
            status_code=exc.status_code,
            code=exc.code,
            message=exc.message,
            details=exc.details,
        )

    @app.exception_handler(Exception)
    async def unhandled_error_handler(_: Request, exc: Exception):
        return error_response(
            status_code=500,
            code="internal_error",
            message="internal server error",
            details={"type": type(exc).__name__},
        )

    return app
