from __future__ import annotations

import hashlib
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, Request
from starlette.middleware.base import RequestResponseEndpoint
from starlette.responses import Response

from customer_ai_runtime.api.routes import router
from customer_ai_runtime.application.container import Container, build_container
from customer_ai_runtime.core.config import get_settings
from customer_ai_runtime.core.errors import AppError
from customer_ai_runtime.core.logging import configure_logging
from customer_ai_runtime.core.rate_limit import TokenBucketRateLimiter
from customer_ai_runtime.core.request_context import reset_request_id, set_request_id
from customer_ai_runtime.core.responses import error_response


def _hash_subject(value: str) -> str:
    # Avoid using raw credentials in in-memory keys.
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]


def _resolve_client_ip(request: Request, *, trust_x_forwarded_for: bool) -> str:
    if trust_x_forwarded_for:
        forwarded_for = request.headers.get("x-forwarded-for")
        if forwarded_for:
            candidate = forwarded_for.split(",", 1)[0].strip()
            if candidate:
                return candidate
    return request.client.host if request.client else "unknown"


def _rate_limit_subject(request: Request, *, cookie_name: str, trust_x_forwarded_for: bool) -> str:
    api_key = request.headers.get("x-api-key")
    if api_key:
        return f"api_key:{_hash_subject(api_key)}"

    authorization = request.headers.get("authorization", "")
    if authorization.startswith("Bearer "):
        token = authorization.split(" ", 1)[1].strip()
        if token:
            return f"bearer:{_hash_subject(token)}"

    host_token = request.headers.get("x-host-token")
    if host_token:
        return f"host_token:{_hash_subject(host_token)}"

    session_cookie = request.cookies.get(cookie_name)
    if session_cookie:
        return f"session:{_hash_subject(session_cookie)}"

    ip = _resolve_client_ip(request, trust_x_forwarded_for=trust_x_forwarded_for)
    return f"ip:{ip}"


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
    async def request_id_middleware(
        request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
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

            subject = _rate_limit_subject(
                request,
                cookie_name=settings.host_session_cookie_name,
                trust_x_forwarded_for=settings.trust_x_forwarded_for,
            )
            key = f"{subject}:{request.method}:{request.url.path}"
            decision = limiter.decide(key)
            if not decision.allowed:
                rate_limited = error_response(
                    status_code=429,
                    code="rate_limited",
                    message="too many requests",
                    details={"retry_after_seconds": decision.retry_after_seconds},
                )
                if decision.retry_after_seconds is not None:
                    rate_limited.headers["Retry-After"] = str(decision.retry_after_seconds)
                rate_limited.headers["X-Request-ID"] = request_id
                return rate_limited
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
