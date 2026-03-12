from __future__ import annotations

from typing import Any

from customer_ai_runtime.application.plugins import BusinessToolPlugin, PluginRegistry
from customer_ai_runtime.core.errors import AppError
from customer_ai_runtime.domain.platform import PluginDescriptor, PluginKind


class ToolCatalogService:
    def __init__(self, registry: PluginRegistry) -> None:
        self._registry = registry

    def list_tools(
        self,
        *,
        tenant_id: str | None = None,
        industry: str | None = None,
        channel: str | None = None,
        include_disabled: bool = True,
    ) -> list[dict[str, Any]]:
        items = []
        for plugin in self._iter_plugins():
            if not include_disabled and not plugin.descriptor.enabled:
                continue
            if not self._scope_match(plugin.descriptor, tenant_id, industry, channel):
                continue
            items.append(
                self._serialize_tool(
                    plugin,
                    tenant_id=tenant_id,
                    industry=industry,
                    channel=channel,
                )
            )
        return items

    def list_categories(
        self,
        *,
        tenant_id: str | None = None,
        industry: str | None = None,
        channel: str | None = None,
        include_disabled: bool = True,
    ) -> list[dict[str, Any]]:
        grouped: dict[str, dict[str, Any]] = {}
        for item in self.list_tools(
            tenant_id=tenant_id,
            industry=industry,
            channel=channel,
            include_disabled=include_disabled,
        ):
            category = str(item["category"])
            if category not in grouped:
                grouped[category] = {
                    "category": category,
                    "tool_count": 0,
                    "enabled_count": 0,
                    "tools": [],
                }
            grouped_item = grouped[category]
            grouped_item["tool_count"] += 1
            grouped_item["enabled_count"] += int(bool(item["enabled"]))
            grouped_item["tools"].append(item["name"])
        return sorted(grouped.values(), key=lambda item: str(item["category"]))

    def get(
        self,
        tool_name: str,
        *,
        tenant_id: str | None = None,
        industry: str | None = None,
        channel: str | None = None,
        include_disabled: bool = True,
    ) -> dict[str, Any]:
        plugin = self.get_plugin(
            tool_name,
            tenant_id=tenant_id,
            industry=industry,
            channel=channel,
            include_disabled=include_disabled,
        )
        if plugin is not None:
            return self._serialize_tool(
                plugin,
                tenant_id=tenant_id,
                industry=industry,
                channel=channel,
            )
        raise AppError(
            code="validation_error",
            message=f"不支持的工具：{tool_name}",
            status_code=400,
        )

    def get_plugin(
        self,
        tool_name: str,
        *,
        tenant_id: str | None = None,
        industry: str | None = None,
        channel: str | None = None,
        include_disabled: bool = True,
    ) -> BusinessToolPlugin | None:
        for plugin in self._iter_plugins():
            if plugin.tool_name != tool_name:
                continue
            if not include_disabled and not plugin.descriptor.enabled:
                continue
            if not self._scope_match(plugin.descriptor, tenant_id, industry, channel):
                continue
            return plugin
        return None

    def validate_parameters(
        self,
        tool_name: str,
        parameters: dict[str, Any],
        *,
        tenant_id: str | None = None,
        industry: str | None = None,
        channel: str | None = None,
    ) -> list[str]:
        definition = self.get(
            tool_name,
            tenant_id=tenant_id,
            industry=industry,
            channel=channel,
            include_disabled=False,
        )
        return [key for key in definition["required_parameters"] if not parameters.get(key)]

    def _iter_plugins(self) -> list[BusinessToolPlugin]:
        items: list[BusinessToolPlugin] = []
        for plugin in self._registry.plugins(PluginKind.BUSINESS_TOOL):
            if isinstance(plugin, BusinessToolPlugin):
                items.append(plugin)
        return items

    def _serialize_tool(
        self,
        plugin: BusinessToolPlugin,
        *,
        tenant_id: str | None = None,
        industry: str | None = None,
        channel: str | None = None,
    ) -> dict[str, Any]:
        descriptor = plugin.descriptor
        return {
            "name": plugin.tool_name,
            "category": plugin.category,
            "description": plugin.description,
            "required_parameters": list(plugin.required_parameters),
            "optional_parameters": list(plugin.optional_parameters),
            "suggested_context_keys": list(plugin.suggested_context_keys),
            "plugin_id": descriptor.plugin_id,
            "version": descriptor.version,
            "priority": descriptor.priority,
            "enabled": descriptor.enabled,
            "available": descriptor.enabled
            and self._scope_match(descriptor, tenant_id, industry, channel),
            "tenant_scopes": list(descriptor.tenant_scopes),
            "industry_scopes": list(descriptor.industry_scopes),
            "channel_scopes": list(descriptor.channel_scopes),
            "capabilities": list(descriptor.capabilities),
        }

    def _scope_match(
        self,
        descriptor: PluginDescriptor,
        tenant_id: str | None,
        industry: str | None,
        channel: str | None,
    ) -> bool:
        return (
            self._matches_scope(descriptor.tenant_scopes, tenant_id)
            and self._matches_scope(descriptor.industry_scopes, industry)
            and self._matches_scope(descriptor.channel_scopes, channel)
        )

    def _matches_scope(self, scopes: list[str], candidate: str | None) -> bool:
        if not scopes:
            return True
        if candidate is None:
            return True
        return candidate in scopes
