from __future__ import annotations

import base64
import hashlib
import hmac
import json
from abc import abstractmethod
from datetime import UTC, datetime
from typing import Any

from fastapi import Request, WebSocket

from customer_ai_runtime.application.plugins import Plugin, PluginRegistry
from customer_ai_runtime.core.config import Settings
from customer_ai_runtime.core.errors import AppError
from customer_ai_runtime.domain.platform import (
    AuthMode,
    AuthRequestContext,
    HostAuthContext,
    PluginDescriptor,
    PluginKind,
    ResolvedAuthContext,
)


class AuthBridgePlugin(Plugin):
    @abstractmethod
    async def can_handle(self, request_data: AuthRequestContext) -> bool: ...

    @abstractmethod
    async def authenticate(self, request_data: AuthRequestContext) -> ResolvedAuthContext: ...


class ApiKeyAuthBridgePlugin(AuthBridgePlugin):
    def __init__(self, settings: Settings) -> None:
        super().__init__(
            PluginDescriptor(
                plugin_id="auth.api_key",
                name="API Key Auth Bridge",
                kind=PluginKind.AUTH_BRIDGE,
                priority=1000,
                capabilities=["api_key"],
            )
        )
        self._settings = settings

    async def can_handle(self, request_data: AuthRequestContext) -> bool:
        return bool(request_data.headers.get("x-api-key"))

    async def authenticate(self, request_data: AuthRequestContext) -> ResolvedAuthContext:
        api_key = request_data.headers.get("x-api-key")
        if not api_key:
            raise AppError(code="auth_error", message="missing api key", status_code=401)
        record = self._settings.get_api_keys().get(api_key)
        if not record:
            raise AppError(code="auth_error", message="invalid api key", status_code=401)
        return ResolvedAuthContext(
            role=record.role,
            tenant_ids=record.tenant_ids,
            auth_mode=AuthMode.API_KEY,
        )


class SessionAuthBridgePlugin(AuthBridgePlugin):
    def __init__(self, settings: Settings) -> None:
        super().__init__(
            PluginDescriptor(
                plugin_id="auth.session",
                name="Session Auth Bridge",
                kind=PluginKind.AUTH_BRIDGE,
                priority=700,
                capabilities=["session", "cookie"],
            )
        )
        self._settings = settings

    async def can_handle(self, request_data: AuthRequestContext) -> bool:
        cookie_name = self._settings.host_session_cookie_name
        return bool(self._settings.get_host_session_map()) and bool(request_data.cookies.get(cookie_name))

    async def authenticate(self, request_data: AuthRequestContext) -> ResolvedAuthContext:
        cookie_name = self._settings.host_session_cookie_name
        session_id = request_data.cookies.get(cookie_name)
        payload = self._settings.get_host_session_map().get(session_id or "")
        if not payload:
            raise AppError(code="host_auth_error", message="invalid host session", status_code=401)
        return _resolved_auth_from_payload(payload, AuthMode.SESSION)


class JWTAuthBridgePlugin(AuthBridgePlugin):
    def __init__(self, settings: Settings) -> None:
        super().__init__(
            PluginDescriptor(
                plugin_id="auth.jwt",
                name="JWT Auth Bridge",
                kind=PluginKind.AUTH_BRIDGE,
                priority=650,
                capabilities=["jwt", "bearer"],
            )
        )
        self._settings = settings

    async def can_handle(self, request_data: AuthRequestContext) -> bool:
        return bool(self._settings.host_jwt_secret) and request_data.headers.get("authorization", "").startswith(
            "Bearer "
        )

    async def authenticate(self, request_data: AuthRequestContext) -> ResolvedAuthContext:
        token = request_data.headers["authorization"].split(" ", 1)[1]
        payload = _decode_hs256_jwt(
            token=token,
            secret=self._settings.host_jwt_secret or "",
            issuer=self._settings.host_jwt_issuer,
            audience=self._settings.host_jwt_audience,
        )
        return _resolved_auth_from_payload(payload, AuthMode.JWT)


class CustomTokenAuthBridgePlugin(AuthBridgePlugin):
    def __init__(self, settings: Settings) -> None:
        super().__init__(
            PluginDescriptor(
                plugin_id="auth.custom_token",
                name="Custom Token Auth Bridge",
                kind=PluginKind.AUTH_BRIDGE,
                priority=600,
                capabilities=["custom_token"],
            )
        )
        self._settings = settings

    async def can_handle(self, request_data: AuthRequestContext) -> bool:
        return bool(self._settings.get_host_token_map()) and bool(request_data.headers.get("x-host-token"))

    async def authenticate(self, request_data: AuthRequestContext) -> ResolvedAuthContext:
        token = request_data.headers.get("x-host-token")
        payload = self._settings.get_host_token_map().get(token or "")
        if not payload:
            raise AppError(code="host_auth_error", message="invalid host token", status_code=401)
        return _resolved_auth_from_payload(payload, AuthMode.CUSTOM_TOKEN)


