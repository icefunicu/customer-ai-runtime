from __future__ import annotations

import re
from abc import abstractmethod
from collections.abc import Callable
from typing import Any

from customer_ai_runtime.application.runtime import RuntimeConfigService, zh
from customer_ai_runtime.core.errors import AppError
from customer_ai_runtime.domain.models import (
    BusinessQuery,
    BusinessResult,
    HandoffPackage,
    MessageRole,
    RouteDecision,
    RouteType,
    Session,
)
from customer_ai_runtime.domain.platform import (
    BusinessContext,
    HandoffDecision,
    IndustryMatchResult,
    PluginContext,
    PluginDescriptor,
    PluginKind,
    RoutePluginResult,
)
from customer_ai_runtime.providers.base import BusinessAdapter


class Plugin:
    def __init__(self, descriptor: PluginDescriptor) -> None:
        self.descriptor = descriptor

    async def startup(self) -> None:
        return

    async def shutdown(self) -> None:
        return


class RouteStrategyPlugin(Plugin):
    @abstractmethod
    async def match(self, context: PluginContext) -> RoutePluginResult: ...


class BusinessToolPlugin(Plugin):
    tool_name: str
    category: str
    description: str
    required_parameters: list[str]
    optional_parameters: list[str]
    suggested_context_keys: list[str]

    def resolve_parameters(
        self,
        context: PluginContext,
        parameters: dict[str, Any],
    ) -> dict[str, Any]:
        return dict(parameters)

    def missing_parameters(
        self,
        context: PluginContext,
        parameters: dict[str, Any],
    ) -> list[str]:
        resolved = self.resolve_parameters(context, parameters)
        return [key for key in self.required_parameters if not resolved.get(key)]

    @abstractmethod
    async def execute(
        self,
        context: PluginContext,
        parameters: dict[str, Any],
    ) -> BusinessResult: ...


class HumanHandoffPlugin(Plugin):
    async def evaluate(self, context: PluginContext) -> HandoffDecision:
        return HandoffDecision()

    async def build_package(self, session: Session, reason: str) -> HandoffPackage | None:
        return None


class IndustryAdapterPlugin(Plugin):
    @abstractmethod
    async def match_industry(self, context: PluginContext) -> IndustryMatchResult: ...

    async def enrich_context(self, context: PluginContext) -> dict[str, Any]:
        return {}


class ContextEnricherPlugin(Plugin):
    @abstractmethod
    async def enrich(self, context: PluginContext) -> dict[str, Any]: ...


class ResponsePostProcessorPlugin(Plugin):
    @abstractmethod
    async def process(self, context: PluginContext, response: dict[str, Any]) -> dict[str, Any]: ...


class PluginRegistry:
    def __init__(
        self,
        persisted_states: dict[str, bool] | None = None,
        on_state_change: Callable[[str, bool], None] | None = None,
    ) -> None:
        self._plugins: dict[str, Plugin] = {}
        self._persisted_states = persisted_states or {}
        self._on_state_change = on_state_change
        self._started = False

    def register(self, plugin: Plugin) -> None:
        persisted_enabled = self._persisted_states.get(plugin.descriptor.plugin_id)
        if persisted_enabled is not None:
            plugin.descriptor.enabled = persisted_enabled
        self._plugins[plugin.descriptor.plugin_id] = plugin

    def unregister(self, plugin_id: str) -> None:
        if plugin_id in self._plugins:
            del self._plugins[plugin_id]

    def enable(self, plugin_id: str) -> PluginDescriptor:
        plugin = self._get(plugin_id)
        plugin.descriptor.enabled = True
        self._persist_state(plugin_id, True)
        return plugin.descriptor.model_copy(deep=True)

    def disable(self, plugin_id: str) -> PluginDescriptor:
        plugin = self._get(plugin_id)
        plugin.descriptor.enabled = False
        self._persist_state(plugin_id, False)
        return plugin.descriptor.model_copy(deep=True)

    def list_descriptors(self, kind: PluginKind | None = None) -> list[PluginDescriptor]:
        descriptors = [
            plugin.descriptor.model_copy(deep=True)
            for plugin in self._plugins.values()
            if kind is None or plugin.descriptor.kind == kind
        ]
        descriptors.sort(key=lambda item: item.priority, reverse=True)
        return descriptors

    def resolve(
        self,
        kind: PluginKind,
        tenant_id: str | None = None,
        industry: str | None = None,
        channel: str | None = None,
    ) -> list[Plugin]:
        plugins = [
            plugin
            for plugin in self._plugins.values()
            if plugin.descriptor.kind == kind
            and plugin.descriptor.enabled
            and _scope_match(plugin.descriptor.tenant_scopes, tenant_id)
            and _scope_match(plugin.descriptor.industry_scopes, industry)
            and _scope_match(plugin.descriptor.channel_scopes, channel)
        ]
        plugins.sort(key=lambda plugin: plugin.descriptor.priority, reverse=True)
        return plugins

    def plugins(self, kind: PluginKind | None = None) -> list[Plugin]:
        items = [
            plugin
            for plugin in self._plugins.values()
            if kind is None or plugin.descriptor.kind == kind
        ]
        items.sort(key=lambda plugin: plugin.descriptor.priority, reverse=True)
        return items

    def get(self, plugin_id: str) -> Plugin:
        return self._get(plugin_id)

    async def startup(self) -> None:
        if self._started:
            return
        for plugin in self.plugins():
            if plugin.descriptor.enabled:
                await plugin.startup()
        self._started = True

    async def shutdown(self) -> None:
        if not self._started:
            return
        for plugin in reversed(self.plugins()):
            if plugin.descriptor.enabled:
                await plugin.shutdown()
        self._started = False

    def _get(self, plugin_id: str) -> Plugin:
        plugin = self._plugins.get(plugin_id)
        if not plugin:
            raise AppError(code="not_found", message=f"插件不存在: {plugin_id}", status_code=404)
        return plugin

    def _persist_state(self, plugin_id: str, enabled: bool) -> None:
        self._persisted_states[plugin_id] = enabled
        if self._on_state_change:
            self._on_state_change(plugin_id, enabled)


