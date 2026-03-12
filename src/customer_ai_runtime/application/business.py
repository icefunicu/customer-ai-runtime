from __future__ import annotations

import re
from typing import Any

from customer_ai_runtime.application.plugins import (
    BusinessToolPlugin,
    ContextEnricherPlugin,
    IndustryAdapterPlugin,
    PluginRegistry,
    ResponsePostProcessorPlugin,
    context_to_plugin_context,
    merge_context_payload,
)
from customer_ai_runtime.domain.models import BusinessQuery, BusinessResult, Session
from customer_ai_runtime.domain.platform import BusinessContext, IndustryMatchResult, PluginKind
from customer_ai_runtime.providers.base import BusinessAdapter


class IndustryService:
    def __init__(self, registry: PluginRegistry) -> None:
        self._registry = registry

    async def detect(
        self,
        context: BusinessContext,
        user_message: str | None = None,
    ) -> IndustryMatchResult:
        plugin_context = context_to_plugin_context(
            tenant_id=context.tenant_id,
            channel=context.channel,
            session_id=context.session_id,
            user_message=user_message,
            industry=context.industry,
            integration_context=context.integration_context,
            host_auth_context=context.host_auth_context,
            business_context=context,
        )
        best = IndustryMatchResult(
            industry=context.industry,
            matched=bool(context.industry),
            confidence=0.99 if context.industry else 0.0,
        )
        for plugin in self._registry.resolve(
            PluginKind.INDUSTRY_ADAPTER,
            tenant_id=context.tenant_id,
            industry=context.industry,
            channel=context.channel,
        ):
            if not isinstance(plugin, IndustryAdapterPlugin):
                continue
            result = await plugin.match_industry(plugin_context)
            if result.matched and result.confidence > best.confidence:
                best = result
        return best

    async def enrich(self, context: BusinessContext) -> dict[str, Any]:
        if not context.industry:
            return {}
        payload: dict[str, Any] = {}
        plugin_context = context_to_plugin_context(
            tenant_id=context.tenant_id,
            channel=context.channel,
            session_id=context.session_id,
            user_message=None,
            industry=context.industry,
            integration_context=context.integration_context,
            host_auth_context=context.host_auth_context,
            business_context=context,
        )
        for plugin in self._registry.resolve(
            PluginKind.INDUSTRY_ADAPTER,
            tenant_id=context.tenant_id,
            industry=context.industry,
            channel=context.channel,
        ):
            if not isinstance(plugin, IndustryAdapterPlugin):
                continue
            matched = await plugin.match_industry(plugin_context)
            if matched.industry != context.industry:
                continue
            payload = merge_context_payload(payload, await plugin.enrich_context(plugin_context))
        return payload


class BusinessContextBuilder:
    def __init__(self, registry: PluginRegistry, industry_service: IndustryService) -> None:
        self._registry = registry
        self._industry_service = industry_service

    async def build(
        self,
        *,
        tenant_id: str,
        channel: str,
        session: Session | None,
        integration_context: dict[str, Any] | None,
        host_auth_context: Any = None,
        user_message: str | None = None,
    ) -> BusinessContext:
        context = BusinessContext(
            tenant_id=tenant_id,
            channel=channel,
            session_id=None if session is None else session.session_id,
            industry=(integration_context or {}).get("industry"),
            host_auth_context=host_auth_context,
            integration_context=integration_context or {},
            session_summary="" if session is None else session.summary,
            permissions=[] if not host_auth_context else list(host_auth_context.permissions),
        )
        detected = await self._industry_service.detect(context, user_message=user_message)
        if detected.industry and not context.industry:
            context.industry = detected.industry
        merged = context.model_dump(mode="json")
        merged = merge_context_payload(merged, await self._industry_service.enrich(context))
        plugin_context = context_to_plugin_context(
            tenant_id=context.tenant_id,
            channel=context.channel,
            session_id=context.session_id,
            user_message=user_message,
            industry=context.industry,
            integration_context=context.integration_context,
            host_auth_context=context.host_auth_context,
            business_context=context,
        )
        for plugin in self._registry.resolve(
            PluginKind.CONTEXT_ENRICHER,
            tenant_id=context.tenant_id,
            industry=context.industry,
            channel=context.channel,
        ):
            if not isinstance(plugin, ContextEnricherPlugin):
                continue
            merged = merge_context_payload(merged, await plugin.enrich(plugin_context))
        return BusinessContext.model_validate(merged)


