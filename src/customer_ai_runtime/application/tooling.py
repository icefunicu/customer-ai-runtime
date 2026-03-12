from __future__ import annotations

from typing import Any

from customer_ai_runtime.application.business import RealTimeBusinessDataProvider
from customer_ai_runtime.application.tool_catalog import ToolCatalogService
from customer_ai_runtime.domain.models import BusinessResult
from customer_ai_runtime.domain.platform import BusinessContext

from customer_ai_runtime.application.runtime import zh


class ToolService:
    def __init__(self, provider: RealTimeBusinessDataProvider, catalog: ToolCatalogService) -> None:
        self._provider = provider
        self._catalog = catalog

    async def execute(
        self,
        *,
        business_context: BusinessContext,
        tool_name: str,
        parameters: dict[str, Any],
    ) -> BusinessResult:
        missing_parameters = self._catalog.validate_parameters(tool_name, parameters)
        if missing_parameters:
            return BusinessResult(
                tool_name=tool_name,
                status="missing_parameter",
                summary=zh("\\u8bf7\\u8865\\u5145\\u5fc5\\u8981\\u53c2\\u6570\\uff1a") + ", ".join(missing_parameters),
                data={"missing_parameters": missing_parameters},
                integration_context=business_context.integration_context,
            )
        return await self._provider.execute(
            context=business_context,
            tool_name=tool_name,
            parameters=parameters,
        )
