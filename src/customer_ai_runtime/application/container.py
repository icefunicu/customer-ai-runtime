from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from customer_ai_runtime.application.access import AccessControlService
from customer_ai_runtime.application.admin import AdminService
from customer_ai_runtime.application.auth import AuthService, build_builtin_auth_plugins
from customer_ai_runtime.application.business import (
    BusinessContextBuilder,
    IndustryService,
    KnowledgeDomainManager,
    RealTimeBusinessDataProvider,
    ResponseEnhancementOrchestrator,
)
from customer_ai_runtime.application.chat import ChatService
from customer_ai_runtime.application.handoff import HandoffService
from customer_ai_runtime.application.knowledge import KnowledgeService
from customer_ai_runtime.application.plugins import PluginRegistry, build_builtin_plugins
from customer_ai_runtime.application.routing import RoutingService
from customer_ai_runtime.application.runtime import (
    DiagnosticsService,
    MetricsService,
    RuntimeConfigService,
)
from customer_ai_runtime.application.session import SessionService
from customer_ai_runtime.application.tool_catalog import ToolCatalogService
from customer_ai_runtime.application.tooling import ToolService
from customer_ai_runtime.application.voice_rtc import RTCService, VoiceService
from customer_ai_runtime.core.config import Settings
from customer_ai_runtime.providers.aliyun_provider import AliyunASRProvider, AliyunTTSProvider
from customer_ai_runtime.providers.base import (
    ASRProvider,
    BusinessAdapter,
    LLMProvider,
    TTSProvider,
    VectorStoreProvider,
)
from customer_ai_runtime.providers.graphql_business_provider import GraphQLBusinessAdapter
from customer_ai_runtime.providers.grpc_business_provider import GrpcBusinessAdapter
from customer_ai_runtime.providers.http_business_provider import HttpBusinessAdapter
from customer_ai_runtime.providers.local import (
    LocalASRProvider,
    LocalBusinessAdapter,
    LocalLLMProvider,
    LocalTTSProvider,
    LocalVectorStoreProvider,
)
from customer_ai_runtime.providers.milvus_provider import MilvusVectorStoreProvider
from customer_ai_runtime.providers.openai_provider import (
    OpenAIASRProvider,
    OpenAILLMProvider,
    OpenAITTSProvider,
)
from customer_ai_runtime.providers.pinecone_provider import PineconeVectorStoreProvider
from customer_ai_runtime.providers.qdrant_provider import QdrantVectorStoreProvider
from customer_ai_runtime.providers.tencent_provider import TencentASRProvider, TencentTTSProvider
from customer_ai_runtime.repositories.memory import (
    InMemoryDiagnosticsRepository,
    InMemoryKnowledgeRepository,
    InMemoryRTCRepository,
    InMemorySessionRepository,
)


@dataclass
class Container:
    settings: Settings
    runtime_config: RuntimeConfigService
    plugin_registry: PluginRegistry
    auth_service: AuthService
    access_control: AccessControlService
    session_service: SessionService
    knowledge_service: KnowledgeService
    business_context_builder: BusinessContextBuilder
    knowledge_domain_manager: KnowledgeDomainManager
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
    session_repository = overrides.session_repository or InMemorySessionRepository(
        settings.storage_root
    )
    knowledge_repository = overrides.knowledge_repository or InMemoryKnowledgeRepository(
        settings.storage_root
    )
    rtc_repository = overrides.rtc_repository or InMemoryRTCRepository(settings.storage_root)
    diagnostics_repository = overrides.diagnostics_repository or InMemoryDiagnosticsRepository(
        storage_root=settings.storage_root
    )

    runtime_config = RuntimeConfigService(settings.storage_root)
    metrics = MetricsService()
    diagnostics = DiagnosticsService(diagnostics_repository)
    plugin_registry = PluginRegistry(
        persisted_states=runtime_config.get_plugin_states(),
        on_state_change=runtime_config.set_plugin_state,
    )
    access_control = AccessControlService()

    llm_provider = overrides.llm_provider or _build_llm_provider(settings)
    asr_provider = overrides.asr_provider or _build_asr_provider(settings)
    tts_provider = overrides.tts_provider or _build_tts_provider(settings)
    vector_store = overrides.vector_store or _build_vector_store(settings)
    business_adapter = overrides.business_adapter or _build_business_adapter(settings)
    for plugin in build_builtin_auth_plugins(settings):
        plugin_registry.register(plugin)
    for plugin in build_builtin_plugins(runtime_config, business_adapter):
        plugin_registry.register(plugin)
    auth_service = AuthService(plugin_registry)
    tool_catalog = ToolCatalogService(plugin_registry)

    session_service = SessionService(session_repository, diagnostics)
    knowledge_service = KnowledgeService(knowledge_repository, vector_store)
    industry_service = IndustryService(plugin_registry)
    business_context_builder = BusinessContextBuilder(plugin_registry, industry_service)
    knowledge_domain_manager = KnowledgeDomainManager(settings.get_knowledge_domain_map())
    business_data_provider = RealTimeBusinessDataProvider(plugin_registry, business_adapter)
    routing_service = RoutingService(plugin_registry, runtime_config)
    tool_service = ToolService(business_data_provider, tool_catalog)
    handoff_service = HandoffService(plugin_registry)
    response_enhancement_orchestrator = ResponseEnhancementOrchestrator(plugin_registry)
    chat_service = ChatService(
        session_service=session_service,
        knowledge_service=knowledge_service,
        routing_service=routing_service,
        runtime_config=runtime_config,
        business_context_builder=business_context_builder,
        knowledge_domain_manager=knowledge_domain_manager,
        llm_provider=llm_provider,
        tool_service=tool_service,
        handoff_service=handoff_service,
        response_enhancer=response_enhancement_orchestrator,
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
        plugin_registry=plugin_registry,
    )
    return Container(
        settings=settings,
        runtime_config=runtime_config,
        plugin_registry=plugin_registry,
        auth_service=auth_service,
        access_control=access_control,
        session_service=session_service,
        knowledge_service=knowledge_service,
        business_context_builder=business_context_builder,
        knowledge_domain_manager=knowledge_domain_manager,
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
    if settings.asr_provider == "aliyun":
        return AliyunASRProvider(settings)
    if settings.asr_provider == "tencent":
        return TencentASRProvider(settings)
    return LocalASRProvider()


def _build_tts_provider(settings: Settings) -> TTSProvider:
    if settings.tts_provider == "openai":
        return OpenAITTSProvider(settings)
    if settings.tts_provider == "aliyun":
        return AliyunTTSProvider(settings)
    if settings.tts_provider == "tencent":
        return TencentTTSProvider(settings)
    return LocalTTSProvider()


def _build_vector_store(settings: Settings) -> VectorStoreProvider:
    if settings.vector_provider == "qdrant":
        return QdrantVectorStoreProvider(settings)
    if settings.vector_provider == "pinecone":
        return PineconeVectorStoreProvider(settings)
    if settings.vector_provider == "milvus":
        return MilvusVectorStoreProvider(settings)
    return LocalVectorStoreProvider()


def _build_business_adapter(settings: Settings) -> BusinessAdapter:
    if settings.business_provider == "http":
        return HttpBusinessAdapter(settings)
    if settings.business_provider == "graphql":
        return GraphQLBusinessAdapter(settings)
    if settings.business_provider == "grpc":
        return GrpcBusinessAdapter(settings)
    return LocalBusinessAdapter()
