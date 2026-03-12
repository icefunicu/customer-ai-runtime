from __future__ import annotations

import asyncio
from typing import Any

from customer_ai_runtime.core.config import Settings
from customer_ai_runtime.core.errors import AppError
from customer_ai_runtime.core.text import build_embedding
from customer_ai_runtime.domain.models import KnowledgeChunk, RetrievalHit
from customer_ai_runtime.providers.base import VectorStoreProvider


class MilvusVectorStoreProvider(VectorStoreProvider):
    def __init__(self, settings: Settings) -> None:
        if not settings.milvus_uri:
            raise AppError(
                code="provider_error",
                message="未配置 CUSTOMER_AI_MILVUS_URI，无法启用 Milvus 提供商。",
                status_code=500,
            )
        self._settings = settings
        self._client = self._build_client()

    async def upsert(self, chunks: list[KnowledgeChunk]) -> None:
        if not chunks:
            return
        collection_name = self._collection_name(chunks[0].tenant_id, chunks[0].knowledge_base_id)
        await self._ensure_collection(collection_name, len(chunks[0].embedding))
        payload = [
            {
                "chunk_id": chunk.chunk_id,
                "embedding": chunk.embedding,
                "tenant_id": chunk.tenant_id,
                "knowledge_base_id": chunk.knowledge_base_id,
                "version_id": chunk.version_id,
                "document_id": chunk.document_id,
                "title": chunk.title,
                "content": chunk.content,
                "position": chunk.position,
                "created_at": chunk.created_at.isoformat(),
            }
            for chunk in chunks
        ]
        await asyncio.to_thread(self._client.upsert, collection_name=collection_name, data=payload)

    async def search(
        self,
        tenant_id: str,
        knowledge_base_id: str,
        query: str,
        top_k: int,
    ) -> list[RetrievalHit]:
        collection_name = self._collection_name(tenant_id, knowledge_base_id)
        results = await asyncio.to_thread(
            self._client.search,
            collection_name=collection_name,
            data=[build_embedding(query)],
            limit=top_k,
            output_fields=[
                "chunk_id",
                "tenant_id",
                "knowledge_base_id",
                "version_id",
                "document_id",
                "title",
                "content",
                "position",
                "created_at",
            ],
        )
        records = results[0] if results else []
        hits: list[RetrievalHit] = []
        for item in records:
            entity = dict(item.get("entity") or {})
            if "embedding" not in entity:
                entity["embedding"] = []
            chunk = KnowledgeChunk.model_validate(entity)
            hits.append(RetrievalHit(chunk=chunk, score=float(item.get("distance", 0.0))))
        return hits

    async def _ensure_collection(self, collection_name: str, dimensions: int) -> None:
        has_collection = await asyncio.to_thread(
            self._client.has_collection, collection_name=collection_name
        )
        if has_collection:
            return
        await asyncio.to_thread(
            self._client.create_collection,
            collection_name=collection_name,
            dimension=dimensions,
            id_type="string",
            primary_field_name="chunk_id",
            vector_field_name="embedding",
            metric_type="COSINE",
        )

    def _build_client(self) -> Any:
        try:
            from pymilvus import MilvusClient
        except ImportError as exc:
            raise AppError(
                code="provider_error",
                message="未安装 pymilvus，请先安装 `pymilvus`。",
                status_code=500,
            ) from exc
        return MilvusClient(uri=self._settings.milvus_uri, token=self._settings.milvus_token)

    def _collection_name(self, tenant_id: str, knowledge_base_id: str) -> str:
        prefix = self._settings.milvus_collection_prefix
        return f"{prefix}_{tenant_id}_{knowledge_base_id}"
