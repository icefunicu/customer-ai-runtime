from __future__ import annotations

import re
from typing import Any

from customer_ai_runtime.application.plugins import (
    PluginRegistry,
    RouteStrategyPlugin,
    context_to_plugin_context,
    route_result_to_decision,
)
from customer_ai_runtime.application.runtime import RuntimeConfigService, zh
from customer_ai_runtime.domain.models import IntentFrame, RouteDecision, RouteType
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
    page_tool_map = {
        "order_detail": "order_status",
        "after_sale_detail": "after_sale_status",
        "tracking": "logistics_tracking",
        "billing": "subscription_lookup",
        "organization": "account_lookup",
        "permission": "account_lookup",
        "service_ticket": "ticket_lookup",
        "course_detail": "course_lookup",
        "learning": "progress_lookup",
        "claim": "claim_lookup",
        "customer_profile": "crm_profile",
    }
    tool_context_keys = {
        "order_status": ("order_id",),
        "after_sale_status": ("after_sale_id",),
        "logistics_tracking": ("tracking_no", "carrier_code"),
        "account_lookup": ("account_id",),
        "subscription_lookup": ("subscription_id",),
        "ticket_lookup": ("ticket_id",),
        "course_lookup": ("course_id",),
        "progress_lookup": ("student_id", "course_id"),
        "waybill_lookup": ("waybill_id",),
        "claim_lookup": ("claim_id",),
        "crm_profile": ("customer_id",),
    }
    contextual_keywords = {
        "order_status": ("状态", "发货", "到了", "到哪", "什么时候到", "物流", "这单", "这个订单"),
        "after_sale_status": ("退款", "退货", "售后", "进度", "处理到哪"),
        "logistics_tracking": ("物流", "快递", "配送", "到哪", "签收"),
        "account_lookup": ("账号", "账户", "权限", "会员", "积分"),
        "subscription_lookup": ("订阅", "套餐", "账单", "续费"),
        "ticket_lookup": ("工单", "服务单", "ticket", "处理到哪"),
        "course_lookup": ("课程", "班级", "考试", "证书", "有效期"),
        "progress_lookup": ("进度", "课时", "学到哪", "完成度"),
        "waybill_lookup": ("运单", "揽收", "签收", "派送"),
        "claim_lookup": ("理赔", "赔付", "异常件", "审核"),
        "crm_profile": ("客户", "等级", "跟进", "档案"),
    }
    referential_keywords = ("这个", "这个订单", "这单", "它", "刚才那个", "那个问题", "还是那个")

    def __init__(
        self,
        registry: PluginRegistry,
        runtime_config: RuntimeConfigService,
    ) -> None:
        self._registry = registry
        self._runtime_config = runtime_config

    async def decide(self, message: str, business_context: BusinessContext) -> RouteDecision:
        policies = self._runtime_config.get_policies()
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
        candidates: list[tuple[RouteDecision, int]] = []
        contextual_candidate = self._build_contextual_candidate(
            message=message,
            business_context=business_context,
            return_keywords=policies.intent_return_keywords,
        )
        if contextual_candidate is not None:
            candidates.append((contextual_candidate, 875))
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
                decision = route_result_to_decision(result)
                decision = self._apply_contextual_signals(
                    decision=decision,
                    message=message,
                    business_context=business_context,
                )
                candidates.append((decision, plugin.descriptor.priority))
        if not candidates:
            candidates.append(
                (
                    RouteDecision(
                        route=RouteType.FALLBACK,
                        confidence=0.3,
                        reason="fallback",
                        intent="fallback_clarification",
                        confidence_band="low",
                        matched_signals=["fallback:no_candidate"],
                        context_snapshot=self._context_snapshot(business_context),
                    ),
                    0,
                )
            )
        best, _ = max(candidates, key=lambda item: (item[0].confidence, item[1]))
        return self._apply_confidence_strategy(best, business_context)

    def apply_context_snapshot(
        self,
        business_context: BusinessContext,
        route_decision: RouteDecision,
    ) -> BusinessContext:
        snapshot = route_decision.context_snapshot
        if not snapshot:
            return business_context
        if snapshot.get("page_context") and not business_context.page_context:
            business_context.page_context = dict(snapshot["page_context"])
            business_context.integration_context["page_context"] = dict(snapshot["page_context"])
        if snapshot.get("business_objects"):
            merged_objects = dict(snapshot["business_objects"])
            merged_objects.update(business_context.business_objects)
            business_context.business_objects = merged_objects
            integration_objects = dict(snapshot["business_objects"])
            integration_objects.update(
                business_context.integration_context.get("business_objects") or {}
            )
            business_context.integration_context["business_objects"] = integration_objects
        return business_context

    def _build_contextual_candidate(
        self,
        *,
        message: str,
        business_context: BusinessContext,
        return_keywords: list[str],
    ) -> RouteDecision | None:
        intent_stack = business_context.intent_stack
        active_intent = self._active_intent(intent_stack)
        current_snapshot = self._context_snapshot(business_context)
        normalized_message = message.strip()

        if normalized_message and any(keyword in normalized_message for keyword in return_keywords):
            previous_intent = self._previous_intent(intent_stack)
            if previous_intent is not None:
                snapshot = self._merge_snapshot(previous_intent.context_snapshot, current_snapshot)
                return RouteDecision(
                    route=previous_intent.route,
                    confidence=self._clamp_confidence(max(previous_intent.confidence, 0.84)),
                    reason=zh("\\u547d\\u4e2d\\u5386\\u53f2\\u610f\\u56fe\\u56de\\u9000"),
                    intent=previous_intent.intent,
                    confidence_band="high",
                    tool_name=previous_intent.tool_name,
                    matched_signals=["intent_stack:return_previous"],
                    context_snapshot=snapshot,
                )

        if (
            active_intent is not None
            and active_intent.route == RouteType.BUSINESS
            and active_intent.tool_name
            and self._is_contextual_followup(normalized_message)
        ):
            snapshot = self._merge_snapshot(active_intent.context_snapshot, current_snapshot)
            if self._context_supports_tool(active_intent.tool_name, snapshot):
                return RouteDecision(
                    route=RouteType.BUSINESS,
                    confidence=self._clamp_confidence(max(active_intent.confidence, 0.8)),
                    reason=zh("\\u5ef6\\u7eed\\u5f53\\u524d\\u4e1a\\u52a1\\u610f\\u56fe"),
                    intent=active_intent.intent,
                    confidence_band="medium",
                    tool_name=active_intent.tool_name,
                    matched_signals=["intent_stack:continue_active"],
                    context_snapshot=snapshot,
                )

        inferred_tool = self._infer_tool_from_context(
            normalized_message, business_context, active_intent
        )
        if inferred_tool is None:
            return None
        snapshot = self._merge_snapshot(
            {} if active_intent is None else active_intent.context_snapshot,
            current_snapshot,
        )
        confidence = 0.78 if self._context_supports_tool(inferred_tool, snapshot) else 0.62
        signals = ["context:page_tool_inference"]
        if current_snapshot.get("business_objects"):
            signals.append("context:business_object")
        return RouteDecision(
            route=RouteType.BUSINESS,
            confidence=self._clamp_confidence(confidence),
            reason=zh(
                "\\u547d\\u4e2d\\u9875\\u9762\\u573a\\u666f\\u4e0e\\u4e1a\\u52a1\\u5bf9\\u8c61"
            ),
            intent=inferred_tool,
            confidence_band="medium",
            tool_name=inferred_tool,
            matched_signals=signals,
            context_snapshot=snapshot,
        )

    def _apply_contextual_signals(
        self,
        *,
        decision: RouteDecision,
        message: str,
        business_context: BusinessContext,
    ) -> RouteDecision:
        snapshot = self._context_snapshot(business_context)
        active_intent = self._active_intent(business_context.intent_stack)
        signals = list(decision.matched_signals)

        if decision.route == RouteType.BUSINESS:
            if (
                active_intent
                and active_intent.tool_name == decision.tool_name
                and self._is_contextual_followup(message)
            ):
                decision.confidence = self._clamp_confidence(decision.confidence + 0.05)
                signals.append("intent_stack:active_match")
                snapshot = self._merge_snapshot(active_intent.context_snapshot, snapshot)
            if decision.tool_name and self._context_supports_tool(decision.tool_name, snapshot):
                decision.confidence = self._clamp_confidence(decision.confidence + 0.08)
                signals.append("context:business_object")
            if decision.tool_name and self._page_matches_tool(
                decision.tool_name, business_context.page_context
            ):
                decision.confidence = self._clamp_confidence(decision.confidence + 0.06)
                signals.append("context:page_context")
            decision.context_snapshot = snapshot
        elif (
            decision.route == RouteType.KNOWLEDGE
            and active_intent is not None
            and active_intent.route == RouteType.BUSINESS
            and self._is_contextual_followup(message)
        ):
            decision.confidence = self._clamp_confidence(decision.confidence - 0.12)
            signals.append("context:business_followup_penalty")
            decision.context_snapshot = self._merge_snapshot(
                active_intent.context_snapshot, snapshot
            )
        else:
            decision.context_snapshot = snapshot

        decision.matched_signals = signals
        return decision

    def _apply_confidence_strategy(
        self,
        decision: RouteDecision,
        business_context: BusinessContext,
    ) -> RouteDecision:
        policies = self._runtime_config.get_policies()
        if decision.route in {RouteType.HANDOFF, RouteType.RISK}:
            decision.confidence_band = "high"
            decision.context_snapshot = decision.context_snapshot or self._context_snapshot(
                business_context
            )
            return decision

        decision.confidence_band = self._confidence_band(
            decision.confidence,
            policies.route_fallback_confidence_threshold,
        )
        if decision.confidence >= policies.route_fallback_confidence_threshold:
            decision.context_snapshot = decision.context_snapshot or self._context_snapshot(
                business_context
            )
            return decision

        signals = list(decision.matched_signals)
        signals.append("threshold:route_fallback")
        if (
            decision.confidence < policies.route_handoff_confidence_threshold
            or self._should_escalate_low_confidence(business_context)
        ):
            return RouteDecision(
                route=RouteType.HANDOFF,
                confidence=decision.confidence,
                reason=zh(
                    "\\u610f\\u56fe\\u7f6e\\u4fe1\\u5ea6\\u8fc7\\u4f4e\\uff0c\\u5efa\\u8bae\\u8f6c\\u4eba\\u5de5"
                ),
                intent="low_confidence_handoff",
                confidence_band="low",
                requires_handoff=True,
                matched_signals=signals + ["threshold:route_handoff"],
                context_snapshot=decision.context_snapshot
                or self._context_snapshot(business_context),
            )
        return RouteDecision(
            route=RouteType.FALLBACK,
            confidence=decision.confidence,
            reason=zh(
                "\\u610f\\u56fe\\u7f6e\\u4fe1\\u5ea6\\u4e0d\\u8db3\\uff0c\\u5148\\u8fdb\\u5165\\u6f84\\u6e05\\u515c\\u5e95"
            ),
            intent="fallback_clarification",
            confidence_band="low",
            matched_signals=signals,
            context_snapshot=decision.context_snapshot or self._context_snapshot(business_context),
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

    def _context_snapshot(self, business_context: BusinessContext) -> dict[str, Any]:
        snapshot: dict[str, Any] = {}
        if business_context.page_context:
            snapshot["page_context"] = dict(business_context.page_context)
        if business_context.business_objects:
            snapshot["business_objects"] = dict(business_context.business_objects)
        return snapshot

    def _merge_snapshot(self, base: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
        merged = {
            "page_context": dict(base.get("page_context") or {}),
            "business_objects": dict(base.get("business_objects") or {}),
        }
        merged["page_context"].update(incoming.get("page_context") or {})
        merged["business_objects"].update(incoming.get("business_objects") or {})
        return {key: value for key, value in merged.items() if value}

    def _active_intent(self, intent_stack: list[IntentFrame]) -> IntentFrame | None:
        return intent_stack[-1] if intent_stack else None

    def _previous_intent(self, intent_stack: list[IntentFrame]) -> IntentFrame | None:
        return intent_stack[-2] if len(intent_stack) >= 2 else None

    def _infer_tool_from_context(
        self,
        message: str,
        business_context: BusinessContext,
        active_intent: IntentFrame | None,
    ) -> str | None:
        page_type = str((business_context.page_context or {}).get("page_type") or "")
        inferred_tool = self.page_tool_map.get(page_type)
        if inferred_tool and self._message_matches_tool(message, inferred_tool):
            return inferred_tool
        if active_intent and active_intent.tool_name and self._is_contextual_followup(message):
            return active_intent.tool_name
        return None

    def _message_matches_tool(self, message: str, tool_name: str) -> bool:
        normalized = message.strip()
        if not normalized:
            return False
        keywords = self.contextual_keywords.get(tool_name, ())
        return any(keyword in normalized for keyword in keywords)

    def _page_matches_tool(self, tool_name: str, page_context: dict[str, Any]) -> bool:
        page_type = str((page_context or {}).get("page_type") or "")
        return self.page_tool_map.get(page_type) == tool_name

    def _context_supports_tool(self, tool_name: str, snapshot: dict[str, Any]) -> bool:
        objects = snapshot.get("business_objects") or {}
        return any(objects.get(key) for key in self.tool_context_keys.get(tool_name, ()))

    def _is_contextual_followup(self, message: str) -> bool:
        normalized = message.strip()
        if not normalized:
            return False
        return (
            len(normalized) <= 12
            or any(keyword in normalized for keyword in self.referential_keywords)
            or normalized in {"还是刚才那个", "继续查一下", "继续看看"}
        )

    def _should_escalate_low_confidence(self, business_context: BusinessContext) -> bool:
        signals = business_context.behavior_signals or {}
        if bool(signals.get("frustrated")):
            return True
        if int(signals.get("repeat_contact_7d") or 0) >= 2:
            return True
        active_intent = self._active_intent(business_context.intent_stack)
        if active_intent and active_intent.low_confidence_count >= 1:
            return True
        return False

    def _confidence_band(self, confidence: float, fallback_threshold: float) -> str:
        if confidence >= 0.85:
            return "high"
        if confidence >= fallback_threshold:
            return "medium"
        return "low"

    def _clamp_confidence(self, confidence: float) -> float:
        return max(0.0, min(0.99, round(confidence, 4)))