class RiskRoutePlugin(RouteStrategyPlugin):
    def __init__(self, runtime_config: RuntimeConfigService) -> None:
        super().__init__(
            PluginDescriptor(
                plugin_id="route.risk",
                name="Risk Route Plugin",
                kind=PluginKind.ROUTE_STRATEGY,
                priority=1000,
                capabilities=["risk_detection", "handoff"],
            )
        )
        self._runtime_config = runtime_config

    async def match(self, context: PluginContext) -> RoutePluginResult:
        policies = self._runtime_config.get_policies()
        message = context.user_message or ""
        if any(keyword in message for keyword in policies.risk_keywords):
            return RoutePluginResult(
                matched=True,
                route=RouteType.RISK.value,
                confidence=0.98,
                reason=zh("\\u547d\\u4e2d\\u9ad8\\u98ce\\u9669\\u5173\\u952e\\u8bcd"),
                intent=RouteType.RISK.value,
                requires_handoff=True,
                matched_signals=["keyword:risk"],
            )
        return RoutePluginResult()


class HumanRequestRoutePlugin(RouteStrategyPlugin):
    def __init__(self, runtime_config: RuntimeConfigService) -> None:
        super().__init__(
            PluginDescriptor(
                plugin_id="route.human_request",
                name="Human Request Route Plugin",
                kind=PluginKind.ROUTE_STRATEGY,
                priority=950,
                capabilities=["handoff"],
            )
        )
        self._runtime_config = runtime_config

    async def match(self, context: PluginContext) -> RoutePluginResult:
        policies = self._runtime_config.get_policies()
        message = context.user_message or ""
        if any(keyword in message for keyword in policies.human_request_keywords):
            return RoutePluginResult(
                matched=True,
                route=RouteType.HANDOFF.value,
                confidence=0.99,
                reason=zh("\\u7528\\u6237\\u4e3b\\u52a8\\u8981\\u6c42\\u4eba\\u5de5"),
                intent="human_request",
                requires_handoff=True,
                matched_signals=["keyword:human_request"],
            )
        return RoutePluginResult()


class BusinessIntentRoutePlugin(RouteStrategyPlugin):
    default_keywords = {
        "order_status": ["订单", "发货", "订单状态", "快递单号"],
        "after_sale_status": ["售后", "退款进度", "退货", "工单"],
        "logistics_tracking": ["物流", "快递", "配送", "轨迹"],
        "account_lookup": ["账号", "会员", "积分", "账户"],
        "subscription_lookup": ["套餐", "订阅", "续费", "账单"],
        "ticket_lookup": ["工单", "服务单", "ticket"],
        "course_lookup": ["课程", "班级", "考试", "证书"],
        "progress_lookup": ["进度", "学习进度", "课时"],
        "waybill_lookup": ["运单", "揽收", "签收"],
        "claim_lookup": ["赔付", "理赔", "异常件"],
        "crm_profile": ["客户档案", "客户等级", "跟进记录"],
    }

    def __init__(self, runtime_config: RuntimeConfigService) -> None:
        super().__init__(
            PluginDescriptor(
                plugin_id="route.business_intent",
                name="Business Intent Route Plugin",
                kind=PluginKind.ROUTE_STRATEGY,
                priority=800,
                capabilities=["business_query"],
            )
        )
        self._runtime_config = runtime_config

    async def match(self, context: PluginContext) -> RoutePluginResult:
        policies = self._runtime_config.get_policies()
        keyword_map = dict(self.default_keywords)
        keyword_map.update(policies.business_keyword_map)
        message = context.user_message or ""
        for tool_name, keywords in keyword_map.items():
            if any(keyword in message for keyword in keywords):
                return RoutePluginResult(
                    matched=True,
                    route=RouteType.BUSINESS.value,
                    confidence=0.88,
                    reason=zh("\\u547d\\u4e2d\\u4e1a\\u52a1\\u5173\\u952e\\u8bcd"),
                    intent=tool_name,
                    tool_name=tool_name,
                    matched_signals=["keyword:business"],
                )
        return RoutePluginResult()


