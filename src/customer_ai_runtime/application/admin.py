from __future__ import annotations

from collections import Counter
from typing import Any

from customer_ai_runtime.application.knowledge import KnowledgeService
from customer_ai_runtime.application.plugins import PluginRegistry
from customer_ai_runtime.application.runtime import (
    DiagnosticsService,
    MetricsService,
    RuntimeConfigService,
)
from customer_ai_runtime.application.session import SessionService
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
        return [
            session.model_dump(mode="json")
            for session in self.session_service.list_by_tenant(tenant_id)
        ]

    def get_metrics(self) -> dict[str, Any]:
        return self.metrics.snapshot()

    def get_metrics_summary(self, tenant_id: str | None = None) -> dict[str, Any]:
        sessions = self.session_service.list_by_tenant(tenant_id) if tenant_id else []
        diagnostics = self.diagnostics_service.query(tenant_id=tenant_id, limit=200)
        level_counts = Counter(event.level.value for event in diagnostics)
        route_counts = {
            key.removeprefix("route_"): value
            for key, value in self.metrics.snapshot().items()
            if key.startswith("route_")
        }
        waiting_human = sum(1 for session in sessions if session.waiting_human)
        rated_sessions = [session for session in sessions if session.satisfaction_score is not None]
        satisfaction_distribution = Counter(
            str(session.satisfaction_score) for session in rated_sessions if session.satisfaction_score is not None
        )
        resolved_sessions = [session for session in sessions if session.resolution_status is not None]
        resolution_distribution = Counter(
            session.resolution_status.value
            for session in resolved_sessions
            if session.resolution_status is not None
        )
        average_satisfaction = None
        if rated_sessions:
            average_satisfaction = round(
                sum(session.satisfaction_score or 0 for session in rated_sessions) / len(rated_sessions),
                2,
            )
        return {
            "tenant_id": tenant_id,
            "counters": self.metrics.snapshot(),
            "route_counts": route_counts,
            "session_summary": {
                "total": len(sessions),
                "waiting_human": waiting_human,
                "active": sum(1 for session in sessions if session.state.value == "active"),
                "closed": sum(1 for session in sessions if session.state.value == "closed"),
            },
            "satisfaction_summary": {
                "rated_sessions": len(rated_sessions),
                "average_score": average_satisfaction,
                "distribution": dict(satisfaction_distribution),
            },
            "resolution_summary": {
                "marked_sessions": len(resolved_sessions),
                "distribution": dict(resolution_distribution),
            },
            "diagnostic_summary": {
                "sample_size": len(diagnostics),
                "info": level_counts.get("info", 0),
                "warning": level_counts.get("warning", 0),
                "error": level_counts.get("error", 0),
            },
        }

    def get_runtime_config(self) -> dict[str, Any]:
        return self.runtime_config.snapshot()

    def update_runtime_config(self, data: dict[str, Any]) -> dict[str, Any]:
        prompts = data.get("prompts")
        if prompts:
            self.runtime_config.update_prompts(prompts)
        policies = data.get("policies")
        if policies:
            self.runtime_config.update_policies(policies)
        alerts = data.get("alerts")
        if alerts:
            self.runtime_config.update_alert_rules(alerts)
        plugin_states = data.get("plugin_states")
        if isinstance(plugin_states, dict):
            for plugin_id, enabled in plugin_states.items():
                if bool(enabled):
                    self.plugin_registry.enable(str(plugin_id))
                else:
                    self.plugin_registry.disable(str(plugin_id))
        return self.get_runtime_config()

    def get_prompts(self) -> dict[str, Any]:
        return self.runtime_config.get_prompts().model_dump(mode="json")

    def update_prompts(self, data: dict[str, Any]) -> dict[str, Any]:
        return self.runtime_config.update_prompts(data).model_dump(mode="json")

    def get_policies(self) -> dict[str, Any]:
        return self.runtime_config.get_policies().model_dump(mode="json")

    def update_policies(self, data: dict[str, Any]) -> dict[str, Any]:
        return self.runtime_config.update_policies(data).model_dump(mode="json")

    def diagnostics(
        self,
        *,
        tenant_id: str | None = None,
        session_id: str | None = None,
        room_id: str | None = None,
        level: str | None = None,
        code_prefix: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        return [
            event.model_dump(mode="json")
            for event in self.diagnostics_service.query(
                tenant_id=tenant_id,
                session_id=session_id,
                room_id=room_id,
                level=level,
                code_prefix=code_prefix,
                limit=limit,
            )
        ]

    def list_knowledge_bases(self, tenant_id: str) -> list[dict[str, Any]]:
        return [
            knowledge_base.model_dump(mode="json")
            for knowledge_base in self.knowledge_service.list_knowledge_bases(tenant_id)
        ]

    def list_rooms(self, tenant_id: str) -> list[dict[str, Any]]:
        return [room.model_dump(mode="json") for room in self.rtc_service.list_rooms(tenant_id)]

    def get_session_monitor(self, tenant_id: str, session_id: str) -> dict[str, Any]:
        session = self.session_service.get(tenant_id, session_id)
        related_rooms = [
            room.model_dump(mode="json")
            for room in self.rtc_service.list_rooms(tenant_id)
            if room.session_id == session_id
        ]
        diagnostics = self.diagnostics(
            tenant_id=tenant_id,
            session_id=session_id,
            limit=100,
        )
        return {
            "session": session.model_dump(mode="json"),
            "message_count": len(session.messages),
            "last_message": None
            if not session.messages
            else session.messages[-1].model_dump(mode="json"),
            "related_rooms": related_rooms,
            "diagnostics": diagnostics,
        }

    def get_alerts(self, tenant_id: str | None = None) -> list[dict[str, Any]]:
        alerts: list[dict[str, Any]] = []
        rules = self.runtime_config.get_alert_rules()

        if rules.provider_not_ready_enabled:
            not_ready_providers = [
                {
                    "name": provider_name,
                    "provider": payload["provider"],
                }
                for provider_name, payload in self.provider_health().items()
                if not payload["ready"]
            ]
            if not_ready_providers:
                alerts.append(
                    {
                        "severity": "critical",
                        "code": "provider.not_ready",
                        "message": "one or more providers are not ready",
                        "scope": {"tenant_id": tenant_id},
                        "count": len(not_ready_providers),
                        "providers": not_ready_providers,
                    }
                )

        error_events = self.diagnostics_service.query(
            tenant_id=tenant_id,
            level="error",
            limit=rules.diagnostic_error_sample_limit,
        )
        if len(error_events) >= rules.diagnostic_error_threshold:
            alerts.append(
                {
                    "severity": "warning",
                    "code": "diagnostic.error_threshold",
                    "message": "diagnostic error threshold reached",
                    "scope": {"tenant_id": tenant_id},
                    "count": len(error_events),
                    "threshold": rules.diagnostic_error_threshold,
                    "events": [
                        {
                            "event_id": event.event_id,
                            "code": event.code,
                            "message": event.message,
                            "context": event.context,
                        }
                        for event in error_events[:5]
                    ],
                }
            )

        if tenant_id is not None:
            waiting_sessions = [
                session
                for session in self.session_service.list_by_tenant(tenant_id)
                if session.waiting_human
            ]
            if len(waiting_sessions) >= rules.waiting_human_session_threshold:
                alerts.append(
                    {
                        "severity": "warning",
                        "code": "session.waiting_human_threshold",
                        "message": "waiting human session threshold reached",
                        "scope": {"tenant_id": tenant_id},
                        "count": len(waiting_sessions),
                        "threshold": rules.waiting_human_session_threshold,
                        "sessions": [
                            {
                                "session_id": session.session_id,
                                "state": session.state.value,
                            }
                            for session in waiting_sessions[
                                : rules.waiting_human_session_sample_limit
                            ]
                        ],
                    }
                )
        return alerts

    def provider_health(self) -> dict[str, dict[str, Any]]:
        return {
            "llm": {
                "provider": self.settings.llm_provider,
                "ready": self._llm_ready(),
            },
            "asr": {
                "provider": self.settings.asr_provider,
                "ready": self._asr_ready(),
            },
            "tts": {
                "provider": self.settings.tts_provider,
                "ready": self._tts_ready(),
            },
            "vector": {
                "provider": self.settings.vector_provider,
                "ready": self._vector_ready(),
            },
            "business": {
                "provider": self.settings.business_provider,
                "ready": self._business_ready(),
            },
            "rtc": {
                "provider": self.settings.rtc_provider,
                "ready": True,
            },
        }

    def tool_catalog_items(
        self,
        *,
        tenant_id: str | None = None,
        industry: str | None = None,
        channel: str | None = None,
        include_disabled: bool = True,
    ) -> list[dict[str, Any]]:
        return self.tool_catalog.list_tools(
            tenant_id=tenant_id,
            industry=industry,
            channel=channel,
            include_disabled=include_disabled,
        )

    def tool_category_items(
        self,
        *,
        tenant_id: str | None = None,
        industry: str | None = None,
        channel: str | None = None,
        include_disabled: bool = True,
    ) -> list[dict[str, Any]]:
        return self.tool_catalog.list_categories(
            tenant_id=tenant_id,
            industry=industry,
            channel=channel,
            include_disabled=include_disabled,
        )

    def list_plugins(self) -> list[dict[str, Any]]:
        return [
            descriptor.model_dump(mode="json")
            for descriptor in self.plugin_registry.list_descriptors()
        ]

    def enable_plugin(self, plugin_id: str) -> dict[str, Any]:
        return self.plugin_registry.enable(plugin_id).model_dump(mode="json")

    def disable_plugin(self, plugin_id: str) -> dict[str, Any]:
        return self.plugin_registry.disable(plugin_id).model_dump(mode="json")

    def _llm_ready(self) -> bool:
        if self.settings.llm_provider == "openai":
            return bool(self.settings.openai_api_key)
        return True

    def _asr_ready(self) -> bool:
        if self.settings.asr_provider == "openai":
            return bool(self.settings.openai_api_key)
        if self.settings.asr_provider == "aliyun":
            return bool(self.settings.aliyun_access_key_id) and bool(
                self.settings.aliyun_access_key_secret
            ) and bool(self.settings.aliyun_app_key)
        if self.settings.asr_provider == "tencent":
            return bool(self.settings.tencent_secret_id) and bool(
                self.settings.tencent_secret_key
            )
        return True

    def _tts_ready(self) -> bool:
        if self.settings.tts_provider == "openai":
            return bool(self.settings.openai_api_key)
        if self.settings.tts_provider == "aliyun":
            return bool(self.settings.aliyun_access_key_id) and bool(
                self.settings.aliyun_access_key_secret
            ) and bool(self.settings.aliyun_app_key)
        if self.settings.tts_provider == "tencent":
            return bool(self.settings.tencent_secret_id) and bool(
                self.settings.tencent_secret_key
            )
        return True

    def _vector_ready(self) -> bool:
        if self.settings.vector_provider == "qdrant":
            return bool(self.settings.qdrant_url)
        if self.settings.vector_provider == "pinecone":
            return bool(self.settings.pinecone_api_key) and bool(
                self.settings.pinecone_index_host or self.settings.pinecone_index_name
            )
        if self.settings.vector_provider == "milvus":
            return bool(self.settings.milvus_uri)
        return True

    def _business_ready(self) -> bool:
        if self.settings.business_provider == "http":
            return bool(self.settings.business_api_base_url)
        if self.settings.business_provider == "graphql":
            return bool(self.settings.business_graphql_endpoint)
        if self.settings.business_provider == "grpc":
            return bool(self.settings.business_grpc_target)
        return True
