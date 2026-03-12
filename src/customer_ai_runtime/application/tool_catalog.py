from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from customer_ai_runtime.core.errors import AppError


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    category: str
    description: str
    required_parameters: list[str]
    optional_parameters: list[str] = field(default_factory=list)
    suggested_context_keys: list[str] = field(default_factory=list)


class ToolCatalogService:
    def __init__(self) -> None:
        self._tools = {
            "order_status": ToolDefinition(
                name="order_status",
                category="ecommerce",
                description="Query order fulfillment and payment status.",
                required_parameters=["order_id"],
                suggested_context_keys=["platform", "shop_id", "customer_id"],
            ),
            "after_sale_status": ToolDefinition(
                name="after_sale_status",
                category="ecommerce",
                description="Query refund, return or after-sale workflow status.",
                required_parameters=["after_sale_id"],
                suggested_context_keys=["platform", "shop_id", "customer_id"],
            ),
            "logistics_tracking": ToolDefinition(
                name="logistics_tracking",
                category="ecommerce",
                description="Query shipment tracking timeline and delivery status.",
                required_parameters=["tracking_no"],
                optional_parameters=["carrier_code"],
                suggested_context_keys=["platform", "shop_id"],
            ),
            "account_lookup": ToolDefinition(
                name="account_lookup",
                category="crm",
                description="Query customer account, membership and points profile.",
                required_parameters=["account_id"],
                suggested_context_keys=["platform", "shop_id", "customer_id"],
            ),
        }

    def get(self, tool_name: str) -> ToolDefinition:
        definition = self._tools.get(tool_name)
        if not definition:
            raise AppError(code="validation_error", message=f"不支持的工具：{tool_name}", status_code=400)
        return definition

    def list_tools(self) -> list[dict[str, Any]]:
        return [
            {
                "name": definition.name,
                "category": definition.category,
                "description": definition.description,
                "required_parameters": definition.required_parameters,
                "optional_parameters": definition.optional_parameters,
                "suggested_context_keys": definition.suggested_context_keys,
            }
            for definition in self._tools.values()
        ]

    def validate_parameters(self, tool_name: str, parameters: dict[str, Any]) -> list[str]:
        definition = self.get(tool_name)
        return [key for key in definition.required_parameters if not parameters.get(key)]

