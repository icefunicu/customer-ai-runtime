from __future__ import annotations

from typing import Any

from customer_ai_runtime.domain.models import BusinessQuery, BusinessResult
from customer_ai_runtime.providers.base import BusinessAdapter
from customer_ai_runtime.application.tool_catalog import ToolCatalogService
from customer_ai_runtime.application.runtime import zh


class ToolService:
    def __init__(self, adapter: BusinessAdapter, catalog: ToolCatalogService) -> None:
        self._adapter = adapter
        self._catalog = catalog

    async def execute(
        self,
        tenant_id: str,
        tool_name: str,
        parameters: dict[str, Any],
        integration_context: dict[str, Any] | None = None,
        session_id: str | None = None,
    ) -> BusinessResult:
        missing_parameters = self._catalog.validate_parameters(tool_name, parameters)
        if missing_parameters:
            return BusinessResult(
                tool_name=tool_name,
                status="missing_parameter",
                summary=zh("\\u8bf7\\u8865\\u5145\\u5fc5\\u8981\\u53c2\\u6570\\uff1a")
                + ", ".join(missing_parameters),
                data={"missing_parameters": missing_parameters},
                integration_context=integration_context or {},
            )
        return await self._adapter.execute(
            BusinessQuery(
                tenant_id=tenant_id,
                tool_name=tool_name,
                parameters=parameters,
                session_id=session_id,
                integration_context=integration_context or {},
            )
        )