class KnowledgeDomainManager:
    def __init__(self, domain_map: dict[str, object]) -> None:
        self._domain_map = domain_map

    def resolve_primary(
        self,
        tenant_id: str,
        industry: str | None,
        explicit: str | None,
    ) -> str | None:
        if explicit:
            return explicit
        tenant_mapping = self._domain_map.get(tenant_id, {})
        if isinstance(tenant_mapping, dict):
            if industry and tenant_mapping.get(industry):
                return str(tenant_mapping[industry])
            if tenant_mapping.get("default"):
                return str(tenant_mapping["default"])
        global_mapping = self._domain_map.get("default", {})
        if isinstance(global_mapping, dict):
            if industry and global_mapping.get(industry):
                return str(global_mapping[industry])
            if global_mapping.get("default"):
                return str(global_mapping["default"])
        return None


class RealTimeBusinessDataProvider:
    def __init__(self, registry: PluginRegistry, adapter: BusinessAdapter) -> None:
        self._registry = registry
        self._adapter = adapter

    async def execute(
        self,
        *,
        context: BusinessContext,
        tool_name: str,
        parameters: dict[str, Any],
    ) -> BusinessResult:
        plugin_context = context_to_plugin_context(
            tenant_id=context.tenant_id,
            channel=context.channel,
            session_id=context.session_id,
            industry=context.industry,
            integration_context=context.integration_context,
            host_auth_context=context.host_auth_context,
            business_context=context,
        )
        for plugin in self._registry.resolve(
            PluginKind.BUSINESS_TOOL,
            tenant_id=context.tenant_id,
            industry=context.industry,
            channel=context.channel,
        ):
            if isinstance(plugin, BusinessToolPlugin) and plugin.tool_name == tool_name:
                return await plugin.execute(plugin_context, parameters)
        return await self._adapter.execute(
            BusinessQuery(
                tenant_id=context.tenant_id,
                tool_name=tool_name,
                parameters=parameters,
                session_id=context.session_id,
                integration_context=context.integration_context,
            )
        )


