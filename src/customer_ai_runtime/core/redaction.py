from __future__ import annotations

import re
from typing import Any

from customer_ai_runtime.core.text import safe_excerpt

_EMAIL_RE = re.compile(r"([A-Za-z0-9._%+-]{1,64})@([A-Za-z0-9.-]{1,255})")
_PHONE_RE = re.compile(r"(?<!\d)(1\d{10})(?!\d)")  # CN mobile as a baseline
_TOKENISH_RE = re.compile(r"\b(sk-[A-Za-z0-9]{8,})\b")

_SENSITIVE_KEYWORDS = (
    "authorization",
    "api_key",
    "apikey",
    "token",
    "secret",
    "password",
    "access_key",
    "private_key",
)


def redact_text(value: str, *, max_length: int = 200) -> str:
    text = value or ""
    text = _EMAIL_RE.sub(lambda m: f"{m.group(1)[:2]}***@{m.group(2)}", text)
    text = _PHONE_RE.sub(lambda m: f"{m.group(1)[:3]}****{m.group(1)[-4:]}", text)
    text = _TOKENISH_RE.sub("sk-***", text)
    return safe_excerpt(text, max_length=max_length)


def sanitize_context(context: dict[str, Any]) -> dict[str, Any]:
    # Keep this intentionally conservative: scrub obvious secrets and truncate free-form text.
    return {str(k): _sanitize_value(str(k), v) for k, v in (context or {}).items()}


def _sanitize_value(key: str, value: Any) -> Any:
    lowered = key.lower()
    if any(word in lowered for word in _SENSITIVE_KEYWORDS):
        return "***"
    if isinstance(value, str):
        if lowered in {"query", "message", "user_message", "comment", "content", "prompt", "input"}:
            return redact_text(value)
        return redact_text(value, max_length=120)
    if isinstance(value, dict):
        return {str(k): _sanitize_value(f"{key}.{k}", v) for k, v in value.items()}
    if isinstance(value, list):
        return [_sanitize_value(f"{key}[]", item) for item in value[:50]]
    return value