class AuthService:
    def __init__(self, registry: PluginRegistry) -> None:
        self._registry = registry

    async def authenticate_request(self, request: Request) -> ResolvedAuthContext:
        request_data = AuthRequestContext(
            method=request.method,
            path=request.url.path,
            headers={key.lower(): value for key, value in request.headers.items()},
            cookies=dict(request.cookies),
            query_params={key: value for key, value in request.query_params.items()},
        )
        return await self.authenticate(request_data)

    async def authenticate_websocket(self, websocket: WebSocket) -> ResolvedAuthContext:
        request_data = AuthRequestContext(
            method="WS",
            path=websocket.url.path,
            headers={key.lower(): value for key, value in websocket.headers.items()},
            cookies=dict(websocket.cookies),
            query_params={key: value for key, value in websocket.query_params.items()},
        )
        return await self.authenticate(request_data)

    async def authenticate(self, request_data: AuthRequestContext) -> ResolvedAuthContext:
        handled = False
        for plugin in self._registry.resolve(PluginKind.AUTH_BRIDGE):
            auth_plugin = plugin
            if not isinstance(auth_plugin, AuthBridgePlugin):
                continue
            if not await auth_plugin.can_handle(request_data):
                continue
            handled = True
            return await auth_plugin.authenticate(request_data)
        if handled:
            raise AppError(code="host_auth_error", message="authentication failed", status_code=401)
        raise AppError(code="auth_error", message="missing authentication credentials", status_code=401)


def build_builtin_auth_plugins(settings: Settings) -> list[AuthBridgePlugin]:
    return [
        ApiKeyAuthBridgePlugin(settings),
        SessionAuthBridgePlugin(settings),
        JWTAuthBridgePlugin(settings),
        CustomTokenAuthBridgePlugin(settings),
    ]


def _resolved_auth_from_payload(payload: dict[str, Any], auth_mode: AuthMode) -> ResolvedAuthContext:
    tenant_id = str(payload["tenant_id"])
    host_auth_context = HostAuthContext(
        tenant_id=tenant_id,
        principal_id=str(payload.get("principal_id") or payload.get("sub") or payload.get("user_id")),
        principal_type=str(payload.get("principal_type", "user")),
        roles=[str(item) for item in payload.get("roles", [])],
        permissions=[str(item) for item in payload.get("permissions", [])],
        source_system=str(payload.get("source_system", "host-system")),
        auth_mode=auth_mode,
        session_claims=dict(payload.get("session_claims", {})),
        business_scope=dict(payload.get("business_scope", {})),
        extra_context=dict(payload.get("extra_context", {})),
    )
    return ResolvedAuthContext(
        role=str(payload.get("platform_role", "customer")),
        tenant_ids=[tenant_id],
        auth_mode=auth_mode,
        host_auth_context=host_auth_context,
    )


def _decode_hs256_jwt(
    *,
    token: str,
    secret: str,
    issuer: str | None,
    audience: str | None,
) -> dict[str, Any]:
    try:
        encoded_header, encoded_payload, encoded_signature = token.split(".")
    except ValueError as exc:
        raise AppError(code="host_auth_error", message="invalid jwt format", status_code=401) from exc
    signing_input = f"{encoded_header}.{encoded_payload}".encode("utf-8")
    expected_signature = _base64url_encode(hmac.new(secret.encode("utf-8"), signing_input, hashlib.sha256).digest())
    if not hmac.compare_digest(expected_signature, encoded_signature):
        raise AppError(code="host_auth_error", message="invalid jwt signature", status_code=401)
    payload = json.loads(_base64url_decode(encoded_payload))
    if issuer and payload.get("iss") != issuer:
        raise AppError(code="host_auth_error", message="invalid jwt issuer", status_code=401)
    if audience and payload.get("aud") != audience:
        raise AppError(code="host_auth_error", message="invalid jwt audience", status_code=401)
    exp = payload.get("exp")
    if exp is not None and datetime.now(UTC).timestamp() >= float(exp):
        raise AppError(code="host_auth_error", message="jwt expired", status_code=401)
    return payload


def _base64url_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("utf-8")


def _base64url_decode(value: str) -> str:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(f"{value}{padding}".encode("utf-8")).decode("utf-8")
