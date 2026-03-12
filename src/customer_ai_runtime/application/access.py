from __future__ import annotations

from typing import Any

from customer_ai_runtime.core.errors import AppError
from customer_ai_runtime.application.runtime import zh
from customer_ai_runtime.domain.platform import ResolvedAuthContext


class AccessControlService:
    def validate_tenant_access(self, auth_context: dict[str, Any] | ResolvedAuthContext, tenant_id: str) -> None:
        resolved = self._normalize(auth_context)
        if resolved["role"] == "admin":
            return
        if tenant_id not in resolved["tenant_ids"]:
            raise AppError(
                code="forbidden",
                message=zh("\\u65e0\\u6743\\u8bbf\\u95ee\\u8be5\\u79df\\u6237"),
                status_code=403,
            )

    def _normalize(self, auth_context: dict[str, Any] | ResolvedAuthContext) -> dict[str, Any]:
        if isinstance(auth_context, ResolvedAuthContext):
            return auth_context.model_dump(mode="json")
        return auth_context
