from __future__ import annotations

from customer_ai_runtime.domain.models import BusinessResult, LLMRequest, MessageRole, RouteType
from customer_ai_runtime.domain.models import DiagnosticLevel
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
        llm_provider: LLMProvider,
        tool_service: ToolService,
        handoff_service: HandoffService,
        metrics: MetricsService,
        diagnostics: DiagnosticsService,
    ) -> None:
        self.session_service = session_service
        self.knowledge_service = knowledge_service
        self.routing_service = routing_service
        self.runtime_config = runtime_config
        self.llm_provider = llm_provider
        self.tool_service = tool_service
        self.handoff_service = handoff_service
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
    ) -> dict:
        session = self.session_service.get_or_create(tenant_id, session_id, channel)
        self.session_service.add_message(session, MessageRole.USER, message)
        route_decision = self.routing_service.decide(message)
        self.diagnostics.record(
            DiagnosticLevel.INFO,
            "chat.route_decided",
            "chat route decision completed",
            {
                "tenant_id": tenant_id,
                "session_id": session.session_id,
                "route": route_decision.route.value,
                "channel": channel,
            },
        )
        session.last_route = route_decision.route
        session.last_intent = route_decision.reason
        prompts = self.runtime_config.get_prompts()
        policies = self.runtime_config.get_policies()
        citations = []
        tool_result: BusinessResult | None = None

        if route_decision.route == RouteType.BUSINESS and route_decision.tool_name:
            parameters = self.routing_service.extract_tool_parameters(route_decision.tool_name, message)
            tool_result = await self.tool_service.execute(
                tenant_id=tenant_id,
                tool_name=route_decision.tool_name,
                parameters=parameters,
                integration_context=integration_context,
                session_id=session.session_id,
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
        elif route_decision.route == RouteType.KNOWLEDGE and knowledge_base_id:
            citations = await self.knowledge_service.retrieve(
                tenant_id=tenant_id,
                knowledge_base_id=knowledge_base_id,
                query=message,
                top_k=policies.knowledge_top_k,
            )
            citations = [citation for citation in citations if citation.score >= policies.knowledge_min_score]
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
            )
        )

        handoff_package = None
        if route_decision.requires_handoff or llm_response.confidence < policies.handoff_confidence_threshold:
            handoff_package = self.handoff_service.create_package(session, route_decision.reason)
            llm_response.answer = zh(
                "\\u5f53\\u524d\\u95ee\\u9898\\u5efa\\u8bae\\u7531\\u4eba\\u5de5\\u5ba2\\u670d"
                "\\u7ee7\\u7eed\\u5904\\u7406\\uff0c\\u6211\\u5df2\\u6574\\u7406\\u4e0a\\u4e0b"
                "\\u6587\\u5e76\\u53d1\\u8d77\\u8f6c\\u63a5\\u3002"
            )
            llm_response.confidence = max(llm_response.confidence, 0.92)
            self.metrics.increment("handoff_count")
            self.diagnostics.record(
                DiagnosticLevel.WARNING,
                "chat.handoff_required",
                "session routed to human handoff",
                {
                    "tenant_id": tenant_id,
                    "session_id": session.session_id,
                    "route": route_decision.route.value,
                },
            )

        self.session_service.add_message(
            session,
            MessageRole.ASSISTANT,
            llm_response.answer,
            metadata={"route": route_decision.route.value},
        )
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
                "confidence": llm_response.confidence,
            },
        )

        return {
            "session_id": session.session_id,
            "state": session.state.value,
            "route": route_decision.route.value,
            "confidence": round(llm_response.confidence, 4),
            "answer": llm_response.answer,
            "citations": [citation.model_dump(mode="json") for citation in llm_response.citations],
            "tool_result": None if tool_result is None else tool_result.model_dump(mode="json"),
            "handoff": None if handoff_package is None else handoff_package.model_dump(mode="json"),
        }
