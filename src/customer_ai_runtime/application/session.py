from __future__ import annotations

from typing import Any

from customer_ai_runtime.core.errors import AppError
from customer_ai_runtime.domain.models import Message, MessageRole, Session, SessionState, utcnow
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
