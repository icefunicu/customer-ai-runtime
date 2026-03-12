from __future__ import annotations

from fastapi import FastAPI

from customer_ai_runtime.application.plugins import (
    ContextEnricherPlugin,
    PluginDescriptor,
)
from customer_ai_runtime.domain.platform import PluginContext, PluginKind
from customer_ai_runtime.integration import CustomerAIRuntimeModule


class CRMContextEnricherPlugin(ContextEnricherPlugin):
    def __init__(self) -> None:
        super().__init__(
            PluginDescriptor(
                plugin_id="context.crm_snapshot",
                name="CRM Context Enricher",
                kind=PluginKind.CONTEXT_ENRICHER,
                priority=860,
                capabilities=["crm_snapshot", "user_tier"],
            )
        )

    async def enrich(self, context: PluginContext) -> dict[str, object]:
        crm_profile = context.integration_context.get("crm_profile") or {}
        behavior_signals = context.integration_context.get("behavior_signals") or {}
        return {
            "user_profile": {
                "customer_tier": crm_profile.get("tier", "standard"),
                "account_owner": crm_profile.get("owner", "unassigned"),
                "last_contact_at": crm_profile.get("last_contact_at"),
            },
            "behavior_signals": {
                "recent_ticket_count": behavior_signals.get("recent_ticket_count", 0),
                "vip_user": behavior_signals.get("vip_user", False),
            },
            "extra": {
                "recommended_reply_style": "concise",
                "crm_tags": crm_profile.get("tags", []),
            },
        }


host_app = FastAPI(title="Host Business System")
customer_ai_module = CustomerAIRuntimeModule.create()
customer_ai_module.register_plugin(CRMContextEnricherPlugin())
customer_ai_module.mount_to(host_app, prefix="/customer-ai")


@host_app.get("/host-healthz")
async def host_healthz() -> dict[str, str]:
    return {"status": "ok"}
