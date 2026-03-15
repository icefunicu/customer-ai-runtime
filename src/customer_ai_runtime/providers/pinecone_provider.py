from __future__ import annotations

import asyncio
from typing import Any

from customer_ai_runtime.core.config import Settings
from customer_ai_runtime.core.errors import AppError
from customer_ai_runtime.core.text import build_embedding
from customer_ai_runtime.domain.models import KnowledgeChunk, RetrievalHit
from customer_ai_runtime.providers.base import VectorStoreProvider


class PineconeVectorStoreProvider(VectorStoreProvider):
    def __init__(self, settings: Settings) -> None:
        if not settings.pinecone_api_key:
            raise AppError(
                code="provider_error",
                message="未配置 CUSTOMER_AI_PINECONE_API_KEY，无法启用 Pinecone 提供商。",
                status_code=503,
            )
        if not settings.pinecone_index_host and not settings.pinecone_index_name:
            raise AppError(
                code="provider_error",
                message=(
                    "未配置 CUSTOMER_AI_PINECONE_INDEX_HOST 或 CUSTOMER_AI_PINECONE_INDEX_NAME。"
                ),
                status_code=503,
            )
        self._settings = settings
        self._index = self._build_index()

    async def upsert(self, chunks: list[KnowledgeChunk]) -> None:
        if not chunks:
            return
        namespace = self._namespace(chunks[0].tenant_id, chunks[0].knowledge_base_id)
        vectors = [
            {
                "id": chunk.chunk_id,
                "values": chunk.embedding,
                "metadata": chunk.model_dump(mode="json"),
            }
            for chunk in chunks
        ]
        await asyncio.to_thread(self._index.upsert, vectors=vectors, namespace=namespace)

    async def search(
        self,
        tenant_id: str,
        knowledge_base_id: str,
        query: str,
        top_k: int,
    ) -> list[RetrievalHit]:
        namespace = self._namespace(tenant_id, knowledge_base_id)
        response = await asyncio.to_thread(
            self._index.query,
            vector=build_embedding(query),
            top_k=top_k,
            namespace=namespace,
            include_metadata=True,
        )
        hits: list[RetrievalHit] = []
        for match in getattr(response, "matches", []) or []:
            metadata = getattr(match, "metadata", {}) or {}
            chunk = KnowledgeChunk.model_validate(metadata)
            hits.append(RetrievalHit(chunk=chunk, score=float(getattr(match, "score", 0.0))))
        return hits

    def _build_index(self) -> Any:
        try:
            from pinecone import Pinecone
        except ImportError as exc:
            raise AppError(
                code="provider_error",
                message="未安装 pinecone SDK，请先安装 `pinecone`。",
                status_code=503,
            ) from exc

        client = Pinecone(api_key=self._settings.pinecone_api_key)
        if self._settings.pinecone_index_host:
            return client.Index(host=self._settings.pinecone_index_host)
        return client.Index(name=self._settings.pinecone_index_name)

    def _namespace(self, tenant_id: str, knowledge_base_id: str) -> str:
        prefix = self._settings.pinecone_namespace_prefix
        return f"{prefix}:{tenant_id}:{knowledge_base_id}"
