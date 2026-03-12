from __future__ import annotations

import pytest

from customer_ai_runtime.application.business import (
    BusinessContextBuilder,
    IndustryService,
    RealTimeBusinessDataProvider,
)
from customer_ai_runtime.application.plugins import PluginRegistry, build_builtin_plugins
from customer_ai_runtime.application.runtime import RuntimeConfigService
from customer_ai_runtime.application.tool_catalog import ToolCatalogService
from customer_ai_runtime.application.tooling import ToolService
from customer_ai_runtime.domain.models import Session
from customer_ai_runtime.providers.local import LocalBusinessAdapter


def build_registry() -> tuple[RuntimeConfigService, LocalBusinessAdapter, PluginRegistry]:
    runtime_config = RuntimeConfigService()
    adapter = LocalBusinessAdapter()
    registry = PluginRegistry()
    for plugin in build_builtin_plugins(runtime_config, adapter):
        registry.register(plugin)
    return runtime_config, adapter, registry


def test_builtin_plugins_register_concrete_implementations() -> None:
    _, _, registry = build_registry()

    assert registry.get("tool.order_status").__class__.__name__ == "OrderStatusToolPlugin"
    assert registry.get("industry.ecommerce").__class__.__name__ == "EcommerceIndustryPlugin"
    assert registry.get("industry.saas").__class__.__name__ == "SaaSIndustryPlugin"
    assert (
        registry.get("context.behavior_signals").__class__.__name__
        == "BehaviorSignalsEnricherPlugin"
    )
    assert (
        registry.get("context.session_insights").__class__.__name__
        == "SessionInsightsEnricherPlugin"
    )


@pytest.mark.anyio
async def test_business_context_builder_enriches_industry_and_context() -> None:
    _, _, registry = build_registry()
    industry_service = IndustryService(registry)
    builder = BusinessContextBuilder(registry, industry_service)
    session = Session(tenant_id="demo-tenant", channel="web", summary="用户已两次催发货")

    context = await builder.build(
        tenant_id="demo-tenant",
        channel="web",
        session=session,
        integration_context={
            "page_context": {"page_type": "order_detail"},
            "business_objects": {"order_id": "ORD-1001"},
            "behavior_signals": {"repeat_contact_7d": 2, "frustrated": True},
        },
        user_message="我的订单什么时候发货",
    )

    assert context.industry == "ecommerce"
    assert context.business_objects["order_id"] == "ORD-1001"
    assert context.behavior_signals == {"repeat_contact_7d": 2, "frustrated": True}
    assert context.extra["preferred_tools"] == [
        "order_status",
        "after_sale_status",
        "logistics_tracking",
    ]
    assert context.extra["session_insights"] == {
        "has_summary": True,
        "summary": "用户已两次催发货",
        "permissions": [],
        "channel": "web",
    }


@pytest.mark.anyio
async def test_tool_service_resolves_parameters_from_context() -> None:
    _, adapter, registry = build_registry()
    industry_service = IndustryService(registry)
    builder = BusinessContextBuilder(registry, industry_service)
    tool_service = ToolService(
        RealTimeBusinessDataProvider(registry, adapter),
        ToolCatalogService(registry),
    )

    context = await builder.build(
        tenant_id="demo-tenant",
        channel="web",
        session=None,
        integration_context={
            "industry": "ecommerce",
            "business_objects": {"order_id": "ORD-1001"},
        },
        user_message="帮我查下订单",
    )

    result = await tool_service.execute(
        business_context=context,
        tool_name="order_status",
        parameters={},
    )

    assert result.status == "success"
    assert result.data["tracking_no"] == "YT-2001"
