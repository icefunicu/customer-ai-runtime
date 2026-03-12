from __future__ import annotations

import re
from typing import Any

from customer_ai_runtime.domain.models import RouteDecision, RouteType

from customer_ai_runtime.application.runtime import RuntimeConfigService, zh


class RoutingService:
    tool_patterns = {
        "order_status": re.compile(r"(ORD-\d+)", re.IGNORECASE),
        "after_sale_status": re.compile(r"(AS-\d+)", re.IGNORECASE),
        "logistics_tracking": re.compile(r"(YT-\d+)", re.IGNORECASE),
        "account_lookup": re.compile(r"(ACC-\d+)", re.IGNORECASE),
    }

    def __init__(self, runtime_config: RuntimeConfigService) -> None:
        self._runtime_config = runtime_config

    def decide(self, message: str) -> RouteDecision:
        policies = self._runtime_config.get_policies()
        if any(keyword in message for keyword in policies.risk_keywords):
            return RouteDecision(
                route=RouteType.RISK,
                confidence=0.98,
                reason=zh("\\u547d\\u4e2d\\u9ad8\\u98ce\\u9669\\u5173\\u952e\\u8bcd"),
                requires_handoff=True,
            )
        if any(keyword in message for keyword in policies.human_request_keywords):
            return RouteDecision(
                route=RouteType.HANDOFF,
                confidence=0.99,
                reason=zh("\\u7528\\u6237\\u4e3b\\u52a8\\u8981\\u6c42\\u4eba\\u5de5"),
                requires_handoff=True,
            )
        for tool_name, keywords in policies.business_keyword_map.items():
            if any(keyword in message for keyword in keywords):
                return RouteDecision(
                    route=RouteType.BUSINESS,
                    confidence=0.88,
                    reason=zh("\\u547d\\u4e2d\\u4e1a\\u52a1\\u5173\\u952e\\u8bcd"),
                    tool_name=tool_name,
                )
        if (
            "?" in message
            or "\uff1f" in message
            or "\u600e\u4e48" in message
            or "\u4e3a\u4ec0\u4e48" in message
            or "\u89c4\u5219" in message
        ):
            return RouteDecision(
                route=RouteType.KNOWLEDGE,
                confidence=0.72,
                reason=zh("\\u547d\\u4e2d\\u77e5\\u8bc6\\u95ee\\u7b54\\u7279\\u5f81"),
            )
        return RouteDecision(
            route=RouteType.FALLBACK,
            confidence=0.36,
            reason=zh("\\u672a\\u8bc6\\u522b\\u5230\\u660e\\u786e\\u610f\\u56fe"),
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
        }
        return {mapping[tool_name]: value}

