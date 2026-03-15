from __future__ import annotations

from uuid import uuid4

from fastapi.responses import JSONResponse

from customer_ai_runtime.core.request_context import get_request_id


def success_response(data: object, request_id: str | None = None) -> JSONResponse:
    resolved_request_id = request_id or get_request_id()
    return JSONResponse(
        status_code=200,
        content={
            "request_id": resolved_request_id or f"req_{uuid4().hex[:12]}",
            "data": data,
            "error": None,
        },
    )


def error_response(
    status_code: int,
    code: str,
    message: str,
    details: dict[str, object] | None = None,
    request_id: str | None = None,
) -> JSONResponse:
    resolved_request_id = request_id or get_request_id()
    return JSONResponse(
        status_code=status_code,
        content={
            "request_id": resolved_request_id or f"req_{uuid4().hex[:12]}",
            "data": None,
            "error": {
                "code": code,
                "message": message,
                "details": details or {},
            },
        },
    )