class KnowledgeQuestionRoutePlugin(RouteStrategyPlugin):
    def __init__(self) -> None:
        super().__init__(
            PluginDescriptor(
                plugin_id="route.knowledge",
                name="Knowledge Route Plugin",
                kind=PluginKind.ROUTE_STRATEGY,
                priority=500,
                capabilities=["rag"],
            )
        )

    async def match(self, context: PluginContext) -> RoutePluginResult:
        message = context.user_message or ""
        if (
            "?" in message
            or "？" in message
            or "怎么" in message
            or "为什么" in message
            or "规则" in message
        ):
            return RoutePluginResult(
                matched=True,
                route=RouteType.KNOWLEDGE.value,
                confidence=0.72,
                reason=zh("\\u547d\\u4e2d\\u77e5\\u8bc6\\u95ee\\u7b54\\u7279\\u5f81"),
                intent="knowledge_question",
                matched_signals=["pattern:knowledge_question"],
            )
        return RoutePluginResult()


class FallbackRoutePlugin(RouteStrategyPlugin):
    def __init__(self) -> None:
        super().__init__(
            PluginDescriptor(
                plugin_id="route.fallback",
                name="Fallback Route Plugin",
                kind=PluginKind.ROUTE_STRATEGY,
                priority=1,
                capabilities=["fallback"],
            )
        )

    async def match(self, context: PluginContext) -> RoutePluginResult:
        return RoutePluginResult(
            matched=True,
            route=RouteType.FALLBACK.value,
            confidence=0.36,
            reason=zh("\\u672a\\u8bc6\\u522b\\u5230\\u660e\\u786e\\u610f\\u56fe"),
            intent="fallback_clarification",
            matched_signals=["fallback:no_match"],
        )


class AdapterBackedBusinessToolPlugin(BusinessToolPlugin):
    def __init__(
        self,
        *,
        plugin_id: str,
        tool_name: str,
        category: str,
        description: str,
        required_parameters: list[str],
        optional_parameters: list[str],
        suggested_context_keys: list[str],
        adapter: BusinessAdapter,
        industry_scopes: list[str] | None = None,
        parameter_aliases: dict[str, list[str]] | None = None,
    ) -> None:
        super().__init__(
            PluginDescriptor(
                plugin_id=plugin_id,
                name=tool_name,
                kind=PluginKind.BUSINESS_TOOL,
                priority=300,
                capabilities=[tool_name],
                industry_scopes=industry_scopes or [],
            )
        )
        self.tool_name = tool_name
        self.category = category
        self.description = description
        self.required_parameters = required_parameters
        self.optional_parameters = optional_parameters
        self.suggested_context_keys = suggested_context_keys
        self._adapter = adapter
        self._parameter_aliases = parameter_aliases or {}

    def resolve_parameters(
        self,
        context: PluginContext,
        parameters: dict[str, Any],
    ) -> dict[str, Any]:
        resolved = dict(parameters)
        for field_name, aliases in self._parameter_aliases.items():
            if resolved.get(field_name):
                continue
            for alias in aliases:
                value = _lookup_context_alias(context, alias)
                if value not in (None, ""):
                    resolved[field_name] = value
                    break
        return resolved

    async def execute(self, context: PluginContext, parameters: dict[str, Any]) -> BusinessResult:
        resolved_parameters = self.resolve_parameters(context, parameters)
        return await self._adapter.execute(
            BusinessQuery(
                tenant_id=context.tenant_id,
                tool_name=self.tool_name,
                parameters=resolved_parameters,
                session_id=context.session_id,
                integration_context=context.integration_context,
            )
        )


class OrderStatusToolPlugin(AdapterBackedBusinessToolPlugin):
    def __init__(self, adapter: BusinessAdapter) -> None:
        super().__init__(
            plugin_id="tool.order_status",
            tool_name="order_status",
            category="ecommerce",
            description="Query order fulfillment and payment status.",
            required_parameters=["order_id"],
            optional_parameters=[],
            suggested_context_keys=["shop_id", "customer_id", "order_id"],
            adapter=adapter,
            industry_scopes=["ecommerce"],
            parameter_aliases={
                "order_id": [
                    "business_context.business_objects.order_id",
                    "integration_context.business_objects.order_id",
                    "integration_context.order_id",
                ]
            },
        )


class AfterSaleStatusToolPlugin(AdapterBackedBusinessToolPlugin):
    def __init__(self, adapter: BusinessAdapter) -> None:
        super().__init__(
            plugin_id="tool.after_sale_status",
            tool_name="after_sale_status",
            category="ecommerce",
            description="Query refund and after-sale status.",
            required_parameters=["after_sale_id"],
            optional_parameters=[],
            suggested_context_keys=["shop_id", "customer_id", "after_sale_id"],
            adapter=adapter,
            industry_scopes=["ecommerce"],
            parameter_aliases={
                "after_sale_id": [
                    "business_context.business_objects.after_sale_id",
                    "integration_context.business_objects.after_sale_id",
                    "integration_context.after_sale_id",
                ]
            },
        )