class ResponseEnhancementOrchestrator:
    phone_pattern = re.compile(r"(?<!\d)(1\d{2})\d{4}(\d{4})(?!\d)")

    def __init__(self, registry: PluginRegistry) -> None:
        self._registry = registry

    async def enhance(self, response: dict[str, Any], context: BusinessContext) -> dict[str, Any]:
        enhanced = self._normalize_response(response)
        enhanced = self._apply_builtin_enhancements(enhanced, context)
        plugin_context = context_to_plugin_context(
            tenant_id=context.tenant_id,
            channel=context.channel,
            session_id=context.session_id,
            industry=context.industry,
            integration_context=context.integration_context,
            host_auth_context=context.host_auth_context,
            business_context=context,
            route=enhanced.get("route"),
            response=enhanced,
        )
        for plugin in self._registry.resolve(
            PluginKind.RESPONSE_POST_PROCESSOR,
            tenant_id=context.tenant_id,
            industry=context.industry,
            channel=context.channel,
        ):
            if not isinstance(plugin, ResponsePostProcessorPlugin):
                continue
            enhanced = await plugin.process(plugin_context, enhanced)
            enhanced = self._normalize_response(enhanced)
            plugin_context.response = enhanced
        return self._finalize_response(enhanced, context)

    def _normalize_response(self, response: dict[str, Any]) -> dict[str, Any]:
        normalized = dict(response)
        normalized["answer"] = str(normalized.get("answer") or "")
        normalized["citations"] = list(normalized.get("citations") or [])
        if not isinstance(normalized.get("references"), list):
            normalized["references"] = []
        return normalized

    def _apply_builtin_enhancements(
        self,
        response: dict[str, Any],
        context: BusinessContext,
    ) -> dict[str, Any]:
        enhanced = dict(response)
        enhanced = self._format_response_fields(enhanced)
        enhanced["references"] = self._build_references(enhanced.get("citations") or [])
        enhanced["answer"] = self._append_reference_titles(
            enhanced.get("answer", ""),
            enhanced["references"],
        )
        enhanced = self._mask_sensitive_payload(enhanced)
        enhanced = self._ensure_structured_output(enhanced, context)
        return enhanced

    def _finalize_response(
        self,
        response: dict[str, Any],
        context: BusinessContext,
    ) -> dict[str, Any]:
        finalized = self._format_response_fields(response)
        finalized["references"] = self._build_references(finalized.get("citations") or [])
        finalized["answer"] = self._append_reference_titles(
            finalized.get("answer", ""),
            finalized["references"],
        )
        finalized = self._mask_sensitive_payload(finalized)
        finalized = self._ensure_structured_output(finalized, context)
        return finalized

    def _format_response_fields(self, response: dict[str, Any]) -> dict[str, Any]:
        formatted = dict(response)
        formatted["answer"] = self._format_text_block(formatted.get("answer"))
        tool_result = formatted.get("tool_result")
        if isinstance(tool_result, dict):
            formatted_tool_result = dict(tool_result)
            if not formatted["answer"] and formatted_tool_result.get("summary"):
                formatted["answer"] = self._format_text_block(
                    formatted_tool_result.get("summary")
                )
            formatted_tool_result["summary"] = self._format_text_block(
                formatted_tool_result.get("summary")
            )
            formatted["tool_result"] = formatted_tool_result
        handoff = formatted.get("handoff")
        if isinstance(handoff, dict):
            formatted_handoff = dict(handoff)
            for key in ("summary", "recommended_reply", "reason", "intent"):
                formatted_handoff[key] = self._format_text_block(formatted_handoff.get(key))
            formatted["handoff"] = formatted_handoff
        return formatted

    def _append_reference_titles(
        self,
        answer: str,
        references: list[dict[str, Any]],
    ) -> str:
        text = self._format_text_block(answer)
        if not text or not references:
            return text
        if "参考：" in text or "引用：" in text:
            return text
        titles = "、".join(
            reference["title"]
            for reference in references[:2]
            if isinstance(reference, dict) and reference.get("title")
        )
        if not titles:
            return text
        return f"{text} 参考：{titles}。"

    def _build_references(self, citations: list[dict[str, Any]]) -> list[dict[str, Any]]:
        references: list[dict[str, Any]] = []
        for item in citations:
            if not isinstance(item, dict):
                continue
            references.append(
                {
                    "title": item.get("title", ""),
                    "knowledge_base_id": item.get("knowledge_base_id"),
                    "document_id": item.get("document_id"),
                    "score": item.get("score"),
                }
            )
        return references

    def _ensure_structured_output(
        self,
        response: dict[str, Any],
        context: BusinessContext,
    ) -> dict[str, Any]:
        if context.integration_context.get("response_format") != "structured":
            return response
        structured_output = dict(response.get("structured_output") or {})
        structured_output.update(
            {
                "route": response.get("route"),
                "answer": response.get("answer"),
                "industry": response.get("industry"),
                "citations": response.get("citations") or [],
                "references": response.get("references") or [],
                "tool_result": response.get("tool_result"),
                "handoff": response.get("handoff"),
            }
        )
        result = dict(response)
        result["structured_output"] = structured_output
        return result

    def _mask_sensitive_payload(self, value: Any) -> Any:
        if isinstance(value, str):
            return self.phone_pattern.sub(r"\1****\2", value)
        if isinstance(value, list):
            return [self._mask_sensitive_payload(item) for item in value]
        if isinstance(value, dict):
            return {key: self._mask_sensitive_payload(item) for key, item in value.items()}
        return value

    def _format_text_block(self, value: Any) -> str:
        if value is None:
            return ""
        text = str(value).replace("\r\n", "\n").strip()
        if not text:
            return ""
        lines = [re.sub(r"\s+", " ", line).strip() for line in text.split("\n")]
        return "\n".join(line for line in lines if line)
