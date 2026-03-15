from __future__ import annotations

from typing import Protocol

from customer_ai_runtime.domain.models import (
    DiagnosticEvent,
    KnowledgeBase,
    KnowledgeChunk,
    KnowledgeDocument,
    KnowledgeVersion,
    RTCRoom,
    Session,
)


class SessionRepository(Protocol):
    def save(self, session: Session) -> Session: ...

    def get(self, tenant_id: str, session_id: str) -> Session | None: ...

    def list_by_tenant(self, tenant_id: str) -> list[Session]: ...


class KnowledgeRepository(Protocol):
    def save_knowledge_base(self, knowledge_base: KnowledgeBase) -> KnowledgeBase: ...

    def get_knowledge_base(
        self, tenant_id: str, knowledge_base_id: str
    ) -> KnowledgeBase | None: ...

    def list_knowledge_bases(self, tenant_id: str) -> list[KnowledgeBase]: ...

    def save_version(self, version: KnowledgeVersion) -> KnowledgeVersion: ...

    def get_version(
        self, tenant_id: str, knowledge_base_id: str, version_id: str
    ) -> KnowledgeVersion | None: ...

    def list_versions(self, tenant_id: str, knowledge_base_id: str) -> list[KnowledgeVersion]: ...

    def save_document(self, document: KnowledgeDocument) -> KnowledgeDocument: ...

    def replace_documents(
        self,
        tenant_id: str,
        knowledge_base_id: str,
        documents: list[KnowledgeDocument],
        version_id: str | None = None,
    ) -> list[KnowledgeDocument]: ...

    def list_documents(
        self,
        tenant_id: str,
        knowledge_base_id: str,
        version_id: str | None = None,
    ) -> list[KnowledgeDocument]: ...

    def replace_chunks(
        self,
        tenant_id: str,
        knowledge_base_id: str,
        chunks: list[KnowledgeChunk],
        version_id: str | None = None,
    ) -> list[KnowledgeChunk]: ...

    def list_chunks(
        self,
        tenant_id: str,
        knowledge_base_id: str,
        version_id: str | None = None,
    ) -> list[KnowledgeChunk]: ...


class RTCRepository(Protocol):
    def save(self, room: RTCRoom) -> RTCRoom: ...

    def get(self, tenant_id: str, room_id: str) -> RTCRoom | None: ...

    def list_by_tenant(self, tenant_id: str) -> list[RTCRoom]: ...


class DiagnosticsRepository(Protocol):
    def add(self, event: DiagnosticEvent) -> None: ...

    def list_recent(self) -> list[DiagnosticEvent]: ...
