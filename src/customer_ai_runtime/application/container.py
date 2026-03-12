from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from customer_ai_runtime.application.access import AccessControlService
from customer_ai_runtime.application.admin import AdminService
from customer_ai_runtime.application.chat import ChatService
from customer_ai_runtime.application.handoff import HandoffService
from customer_ai_runtime.application.knowledge import KnowledgeService
from customer_ai_runtime.application.routing import RoutingService
from customer_ai_runtime.application.runtime import DiagnosticsService, MetricsService, RuntimeConfigService
from customer_ai_runtime.application.session import SessionService
from customer_ai_runtime.application.tool_catalog import ToolCatalogService
from customer_ai_runtime.application.tooling import ToolService
from customer_ai_runtime.application.voice_rtc import RTCService, VoiceService
from customer_ai_runtime.core.config import Settings
from customer_ai_runtime.providers.base import ASRProvider, BusinessAdapter, LLMProvider, TTSProvider, VectorStoreProvider
from customer_ai_runtime.providers.http_business_provider import HttpBusinessAdapter
from customer_ai_runtime.providers.local import LocalASRProvider, LocalBusinessAdapter, LocalLLMProvider, LocalTTSProvider, LocalVectorStoreProvider
from customer_ai_runtime.providers.openai_provider import OpenAIASRProvider, OpenAILLMProvider, OpenAITTSProvider
from customer_ai_runtime.providers.qdrant_provider import QdrantVectorStoreProvider
from customer_ai_runtime.repositories.memory import InMemoryDiagnosticsRepository, InMemoryKnowledgeRepository, InMemoryRTCRepository, InMemorySessionRepository


@dataclass
class Container:
    settings: Settings
    access_control: AccessControlService
    session_service: SessionService
    knowledge_service: KnowledgeService
    tool_catalog: ToolCatalogService
    tool_service: ToolService
    chat_service: ChatService
    voice_service: VoiceService
    rtc_service: RTCService
    admin_service: AdminService


@dataclass
class ContainerOverrides:
    llm_provider: LLMProvider | None = None
    asr_provider: ASRProvider | None = None
    tts_provider: TTSProvider | None = None
    vector_store: VectorStoreProvider | None = None
    business_adapter: BusinessAdapter | None = None
    session_repository: InMemorySessionRepository | None = None
    knowledge_repository: InMemoryKnowledgeRepository | None = None
    rtc_repository: InMemoryRTCRepository | None = None
    diagnostics_repository: InMemoryDiagnosticsRepository | None = None
    extra: dict[str, Any] | None = None


def build_container(settings: Settings, overrides: ContainerOverrides | None = None) -> Container:
    overrides = overrides or ContainerOverrides()
    session_repository = overrides.session_repository or InMemorySessionRepository(settings.storage_root)
    knowledge_repository = overrides.knowledge_repository or InMemoryKnowledgeRepository(settings.storage_root)
    rtc_repository = overrides.rtc_repository or InMemoryRTCRepository(settings.storage_root)
    diagnostics_repository = overrides.diagnostics_repository or InMemoryDiagnosticsRepository(
        storage_root=settings.storage_root
    )

    runtime_config = RuntimeConfigService(settings.storage_root)
    metrics = MetricsService()
    diagnostics = DiagnosticsService(diagnostics_repository)
    access_control = AccessControlService()
    tool_catalog = ToolCatalogService()

    llm_provider = overrides.llm_provider or _build_llm_provider(settings)
    asr_provider = overrides.asr_provider or _build_asr_provider(settings)
    tts_provider = overrides.tts_provider or _build_tts_provider(settings)
    vector_store = overrides.vector_store or _build_vector_store(settings)
    business_adapter = overrides.business_adapter or _build_business_adapter(settings)

    session_service = SessionService(session_repository, diagnostics)
    knowledge_service = KnowledgeService(knowledge_repository, vector_store)
    routing_service = RoutingService(runtime_config)
    tool_service = ToolService(business_adapter, tool_catalog)
    handoff_service = HandoffService()
    chat_service = ChatService(
        session_service=session_service,
        knowledge_service=knowledge_service,
        routing_service=routing_service,
        runtime_config=runtime_config,
        llm_provider=llm_provider,
        tool_service=tool_service,
        handoff_service=handoff_service,
        metrics=metrics,
        diagnostics=diagnostics,
    )
    voice_service = VoiceService(asr_provider, tts_provider, chat_service, metrics, diagnostics)
    rtc_service = RTCService(rtc_repository, session_service, voice_service, metrics, diagnostics)
    admin_service = AdminService(
        settings=settings,
        session_service=session_service,
        knowledge_service=knowledge_service,
        tool_catalog=tool_catalog,
        rtc_service=rtc_service,
        runtime_config=runtime_config,
        metrics=metrics,
        diagnostics=diagnostics,
    )
    return Container(
        settings=settings,
        access_control=access_control,
        session_service=session_service,
        knowledge_service=knowledge_service,
        tool_catalog=tool_catalog,
        tool_service=tool_service,
        chat_service=chat_service,
        voice_service=voice_service,
        rtc_service=rtc_service,
        admin_service=admin_service,
    )


def _build_llm_provider(settings: Settings) -> LLMProvider:
    if settings.llm_provider == "openai":
        return OpenAILLMProvider(settings)
    return LocalLLMProvider()


def _build_asr_provider(settings: Settings) -> ASRProvider:
    if settings.asr_provider == "openai":
        return OpenAIASRProvider(settings)
    return LocalASRProvider()


def _build_tts_provider(settings: Settings) -> TTSProvider:
    if settings.tts_provider == "openai":
        return OpenAITTSProvider(settings)
    return LocalTTSProvider()


def _build_vector_store(settings: Settings) -> VectorStoreProvider:
    if settings.vector_provider == "qdrant":
        return QdrantVectorStoreProvider(settings)
    return LocalVectorStoreProvider()


def _build_business_adapter(settings: Settings) -> BusinessAdapter:
    if settings.business_provider == "http":
        return HttpBusinessAdapter(settings)
    return LocalBusinessAdapter()
