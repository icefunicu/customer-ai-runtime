from __future__ import annotations

import pytest

from customer_ai_runtime.application.business import BusinessContextBuilder, IndustryService
from customer_ai_runtime.application.plugins import PluginRegistry, build_builtin_plugins
from customer_ai_runtime.application.routing import RoutingService
from customer_ai_runtime.application.runtime import RuntimeConfigService
from customer_ai_runtime.domain.models import IntentFrame, RouteType, Session
from customer_ai_runtime.providers.local import LocalBusinessAdapter


def build_services() -> tuple[RuntimeConfigService, BusinessContextBuilder, RoutingService]:
    runtime_config = RuntimeConfigService()
    registry = PluginRegistry()
    adapter = LocalBusinessAdapter()
    for plugin in build_builtin_plugins(runtime_config, adapter):
        registry.register(plugin)
    industry_service = IndustryService(registry)
    builder = BusinessContextBuilder(registry, industry_service)
    routing = RoutingService(registry, runtime_config)
    return runtime_config, builder, routing


@pytest.mark.anyio
async def test_route_uses_page_context_for_ambiguous_followup() -> None:
    _, builder, routing = build_services()
    context = await builder.build(
        tenant_id="demo-tenant",
        channel="web",
        session=None,
        integration_context={
            "industry": "ecommerce",
            "page_context": {"page_type": "order_detail"},
            "business_objects": {"order_id": "ORD-1001"},
        },
        user_message="这个现在到哪了",
    )

    decision = await routing.decide("这个现在到哪了", context)

    assert decision.route == RouteType.BUSINESS
    assert decision.tool_name == "order_status"
    assert "context:page_tool_inference" in decision.matched_signals


@pytest.mark.anyio
async def test_route_can_resume_previous_intent_from_intent_stack() -> None:
    _, builder, routing = build_services()
    session = Session(
        tenant_id="demo-tenant",
        channel="web",
        intent_stack=[
            IntentFrame(
                intent="order_status",
                route=RouteType.BUSINESS,
                tool_name="order_status",
                confidence=0.92,
                confidence_band="high",
                context_snapshot={"business_objects": {"order_id": "ORD-1001"}},
                last_user_message="我的订单什么时候发货",
            ),
            IntentFrame(
                intent="knowledge_question",
                route=RouteType.KNOWLEDGE,
                confidence=0.79,
                confidence_band="medium",
                last_user_message="退款规则是什么",
            ),
        ],
    )
    context = await builder.build(
        tenant_id="demo-tenant",
        channel="web",
        session=session,
        integration_context={},
        user_message="还是回到刚才的问题",
    )

    decision = await routing.decide("还是回到刚才的问题", context)
    hydrated = routing.apply_context_snapshot(context, decision)

    assert decision.route == RouteType.BUSINESS
    assert decision.tool_name == "order_status"
    assert "intent_stack:return_previous" in decision.matched_signals
    assert hydrated.business_objects["order_id"] == "ORD-1001"


@pytest.mark.anyio
async def test_route_escalates_after_repeated_low_confidence() -> None:
    _, builder, routing = build_services()
    session = Session(
        tenant_id="demo-tenant",
        channel="web",
        intent_stack=[
            IntentFrame(
                intent="fallback_clarification",
                route=RouteType.FALLBACK,
                confidence=0.34,
                confidence_band="low",
                low_confidence_count=1,
                last_user_message="这个怎么处理",
            )
        ],
    )
    context = await builder.build(
        tenant_id="demo-tenant",
        channel="web",
        session=session,
        integration_context={},
        user_message="还是那个",
    )

    decision = await routing.decide("还是那个", context)

    assert decision.route == RouteType.HANDOFF
    assert decision.requires_handoff is True
    assert "threshold:route_handoff" in decision.matched_signals
