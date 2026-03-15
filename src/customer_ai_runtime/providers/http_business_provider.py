from __future__ import annotations

import httpx

from customer_ai_runtime.core.config import Settings
from customer_ai_runtime.core.errors import AppError
from customer_ai_runtime.domain.models import BusinessQuery, BusinessResult
from customer_ai_runtime.providers.base import BusinessAdapter


class HttpBusinessAdapter(BusinessAdapter):
    def __init__(self, settings: Settings) -> None:
        if not settings.business_api_base_url:
            raise AppError(
                code="provider_error",
                message="未配置 CUSTOMER_AI_BUSINESS_API_BASE_URL，无法启用 HTTP 业务适配器。",
                status_code=503,
            )
        self._base_url = settings.business_api_base_url.rstrip("/")
        self._api_key = settings.business_api_key
        self._timeout = settings.business_api_timeout_seconds
        self._endpoint_map = settings.get_business_tool_endpoint_map()

    async def execute(self, query: BusinessQuery) -> BusinessResult:
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["X-Business-API-Key"] = self._api_key
        payload = query.model_dump(mode="json")
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            try:
                response = await client.post(
                    f"{self._base_url}{self._resolve_path(query.tool_name)}",
                    json=payload,
                    headers=headers,
                )
                response.raise_for_status()
            except httpx.HTTPError as exc:
                raise AppError(
                    code="provider_error",
                    message="业务系统调用失败",
                    status_code=502,
                    details={"tool_name": query.tool_name},
                ) from exc
        return BusinessResult.model_validate(response.json())

    def _resolve_path(self, tool_name: str) -> str:
        mapped = self._endpoint_map.get(tool_name)
        if not mapped:
            return f"/tools/{tool_name}"
        return mapped if mapped.startswith("/") else f"/{mapped}"