class LogisticsTrackingToolPlugin(AdapterBackedBusinessToolPlugin):
    def __init__(self, adapter: BusinessAdapter) -> None:
        super().__init__(
            plugin_id="tool.logistics_tracking",
            tool_name="logistics_tracking",
            category="ecommerce",
            description="Query logistics tracking.",
            required_parameters=["tracking_no"],
            optional_parameters=["carrier_code"],
            suggested_context_keys=["shop_id", "tracking_no"],
            adapter=adapter,
            industry_scopes=["ecommerce", "logistics"],
            parameter_aliases={
                "tracking_no": [
                    "business_context.business_objects.tracking_no",
                    "integration_context.business_objects.tracking_no",
                    "integration_context.tracking_no",
                ],
                "carrier_code": [
                    "business_context.business_objects.carrier_code",
                    "integration_context.business_objects.carrier_code",
                    "integration_context.carrier_code",
                ],
            },
        )


class AccountLookupToolPlugin(AdapterBackedBusinessToolPlugin):
    def __init__(self, adapter: BusinessAdapter) -> None:
        super().__init__(
            plugin_id="tool.account_lookup",
            tool_name="account_lookup",
            category="crm",
            description="Query customer account profile.",
            required_parameters=["account_id"],
            optional_parameters=[],
            suggested_context_keys=["customer_id", "account_id"],
            adapter=adapter,
            industry_scopes=["crm", "saas"],
            parameter_aliases={
                "account_id": [
                    "business_context.business_objects.account_id",
                    "integration_context.business_objects.account_id",
                    "integration_context.account_id",
                ]
            },
        )


class SubscriptionLookupToolPlugin(AdapterBackedBusinessToolPlugin):
    def __init__(self, adapter: BusinessAdapter) -> None:
        super().__init__(
            plugin_id="tool.subscription_lookup",
            tool_name="subscription_lookup",
            category="saas",
            description="Query subscription and billing information.",
            required_parameters=["subscription_id"],
            optional_parameters=[],
            suggested_context_keys=["organization_id", "subscription_id"],
            adapter=adapter,
            industry_scopes=["saas"],
            parameter_aliases={
                "subscription_id": [
                    "business_context.business_objects.subscription_id",
                    "integration_context.business_objects.subscription_id",
                    "integration_context.subscription_id",
                ]
            },
        )


class TicketLookupToolPlugin(AdapterBackedBusinessToolPlugin):
    def __init__(self, adapter: BusinessAdapter) -> None:
        super().__init__(
            plugin_id="tool.ticket_lookup",
            tool_name="ticket_lookup",
            category="service",
            description="Query service ticket status.",
            required_parameters=["ticket_id"],
            optional_parameters=[],
            suggested_context_keys=["organization_id", "ticket_id"],
            adapter=adapter,
            industry_scopes=["saas", "crm"],
            parameter_aliases={
                "ticket_id": [
                    "business_context.business_objects.ticket_id",
                    "integration_context.business_objects.ticket_id",
                    "integration_context.ticket_id",
                ]
            },
        )


class CourseLookupToolPlugin(AdapterBackedBusinessToolPlugin):
    def __init__(self, adapter: BusinessAdapter) -> None:
        super().__init__(
            plugin_id="tool.course_lookup",
            tool_name="course_lookup",
            category="education",
            description="Query course information.",
            required_parameters=["course_id"],
            optional_parameters=[],
            suggested_context_keys=["student_id", "course_id"],
            adapter=adapter,
            industry_scopes=["education"],
            parameter_aliases={
                "course_id": [
                    "business_context.business_objects.course_id",
                    "integration_context.business_objects.course_id",
                    "integration_context.course_id",
                ]
            },
        )


class ProgressLookupToolPlugin(AdapterBackedBusinessToolPlugin):
    def __init__(self, adapter: BusinessAdapter) -> None:
        super().__init__(
            plugin_id="tool.progress_lookup",
            tool_name="progress_lookup",
            category="education",
            description="Query learning progress.",
            required_parameters=["student_id"],
            optional_parameters=["course_id"],
            suggested_context_keys=["student_id", "course_id"],
            adapter=adapter,
            industry_scopes=["education"],
            parameter_aliases={
                "student_id": [
                    "business_context.business_objects.student_id",
                    "integration_context.business_objects.student_id",
                    "integration_context.student_id",
                ],
                "course_id": [
                    "business_context.business_objects.course_id",
                    "integration_context.business_objects.course_id",
                    "integration_context.course_id",
                ],
            },
        )


class WaybillLookupToolPlugin(AdapterBackedBusinessToolPlugin):
    def __init__(self, adapter: BusinessAdapter) -> None:
        super().__init__(
            plugin_id="tool.waybill_lookup",
            tool_name="waybill_lookup",
            category="logistics",
            description="Query waybill status.",
            required_parameters=["waybill_id"],
            optional_parameters=[],
            suggested_context_keys=["waybill_id"],
            adapter=adapter,
            industry_scopes=["logistics"],
            parameter_aliases={
                "waybill_id": [
                    "business_context.business_objects.waybill_id",
                    "integration_context.business_objects.waybill_id",
                    "integration_context.waybill_id",
                ]
            },
        )


