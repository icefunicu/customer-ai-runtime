from __future__ import annotations

from abc import ABC, abstractmethod

from customer_ai_runtime.domain.models import (
    ASRRequest,
    ASRResult,
    BusinessQuery,
    BusinessResult,
    KnowledgeChunk,
    LLMRequest,
    LLMResponse,
    RetrievalHit,
    TTSRequest,
    TTSResult,
)


class LLMProvider(ABC):
    @abstractmethod
    async def generate(self, request: LLMRequest) -> LLMResponse: ...


class ASRProvider(ABC):
    @abstractmethod
    async def transcribe(self, request: ASRRequest) -> ASRResult: ...


class TTSProvider(ABC):
    @abstractmethod
    async def synthesize(self, request: TTSRequest) -> TTSResult: ...


class VectorStoreProvider(ABC):
    @abstractmethod
    async def upsert(self, chunks: list[KnowledgeChunk]) -> None: ...

    @abstractmethod
    async def search(
        self,
        tenant_id: str,
        knowledge_base_id: str,
        query: str,
        top_k: int,
    ) -> list[RetrievalHit]: ...


class BusinessAdapter(ABC):
    @abstractmethod
    async def execute(self, query: BusinessQuery) -> BusinessResult: ...
