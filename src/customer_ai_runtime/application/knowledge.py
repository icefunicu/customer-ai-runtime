from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from customer_ai_runtime.application.runtime import zh
from customer_ai_runtime.core.errors import AppError
from customer_ai_runtime.core.text import build_embedding, chunk_text, cosine_similarity
from customer_ai_runtime.domain.models import (
    KnowledgeBase,
    KnowledgeChunk,
    KnowledgeChunkConfig,
    KnowledgeDocument,
    KnowledgeVersion,
    KnowledgeVersionStatus,
    utcnow,
)
from customer_ai_runtime.providers.base import VectorStoreProvider
from customer_ai_runtime.providers.local import citations_from_hits
from customer_ai_runtime.repositories.base import KnowledgeRepository


class KnowledgeService:
    def __init__(
        self,
        repository: KnowledgeRepository,
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
        initial_config = KnowledgeChunkConfig()
        initial_version = KnowledgeVersion(
            tenant_id=tenant_id,
            knowledge_base_id=knowledge_base_id,
            status=KnowledgeVersionStatus.ACTIVE,
            description="initial version",
            chunk_config=initial_config,
            activated_at=utcnow(),
        )
        knowledge_base = KnowledgeBase(
            tenant_id=tenant_id,
            knowledge_base_id=knowledge_base_id,
            name=name,
            description=description,
            active_version_id=initial_version.version_id,
            version_count=1,
            chunk_max_tokens=initial_config.max_tokens,
            chunk_overlap=initial_config.overlap,
        )
        self._repository.save_version(initial_version)
        return self._repository.save_knowledge_base(knowledge_base)

    def get_knowledge_base(self, tenant_id: str, knowledge_base_id: str) -> KnowledgeBase:
        knowledge_base = self._repository.get_knowledge_base(tenant_id, knowledge_base_id)
        if not knowledge_base:
            raise AppError(
                code="not_found",
                message=zh("\\u77e5\\u8bc6\\u5e93\\u4e0d\\u5b58\\u5728"),
                status_code=404,
            )
        if not knowledge_base.active_version_id:
            legacy_version = self._bootstrap_legacy_version(knowledge_base)
            knowledge_base.active_version_id = legacy_version.version_id
            knowledge_base.version_count = len(
                self._repository.list_versions(tenant_id, knowledge_base_id)
            )
            knowledge_base.chunk_max_tokens = legacy_version.chunk_config.max_tokens
            knowledge_base.chunk_overlap = legacy_version.chunk_config.overlap
            self._repository.save_knowledge_base(knowledge_base)
        return knowledge_base

    def list_knowledge_bases(self, tenant_id: str) -> list[KnowledgeBase]:
        return self._repository.list_knowledge_bases(tenant_id)

    def list_versions(self, tenant_id: str, knowledge_base_id: str) -> list[KnowledgeVersion]:
        self.get_knowledge_base(tenant_id, knowledge_base_id)
        versions = self._repository.list_versions(tenant_id, knowledge_base_id)
        versions.sort(key=lambda item: item.created_at, reverse=True)
        return versions

    def get_version(
        self, tenant_id: str, knowledge_base_id: str, version_id: str
    ) -> KnowledgeVersion:
        self.get_knowledge_base(tenant_id, knowledge_base_id)
        version = self._repository.get_version(tenant_id, knowledge_base_id, version_id)
        if not version:
            raise AppError(
                code="not_found",
                message=zh("\\u77e5\\u8bc6\\u7248\\u672c\\u4e0d\\u5b58\\u5728"),
                status_code=404,
            )
        return version

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
        active_version = self._get_active_version(knowledge_base)
        document = KnowledgeDocument(
            tenant_id=tenant_id,
            knowledge_base_id=knowledge_base_id,
            version_id=active_version.version_id,
            title=title,
            content=content,
            metadata=metadata,
        )
        self._repository.save_document(document)
        existing_chunks = self._repository.list_chunks(
            tenant_id,
            knowledge_base_id,
            version_id=active_version.version_id,
        )
        new_chunks = self._build_chunks(
            tenant_id=tenant_id,
            knowledge_base_id=knowledge_base_id,
            version_id=active_version.version_id,
            document=document,
            chunk_config=active_version.chunk_config,
        )
        merged_chunks = existing_chunks + new_chunks
        self._repository.replace_chunks(
            tenant_id,
            knowledge_base_id,
            merged_chunks,
            version_id=active_version.version_id,
        )
        await self._vector_store.upsert(
            self._vectorize_chunks(knowledge_base_id, active_version.version_id, merged_chunks)
        )
        version_documents = self._repository.list_documents(
            tenant_id,
            knowledge_base_id,
            version_id=active_version.version_id,
        )
        knowledge_base.document_count = len(version_documents)
        knowledge_base.chunk_count = len(merged_chunks)
        self._repository.save_knowledge_base(knowledge_base)
        active_version.document_count = knowledge_base.document_count
        active_version.chunk_count = knowledge_base.chunk_count
        self._repository.save_version(active_version)
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
        knowledge_base = self.get_knowledge_base(tenant_id, knowledge_base_id)
        active_version = self._get_active_version(knowledge_base)
        hits = await self._vector_store.search(
            tenant_id,
            self._version_namespace(knowledge_base_id, active_version.version_id),
            query,
            top_k,
        )
        normalized_hits = self._normalize_hits(knowledge_base_id, active_version.version_id, hits)
        return [
            {
                "score": round(hit.score, 4),
                "title": hit.chunk.title,
                "chunk_id": hit.chunk.chunk_id,
                "content": hit.chunk.content,
            }
            for hit in normalized_hits
            if hit.score >= min_score
        ]

    async def retrieve(self, tenant_id: str, knowledge_base_id: str, query: str, top_k: int):
        knowledge_base = self.get_knowledge_base(tenant_id, knowledge_base_id)
        active_version = self._get_active_version(knowledge_base)
        hits = await self._vector_store.search(
            tenant_id,
            self._version_namespace(knowledge_base_id, active_version.version_id),
            query,
            top_k,
        )
        hits = self._normalize_hits(knowledge_base_id, active_version.version_id, hits)
        if not hits:
            fallback_chunks = self._repository.list_chunks(
                tenant_id,
                knowledge_base_id,
                version_id=active_version.version_id,
            )[:top_k]
            hits = [SimpleNamespace(chunk=chunk, score=0.1) for chunk in fallback_chunks]
        return citations_from_hits(hits)

    def health_report(self, tenant_id: str, knowledge_base_id: str) -> dict[str, Any]:
        knowledge_base = self.get_knowledge_base(tenant_id, knowledge_base_id)
        active_version = self._get_active_version(knowledge_base)
        documents = self._repository.list_documents(
            tenant_id,
            knowledge_base_id,
            version_id=active_version.version_id,
        )
        chunks = self._repository.list_chunks(
            tenant_id,
            knowledge_base_id,
            version_id=active_version.version_id,
        )
        chunk_lengths = [len(chunk.content.strip()) for chunk in chunks if chunk.content.strip()]
        normalized_chunks = [
            " ".join(chunk.content.split()).strip().lower()
            for chunk in chunks
            if chunk.content.strip()
        ]
        duplicate_count = len(normalized_chunks) - len(set(normalized_chunks))
        duplicate_ratio = (
            0.0 if not normalized_chunks else round(duplicate_count / len(normalized_chunks), 4)
        )
        empty_documents = sum(1 for document in documents if not document.content.strip())
        average_chunk_length = (
            0.0 if not chunk_lengths else round(sum(chunk_lengths) / len(chunk_lengths), 2)
        )
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
            "active_version_id": active_version.version_id,
            "document_count": knowledge_base.document_count,
            "chunk_count": knowledge_base.chunk_count,
            "chunk_config": active_version.chunk_config.model_dump(mode="json"),
            "average_chunk_length": average_chunk_length,
            "duplicate_chunk_ratio": duplicate_ratio,
            "empty_document_count": empty_documents,
            "health_score": score,
        }

    def chunk_optimization_report(
        self,
        tenant_id: str,
        knowledge_base_id: str,
        miss_queries: list[str] | None = None,
    ) -> dict[str, Any]:
        knowledge_base = self.get_knowledge_base(tenant_id, knowledge_base_id)
        active_version = self._get_active_version(knowledge_base)
        documents = self._repository.list_documents(
            tenant_id,
            knowledge_base_id,
            version_id=active_version.version_id,
        )
        if not documents:
            raise AppError(
                code="validation_error",
                message=zh(
                    "\\u77e5\\u8bc6\\u5e93\\u6682\\u65e0\\u6587\\u6863\\uff0c\\u65e0\\u6cd5\\u751f\\u6210\\u5207\\u7247\\u4f18\\u5316\\u5efa\\u8bae"
                ),
                status_code=400,
            )
        current = (active_version.chunk_config.max_tokens, active_version.chunk_config.overlap)
        candidates = [
            current,
            (96, 16),
            (160, 24),
            (256, 32),
        ]
        unique_candidates: list[tuple[int, int]] = []
        for item in candidates:
            if item not in unique_candidates:
                unique_candidates.append(item)
        reports = [
            self._evaluate_chunk_candidate(
                tenant_id=tenant_id,
                knowledge_base_id=knowledge_base_id,
                documents=documents,
                max_tokens=max_tokens,
                overlap=overlap,
                miss_queries=miss_queries or [],
                is_current=(max_tokens, overlap) == current,
            )
            for max_tokens, overlap in unique_candidates
        ]
        recommended = max(reports, key=lambda item: item["score"])
        return {
            "tenant_id": tenant_id,
            "knowledge_base_id": knowledge_base_id,
            "active_version_id": active_version.version_id,
            "current_config": active_version.chunk_config.model_dump(mode="json"),
            "recommended_config": recommended["chunk_config"],
            "candidates": reports,
        }

    async def create_version_snapshot(
        self,
        tenant_id: str,
        knowledge_base_id: str,
        description: str,
        source_version_id: str | None = None,
    ) -> KnowledgeVersion:
        knowledge_base = self.get_knowledge_base(tenant_id, knowledge_base_id)
        source_version = self.get_version(
            tenant_id,
            knowledge_base_id,
            source_version_id or self._require_active_version_id(knowledge_base),
        )
        documents = self._repository.list_documents(
            tenant_id,
            knowledge_base_id,
            version_id=source_version.version_id,
        )
        chunks = self._repository.list_chunks(
            tenant_id,
            knowledge_base_id,
            version_id=source_version.version_id,
        )
        version = KnowledgeVersion(
            tenant_id=tenant_id,
            knowledge_base_id=knowledge_base_id,
            status=KnowledgeVersionStatus.DRAFT,
            description=description or f"snapshot from {source_version.version_id}",
            chunk_config=source_version.chunk_config.model_copy(deep=True),
            document_count=len(documents),
            chunk_count=len(chunks),
            source_version_id=source_version.version_id,
        )
        cloned_documents = [
            document.model_copy(update={"version_id": version.version_id}) for document in documents
        ]
        cloned_chunks = [
            chunk.model_copy(update={"version_id": version.version_id}) for chunk in chunks
        ]
        self._repository.save_version(version)
        self._repository.replace_documents(
            tenant_id,
            knowledge_base_id,
            cloned_documents,
            version_id=version.version_id,
        )
        self._repository.replace_chunks(
            tenant_id,
            knowledge_base_id,
            cloned_chunks,
            version_id=version.version_id,
        )
        await self._vector_store.upsert(
            self._vectorize_chunks(knowledge_base_id, version.version_id, cloned_chunks)
        )
        knowledge_base.version_count = len(
            self._repository.list_versions(tenant_id, knowledge_base_id)
        )
        self._repository.save_knowledge_base(knowledge_base)
        return version

    async def apply_chunk_optimization(
        self,
        tenant_id: str,
        knowledge_base_id: str,
        *,
        max_tokens: int,
        overlap: int,
        description: str = "",
        activate: bool = True,
    ) -> dict[str, Any]:
        knowledge_base = self.get_knowledge_base(tenant_id, knowledge_base_id)
        source_version = self._get_active_version(knowledge_base)
        documents = self._repository.list_documents(
            tenant_id,
            knowledge_base_id,
            version_id=source_version.version_id,
        )
        if not documents:
            raise AppError(
                code="validation_error",
                message=zh(
                    "\\u77e5\\u8bc6\\u5e93\\u6682\\u65e0\\u6587\\u6863\\uff0c\\u65e0\\u6cd5\\u6267\\u884c\\u5207\\u7247\\u4f18\\u5316"
                ),
                status_code=400,
            )
        chunk_config = KnowledgeChunkConfig(max_tokens=max_tokens, overlap=overlap)
        version = KnowledgeVersion(
            tenant_id=tenant_id,
            knowledge_base_id=knowledge_base_id,
            status=KnowledgeVersionStatus.ACTIVE if activate else KnowledgeVersionStatus.DRAFT,
            description=description or f"chunk optimization {max_tokens}/{overlap}",
            chunk_config=chunk_config,
            document_count=len(documents),
            chunk_count=0,
            source_version_id=source_version.version_id,
            activated_at=utcnow() if activate else None,
        )
        cloned_documents = [
            document.model_copy(update={"version_id": version.version_id}) for document in documents
        ]
        optimized_chunks = [
            chunk
            for document in cloned_documents
            for chunk in self._build_chunks(
                tenant_id=tenant_id,
                knowledge_base_id=knowledge_base_id,
                version_id=version.version_id,
                document=document,
                chunk_config=chunk_config,
            )
        ]
        version.chunk_count = len(optimized_chunks)
        self._repository.save_version(version)
        self._repository.replace_documents(
            tenant_id,
            knowledge_base_id,
            cloned_documents,
            version_id=version.version_id,
        )
        self._repository.replace_chunks(
            tenant_id,
            knowledge_base_id,
            optimized_chunks,
            version_id=version.version_id,
        )
        await self._vector_store.upsert(
            self._vectorize_chunks(knowledge_base_id, version.version_id, optimized_chunks)
        )
        if activate:
            version = self.activate_version(tenant_id, knowledge_base_id, version.version_id)
            knowledge_base = self.get_knowledge_base(tenant_id, knowledge_base_id)
        else:
            knowledge_base.version_count = len(
                self._repository.list_versions(tenant_id, knowledge_base_id)
            )
            self._repository.save_knowledge_base(knowledge_base)
        return {
            "knowledge_base": knowledge_base,
            "version": version,
            "document_count": len(cloned_documents),
            "chunk_count": len(optimized_chunks),
        }

    def activate_version(
        self,
        tenant_id: str,
        knowledge_base_id: str,
        version_id: str,
    ) -> KnowledgeVersion:
        knowledge_base = self.get_knowledge_base(tenant_id, knowledge_base_id)
        target_version = self.get_version(tenant_id, knowledge_base_id, version_id)
        versions = self._repository.list_versions(tenant_id, knowledge_base_id)
        for version in versions:
            if version.version_id == version_id:
                version.status = KnowledgeVersionStatus.ACTIVE
                version.activated_at = utcnow()
                target_version = version
            elif version.status == KnowledgeVersionStatus.ACTIVE:
                version.status = KnowledgeVersionStatus.ARCHIVED
            self._repository.save_version(version)
        knowledge_base.active_version_id = target_version.version_id
        knowledge_base.version_count = len(versions)
        knowledge_base.chunk_max_tokens = target_version.chunk_config.max_tokens
        knowledge_base.chunk_overlap = target_version.chunk_config.overlap
        knowledge_base.document_count = target_version.document_count
        knowledge_base.chunk_count = target_version.chunk_count
        self._repository.save_knowledge_base(knowledge_base)
        return target_version

    def _get_active_version(self, knowledge_base: KnowledgeBase) -> KnowledgeVersion:
        return self.get_version(
            knowledge_base.tenant_id,
            knowledge_base.knowledge_base_id,
            self._require_active_version_id(knowledge_base),
        )

    def _require_active_version_id(self, knowledge_base: KnowledgeBase) -> str:
        if knowledge_base.active_version_id:
            return knowledge_base.active_version_id
        raise AppError(
            code="validation_error",
            message=zh("\\u77e5\\u8bc6\\u5e93\\u7f3a\\u5c11\\u6d3b\\u8dc3\\u7248\\u672c"),
            status_code=409,
        )

    def _bootstrap_legacy_version(self, knowledge_base: KnowledgeBase) -> KnowledgeVersion:
        legacy_version = self._repository.get_version(
            knowledge_base.tenant_id,
            knowledge_base.knowledge_base_id,
            "legacy",
        )
        if legacy_version:
            return legacy_version
        documents = self._repository.list_documents(
            knowledge_base.tenant_id,
            knowledge_base.knowledge_base_id,
        )
        chunks = self._repository.list_chunks(
            knowledge_base.tenant_id,
            knowledge_base.knowledge_base_id,
        )
        legacy_version = KnowledgeVersion(
            tenant_id=knowledge_base.tenant_id,
            knowledge_base_id=knowledge_base.knowledge_base_id,
            version_id="legacy",
            status=KnowledgeVersionStatus.ACTIVE,
            description="legacy imported version",
            chunk_config=KnowledgeChunkConfig(
                max_tokens=knowledge_base.chunk_max_tokens,
                overlap=knowledge_base.chunk_overlap,
            ),
            document_count=len(documents),
            chunk_count=len(chunks),
            activated_at=utcnow(),
        )
        self._repository.save_version(legacy_version)
        if documents:
            self._repository.replace_documents(
                knowledge_base.tenant_id,
                knowledge_base.knowledge_base_id,
                [document.model_copy(update={"version_id": "legacy"}) for document in documents],
                version_id="legacy",
            )
        if chunks:
            self._repository.replace_chunks(
                knowledge_base.tenant_id,
                knowledge_base.knowledge_base_id,
                [chunk.model_copy(update={"version_id": "legacy"}) for chunk in chunks],
                version_id="legacy",
            )
        return legacy_version

    def _version_namespace(self, knowledge_base_id: str, version_id: str) -> str:
        return f"{knowledge_base_id}__{version_id}"

    def _build_chunks(
        self,
        *,
        tenant_id: str,
        knowledge_base_id: str,
        version_id: str,
        document: KnowledgeDocument,
        chunk_config: KnowledgeChunkConfig,
    ) -> list[KnowledgeChunk]:
        return [
            KnowledgeChunk(
                tenant_id=tenant_id,
                knowledge_base_id=knowledge_base_id,
                version_id=version_id,
                document_id=document.document_id,
                title=document.title,
                content=chunk,
                position=index,
                embedding=build_embedding(chunk),
            )
            for index, chunk in enumerate(
                chunk_text(
                    document.content,
                    max_tokens=chunk_config.max_tokens,
                    overlap=chunk_config.overlap,
                )
            )
        ]

    def _vectorize_chunks(
        self,
        knowledge_base_id: str,
        version_id: str,
        chunks: list[KnowledgeChunk],
    ) -> list[KnowledgeChunk]:
        namespace = self._version_namespace(knowledge_base_id, version_id)
        return [chunk.model_copy(update={"knowledge_base_id": namespace}) for chunk in chunks]

    def _normalize_hits(
        self,
        knowledge_base_id: str,
        version_id: str,
        hits: list[Any],
    ) -> list[Any]:
        normalized: list[Any] = []
        for hit in hits:
            normalized_chunk = hit.chunk.model_copy(
                update={"knowledge_base_id": knowledge_base_id, "version_id": version_id}
            )
            if isinstance(hit, SimpleNamespace):
                normalized.append(SimpleNamespace(chunk=normalized_chunk, score=hit.score))
            else:
                normalized.append(hit.model_copy(update={"chunk": normalized_chunk}))
        return normalized

    def _evaluate_chunk_candidate(
        self,
        *,
        tenant_id: str,
        knowledge_base_id: str,
        documents: list[KnowledgeDocument],
        max_tokens: int,
        overlap: int,
        miss_queries: list[str],
        is_current: bool,
    ) -> dict[str, Any]:
        chunk_config = KnowledgeChunkConfig(max_tokens=max_tokens, overlap=overlap)
        chunks = [
            chunk
            for document in documents
            for chunk in self._build_chunks(
                tenant_id=tenant_id,
                knowledge_base_id=knowledge_base_id,
                version_id="simulation",
                document=document,
                chunk_config=chunk_config,
            )
        ]
        chunk_lengths = [len(chunk.content.split()) for chunk in chunks if chunk.content.strip()]
        average_chunk_length = (
            0.0 if not chunk_lengths else round(sum(chunk_lengths) / len(chunk_lengths), 2)
        )
        normalized_chunks = [
            " ".join(chunk.content.split()).strip().lower()
            for chunk in chunks
            if chunk.content.strip()
        ]
        duplicate_ratio = (
            0.0
            if not normalized_chunks
            else round(
                (len(normalized_chunks) - len(set(normalized_chunks))) / len(normalized_chunks), 4
            )
        )
        query_support = 0.0
        if miss_queries and chunks:
            support_scores: list[float] = []
            for query in miss_queries:
                query_vector = build_embedding(query)
                support_scores.append(
                    max(cosine_similarity(query_vector, chunk.embedding) for chunk in chunks)
                )
            query_support = round(sum(support_scores) / len(support_scores), 4)
        score = 100.0
        if not chunks:
            score -= 60
        score -= min(25.0, duplicate_ratio * 100)
        if average_chunk_length < 50:
            score -= 12
        elif average_chunk_length > 280:
            score -= 8
        if len(chunks) > len(documents) * 12:
            score -= 8
        if len(chunks) < len(documents):
            score -= 8
        score += min(10.0, query_support * 10)
        if is_current:
            score += 2
        score = round(max(0.0, score), 2)
        return {
            "chunk_config": chunk_config.model_dump(mode="json"),
            "chunk_count": len(chunks),
            "average_chunk_length": average_chunk_length,
            "duplicate_chunk_ratio": duplicate_ratio,
            "query_support_score": query_support,
            "score": score,
            "is_current": is_current,
        }
