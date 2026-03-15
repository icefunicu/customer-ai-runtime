from __future__ import annotations

import base64
import io

from openai import AsyncOpenAI

from customer_ai_runtime.core.config import Settings
from customer_ai_runtime.core.errors import AppError
from customer_ai_runtime.domain.models import (
    ASRRequest,
    ASRResult,
    LLMRequest,
    LLMResponse,
    TTSRequest,
    TTSResult,
)
from customer_ai_runtime.providers.base import ASRProvider, LLMProvider, TTSProvider


class OpenAILLMProvider(LLMProvider):
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client = _build_client(settings)

    async def generate(self, request: LLMRequest) -> LLMResponse:
        prompt = (
            f"{request.prompt_template}\n"
            f"用户问题：{request.user_message}\n"
            f"历史消息：{[message.content for message in request.history[-6:]]}\n"
            f"引用：{[citation.excerpt for citation in request.citations]}\n"
            f"工具结果：{request.tool_result.model_dump() if request.tool_result else None}"
        )
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
            format=request.audio_format,
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
