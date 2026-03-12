from __future__ import annotations

from typing import Any

from customer_ai_runtime.application.plugins import (
    BusinessToolPlugin,
    ContextEnricherPlugin,
    IndustryAdapterPlugin,
    PluginRegistry,
    ResponsePostProcessorPlugin,
    context_to_plugin_context,
    merge_context_payload,
)
from customer_ai_runtime.domain.models import BusinessQuery, BusinessResult, Session
from customer_ai_runtime.domain.platform import BusinessContext, IndustryMatchResult, PluginKind
from customer_ai_runtime.providers.base import BusinessAdapter


class IndustryService:
    def __init__(self, registry: PluginRegistry) -> None:
        self._registry = registry

    async def detect(self, context: BusinessContext, user_message: str | None = None) -> IndustryMatchResult:
        plugin_context = context_to_plugin_context(
            tenant_id=context.tenant_id,
            channel=context.channel,
            session_id=context.session_id,
            user_message=user_message,
            industry=context.industry,
            integration_context=context.integration_context,
            host_auth_context=context.host_auth_context,
            business_context=context,
        )
        best = IndustryMatchResult(industry=context.industry, matched=bool(context.industry), confidence=0.99)
        for plugin in self._registry.resolve(
            PluginKind.INDUSTRY_ADAPTER,
            tenant_id=context.tenant_id,
            industry=context.industry,
            channel=context.channel,
        ):
            if not isinstance(plugin, IndustryAdapterPlugin):
                continue
            result = await plugin.match_industry(plugin_context)
            if result.matched and result.confidence > best.confidence:
                best = result
        return best

    async def enrich(self, context: BusinessContext) -> dict[str, Any]:
        if not context.industry:
            return {}
        payload: dict[str, Any] = {}
        plugin_context = context_to_plugin_context(
            tenant_id=context.tenant_id,
            channel=context.channel,
            session_id=context.session_id,
            user_message=None,
            industry=context.industry,
            integration_context=context.integration_context,
            host_auth_context=context.host_auth_context,
            business_context=context,
        )
        for plugin in self._registry.resolve(
            PluginKind.INDUSTRY_ADAPTER,
            tenant_id=context.tenant_id,
            industry=context.industry,
            channel=context.channel,
        ):
            if not isinstance(plugin, IndustryAdapterPlugin):
                continue
            matched = await plugin.match_industry(plugin_context)
            if matched.industry != context.industry:
                continue
            payload = merge_context_payload(payload, await plugin.enrich_context(plugin_context))
        return payload


class BusinessContextBuilder:
    def __init__(self, registry: PluginRegistry, industry_service: IndustryService) -> None:
        self._registry = registry
        self._industry_service = industry_service

    async def build(
        self,
        *,
        tenant_id: str,
        channel: str,
        session: Session | None,
        integration_context: dict[str, Any] | None,
        host_auth_context: Any = None,
        user_message: str | None = None,
    ) -> BusinessContext:
        context = BusinessContext(
            tenant_id=tenant_id,
            channel=channel,
            session_id=None if session is None else session.session_id,
            industry=(integration_context or {}).get("industry"),
            host_auth_context=host_auth_context,
            integration_context=integration_context or {},
            session_summary="" if session is None else session.summary,
            permissions=[] if not host_auth_context else list(host_auth_context.permissions),
        )
        detected = await self._industry_service.detect(context, user_message=user_message)
        if detected.industry and not context.industry:
            context.industry = detected.industry
        merged = context.model_dump(mode="json")
        merged = merge_context_payload(merged, await self._industry_service.enrich(context))
        plugin_context = context_to_plugin_context(
            tenant_id=context.tenant_id,
            channel=context.channel,
            session_id=context.session_id,
            user_message=user_message,
            industry=context.industry,
            integration_context=context.integration_context,
            host_auth_context=context.host_auth_context,
            business_context=context,
        )
        for plugin in self._registry.resolve(
            PluginKind.CONTEXT_ENRICHER,
            tenant_id=context.tenant_id,
            industry=context.industry,
            channel=context.channel,
        ):
            if not isinstance(plugin, ContextEnricherPlugin):
                continue
            merged = merge_context_payload(merged, await plugin.enrich(plugin_context))
        return BusinessContext.model_validate(merged)


class KnowledgeDomainManager:
    def __init__(self, domain_map: dict[str, object]) -> None:
        self._domain_map = domain_map

    def resolve_primary(self, tenant_id: str, industry: str | None, explicit: str | None) -> str | None:
        if explicit:
            return explicit
        tenant_mapping = self._domain_map.get(tenant_id, {})
        if isinstance(tenant_mapping, dict):
            if industry and tenant_mapping.get(industry):
                return str(tenant_mapping[industry])
            if tenant_mapping.get("default"):
                return str(tenant_mapping["default"])
        global_mapping = self._domain_map.get("default", {})
        if isinstance(global_mapping, dict):
            if industry and global_mapping.get(industry):
                return str(global_mapping[industry])
            if global_mapping.get("default"):
                return str(global_mapping["default"])
        return None


class RealTimeBusinessDataProvider:
    def __init__(self, registry: PluginRegistry, adapter: BusinessAdapter) -> None:
        self._registry = registry
        self._adapter = adapter

    async def execute(
        self,
        *,
        context: BusinessContext,
        tool_name: str,
        parameters: dict[str, Any],
    ) -> BusinessResult:
        plugin_context = context_to_plugin_context(
            tenant_id=context.tenant_id,
            channel=context.channel,
            session_id=context.session_id,
            industry=context.industry,
            integration_context=context.integration_context,
            host_auth_context=context.host_auth_context,
            business_context=context,
        )
        for plugin in self._registry.resolve(
            PluginKind.BUSINESS_TOOL,
            tenant_id=context.tenant_id,
            industry=context.industry,
            channel=context.channel,
        ):
            if isinstance(plugin, BusinessToolPlugin) and plugin.tool_name == tool_name:
                return await plugin.execute(plugin_context, parameters)
        return await self._adapter.execute(
            BusinessQuery(
                tenant_id=context.tenant_id,
                tool_name=tool_name,
                parameters=parameters,
                session_id=context.session_id,
                integration_context=context.integration_context,
            )
        )


class ResponseEnhancementOrchestrator:
    def __init__(self, registry: PluginRegistry) -> None:
        self._registry = registry

    async def enhance(self, response: dict[str, Any], context: BusinessContext) -> dict[str, Any]:
        plugin_context = context_to_plugin_context(
            tenant_id=context.tenant_id,
            channel=context.channel,
            session_id=context.session_id,
            industry=context.industry,
            integration_context=context.integration_context,
            host_auth_context=context.host_auth_context,
            business_context=context,
            route=response.get("route"),
            response=response,
        )
        enhanced = dict(response)
        for plugin in self._registry.resolve(
            PluginKind.RESPONSE_POST_PROCESSOR,
            tenant_id=context.tenant_id,
            industry=context.industry,
            channel=context.channel,
        ):
            if not isinstance(plugin, ResponsePostProcessorPlugin):
                continue
            enhanced = await plugin.process(plugin_context, enhanced)
            plugin_context.response = enhanced
        return enhanced
