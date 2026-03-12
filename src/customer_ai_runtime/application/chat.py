from __future__ import annotations

from time import perf_counter

from customer_ai_runtime.application.business import (
    BusinessContextBuilder,
    KnowledgeDomainManager,
    ResponseEnhancementOrchestrator,
)
from customer_ai_runtime.domain.models import BusinessResult, DiagnosticLevel, LLMRequest, MessageRole, RouteType
from customer_ai_runtime.domain.platform import HostAuthContext
from customer_ai_runtime.providers.base import LLMProvider

from customer_ai_runtime.application.handoff import HandoffService
from customer_ai_runtime.application.knowledge import KnowledgeService
from customer_ai_runtime.application.routing import RoutingService
from customer_ai_runtime.application.runtime import DiagnosticsService, MetricsService, RuntimeConfigService, zh
from customer_ai_runtime.application.session import SessionService
from customer_ai_runtime.application.tooling import ToolService


class ChatService:
    def __init__(
        self,
        session_service: SessionService,
        knowledge_service: KnowledgeService,
        routing_service: RoutingService,
        runtime_config: RuntimeConfigService,
        business_context_builder: BusinessContextBuilder,
        knowledge_domain_manager: KnowledgeDomainManager,
        llm_provider: LLMProvider,
        tool_service: ToolService,
        handoff_service: HandoffService,
        response_enhancer: ResponseEnhancementOrchestrator,
        metrics: MetricsService,
        diagnostics: DiagnosticsService,
    ) -> None:
        self.session_service = session_service
        self.knowledge_service = knowledge_service
        self.routing_service = routing_service
        self.runtime_config = runtime_config
        self.business_context_builder = business_context_builder
        self.knowledge_domain_manager = knowledge_domain_manager
        self.llm_provider = llm_provider
        self.tool_service = tool_service
        self.handoff_service = handoff_service
        self.response_enhancer = response_enhancer
        self.metrics = metrics
        self.diagnostics = diagnostics

    async def process_message(
        self,
        tenant_id: str,
        session_id: str | None,
        channel: str,
        message: str,
        knowledge_base_id: str | None,
        integration_context: dict | None = None,
        host_auth_context: HostAuthContext | None = None,
        track_response_timing: bool = True,
    ) -> dict:
        started_at = perf_counter() if track_response_timing else None
        session = self.session_service.get_or_create(tenant_id, session_id, channel)
        self.session_service.add_message(session, MessageRole.USER, message)
        business_context = await self.business_context_builder.build(
            tenant_id=tenant_id,
            channel=channel,
            session=session,
            integration_context=integration_context,
            host_auth_context=host_auth_context,
            user_message=message,
        )
        route_decision = await self.routing_service.decide(message, business_context)
        business_context = self.routing_service.apply_context_snapshot(business_context, route_decision)
        self.diagnostics.record(
            DiagnosticLevel.INFO,
            "chat.route_decided",
            "chat route decision completed",
            {
                "tenant_id": tenant_id,
                "session_id": session.session_id,
                "route": route_decision.route.value,
                "intent": route_decision.intent,
                "route_confidence": route_decision.confidence,
                "confidence_band": route_decision.confidence_band,
                "channel": channel,
                "industry": business_context.industry,
            },
        )
        self.session_service.record_route_decision(
            session,
            route_decision,
            message,
            max_depth=self.runtime_config.get_policies().intent_stack_max_depth,
        )
        prompts = self.runtime_config.get_prompts()
        policies = self.runtime_config.get_policies()
        citations = []
        tool_result: BusinessResult | None = None

        if route_decision.route == RouteType.BUSINESS and route_decision.tool_name:
            parameters = self.routing_service.extract_tool_parameters(route_decision.tool_name, message)
            tool_result = await self.tool_service.execute(
                business_context=business_context,
                tool_name=route_decision.tool_name,
                parameters=parameters,
            )
            self.diagnostics.record(
                DiagnosticLevel.INFO,
                "chat.tool_executed",
                "business tool executed",
                {
                    "tenant_id": tenant_id,
                    "session_id": session.session_id,
                    "tool_name": route_decision.tool_name,
                    "status": tool_result.status,
                },
            )
        elif route_decision.route == RouteType.KNOWLEDGE:
            knowledge_base_id = self.knowledge_domain_manager.resolve_primary(
                tenant_id=tenant_id,
                industry=business_context.industry,
                explicit=knowledge_base_id,
            )
            if knowledge_base_id:
                citations = await self.knowledge_service.retrieve(
                    tenant_id=tenant_id,
                    knowledge_base_id=knowledge_base_id,
                    query=message,
                    top_k=policies.knowledge_top_k,
                )
                filtered_citations = [
                    citation for citation in citations if citation.score >= policies.knowledge_min_score
                ]
                if not filtered_citations:
                    top_score = None if not citations else round(citations[0].score, 4)
                    self.diagnostics.record(
                        DiagnosticLevel.WARNING,
                        "knowledge.retrieve_miss",
                        "knowledge retrieval missed effective citations",
                        {
                            "tenant_id": tenant_id,
                            "session_id": session.session_id,
                            "channel": channel,
                            "knowledge_base_id": knowledge_base_id,
                            "query": message,
                            "top_score": top_score,
                        },
                    )
                citations = filtered_citations or citations[:1]
                self.diagnostics.record(
                    DiagnosticLevel.INFO,
                    "chat.knowledge_retrieved",
                    "knowledge retrieval completed",
                    {
                        "tenant_id": tenant_id,
                        "session_id": session.session_id,
                        "knowledge_base_id": knowledge_base_id,
                        "hit_count": len(citations),
                    },
                )

        prompt_template = prompts.fallback_answer
        if route_decision.route == RouteType.KNOWLEDGE:
            prompt_template = prompts.knowledge_answer
        elif route_decision.route == RouteType.BUSINESS:
            prompt_template = prompts.business_answer

        llm_response = await self.llm_provider.generate(
            LLMRequest(
                tenant_id=tenant_id,
                session_id=session.session_id,
                route=route_decision.route,
                user_message=message,
                history=session.messages,
                citations=citations,
                tool_result=tool_result,
                prompt_template=prompt_template,
                business_context=business_context.model_dump(mode="json"),
            )
        )

        response_payload = {
            "session_id": session.session_id,
            "state": session.state.value,
            "route": route_decision.route.value,
            "confidence": round(llm_response.confidence, 4),
            "route_confidence": round(route_decision.confidence, 4),
            "route_confidence_band": route_decision.confidence_band,
            "intent": route_decision.intent,
            "answer": llm_response.answer,
            "citations": [citation.model_dump(mode="json") for citation in llm_response.citations],
            "tool_result": None if tool_result is None else tool_result.model_dump(mode="json"),
            "handoff": None,
            "industry": business_context.industry,
            "host_auth_context": None
            if host_auth_context is None
            else host_auth_context.model_dump(mode="json"),
            "requires_handoff": route_decision.requires_handoff,
            "reason": route_decision.reason,
            "route_decision": {
                "route": route_decision.route.value,
                "confidence": round(route_decision.confidence, 4),
                "confidence_band": route_decision.confidence_band,
                "intent": route_decision.intent,
                "tool_name": route_decision.tool_name,
                "reason": route_decision.reason,
                "matched_signals": list(route_decision.matched_signals),
            },
        }

        should_handoff, handoff_reason = await self.handoff_service.should_handoff(
            business_context=business_context,
            route=route_decision.route.value,
            response=response_payload,
        )
        if should_handoff:
            handoff_package = await self.handoff_service.create_package(
                session,
                handoff_reason or route_decision.reason,
                business_context,
            )
            response_payload["handoff"] = (
                None if handoff_package is None else handoff_package.model_dump(mode="json")
            )
            response_payload["answer"] = zh(
                "\\u5f53\\u524d\\u95ee\\u9898\\u5efa\\u8bae\\u7531\\u4eba\\u5de5\\u5ba2\\u670d"
                "\\u7ee7\\u7eed\\u5904\\u7406\\uff0c\\u6211\\u5df2\\u6574\\u7406\\u4e0a\\u4e0b"
                "\\u6587\\u5e76\\u53d1\\u8d77\\u8f6c\\u63a5\\u3002"
            )
            response_payload["confidence"] = max(response_payload["confidence"], 0.92)
            response_payload["state"] = session.state.value
            self.metrics.increment("handoff_count")
            self.diagnostics.record(
                DiagnosticLevel.WARNING,
                "chat.handoff_required",
                "session routed to human handoff",
                {
                    "tenant_id": tenant_id,
                    "session_id": session.session_id,
                    "route": route_decision.route.value,
                    "reason": handoff_reason,
                },
            )

        response_payload = await self.response_enhancer.enhance(response_payload, business_context)
        self.session_service.add_message(
            session,
            MessageRole.ASSISTANT,
            response_payload["answer"],
            metadata={
                "route": route_decision.route.value,
                "industry": business_context.industry,
                "intent": route_decision.intent,
                "route_confidence_band": route_decision.confidence_band,
            },
        )
        if started_at is not None:
            duration_ms = max(1, int((perf_counter() - started_at) * 1000))
            self.session_service.record_response_timing(session, duration_ms)
        self.session_service.save(session)
        self.metrics.increment("chat_requests")
        self.metrics.increment(f"route_{route_decision.route.value}")
        self.diagnostics.record(
            DiagnosticLevel.INFO,
            "chat.completed",
            "chat request completed",
            {
                "tenant_id": tenant_id,
                "session_id": session.session_id,
                "route": route_decision.route.value,
                "confidence": response_payload["confidence"],
                "industry": business_context.industry,
            },
        )
        response_payload.pop("requires_handoff", None)
        response_payload.pop("reason", None)
        return response_payload
