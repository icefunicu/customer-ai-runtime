from __future__ import annotations

import re
from typing import Any

from customer_ai_runtime.application.plugins import (
    PluginRegistry,
    RouteStrategyPlugin,
    context_to_plugin_context,
    route_result_to_decision,
)
from customer_ai_runtime.domain.models import RouteDecision, RouteType
from customer_ai_runtime.domain.platform import BusinessContext, PluginKind


class RoutingService:
    tool_patterns = {
        "order_status": re.compile(r"(ORD-\d+)", re.IGNORECASE),
        "after_sale_status": re.compile(r"(AS-\d+)", re.IGNORECASE),
        "logistics_tracking": re.compile(r"(YT-\d+)", re.IGNORECASE),
        "account_lookup": re.compile(r"(ACC-\d+)", re.IGNORECASE),
        "subscription_lookup": re.compile(r"(SUB-\d+)", re.IGNORECASE),
        "ticket_lookup": re.compile(r"(TK-\d+)", re.IGNORECASE),
        "course_lookup": re.compile(r"(COURSE-\d+)", re.IGNORECASE),
        "progress_lookup": re.compile(r"(STU-\d+)", re.IGNORECASE),
        "waybill_lookup": re.compile(r"(WB-\d+)", re.IGNORECASE),
        "claim_lookup": re.compile(r"(CLM-\d+)", re.IGNORECASE),
        "crm_profile": re.compile(r"(CUS-\d+)", re.IGNORECASE),
    }

    def __init__(self, registry: PluginRegistry) -> None:
        self._registry = registry

    async def decide(self, message: str, business_context: BusinessContext) -> RouteDecision:
        plugin_context = context_to_plugin_context(
            tenant_id=business_context.tenant_id,
            channel=business_context.channel,
            session_id=business_context.session_id,
            user_message=message,
            industry=business_context.industry,
            integration_context=business_context.integration_context,
            host_auth_context=business_context.host_auth_context,
            business_context=business_context,
        )
        for plugin in self._registry.resolve(
            PluginKind.ROUTE_STRATEGY,
            tenant_id=business_context.tenant_id,
            industry=business_context.industry,
            channel=business_context.channel,
        ):
            if not isinstance(plugin, RouteStrategyPlugin):
                continue
            result = await plugin.match(plugin_context)
            if result.matched:
                return route_result_to_decision(result)
        return RouteDecision(
            route=RouteType.FALLBACK,
            confidence=0.3,
            reason="fallback",
        )

    def extract_tool_parameters(self, tool_name: str, message: str) -> dict[str, Any]:
        pattern = self.tool_patterns.get(tool_name)
        if not pattern:
            return {}
        match = pattern.search(message)
        if not match:
            return {}
        value = match.group(1).upper()
        mapping = {
            "order_status": "order_id",
            "after_sale_status": "after_sale_id",
            "logistics_tracking": "tracking_no",
            "account_lookup": "account_id",
            "subscription_lookup": "subscription_id",
            "ticket_lookup": "ticket_id",
            "course_lookup": "course_id",
            "progress_lookup": "student_id",
            "waybill_lookup": "waybill_id",
            "claim_lookup": "claim_id",
            "crm_profile": "customer_id",
        }
        return {mapping[tool_name]: value}
