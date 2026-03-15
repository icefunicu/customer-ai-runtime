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


def _percentile_ms(values: list[int], quantile: float) -> float | None:
    if not values:
        return None
    if quantile <= 0:
        return float(min(values))
    if quantile >= 1:
        return float(max(values))
    ordered = sorted(values)
    index = int(round((len(ordered) - 1) * quantile))
    index = max(0, min(index, len(ordered) - 1))
    return float(ordered[index])


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
            str(session.satisfaction_score)
            for session in rated_sessions
            if session.satisfaction_score is not None
        )
        resolved_sessions = [
            session for session in sessions if session.resolution_status is not None
        ]
        resolution_distribution = Counter(
            session.resolution_status.value
            for session in resolved_sessions
            if session.resolution_status is not None
        )
        feedback_messages = [
            message
            for session in sessions
            for message in session.messages
            if message.feedback_type is not None
        ]
        feedback_distribution = Counter(
            message.feedback_type.value
            for message in feedback_messages
            if message.feedback_type is not None
        )
        average_satisfaction = None
        if rated_sessions:
            average_satisfaction = round(
                sum(session.satisfaction_score or 0 for session in rated_sessions)
                / len(rated_sessions),
                2,
            )
        tracked_sessions = [
            session for session in sessions if session.first_response_time is not None
        ]
        channel_breakdown: dict[str, dict[str, Any]] = {}
        for channel in {session.channel for session in tracked_sessions}:
            channel_sessions = [
                session for session in tracked_sessions if session.channel == channel
            ]
            channel_breakdown[channel] = {
                "sessions": len(channel_sessions),
                "first_response_avg_ms": round(
                    sum(session.first_response_time or 0 for session in channel_sessions)
                    / len(channel_sessions),
                    2,
                ),
                "avg_response_avg_ms": round(
                    sum(session.avg_response_time or 0.0 for session in channel_sessions)
                    / len(channel_sessions),
                    2,
                ),
            }

        duration_samples: list[int] = []
        duration_by_channel: dict[str, list[int]] = {}
        for event in diagnostics:
            duration = event.context.get("duration_ms")
            event_channel = event.context.get("channel")
            if not isinstance(duration, int) or duration <= 0:
                continue
            if not isinstance(event_channel, str) or not event_channel:
                continue
            duration_samples.append(duration)
            duration_by_channel.setdefault(event_channel, []).append(duration)

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
            "feedback_summary": {
                "feedback_count": len(feedback_messages),
                "distribution": dict(feedback_distribution),
            },
            "response_time_summary": {
                "tracked_sessions": len(tracked_sessions),
                "first_response_avg_ms": None
                if not tracked_sessions
                else round(
                    sum(session.first_response_time or 0 for session in tracked_sessions)
                    / len(tracked_sessions),
                    2,
                ),
                "avg_response_avg_ms": None
                if not tracked_sessions
                else round(
                    sum(session.avg_response_time or 0.0 for session in tracked_sessions)
                    / len(tracked_sessions),
                    2,
                ),
                "channel_breakdown": channel_breakdown,
                "turn_duration_sample_size": len(duration_samples),
                "turn_duration_p50_ms": _percentile_ms(duration_samples, 0.50),
                "turn_duration_p95_ms": _percentile_ms(duration_samples, 0.95),
                "turn_duration_channel_breakdown": {
                    channel: {
                        "sample_size": len(samples),
                        "p50_ms": _percentile_ms(samples, 0.50),
                        "p95_ms": _percentile_ms(samples, 0.95),
                    }
                    for channel, samples in duration_by_channel.items()
                },
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

    def get_knowledge_health_report(self, tenant_id: str, knowledge_base_id: str) -> dict[str, Any]:
        return self.knowledge_service.health_report(tenant_id, knowledge_base_id)

    def list_knowledge_versions(
        self, tenant_id: str, knowledge_base_id: str
    ) -> list[dict[str, Any]]:
        return [
            version.model_dump(mode="json")
            for version in self.knowledge_service.list_versions(tenant_id, knowledge_base_id)
        ]

    async def create_knowledge_version_snapshot(
        self,
        *,
        tenant_id: str,
        knowledge_base_id: str,
        description: str,
        source_version_id: str | None = None,
    ) -> dict[str, Any]:
        version = await self.knowledge_service.create_version_snapshot(
            tenant_id=tenant_id,
            knowledge_base_id=knowledge_base_id,
            description=description,
            source_version_id=source_version_id,
        )
        knowledge_base = self.knowledge_service.get_knowledge_base(tenant_id, knowledge_base_id)
        return {
            "knowledge_base": knowledge_base.model_dump(mode="json"),
            "version": version.model_dump(mode="json"),
        }

    def activate_knowledge_version(
        self,
        *,
        tenant_id: str,
        knowledge_base_id: str,
        version_id: str,
    ) -> dict[str, Any]:
        version = self.knowledge_service.activate_version(tenant_id, knowledge_base_id, version_id)
        knowledge_base = self.knowledge_service.get_knowledge_base(tenant_id, knowledge_base_id)
        return {
            "knowledge_base": knowledge_base.model_dump(mode="json"),
            "version": version.model_dump(mode="json"),
        }

    def get_chunk_optimization_report(
        self, tenant_id: str, knowledge_base_id: str
    ) -> dict[str, Any]:
        miss_queries = [
            str(event.context.get("query") or "").strip()
            for event in self.diagnostics_service.query(
                tenant_id=tenant_id,
                code_prefix="knowledge.retrieve_miss",
                limit=50,
            )
            if str(event.context.get("knowledge_base_id")) == knowledge_base_id
            and str(event.context.get("query") or "").strip()
        ]
        return self.knowledge_service.chunk_optimization_report(
            tenant_id,
            knowledge_base_id,
            miss_queries=miss_queries,
        )

    async def apply_chunk_optimization(
        self,
        *,
        tenant_id: str,
        knowledge_base_id: str,
        max_tokens: int,
        overlap: int,
        description: str = "",
        activate: bool = True,
    ) -> dict[str, Any]:
        result = await self.knowledge_service.apply_chunk_optimization(
            tenant_id,
            knowledge_base_id,
            max_tokens=max_tokens,
            overlap=overlap,
            description=description,
            activate=activate,
        )
        return {
            "knowledge_base": result["knowledge_base"].model_dump(mode="json"),
            "version": result["version"].model_dump(mode="json"),
            "document_count": result["document_count"],
            "chunk_count": result["chunk_count"],
        }

    def get_retrieval_miss_report(
        self,
        *,
        tenant_id: str,
        knowledge_base_id: str | None = None,
        limit: int = 20,
    ) -> dict[str, Any]:
        events = self.diagnostics_service.query(
            tenant_id=tenant_id,
            level=None,
            code_prefix="knowledge.retrieve_miss",
            limit=200,
        )
        filtered_events = [
            event
            for event in events
            if knowledge_base_id is None
            or str(event.context.get("knowledge_base_id")) == knowledge_base_id
        ]
        counts: Counter[str] = Counter()
        samples: dict[str, dict[str, Any]] = {}
        for event in filtered_events:
            query = str(event.context.get("query") or "").strip()
            if not query:
                continue
            counts[query] += 1
            samples.setdefault(
                query,
                {
                    "knowledge_base_id": event.context.get("knowledge_base_id"),
                    "top_score": event.context.get("top_score"),
                    "channel": event.context.get("channel"),
                },
            )
        top_queries = [
            {
                "query": query,
                "count": count,
                **samples.get(query, {}),
            }
            for query, count in counts.most_common(limit)
        ]
        return {
            "tenant_id": tenant_id,
            "knowledge_base_id": knowledge_base_id,
            "miss_count": sum(counts.values()),
            "top_queries": top_queries,
        }

    def get_knowledge_effectiveness_report(
        self,
        *,
        tenant_id: str,
        knowledge_base_id: str | None = None,
    ) -> dict[str, Any]:
        events = self.diagnostics_service.query(
            tenant_id=tenant_id,
            code_prefix="chat.knowledge_retrieved",
            limit=500,
        )
        filtered_events = [
            event
            for event in events
            if knowledge_base_id is None
            or str(event.context.get("knowledge_base_id")) == knowledge_base_id
        ]
        grouped_events: dict[str, list[Any]] = {}
        for event in filtered_events:
            kb_id = str(event.context.get("knowledge_base_id") or "").strip()
            if not kb_id:
                continue
            grouped_events.setdefault(kb_id, []).append(event)

        sessions = self.session_service.list_by_tenant(tenant_id)
        session_satisfaction: dict[str, list[int]] = {}
        response_stats: dict[str, dict[str, int]] = {}
        version_stats: dict[str, Counter[str]] = {}
        for session in sessions:
            session_kbs: set[str] = set()
            for message in session.messages:
                kb_id = str(message.metadata.get("knowledge_base_id") or "").strip()
                if not kb_id:
                    continue
                session_kbs.add(kb_id)
                version_id = str(message.metadata.get("knowledge_version_id") or "").strip()
                if version_id:
                    version_stats.setdefault(kb_id, Counter())[version_id] += 1
                kb_stats = response_stats.setdefault(
                    kb_id,
                    {
                        "response_count": 0,
                        "feedback_count": 0,
                        "negative_feedback_count": 0,
                    },
                )
                if message.role.value == "assistant":
                    kb_stats["response_count"] += 1
                    if message.feedback_type is not None:
                        kb_stats["feedback_count"] += 1
                        if message.feedback_type.value in {"downvote", "request_human"}:
                            kb_stats["negative_feedback_count"] += 1
            if session.satisfaction_score is not None:
                for kb_id in session_kbs:
                    session_satisfaction.setdefault(kb_id, []).append(session.satisfaction_score)

        items: list[dict[str, Any]] = []
        for kb_id, kb_events in grouped_events.items():
            kb_stats = response_stats.get(
                kb_id,
                {"response_count": 0, "feedback_count": 0, "negative_feedback_count": 0},
            )
            effective_hits = sum(
                1 for event in kb_events if bool(event.context.get("effective_hit"))
            )
            total_queries = len(kb_events)
            hit_rate = 0.0 if total_queries == 0 else round(effective_hits / total_queries, 4)
            satisfaction_scores = session_satisfaction.get(kb_id, [])
            average_satisfaction = (
                None
                if not satisfaction_scores
                else round(sum(satisfaction_scores) / len(satisfaction_scores), 2)
            )
            negative_feedback_rate = (
                0.0
                if kb_stats["response_count"] == 0
                else round(kb_stats["negative_feedback_count"] / kb_stats["response_count"], 4)
            )
            items.append(
                {
                    "knowledge_base_id": kb_id,
                    "query_count": total_queries,
                    "effective_hit_count": effective_hits,
                    "miss_count": total_queries - effective_hits,
                    "hit_rate": hit_rate,
                    "rated_sessions": len(satisfaction_scores),
                    "average_satisfaction": average_satisfaction,
                    "response_count": kb_stats["response_count"],
                    "feedback_count": kb_stats["feedback_count"],
                    "negative_feedback_count": kb_stats["negative_feedback_count"],
                    "negative_feedback_rate": negative_feedback_rate,
                    "active_versions": dict(version_stats.get(kb_id, Counter())),
                    "recommendation": self._knowledge_effectiveness_recommendation(
                        hit_rate=hit_rate,
                        negative_feedback_rate=negative_feedback_rate,
                        average_satisfaction=average_satisfaction,
                    ),
                }
            )
        items.sort(key=lambda item: (item["hit_rate"], item["negative_feedback_rate"]))
        return {
            "tenant_id": tenant_id,
            "knowledge_base_id": knowledge_base_id,
            "knowledge_bases": items,
        }

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

    def _knowledge_effectiveness_recommendation(
        self,
        *,
        hit_rate: float,
        negative_feedback_rate: float,
        average_satisfaction: float | None,
    ) -> str:
        if hit_rate < 0.5:
            return "优先补充高频缺口问题，并重新评估切片策略。"
        if negative_feedback_rate >= 0.25:
            return "命中率尚可，但回答可用性偏低，建议优化内容表达或业务衔接。"
        if average_satisfaction is not None and average_satisfaction < 4:
            return "建议结合满意度回溯知识内容是否过时或缺少操作指引。"
        return "当前知识库效果稳定，可继续关注新增缺口与版本迭代。"

    def _llm_ready(self) -> bool:
        if self.settings.llm_provider == "openai":
            return bool(self.settings.openai_api_key)
        return True

    def _asr_ready(self) -> bool:
        if self.settings.asr_provider == "openai":
            return bool(self.settings.openai_api_key)
        if self.settings.asr_provider == "aliyun":
            return (
                bool(self.settings.aliyun_access_key_id)
                and bool(self.settings.aliyun_access_key_secret)
                and bool(self.settings.aliyun_app_key)
            )
        if self.settings.asr_provider == "tencent":
            return bool(self.settings.tencent_secret_id) and bool(self.settings.tencent_secret_key)
        return True

    def _tts_ready(self) -> bool:
        if self.settings.tts_provider == "openai":
            return bool(self.settings.openai_api_key)
        if self.settings.tts_provider == "aliyun":
            return (
                bool(self.settings.aliyun_access_key_id)
                and bool(self.settings.aliyun_access_key_secret)
                and bool(self.settings.aliyun_app_key)
            )
        if self.settings.tts_provider == "tencent":
            return bool(self.settings.tencent_secret_id) and bool(self.settings.tencent_secret_key)
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
