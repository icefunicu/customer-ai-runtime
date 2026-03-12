from __future__ import annotations

import json
from collections import deque
from copy import deepcopy
from pathlib import Path

from customer_ai_runtime.domain.models import (
    DiagnosticEvent,
    KnowledgeBase,
    KnowledgeChunk,
    KnowledgeDocument,
    RTCRoom,
    Session,
)


class InMemorySessionRepository:
    def __init__(self, storage_root: str | Path | None = None) -> None:
        self._sessions: dict[tuple[str, str], Session] = {}
        self._storage_path = _state_file(storage_root, "sessions.json")
        self._load()

    def save(self, session: Session) -> Session:
        self._sessions[(session.tenant_id, session.session_id)] = deepcopy(session)
        self._flush()
        return deepcopy(session)

    def get(self, tenant_id: str, session_id: str) -> Session | None:
        session = self._sessions.get((tenant_id, session_id))
        return deepcopy(session) if session else None

    def list_by_tenant(self, tenant_id: str) -> list[Session]:
        return [
            deepcopy(session)
            for (session_tenant_id, _), session in self._sessions.items()
            if session_tenant_id == tenant_id
        ]

    def _load(self) -> None:
        if not self._storage_path:
            return
        payload = _read_json(self._storage_path, default=[])
        for item in payload:
            session = Session.model_validate(item)
            self._sessions[(session.tenant_id, session.session_id)] = session

    def _flush(self) -> None:
        if not self._storage_path:
            return
        _write_json(
            self._storage_path,
            [session.model_dump(mode="json") for session in self._sessions.values()],
        )


class InMemoryKnowledgeRepository:
    def __init__(self, storage_root: str | Path | None = None) -> None:
        self._knowledge_bases: dict[tuple[str, str], KnowledgeBase] = {}
        self._documents: dict[tuple[str, str], list[KnowledgeDocument]] = {}
        self._chunks: dict[tuple[str, str], list[KnowledgeChunk]] = {}
        self._storage_path = _state_file(storage_root, "knowledge.json")
        self._load()

    def save_knowledge_base(self, knowledge_base: KnowledgeBase) -> KnowledgeBase:
        self._knowledge_bases[(knowledge_base.tenant_id, knowledge_base.knowledge_base_id)] = deepcopy(
            knowledge_base
        )
        self._flush()
        return deepcopy(knowledge_base)

    def get_knowledge_base(self, tenant_id: str, knowledge_base_id: str) -> KnowledgeBase | None:
        item = self._knowledge_bases.get((tenant_id, knowledge_base_id))
        return deepcopy(item) if item else None

    def list_knowledge_bases(self, tenant_id: str) -> list[KnowledgeBase]:
        return [
            deepcopy(knowledge_base)
            for (knowledge_tenant_id, _), knowledge_base in self._knowledge_bases.items()
            if knowledge_tenant_id == tenant_id
        ]

    def save_document(self, document: KnowledgeDocument) -> KnowledgeDocument:
        key = (document.tenant_id, document.knowledge_base_id)
        self._documents.setdefault(key, []).append(deepcopy(document))
        self._flush()
        return deepcopy(document)

    def list_documents(self, tenant_id: str, knowledge_base_id: str) -> list[KnowledgeDocument]:
        return deepcopy(self._documents.get((tenant_id, knowledge_base_id), []))

    def replace_chunks(
        self, tenant_id: str, knowledge_base_id: str, chunks: list[KnowledgeChunk]
    ) -> list[KnowledgeChunk]:
        self._chunks[(tenant_id, knowledge_base_id)] = deepcopy(chunks)
        self._flush()
        return deepcopy(chunks)

    def list_chunks(self, tenant_id: str, knowledge_base_id: str) -> list[KnowledgeChunk]:
        return deepcopy(self._chunks.get((tenant_id, knowledge_base_id), []))

    def _load(self) -> None:
        if not self._storage_path:
            return
        payload = _read_json(self._storage_path, default={})
        for item in payload.get("knowledge_bases", []):
            knowledge_base = KnowledgeBase.model_validate(item)
            self._knowledge_bases[(knowledge_base.tenant_id, knowledge_base.knowledge_base_id)] = knowledge_base
        for item in payload.get("documents", []):
            document = KnowledgeDocument.model_validate(item)
            self._documents.setdefault((document.tenant_id, document.knowledge_base_id), []).append(document)
        for item in payload.get("chunks", []):
            chunk = KnowledgeChunk.model_validate(item)
            self._chunks.setdefault((chunk.tenant_id, chunk.knowledge_base_id), []).append(chunk)

    def _flush(self) -> None:
        if not self._storage_path:
            return
        _write_json(
            self._storage_path,
            {
                "knowledge_bases": [
                    item.model_dump(mode="json") for item in self._knowledge_bases.values()
                ],
                "documents": [
                    document.model_dump(mode="json")
                    for documents in self._documents.values()
                    for document in documents
                ],
                "chunks": [
                    chunk.model_dump(mode="json")
                    for chunks in self._chunks.values()
                    for chunk in chunks
                ],
            },
        )


class InMemoryRTCRepository:
    def __init__(self, storage_root: str | Path | None = None) -> None:
        self._rooms: dict[tuple[str, str], RTCRoom] = {}
        self._storage_path = _state_file(storage_root, "rtc_rooms.json")
        self._load()

    def save(self, room: RTCRoom) -> RTCRoom:
        self._rooms[(room.tenant_id, room.room_id)] = deepcopy(room)
        self._flush()
        return deepcopy(room)

    def get(self, tenant_id: str, room_id: str) -> RTCRoom | None:
        room = self._rooms.get((tenant_id, room_id))
        return deepcopy(room) if room else None

    def list_by_tenant(self, tenant_id: str) -> list[RTCRoom]:
        return [
            deepcopy(room)
            for (room_tenant_id, _), room in self._rooms.items()
            if room_tenant_id == tenant_id
        ]

    def _load(self) -> None:
        if not self._storage_path:
            return
        payload = _read_json(self._storage_path, default=[])
        for item in payload:
            room = RTCRoom.model_validate(item)
            self._rooms[(room.tenant_id, room.room_id)] = room

    def _flush(self) -> None:
        if not self._storage_path:
            return
        _write_json(
            self._storage_path,
            [room.model_dump(mode="json") for room in self._rooms.values()],
        )


class InMemoryDiagnosticsRepository:
    def __init__(self, max_size: int = 200, storage_root: str | Path | None = None) -> None:
        self._events: deque[DiagnosticEvent] = deque(maxlen=max_size)
        self._storage_path = _state_file(storage_root, "diagnostics.json")
        self._load()

    def add(self, event: DiagnosticEvent) -> None:
        self._events.appendleft(deepcopy(event))
        self._flush()

    def list_recent(self) -> list[DiagnosticEvent]:
        return [deepcopy(event) for event in self._events]

    def _load(self) -> None:
        if not self._storage_path:
            return
        payload = _read_json(self._storage_path, default=[])
        for item in payload:
            self._events.append(DiagnosticEvent.model_validate(item))

    def _flush(self) -> None:
        if not self._storage_path:
            return
        _write_json(self._storage_path, [event.model_dump(mode="json") for event in self._events])


def _state_file(storage_root: str | Path | None, filename: str) -> Path | None:
    if not storage_root:
        return None
    root = Path(storage_root) / "state"
    root.mkdir(parents=True, exist_ok=True)
    return root / filename


def _read_json(path: Path, default):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