class ClaimLookupToolPlugin(AdapterBackedBusinessToolPlugin):
    def __init__(self, adapter: BusinessAdapter) -> None:
        super().__init__(
            plugin_id="tool.claim_lookup",
            tool_name="claim_lookup",
            category="logistics",
            description="Query logistics claim status.",
            required_parameters=["claim_id"],
            optional_parameters=[],
            suggested_context_keys=["claim_id"],
            adapter=adapter,
            industry_scopes=["logistics"],
            parameter_aliases={
                "claim_id": [
                    "business_context.business_objects.claim_id",
                    "integration_context.business_objects.claim_id",
                    "integration_context.claim_id",
                ]
            },
        )


class CRMProfileToolPlugin(AdapterBackedBusinessToolPlugin):
    def __init__(self, adapter: BusinessAdapter) -> None:
        super().__init__(
            plugin_id="tool.crm_profile",
            tool_name="crm_profile",
            category="crm",
            description="Query CRM customer profile.",
            required_parameters=["customer_id"],
            optional_parameters=[],
            suggested_context_keys=["customer_id"],
            adapter=adapter,
            industry_scopes=["crm"],
            parameter_aliases={
                "customer_id": [
                    "business_context.business_objects.customer_id",
                    "integration_context.business_objects.customer_id",
                    "integration_context.customer_id",
                ]
            },
        )


class ConfiguredIndustryAdapterPlugin(IndustryAdapterPlugin):
    def __init__(
        self,
        *,
        industry: str,
        name: str | None = None,
        keywords: list[str],
        page_types: list[str],
        preferred_tools: list[str],
        description: str = "",
        knowledge_domains: list[str] | None = None,
        extra_context: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            PluginDescriptor(
                plugin_id=f"industry.{industry}",
                name=name or f"{industry} adapter",
                kind=PluginKind.INDUSTRY_ADAPTER,
                priority=400,
                capabilities=[industry],
                description=description,
            )
        )
        self._industry = industry
        self._keywords = keywords
        self._page_types = page_types
        self._preferred_tools = preferred_tools
        self._knowledge_domains = knowledge_domains or [f"kb_{industry}"]
        self._extra_context = extra_context or {}

    async def match_industry(self, context: PluginContext) -> IndustryMatchResult:
        integration_context = context.integration_context
        explicit = integration_context.get("industry")
        if explicit == self._industry:
            return IndustryMatchResult(
                matched=True,
                industry=self._industry,
                confidence=0.99,
                context=self._build_match_context(),
            )
        page_type = (integration_context.get("page_context") or {}).get("page_type", "")
        if page_type in self._page_types:
            return IndustryMatchResult(
                matched=True,
                industry=self._industry,
                confidence=0.8,
                context=self._build_match_context(),
            )
        text = f"{context.user_message or ''} {page_type}"
        if any(keyword in text for keyword in self._keywords):
            return IndustryMatchResult(
                matched=True,
                industry=self._industry,
                confidence=0.65,
                context=self._build_match_context(),
            )
        return IndustryMatchResult()

    async def enrich_context(self, context: PluginContext) -> dict[str, Any]:
        return {
            "industry": self._industry,
            "extra": {
                "preferred_tools": self._preferred_tools,
                "knowledge_domains": self._knowledge_domains,
                **self._extra_context,
            },
        }

    def _build_match_context(self) -> dict[str, Any]:
        return {
            "preferred_tools": self._preferred_tools,
            "knowledge_domains": self._knowledge_domains,
            **self._extra_context,
        }


class EcommerceIndustryPlugin(ConfiguredIndustryAdapterPlugin):
    def __init__(self) -> None:
        super().__init__(
            industry="ecommerce",
            name="Ecommerce Industry Plugin",
            keywords=["订单", "售后", "发货", "物流", "优惠券"],
            page_types=["product_detail", "order_detail", "after_sale_detail"],
            preferred_tools=["order_status", "after_sale_status", "logistics_tracking"],
            description="Built-in industry adapter for ecommerce customer service scenarios.",
            extra_context={
                "domain_focus": ["order", "fulfillment", "after_sale"],
                "default_object_keys": ["order_id", "after_sale_id", "tracking_no"],
            },
        )


class SaaSIndustryPlugin(ConfiguredIndustryAdapterPlugin):
    def __init__(self) -> None:
        super().__init__(
            industry="saas",
            name="SaaS Industry Plugin",
            keywords=["套餐", "订阅", "权限", "组织", "账单"],
            page_types=["billing", "organization", "permission"],
            preferred_tools=["account_lookup", "subscription_lookup", "ticket_lookup"],
            description="Built-in industry adapter for SaaS account, billing, and support flows.",
            extra_context={
                "domain_focus": ["subscription", "organization", "permission"],
                "default_object_keys": ["account_id", "subscription_id", "ticket_id"],
            },
        )


