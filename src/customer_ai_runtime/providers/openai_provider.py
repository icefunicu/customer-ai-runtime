from __future__ import annotations

import base64
import io
import json
from typing import Any, cast

from openai import AsyncOpenAI

from customer_ai_runtime.core.config import Settings
from customer_ai_runtime.core.errors import AppError
from customer_ai_runtime.core.redaction import redact_text, sanitize_context
from customer_ai_runtime.core.text import safe_excerpt
from customer_ai_runtime.domain.models import (
    ASRRequest,
    ASRResult,
    LLMRequest,
    LLMResponse,
    TTSRequest,
    TTSResult,
)
from customer_ai_runtime.providers.base import ASRProvider, LLMProvider, TTSProvider

_MAX_MESSAGE_CHARS = 240
_MAX_HISTORY_MESSAGE_CHARS = 180
_MAX_CITATION_EXCERPT_CHARS = 220
_MAX_TOOL_RESULT_CHARS = 1200
_MAX_PROMPT_CHARS = 4000


def _build_prompt(request: LLMRequest) -> str:
    history = [
        redact_text(message.content, max_length=_MAX_HISTORY_MESSAGE_CHARS)
        for message in request.history[-6:]
    ]
    citations = [
        redact_text(citation.excerpt, max_length=_MAX_CITATION_EXCERPT_CHARS)
        for citation in request.citations
    ]
    tool_payload = None
    if request.tool_result is not None:
        dumped = request.tool_result.model_dump(mode="json")
        tool_payload = safe_excerpt(
            json.dumps(sanitize_context(dumped), ensure_ascii=False),
            max_length=_MAX_TOOL_RESULT_CHARS,
        )

    prompt = (
        f"{safe_excerpt(request.prompt_template, max_length=800)}\n"
        f"用户问题：{redact_text(request.user_message, max_length=_MAX_MESSAGE_CHARS)}\n"
        f"历史消息：{history}\n"
        f"引用：{citations}\n"
        f"工具结果：{tool_payload}"
    )
    return safe_excerpt(prompt, max_length=_MAX_PROMPT_CHARS)


class OpenAILLMProvider(LLMProvider):
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client = _build_client(settings)

    async def generate(self, request: LLMRequest) -> LLMResponse:
        prompt = _build_prompt(request)
        response = await self._client.responses.create(
            model=self._settings.openai_chat_model,
            input=prompt,
        )
        output_text = response.output_text or "抱歉，我暂时没有生成有效答案。"
        return LLMResponse(answer=output_text, confidence=0.78, citations=request.citations)


class OpenAIASRProvider(ASRProvider):
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client = _build_client(settings)

    async def transcribe(self, request: ASRRequest) -> ASRResult:
        audio_bytes = base64.b64decode(request.audio_base64)
        file_like = io.BytesIO(audio_bytes)
        transcript = await self._client.audio.transcriptions.create(
            model=self._settings.openai_transcription_model,
            file=("audio.wav", file_like, request.content_type),
        )
        return ASRResult(transcript=transcript.text, confidence=0.85)


class OpenAITTSProvider(TTSProvider):
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client = _build_client(settings)

    async def synthesize(self, request: TTSRequest) -> TTSResult:
        response = await self._client.audio.speech.create(
            model=self._settings.openai_tts_model,
            voice=request.voice or self._settings.openai_tts_voice,
            input=request.text,
            response_format=cast(Any, request.audio_format),
        )
        audio_bytes = await response.aread()
        return TTSResult(
            audio_base64=base64.b64encode(audio_bytes).decode("utf-8"),
            audio_format=request.audio_format,
            segments=[request.text],
        )


def _build_client(settings: Settings) -> AsyncOpenAI:
    if not settings.openai_api_key:
        raise AppError(
            code="provider_error",
            message="未配置 CUSTOMER_AI_OPENAI_API_KEY，无法启用 OpenAI 提供商。",
            status_code=503,
        )
    return AsyncOpenAI(api_key=settings.openai_api_key, base_url=settings.openai_base_url)
