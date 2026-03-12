from __future__ import annotations

from typing import Any

from customer_ai_runtime.core.errors import AppError
from customer_ai_runtime.domain.models import (
    IntentFrame,
    Message,
    MessageRole,
    RouteDecision,
    Session,
    SessionState,
    utcnow,
)
from customer_ai_runtime.repositories.memory import InMemorySessionRepository

from customer_ai_runtime.application.runtime import DiagnosticsService, zh


class SessionService:
    def __init__(
        self,
        repository: InMemorySessionRepository,
        diagnostics: DiagnosticsService,
    ) -> None:
        self._repository = repository
        self._diagnostics = diagnostics

    def get_or_create(self, tenant_id: str, session_id: str | None, channel: str) -> Session:
        if session_id:
            session = self._repository.get(tenant_id, session_id)
            if not session:
                raise AppError(
                    code="not_found",
                    message=zh("\\u4f1a\\u8bdd\\u4e0d\\u5b58\\u5728"),
                    status_code=404,
                )
            return session
        session = Session(tenant_id=tenant_id, channel=channel)
        self._repository.save(session)
        return session

    def save(self, session: Session) -> Session:
        session.updated_at = utcnow()
        return self._repository.save(session)

    def add_message(
        self,
        session: Session,
        role: MessageRole,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> Session:
        session.messages.append(Message(role=role, content=content, metadata=metadata or {}))
        session.updated_at = utcnow()
        if len(session.messages) > 20:
            session.summary = " | ".join(message.content for message in session.messages[-6:])
        self._repository.save(session)
        return session

    def record_route_decision(
        self,
        session: Session,
        route_decision: RouteDecision,
        user_message: str,
        *,
        max_depth: int = 6,
    ) -> Session:
        session.last_route = route_decision.route
        session.last_intent = route_decision.intent or route_decision.reason
        low_confidence_count = 1 if route_decision.confidence_band == "low" else 0
        frame = IntentFrame(
            intent=route_decision.intent or route_decision.route.value,
            route=route_decision.route,
            tool_name=route_decision.tool_name,
            confidence=route_decision.confidence,
            confidence_band=route_decision.confidence_band,
            low_confidence_count=low_confidence_count,
            matched_signals=list(route_decision.matched_signals),
            context_snapshot=dict(route_decision.context_snapshot),
            last_user_message=user_message,
        )

        if session.intent_stack:
            top = session.intent_stack[-1]
            if self._is_same_intent(top, frame):
                frame.created_at = top.created_at
                frame.low_confidence_count = (
                    top.low_confidence_count + 1
                    if route_decision.confidence_band == "low"
                    else 0
                )
                session.intent_stack[-1] = frame
            elif len(session.intent_stack) >= 2 and self._is_same_intent(session.intent_stack[-2], frame):
                previous = session.intent_stack[-2]
                frame.low_confidence_count = (
                    previous.low_confidence_count + 1
                    if route_decision.confidence_band == "low"
                    else 0
                )
                session.intent_stack.append(frame)
            else:
                session.intent_stack.append(frame)
        else:
            session.intent_stack.append(frame)

        session.intent_stack = session.intent_stack[-max_depth:]
        session.updated_at = utcnow()
        self._repository.save(session)
        return session

    def get(self, tenant_id: str, session_id: str) -> Session:
        session = self._repository.get(tenant_id, session_id)
        if not session:
            raise AppError(
                code="not_found",
                message=zh("\\u4f1a\\u8bdd\\u4e0d\\u5b58\\u5728"),
                status_code=404,
            )
        return session

    def list_by_tenant(self, tenant_id: str) -> list[Session]:
        return self._repository.list_by_tenant(tenant_id)

    def claim_human(self, tenant_id: str, session_id: str) -> Session:
        session = self.get(tenant_id, session_id)
        session.state = SessionState.HUMAN_IN_SERVICE
        session.waiting_human = False
        return self.save(session)

    def close_session(self, tenant_id: str, session_id: str) -> Session:
        session = self.get(tenant_id, session_id)
        session.state = SessionState.CLOSED
        session.waiting_human = False
        return self.save(session)

    def add_human_reply(self, tenant_id: str, session_id: str, content: str) -> Session:
        session = self.get(tenant_id, session_id)
        session.state = SessionState.HUMAN_IN_SERVICE
        session.waiting_human = False
        self.add_message(session, MessageRole.HUMAN, content)
        return self.save(session)

    def _is_same_intent(self, current: IntentFrame, incoming: IntentFrame) -> bool:
        return (
            current.intent == incoming.intent
            and current.route == incoming.route
            and current.tool_name == incoming.tool_name
        )