class EducationIndustryPlugin(ConfiguredIndustryAdapterPlugin):
    def __init__(self) -> None:
        super().__init__(
            industry="education",
            name="Education Industry Plugin",
            keywords=["课程", "班级", "学习", "考试", "证书"],
            page_types=["course_detail", "learning", "exam"],
            preferred_tools=["course_lookup", "progress_lookup"],
            description="Built-in industry adapter for course, exam, and learning progress flows.",
            extra_context={
                "domain_focus": ["course", "learning", "exam"],
                "default_object_keys": ["course_id", "student_id"],
            },
        )


class LogisticsIndustryPlugin(ConfiguredIndustryAdapterPlugin):
    def __init__(self) -> None:
        super().__init__(
            industry="logistics",
            name="Logistics Industry Plugin",
            keywords=["运单", "签收", "揽收", "赔付", "配送"],
            page_types=["tracking", "claim"],
            preferred_tools=["waybill_lookup", "claim_lookup", "logistics_tracking"],
            description="Built-in industry adapter for delivery tracking and claims.",
            extra_context={
                "domain_focus": ["delivery", "tracking", "claim"],
                "default_object_keys": ["waybill_id", "claim_id", "tracking_no"],
            },
        )


class CRMIndustryPlugin(ConfiguredIndustryAdapterPlugin):
    def __init__(self) -> None:
        super().__init__(
            industry="crm",
            name="CRM Industry Plugin",
            keywords=["客户", "服务记录", "工单", "服务等级"],
            page_types=["customer_profile", "service_ticket"],
            preferred_tools=["crm_profile", "ticket_lookup", "account_lookup"],
            description="Built-in industry adapter for CRM profile and service workflows.",
            extra_context={
                "domain_focus": ["customer", "service", "ticket"],
                "default_object_keys": ["customer_id", "ticket_id", "account_id"],
            },
        )


class PageContextEnricherPlugin(ContextEnricherPlugin):
    def __init__(self) -> None:
        super().__init__(
            PluginDescriptor(
                plugin_id="context.page",
                name="Page Context Enricher",
                kind=PluginKind.CONTEXT_ENRICHER,
                priority=300,
                capabilities=["page_context"],
            )
        )

    async def enrich(self, context: PluginContext) -> dict[str, Any]:
        return {"page_context": context.integration_context.get("page_context", {})}


class BusinessObjectEnricherPlugin(ContextEnricherPlugin):
    def __init__(self) -> None:
        super().__init__(
            PluginDescriptor(
                plugin_id="context.business_object",
                name="Business Object Context Enricher",
                kind=PluginKind.CONTEXT_ENRICHER,
                priority=280,
                capabilities=["business_objects"],
            )
        )

    async def enrich(self, context: PluginContext) -> dict[str, Any]:
        return {"business_objects": context.integration_context.get("business_objects", {})}


class UserProfileEnricherPlugin(ContextEnricherPlugin):
    def __init__(self) -> None:
        super().__init__(
            PluginDescriptor(
                plugin_id="context.user_profile",
                name="User Profile Enricher",
                kind=PluginKind.CONTEXT_ENRICHER,
                priority=260,
                capabilities=["user_profile"],
            )
        )

    async def enrich(self, context: PluginContext) -> dict[str, Any]:
        host_auth = context.host_auth_context
        if not host_auth:
            return {}
        return {
            "user_profile": {
                "principal_id": host_auth.principal_id,
                "roles": host_auth.roles,
                "permissions": host_auth.permissions,
                "source_system": host_auth.source_system,
            }
        }


class BehaviorSignalsEnricherPlugin(ContextEnricherPlugin):
    def __init__(self) -> None:
        super().__init__(
            PluginDescriptor(
                plugin_id="context.behavior_signals",
                name="Behavior Signals Enricher",
                kind=PluginKind.CONTEXT_ENRICHER,
                priority=240,
                capabilities=["behavior_signals"],
            )
        )

    async def enrich(self, context: PluginContext) -> dict[str, Any]:
        return {"behavior_signals": context.integration_context.get("behavior_signals", {})}


class SessionInsightsEnricherPlugin(ContextEnricherPlugin):
    def __init__(self) -> None:
        super().__init__(
            PluginDescriptor(
                plugin_id="context.session_insights",
                name="Session Insights Enricher",
                kind=PluginKind.CONTEXT_ENRICHER,
                priority=220,
                capabilities=["session_insights"],
            )
        )

    async def enrich(self, context: PluginContext) -> dict[str, Any]:
        business_context = context.business_context
        if not business_context:
            return {}
        messages = getattr(business_context, "session_summary", "")
        return {
            "extra": {
                "session_insights": {
                    "has_summary": bool(messages),
                    "summary": messages,
                    "permissions": list(business_context.permissions),
                    "channel": business_context.channel,
                }
            }
        }


