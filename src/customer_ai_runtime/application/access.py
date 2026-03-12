from __future__ import annotations

from typing import Any

from customer_ai_runtime.core.errors import AppError
from customer_ai_runtime.application.runtime import zh


class AccessControlService:
    def validate_tenant_access(self, auth_context: dict[str, Any], tenant_id: str) -> None:
        if auth_context["role"] == "admin":
            return
        if tenant_id not in auth_context["tenant_ids"]:
            raise AppError(
                code="forbidden",
                message=zh("\\u65e0\\u6743\\u8bbf\\u95ee\\u8be5\\u79df\\u6237"),
                status_code=403,
            )

