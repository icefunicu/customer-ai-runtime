from __future__ import annotations

import json
from typing import Any

import httpx

from customer_ai_runtime.core.config import Settings
from customer_ai_runtime.core.errors import AppError
from customer_ai_runtime.domain.models import BusinessQuery, BusinessResult
from customer_ai_runtime.providers.base import BusinessAdapter


class GraphQLBusinessAdapter(BusinessAdapter):
    def __init__(self, settings: Settings) -> None:
        if not settings.business_graphql_endpoint:
            raise AppError(
                code="provider_error",
                message=(
                    "未配置 CUSTOMER_AI_BUSINESS_GRAPHQL_ENDPOINT，"
                    "无法启用 GraphQL 业务适配器。"
                ),
                status_code=500,
            )
        self._endpoint = settings.business_graphql_endpoint.rstrip("/")
        self._api_key = settings.business_graphql_api_key
        self._timeout = settings.business_graphql_timeout_seconds
        self._query_map = settings.get_business_graphql_query_map()
        self._response_path_map = settings.get_business_graphql_response_path_map()
        self._headers = settings.get_business_graphql_headers()

    async def execute(self, query: BusinessQuery) -> BusinessResult:
        query_template = self._query_map.get(query.tool_name)
        if not query_template:
            raise AppError(
                code="provider_error",
                message="未配置 GraphQL 工具查询模板。",
                status_code=500,
                details={"tool_name": query.tool_name},
            )
        headers = {"Content-Type": "application/json", **self._headers}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        payload = {
            "query": query_template,
            "variables": {
                "tenant_id": query.tenant_id,
                "session_id": query.session_id,
                "tool_name": query.tool_name,
                "parameters": query.parameters,
                "integration_context": query.integration_context,
            },
        }
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            try:
                response = await client.post(self._endpoint, json=payload, headers=headers)
                response.raise_for_status()
            except httpx.HTTPError as exc:
                raise AppError(
                    code="provider_error",
                    message="GraphQL 业务系统调用失败",
                    status_code=502,
                    details={"tool_name": query.tool_name},
                ) from exc
        response_payload = response.json()
        if response_payload.get("errors"):
            raise AppError(
                code="provider_error",
                message="GraphQL 业务系统返回错误",
                status_code=502,
                details={"tool_name": query.tool_name, "errors": response_payload["errors"]},
            )
        data = self._extract_data(response_payload.get("data") or {}, query.tool_name)
        return self._normalize_result(query, data)

    def _extract_data(self, data: dict[str, Any], tool_name: str) -> Any:
        path = self._response_path_map.get(tool_name)
        if not path:
            return data
        current: Any = data
        for segment in path.split("."):
            if not isinstance(current, dict):
                return {}
            current = current.get(segment)
        return current

    def _normalize_result(self, query: BusinessQuery, payload: Any) -> BusinessResult:
        if isinstance(payload, dict):
            if {"tool_name", "status", "summary"}.issubset(payload):
                return BusinessResult.model_validate(payload)
            return BusinessResult(
                tool_name=query.tool_name,
                status=str(payload.get("status", "success")),
                summary=str(payload.get("summary", json.dumps(payload, ensure_ascii=False))),
                data=dict(payload.get("data") or payload),
                requires_handoff=bool(payload.get("requires_handoff", False)),
                integration_context=query.integration_context,
            )
        return BusinessResult(
            tool_name=query.tool_name,
            status="success",
            summary=json.dumps(payload, ensure_ascii=False),
            data={"result": payload},
            integration_context=query.integration_context,
        )
