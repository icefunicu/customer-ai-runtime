from __future__ import annotations

from fastapi import FastAPI

from customer_ai_runtime.application.plugins import (
    IndustryAdapterPlugin,
    PluginDescriptor,
)
from customer_ai_runtime.domain.platform import (
    IndustryMatchResult,
    PluginContext,
    PluginKind,
)
from customer_ai_runtime.integration import CustomerAIRuntimeModule


class TravelIndustryAdapterPlugin(IndustryAdapterPlugin):
    def __init__(self) -> None:
        super().__init__(
            PluginDescriptor(
                plugin_id="industry.travel",
                name="Travel Industry Adapter",
                kind=PluginKind.INDUSTRY_ADAPTER,
                priority=880,
                capabilities=["travel", "booking", "itinerary"],
            )
        )
        self._keywords = ["flight", "hotel", "booking", "itinerary", "trip"]
        self._page_types = ["booking_detail", "trip_center", "refund_request"]

    async def match_industry(self, context: PluginContext) -> IndustryMatchResult:
        if context.integration_context.get("industry") == "travel":
            return IndustryMatchResult(
                matched=True,
                industry="travel",
                confidence=0.99,
                context={"preferred_tools": ["booking_lookup", "refund_status_lookup"]},
            )

        page_type = (context.integration_context.get("page_context") or {}).get("page_type", "")
        if page_type in self._page_types:
            return IndustryMatchResult(
                matched=True,
                industry="travel",
                confidence=0.86,
                context={"preferred_tools": ["booking_lookup", "refund_status_lookup"]},
            )

        message = (context.user_message or "").lower()
        if any(keyword in message for keyword in self._keywords):
            return IndustryMatchResult(
                matched=True,
                industry="travel",
                confidence=0.72,
                context={"preferred_tools": ["booking_lookup", "refund_status_lookup"]},
            )
        return IndustryMatchResult()

    async def enrich_context(self, context: PluginContext) -> dict[str, object]:
        return {
            "industry": "travel",
            "extra": {
                "preferred_tools": ["booking_lookup", "refund_status_lookup"],
                "knowledge_domains": ["kb_travel_policy", "kb_travel_booking"],
            },
        }


host_app = FastAPI(title="Host Business System")
customer_ai_module = CustomerAIRuntimeModule.create()
customer_ai_module.register_plugin(TravelIndustryAdapterPlugin())
customer_ai_module.mount_to(host_app, prefix="/customer-ai")


@host_app.get("/host-healthz")
async def host_healthz() -> dict[str, str]:
    return {"status": "ok"}
