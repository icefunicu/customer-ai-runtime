from __future__ import annotations

from fastapi import FastAPI

from customer_ai_runtime.application.auth import AuthBridgePlugin
from customer_ai_runtime.application.plugins import PluginDescriptor
from customer_ai_runtime.domain.platform import (
    AuthMode,
    AuthRequestContext,
    PluginKind,
    ResolvedAuthContext,
)
from customer_ai_runtime.integration import CustomerAIRuntimeModule


class HostHeaderBridge(AuthBridgePlugin):
    def __init__(self) -> None:
        super().__init__(
            PluginDescriptor(
                plugin_id="auth.host_header",
                name="Host Header Bridge",
                kind=PluginKind.AUTH_BRIDGE,
                priority=900,
                capabilities=["host_header"],
            )
        )

    async def can_handle(self, request_data: AuthRequestContext) -> bool:
        return bool(request_data.headers.get("x-host-user"))

    async def authenticate(self, request_data: AuthRequestContext) -> ResolvedAuthContext:
        tenant_id = request_data.headers.get("x-host-tenant", "demo-tenant")
        return ResolvedAuthContext(
            role="customer",
            tenant_ids=[tenant_id],
            auth_mode=AuthMode.CUSTOM_BRIDGE,
        )


host_app = FastAPI(title="Host Business System")
customer_ai_module = CustomerAIRuntimeModule.create()
customer_ai_module.register_plugin(HostHeaderBridge())
customer_ai_module.mount_to(host_app, prefix="/customer-ai")


@host_app.get("/host-healthz")
async def host_healthz() -> dict[str, str]:
    return {"status": "ok"}
