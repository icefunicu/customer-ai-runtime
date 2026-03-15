from __future__ import annotations

from customer_ai_runtime.application.plugins import (
    HumanHandoffPlugin,
    PluginRegistry,
    context_to_plugin_context,
)
from customer_ai_runtime.domain.models import Session, SessionState
from customer_ai_runtime.domain.platform import BusinessContext, PluginKind


class HandoffService:
    def __init__(self, registry: PluginRegistry) -> None:
        self._registry = registry

    async def should_handoff(
        self,
        *,
        business_context: BusinessContext,
        route: str,
        response: dict,
    ) -> tuple[bool, str]:
        plugin_context = context_to_plugin_context(
            tenant_id=business_context.tenant_id,
            channel=business_context.channel,
            session_id=business_context.session_id,
            industry=business_context.industry,
            integration_context=business_context.integration_context,
            host_auth_context=business_context.host_auth_context,
            business_context=business_context,
            route=route,
            response=response,
        )
        best_reason = ""
        should_handoff = False
        best_priority = -1
        for plugin in self._registry.resolve(
            PluginKind.HUMAN_HANDOFF,
            tenant_id=business_context.tenant_id,
            industry=business_context.industry,
            channel=business_context.channel,
        ):
            if not isinstance(plugin, HumanHandoffPlugin):
                continue
            decision = await plugin.evaluate(plugin_context)
            if decision.should_handoff and decision.priority > best_priority:
                should_handoff = True
                best_reason = decision.reason
                best_priority = decision.priority
        return should_handoff, best_reason

    async def create_package(
        self,
        session: Session,
        reason: str,
        business_context: BusinessContext,
    ):
        session.state = SessionState.WAITING_HUMAN
        session.waiting_human = True
        for plugin in self._registry.resolve(
            PluginKind.HUMAN_HANDOFF,
            tenant_id=business_context.tenant_id,
            industry=business_context.industry,
            channel=business_context.channel,
        ):
            if not isinstance(plugin, HumanHandoffPlugin):
                continue
            package = await plugin.build_package(session, reason)
            if package is not None:
                return package
        return None
