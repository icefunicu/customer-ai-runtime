from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from customer_ai_runtime.core.errors import AppError
from customer_ai_runtime.core.text import build_embedding, chunk_text
from customer_ai_runtime.domain.models import KnowledgeBase, KnowledgeChunk, KnowledgeDocument
from customer_ai_runtime.providers.base import VectorStoreProvider
from customer_ai_runtime.providers.local import citations_from_hits
from customer_ai_runtime.repositories.memory import InMemoryKnowledgeRepository

from customer_ai_runtime.application.runtime import zh


class KnowledgeService:
    def __init__(
        self,
        repository: InMemoryKnowledgeRepository,
        vector_store: VectorStoreProvider,
    ) -> None:
        self._repository = repository
        self._vector_store = vector_store

    async def create_knowledge_base(
        self,
        tenant_id: str,
        knowledge_base_id: str,
        name: str,
        description: str,
    ) -> KnowledgeBase:
        knowledge_base = KnowledgeBase(
            tenant_id=tenant_id,
            knowledge_base_id=knowledge_base_id,
            name=name,
            description=description,
        )
        return self._repository.save_knowledge_base(knowledge_base)

    def get_knowledge_base(self, tenant_id: str, knowledge_base_id: str) -> KnowledgeBase:
        knowledge_base = self._repository.get_knowledge_base(tenant_id, knowledge_base_id)
        if not knowledge_base:
            raise AppError(
                code="not_found",
                message=zh("\\u77e5\\u8bc6\\u5e93\\u4e0d\\u5b58\\u5728"),
                status_code=404,
            )
        return knowledge_base

    def list_knowledge_bases(self, tenant_id: str) -> list[KnowledgeBase]:
        return self._repository.list_knowledge_bases(tenant_id)

    async def add_document(
        self,
        tenant_id: str,
        knowledge_base_id: str,
        title: str,
        content: str,
        metadata: dict[str, Any],
    ) -> dict[str, Any]:
        if not content.strip():
            raise AppError(
                code="validation_error",
                message=zh("\\u6587\\u6863\\u5185\\u5bb9\\u4e0d\\u80fd\\u4e3a\\u7a7a"),
                status_code=400,
            )
        knowledge_base = self.get_knowledge_base(tenant_id, knowledge_base_id)
        document = KnowledgeDocument(
            tenant_id=tenant_id,
            knowledge_base_id=knowledge_base_id,
            title=title,
            content=content,
            metadata=metadata,
        )
        self._repository.save_document(document)
        existing_chunks = self._repository.list_chunks(tenant_id, knowledge_base_id)
        new_chunks = [
            KnowledgeChunk(
                tenant_id=tenant_id,
                knowledge_base_id=knowledge_base_id,
                document_id=document.document_id,
                title=title,
                content=chunk,
                position=index,
                embedding=build_embedding(chunk),
            )
            for index, chunk in enumerate(chunk_text(content))
        ]
        merged_chunks = existing_chunks + new_chunks
        self._repository.replace_chunks(tenant_id, knowledge_base_id, merged_chunks)
        await self._vector_store.upsert(merged_chunks)
        knowledge_base.document_count = len(self._repository.list_documents(tenant_id, knowledge_base_id))
        knowledge_base.chunk_count = len(merged_chunks)
        self._repository.save_knowledge_base(knowledge_base)
        return {
            "knowledge_base": knowledge_base,
            "document": document,
            "chunks": new_chunks,
        }

    async def search(
        self,
        tenant_id: str,
        knowledge_base_id: str,
        query: str,
        top_k: int,
        min_score: float,
    ) -> list[dict[str, Any]]:
        self.get_knowledge_base(tenant_id, knowledge_base_id)
        hits = await self._vector_store.search(tenant_id, knowledge_base_id, query, top_k)
        return [
            {
                "score": round(hit.score, 4),
                "title": hit.chunk.title,
                "chunk_id": hit.chunk.chunk_id,
                "content": hit.chunk.content,
            }
            for hit in hits
            if hit.score >= min_score
        ]

    async def retrieve(self, tenant_id: str, knowledge_base_id: str, query: str, top_k: int):
        hits = await self._vector_store.search(tenant_id, knowledge_base_id, query, top_k)
        if not hits:
            fallback_chunks = self._repository.list_chunks(tenant_id, knowledge_base_id)[:top_k]
            hits = [SimpleNamespace(chunk=chunk, score=0.1) for chunk in fallback_chunks]
        return citations_from_hits(hits)

    def health_report(self, tenant_id: str, knowledge_base_id: str) -> dict[str, Any]:
        knowledge_base = self.get_knowledge_base(tenant_id, knowledge_base_id)
        documents = self._repository.list_documents(tenant_id, knowledge_base_id)
        chunks = self._repository.list_chunks(tenant_id, knowledge_base_id)
        chunk_lengths = [len(chunk.content.strip()) for chunk in chunks if chunk.content.strip()]
        normalized_chunks = [
            " ".join(chunk.content.split()).strip().lower()
            for chunk in chunks
            if chunk.content.strip()
        ]
        duplicate_count = len(normalized_chunks) - len(set(normalized_chunks))
        duplicate_ratio = 0.0 if not normalized_chunks else round(duplicate_count / len(normalized_chunks), 4)
        empty_documents = sum(1 for document in documents if not document.content.strip())
        average_chunk_length = 0.0 if not chunk_lengths else round(sum(chunk_lengths) / len(chunk_lengths), 2)
        score = 100.0
        if knowledge_base.document_count == 0:
            score -= 40
        if knowledge_base.chunk_count == 0:
            score -= 30
        score -= min(30.0, duplicate_ratio * 100)
        if average_chunk_length < 80 and knowledge_base.chunk_count > 0:
            score -= 10
        if average_chunk_length > 1600:
            score -= 10
        score -= min(10.0, empty_documents * 2.0)
        score = round(max(0.0, score), 2)
        return {
            "tenant_id": tenant_id,
            "knowledge_base_id": knowledge_base_id,
            "document_count": knowledge_base.document_count,
            "chunk_count": knowledge_base.chunk_count,
            "average_chunk_length": average_chunk_length,
            "duplicate_chunk_ratio": duplicate_ratio,
            "empty_document_count": empty_documents,
            "health_score": score,
        }
