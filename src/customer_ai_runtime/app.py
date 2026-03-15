from __future__ import annotations

from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, Request

from customer_ai_runtime.api.routes import router
from customer_ai_runtime.application.container import Container, build_container
from customer_ai_runtime.core.config import get_settings
from customer_ai_runtime.core.errors import AppError
from customer_ai_runtime.core.logging import configure_logging
from customer_ai_runtime.core.rate_limit import TokenBucketRateLimiter
from customer_ai_runtime.core.request_context import reset_request_id, set_request_id
from customer_ai_runtime.core.responses import error_response


def create_app(container: Container | None = None, route_prefix: str = "") -> FastAPI:
    settings = container.settings if container else get_settings()
    settings.validate_startup()
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

    limiter = TokenBucketRateLimiter(
        enabled=settings.rate_limit_enabled,
        rate_per_minute=settings.rate_limit_per_minute,
        burst=settings.rate_limit_burst,
    )

    @app.middleware("http")
    async def request_id_middleware(request: Request, call_next):  # type: ignore[no-untyped-def]
        request_id = request.headers.get("x-request-id") or f"req_{uuid4().hex[:12]}"
        token = set_request_id(request_id)
        try:
            content_length = request.headers.get("content-length")
            if content_length:
                try:
                    size = int(content_length)
                except ValueError:
                    size = -1
                if size > settings.max_request_bytes:
                    return error_response(
                        status_code=413,
                        code="payload_too_large",
                        message="request payload too large",
                        details={"max_bytes": settings.max_request_bytes},
                    )

            ip = request.client.host if request.client else "unknown"
            key = f"{ip}:{request.method}:{request.url.path}"
            decision = limiter.decide(key)
            if not decision.allowed:
                response = error_response(
                    status_code=429,
                    code="rate_limited",
                    message="too many requests",
                    details={"retry_after_seconds": decision.retry_after_seconds},
                )
                if decision.retry_after_seconds is not None:
                    response.headers["Retry-After"] = str(decision.retry_after_seconds)
                response.headers["X-Request-ID"] = request_id
                return response
            response = await call_next(request)
        finally:
            reset_request_id(token)
        response.headers["X-Request-ID"] = request_id
        return response

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
