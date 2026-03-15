from __future__ import annotations

from fastapi import FastAPI

from customer_ai_runtime.application.plugins import (
    BusinessToolPlugin,
    PluginDescriptor,
)
from customer_ai_runtime.domain.models import BusinessResult
from customer_ai_runtime.domain.platform import PluginContext, PluginKind
from customer_ai_runtime.integration import CustomerAIRuntimeModule


class TenantOrderStatusToolPlugin(BusinessToolPlugin):
    def __init__(self) -> None:
        super().__init__(
            PluginDescriptor(
                plugin_id="tool.tenant_order_status",
                name="Tenant Order Status Tool",
                kind=PluginKind.BUSINESS_TOOL,
                priority=950,
                tenant_scopes=["demo-tenant"],
                industry_scopes=["ecommerce"],
                capabilities=["order_status"],
            )
        )
        self.tool_name = "order_status"
        self.category = "ecommerce"
        self.description = "Example tenant-specific order status plugin."
        self.required_parameters = ["order_id"]
        self.optional_parameters = ["shop_id"]
        self.suggested_context_keys = ["order_id", "shop_id", "customer_id"]

    def resolve_parameters(
        self,
        context: PluginContext,
        parameters: dict[str, object],
    ) -> dict[str, object]:
        resolved = dict(parameters)
        business_objects = context.integration_context.get("business_objects") or {}
        if not resolved.get("order_id"):
            order_id = business_objects.get("order_id") or context.integration_context.get(
                "order_id"
            )
            if order_id:
                resolved["order_id"] = order_id
        return resolved

    async def execute(
        self,
        context: PluginContext,
        parameters: dict[str, object],
    ) -> BusinessResult:
        resolved = self.resolve_parameters(context, parameters)
        order_id = str(resolved.get("order_id") or "")
        if not order_id:
            return BusinessResult(
                tool_name=self.tool_name,
                status="missing_parameter",
                summary="Please provide order_id before invoking the tenant order tool.",
                integration_context=context.integration_context,
            )

        return BusinessResult(
            tool_name=self.tool_name,
            status="success",
            summary=f"Tenant plugin resolved order {order_id} as packed and ready to ship.",
            data={
                "order_id": order_id,
                "status": "packed",
                "warehouse": "WH-SH-01",
                "source": "tenant-plugin-example",
            },
            integration_context=context.integration_context,
        )


host_app = FastAPI(title="Host Business System")
customer_ai_module = CustomerAIRuntimeModule.create()
customer_ai_module.register_plugin(TenantOrderStatusToolPlugin())
customer_ai_module.mount_to(host_app, prefix="/customer-ai")


@host_app.get("/host-healthz")
async def host_healthz() -> dict[str, str]:
    return {"status": "ok"}