class ReferenceAppendPostProcessorPlugin(ResponsePostProcessorPlugin):
    def __init__(self) -> None:
        super().__init__(
            PluginDescriptor(
                plugin_id="response.references",
                name="Reference Append Post Processor",
                kind=PluginKind.RESPONSE_POST_PROCESSOR,
                priority=200,
                capabilities=["references"],
            )
        )

    async def process(self, context: PluginContext, response: dict[str, Any]) -> dict[str, Any]:
        citations = response.get("citations") or []
        if not citations:
            return response
        titles = "、".join(item["title"] for item in citations[:2] if item.get("title"))
        if titles and "参考：" not in response["answer"]:
            response["answer"] = f"{response['answer']} 参考：{titles}。"
        return response


class SensitiveMaskPostProcessorPlugin(ResponsePostProcessorPlugin):
    phone_pattern = re.compile(r"(?<!\d)(1\d{2})\d{4}(\d{4})(?!\d)")

    def __init__(self) -> None:
        super().__init__(
            PluginDescriptor(
                plugin_id="response.mask",
                name="Sensitive Mask Post Processor",
                kind=PluginKind.RESPONSE_POST_PROCESSOR,
                priority=190,
                capabilities=["masking"],
            )
        )

    async def process(self, context: PluginContext, response: dict[str, Any]) -> dict[str, Any]:
        response["answer"] = self.phone_pattern.sub(r"\1****\2", response["answer"])
        return response


class StructuredOutputPostProcessorPlugin(ResponsePostProcessorPlugin):
    def __init__(self) -> None:
        super().__init__(
            PluginDescriptor(
                plugin_id="response.structured",
                name="Structured Output Post Processor",
                kind=PluginKind.RESPONSE_POST_PROCESSOR,
                priority=100,
                capabilities=["structured_output"],
            )
        )

    async def process(self, context: PluginContext, response: dict[str, Any]) -> dict[str, Any]:
        if context.integration_context.get("response_format") != "structured":
            return response
        response["structured_output"] = {
            "route": response.get("route"),
            "answer": response.get("answer"),
            "industry": response.get("industry"),
            "citations": response.get("citations") or [],
            "tool_result": response.get("tool_result"),
            "handoff": response.get("handoff"),
        }
        return response


class RouteDecisionHandoffPlugin(HumanHandoffPlugin):
    def __init__(self) -> None:
        super().__init__(
            PluginDescriptor(
                plugin_id="handoff.route",
                name="Route Decision Handoff Plugin",
                kind=PluginKind.HUMAN_HANDOFF,
                priority=300,
                capabilities=["handoff"],
            )
        )

    async def evaluate(self, context: PluginContext) -> HandoffDecision:
        if context.response.get("requires_handoff"):
            return HandoffDecision(
                should_handoff=True,
                reason=context.response.get("reason", ""),
                priority=300,
            )
        if context.route in {RouteType.HANDOFF.value, RouteType.RISK.value}:
            return HandoffDecision(
                should_handoff=True,
                reason=context.response.get("reason", ""),
                priority=280,
            )
        return HandoffDecision()


class ConfidenceHandoffPlugin(HumanHandoffPlugin):
    def __init__(self, runtime_config: RuntimeConfigService) -> None:
        super().__init__(
            PluginDescriptor(
                plugin_id="handoff.confidence",
                name="Confidence Handoff Plugin",
                kind=PluginKind.HUMAN_HANDOFF,
                priority=250,
                capabilities=["confidence_handoff"],
            )
        )
        self._runtime_config = runtime_config

    async def evaluate(self, context: PluginContext) -> HandoffDecision:
        threshold = self._runtime_config.get_policies().handoff_confidence_threshold
        confidence = float(context.response.get("confidence", 0.0))
        if confidence < threshold:
            return HandoffDecision(
                should_handoff=True,
                reason=zh("\\u4f4e\\u7f6e\\u4fe1\\u5ea6"),
                priority=250,
            )
        return HandoffDecision()


class DefaultSummaryHandoffPlugin(HumanHandoffPlugin):
    def __init__(self) -> None:
        super().__init__(
            PluginDescriptor(
                plugin_id="handoff.summary",
                name="Default Summary Handoff Plugin",
                kind=PluginKind.HUMAN_HANDOFF,
                priority=100,
                capabilities=["handoff_summary"],
            )
        )

    async def build_package(self, session: Session, reason: str) -> HandoffPackage | None:
        history = session.messages[-10:]
        user_messages = [message.content for message in history if message.role == MessageRole.USER]
        intent = (
            user_messages[-1] if user_messages else zh("\\u7528\\u6237\\u9700\\u8981\\u4eba\\u5de5")
        )
        summary = " | ".join(message.content for message in history[-6:])
        return HandoffPackage(
            tenant_id=session.tenant_id,
            session_id=session.session_id,
            reason=reason,
            summary=summary,
            intent=intent,
            recommended_reply=zh(
                "\\u4eba\\u5de5\\u5ba2\\u670d\\u53ef\\u5148\\u786e\\u8ba4\\u7528\\u6237\\u8bc9\\u6c42"
                "\\uff0c\\u518d\\u57fa\\u4e8e\\u5f53\\u524d\\u6458\\u8981\\u7ee7\\u7eed\\u5904\\u7406\\u3002"
            ),
            history=history,
        )


