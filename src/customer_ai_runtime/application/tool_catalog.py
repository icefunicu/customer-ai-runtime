from __future__ import annotations

from typing import Any

from customer_ai_runtime.application.plugins import BusinessToolPlugin, PluginRegistry
from customer_ai_runtime.core.errors import AppError
from customer_ai_runtime.domain.platform import PluginKind


class ToolCatalogService:
    def __init__(self, registry: PluginRegistry) -> None:
        self._registry = registry

    def list_tools(self) -> list[dict[str, Any]]:
        items = []
        for plugin in self._registry.plugins(PluginKind.BUSINESS_TOOL):
            if not isinstance(plugin, BusinessToolPlugin):
                continue
            items.append(
                {
                    "name": plugin.tool_name,
                    "category": plugin.category,
                    "description": plugin.description,
                    "required_parameters": plugin.required_parameters,
                    "optional_parameters": plugin.optional_parameters,
                    "suggested_context_keys": plugin.suggested_context_keys,
                    "plugin_id": plugin.descriptor.plugin_id,
                    "enabled": plugin.descriptor.enabled,
                }
            )
        return items

    def get(self, tool_name: str) -> dict[str, Any]:
        for plugin in self._registry.plugins(PluginKind.BUSINESS_TOOL):
            if isinstance(plugin, BusinessToolPlugin) and plugin.tool_name == tool_name:
                return {
                    "name": plugin.tool_name,
                    "category": plugin.category,
                    "description": plugin.description,
                    "required_parameters": plugin.required_parameters,
                    "optional_parameters": plugin.optional_parameters,
                    "suggested_context_keys": plugin.suggested_context_keys,
                    "plugin_id": plugin.descriptor.plugin_id,
                }
        raise AppError(code="validation_error", message=f"不支持的工具：{tool_name}", status_code=400)

    def validate_parameters(self, tool_name: str, parameters: dict[str, Any]) -> list[str]:
        definition = self.get(tool_name)
        return [key for key in definition["required_parameters"] if not parameters.get(key)]
