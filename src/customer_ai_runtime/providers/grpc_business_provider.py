from __future__ import annotations

import json
from typing import Any

from customer_ai_runtime.core.config import Settings
from customer_ai_runtime.core.errors import AppError
from customer_ai_runtime.domain.models import BusinessQuery, BusinessResult
from customer_ai_runtime.providers.base import BusinessAdapter


class GrpcBusinessAdapter(BusinessAdapter):
    def __init__(self, settings: Settings) -> None:
        if not settings.business_grpc_target:
            raise AppError(
                code="provider_error",
                message="未配置 CUSTOMER_AI_BUSINESS_GRPC_TARGET，无法启用 gRPC 业务适配器。",
                status_code=500,
            )
        self._target = settings.business_grpc_target
        self._timeout = settings.business_grpc_timeout_seconds
        self._method_map = settings.get_business_grpc_method_map()
        self._metadata = settings.get_business_grpc_metadata()

    async def execute(self, query: BusinessQuery) -> BusinessResult:
        method = self._method_map.get(query.tool_name)
        if not method:
            raise AppError(
                code="provider_error",
                message="未配置 gRPC 工具方法映射。",
                status_code=500,
                details={"tool_name": query.tool_name},
            )
        try:
            import grpc
        except ImportError as exc:
            raise AppError(
                code="provider_error",
                message="未安装 grpcio，请先安装 `grpcio`。",
                status_code=500,
            ) from exc

        async with grpc.aio.insecure_channel(self._target) as channel:
            unary_call = channel.unary_unary(
                method,
                request_serializer=lambda item: json.dumps(item, ensure_ascii=False).encode(
                    "utf-8"
                ),
                response_deserializer=lambda raw: json.loads(raw.decode("utf-8")),
            )
            try:
                response_payload = await unary_call(
                    query.model_dump(mode="json"),
                    timeout=self._timeout,
                    metadata=list(self._metadata.items()),
                )
            except grpc.RpcError as exc:
                raise AppError(
                    code="provider_error",
                    message="gRPC 业务系统调用失败",
                    status_code=502,
                    details={"tool_name": query.tool_name, "method": method},
                ) from exc
        return self._normalize_result(query, response_payload)

    def _normalize_result(self, query: BusinessQuery, payload: Any) -> BusinessResult:
        if isinstance(payload, dict) and {"tool_name", "status", "summary"}.issubset(payload):
            return BusinessResult.model_validate(payload)
        if isinstance(payload, dict):
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