def build_builtin_plugins(
    runtime_config: RuntimeConfigService,
    adapter: BusinessAdapter,
) -> list[Plugin]:
    return [
        RiskRoutePlugin(runtime_config),
        HumanRequestRoutePlugin(runtime_config),
        BusinessIntentRoutePlugin(runtime_config),
        KnowledgeQuestionRoutePlugin(),
        FallbackRoutePlugin(),
        OrderStatusToolPlugin(adapter),
        AfterSaleStatusToolPlugin(adapter),
        LogisticsTrackingToolPlugin(adapter),
        AccountLookupToolPlugin(adapter),
        SubscriptionLookupToolPlugin(adapter),
        TicketLookupToolPlugin(adapter),
        CourseLookupToolPlugin(adapter),
        ProgressLookupToolPlugin(adapter),
        WaybillLookupToolPlugin(adapter),
        ClaimLookupToolPlugin(adapter),
        CRMProfileToolPlugin(adapter),
        ConfiguredIndustryAdapterPlugin(
            industry="ecommerce",
            keywords=["订单", "售后", "发货", "物流", "优惠券"],
            page_types=["product_detail", "order_detail", "after_sale_detail"],
            preferred_tools=["order_status", "after_sale_status", "logistics_tracking"],
        ),
        ConfiguredIndustryAdapterPlugin(
            industry="saas",
            keywords=["套餐", "订阅", "权限", "组织", "账单"],
            page_types=["billing", "organization", "permission"],
            preferred_tools=["account_lookup", "subscription_lookup", "ticket_lookup"],
        ),
        ConfiguredIndustryAdapterPlugin(
            industry="education",
            keywords=["课程", "班级", "学习", "考试", "证书"],
            page_types=["course_detail", "learning", "exam"],
            preferred_tools=["course_lookup", "progress_lookup"],
        ),
        ConfiguredIndustryAdapterPlugin(
            industry="logistics",
            keywords=["运单", "签收", "揽收", "赔付", "配送"],
            page_types=["tracking", "claim"],
            preferred_tools=["waybill_lookup", "claim_lookup", "logistics_tracking"],
        ),
        ConfiguredIndustryAdapterPlugin(
            industry="crm",
            keywords=["客户", "服务记录", "工单", "服务等级"],
            page_types=["customer_profile", "service_ticket"],
            preferred_tools=["crm_profile", "ticket_lookup", "account_lookup"],
        ),
        EcommerceIndustryPlugin(),
        SaaSIndustryPlugin(),
        EducationIndustryPlugin(),
        LogisticsIndustryPlugin(),
        CRMIndustryPlugin(),
        PageContextEnricherPlugin(),
        BusinessObjectEnricherPlugin(),
        UserProfileEnricherPlugin(),
        BehaviorSignalsEnricherPlugin(),
        SessionInsightsEnricherPlugin(),
        RouteDecisionHandoffPlugin(),
        ConfidenceHandoffPlugin(runtime_config),
        DefaultSummaryHandoffPlugin(),
        ReferenceAppendPostProcessorPlugin(),
        SensitiveMaskPostProcessorPlugin(),
        StructuredOutputPostProcessorPlugin(),
    ]


def route_result_to_decision(result: RoutePluginResult) -> RouteDecision:
    route = result.route or RouteType.FALLBACK.value
    return RouteDecision(
        route=RouteType(route),
        confidence=result.confidence,
        reason=result.reason,
        intent=result.intent or result.tool_name or route,
        confidence_band="high"
        if result.confidence >= 0.85
        else "medium"
        if result.confidence >= 0.55
        else "low",
        tool_name=result.tool_name,
        requires_handoff=result.requires_handoff,
        matched_signals=list(result.matched_signals),
    )


def context_to_plugin_context(
    *,
    tenant_id: str,
    channel: str,
    session_id: str | None = None,
    user_message: str | None = None,
    industry: str | None = None,
    integration_context: dict[str, Any] | None = None,
    host_auth_context: Any = None,
    business_context: BusinessContext | None = None,
    route: str | None = None,
    response: dict[str, Any] | None = None,
    extra: dict[str, Any] | None = None,
) -> PluginContext:
    return PluginContext(
        tenant_id=tenant_id,
        channel=channel,
        session_id=session_id,
        user_message=user_message,
        industry=industry,
        integration_context=integration_context or {},
        host_auth_context=host_auth_context,
        business_context=business_context,
        route=route,
        response=response or {},
        extra=extra or {},
    )


def merge_context_payload(target: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    result = dict(target)
    for key, value in payload.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = merge_context_payload(result[key], value)
        else:
            result[key] = value
    return result


def _lookup_context_alias(context: PluginContext, alias: str) -> Any:
    current: Any = context
    for segment in alias.split("."):
        if current is None:
            return None
        if hasattr(current, segment):
            current = getattr(current, segment)
            continue
        if isinstance(current, dict):
            current = current.get(segment)
            continue
        return None
    return current


def _scope_match(scopes: list[str], candidate: str | None) -> bool:
    if not scopes:
        return True
    if candidate is None:
        return False
    return candidate in scopes
