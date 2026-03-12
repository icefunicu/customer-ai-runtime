from __future__ import annotations

from typing import Any

from customer_ai_runtime.application.plugins import PluginRegistry
from customer_ai_runtime.application.runtime import DiagnosticsService, MetricsService, RuntimeConfigService
from customer_ai_runtime.application.session import SessionService
from customer_ai_runtime.application.knowledge import KnowledgeService
from customer_ai_runtime.application.tool_catalog import ToolCatalogService
from customer_ai_runtime.application.voice_rtc import RTCService
from customer_ai_runtime.core.config import Settings


class AdminService:
    def __init__(
        self,
        settings: Settings,
        session_service: SessionService,
        knowledge_service: KnowledgeService,
        tool_catalog: ToolCatalogService,
        rtc_service: RTCService,
        runtime_config: RuntimeConfigService,
        metrics: MetricsService,
        diagnostics: DiagnosticsService,
        plugin_registry: PluginRegistry,
    ) -> None:
        self.settings = settings
        self.session_service = session_service
        self.knowledge_service = knowledge_service
        self.tool_catalog = tool_catalog
        self.rtc_service = rtc_service
        self.runtime_config = runtime_config
        self.metrics = metrics
        self.diagnostics_service = diagnostics
        self.plugin_registry = plugin_registry

    def list_sessions(self, tenant_id: str) -> list[dict[str, Any]]:
        return [session.model_dump(mode="json") for session in self.session_service.list_by_tenant(tenant_id)]

    def get_metrics(self) -> dict[str, Any]:
        return self.metrics.snapshot()

    def get_prompts(self) -> dict[str, Any]:
        return self.runtime_config.get_prompts().model_dump(mode="json")

    def update_prompts(self, data: dict[str, Any]) -> dict[str, Any]:
        return self.runtime_config.update_prompts(data).model_dump(mode="json")

    def get_policies(self) -> dict[str, Any]:
        return self.runtime_config.get_policies().model_dump(mode="json")

    def update_policies(self, data: dict[str, Any]) -> dict[str, Any]:
        return self.runtime_config.update_policies(data).model_dump(mode="json")

    def diagnostics(self) -> list[dict[str, Any]]:
        return [event.model_dump(mode="json") for event in self.diagnostics_service.list_recent()]

    def list_knowledge_bases(self, tenant_id: str) -> list[dict[str, Any]]:
        return [
            knowledge_base.model_dump(mode="json")
            for knowledge_base in self.knowledge_service.list_knowledge_bases(tenant_id)
        ]

    def list_rooms(self, tenant_id: str) -> list[dict[str, Any]]:
        return [room.model_dump(mode="json") for room in self.rtc_service.list_rooms(tenant_id)]

    def provider_health(self) -> dict[str, dict[str, Any]]:
        return {
            "llm": {
                "provider": self.settings.llm_provider,
                "ready": self.settings.llm_provider != "openai" or bool(self.settings.openai_api_key),
            },
            "asr": {
                "provider": self.settings.asr_provider,
                "ready": self.settings.asr_provider != "openai" or bool(self.settings.openai_api_key),
            },
            "tts": {
                "provider": self.settings.tts_provider,
                "ready": self.settings.tts_provider != "openai" or bool(self.settings.openai_api_key),
            },
            "vector": {
                "provider": self.settings.vector_provider,
                "ready": self.settings.vector_provider != "qdrant" or bool(self.settings.qdrant_url),
            },
            "business": {
                "provider": self.settings.business_provider,
                "ready": self.settings.business_provider != "http"
                or bool(self.settings.business_api_base_url),
            },
            "rtc": {
                "provider": self.settings.rtc_provider,
                "ready": True,
            },
        }

    def tool_catalog_items(self) -> list[dict[str, Any]]:
        return self.tool_catalog.list_tools()

    def list_plugins(self) -> list[dict[str, Any]]:
        return [descriptor.model_dump(mode="json") for descriptor in self.plugin_registry.list_descriptors()]

    def enable_plugin(self, plugin_id: str) -> dict[str, Any]:
        return self.plugin_registry.enable(plugin_id).model_dump(mode="json")

    def disable_plugin(self, plugin_id: str) -> dict[str, Any]:
        return self.plugin_registry.disable(plugin_id).model_dump(mode="json")
