from __future__ import annotations

from contextvars import ContextVar, Token

_request_id_var: ContextVar[str | None] = ContextVar("customer_ai_request_id", default=None)


def get_request_id() -> str | None:
    return _request_id_var.get()


def set_request_id(value: str | None) -> Token[str | None]:
    return _request_id_var.set(value)


def reset_request_id(token: Token[str | None]) -> None:
    _request_id_var.reset(token)
