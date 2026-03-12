from __future__ import annotations

from qdrant_client import AsyncQdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

from customer_ai_runtime.core.config import Settings
from customer_ai_runtime.core.errors import AppError
from customer_ai_runtime.domain.models import KnowledgeChunk, RetrievalHit
from customer_ai_runtime.providers.base import VectorStoreProvider


class QdrantVectorStoreProvider(VectorStoreProvider):
    def __init__(self, settings: Settings) -> None:
        if not settings.qdrant_url:
            raise AppError(
                code="provider_error",
                message="未配置 CUSTOMER_AI_QDRANT_URL，无法启用 Qdrant 提供商。",
                status_code=500,
            )
        self._settings = settings
        self._client = AsyncQdrantClient(url=settings.qdrant_url, api_key=settings.qdrant_api_key)

    async def upsert(self, chunks: list[KnowledgeChunk]) -> None:
        if not chunks:
            return
        collection_name = self._collection_name(chunks[0].tenant_id, chunks[0].knowledge_base_id)
        await self._ensure_collection(collection_name, len(chunks[0].embedding))
        await self._client.upsert(
            collection_name=collection_name,
            points=[
                PointStruct(
                    id=chunk.chunk_id,
                    vector=chunk.embedding,
                    payload=chunk.model_dump(mode="json"),
                )
                for chunk in chunks
            ],
        )

    async def search(
        self,
        tenant_id: str,
        knowledge_base_id: str,
        query: str,
        top_k: int,
    ) -> list[RetrievalHit]:
        from customer_ai_runtime.core.text import build_embedding

        collection_name = self._collection_name(tenant_id, knowledge_base_id)
        results = await self._client.search(
            collection_name=collection_name,
            query_vector=build_embedding(query),
            limit=top_k,
        )
        hits: list[RetrievalHit] = []
        for result in results:
            payload = result.payload or {}
            chunk = KnowledgeChunk.model_validate(payload)
            hits.append(RetrievalHit(chunk=chunk, score=float(result.score)))
        return hits

    async def _ensure_collection(self, collection_name: str, dimensions: int) -> None:
        collections = await self._client.get_collections()
        if any(item.name == collection_name for item in collections.collections):
            return
        await self._client.create_collection(
            collection_name=collection_name,
            vectors_config=VectorParams(size=dimensions, distance=Distance.COSINE),
        )

    def _collection_name(self, tenant_id: str, knowledge_base_id: str) -> str:
        return f"{self._settings.qdrant_collection_prefix}_{tenant_id}_{knowledge_base_id}"

