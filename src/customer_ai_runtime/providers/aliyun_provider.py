from __future__ import annotations

import asyncio
import base64
import json
from importlib import import_module
from time import time
from typing import Any

import httpx

from customer_ai_runtime.core.config import Settings
from customer_ai_runtime.core.errors import AppError
from customer_ai_runtime.domain.models import ASRRequest, ASRResult, TTSRequest, TTSResult
from customer_ai_runtime.providers.base import ASRProvider, TTSProvider

_ALIYUN_TOKEN_REFRESH_BUFFER_SECONDS = 600


class AliyunASRProvider(ASRProvider):
    def __init__(self, settings: Settings) -> None:
        _ensure_aliyun_speech_config(settings)
        self._settings = settings
        self._token_provider = _AliyunTokenProvider(settings)

    async def transcribe(self, request: ASRRequest) -> ASRResult:
        audio_bytes = _decode_audio_base64(request.audio_base64)
        token = await self._token_provider.get_token()
        params = {
            "appkey": self._settings.aliyun_app_key,
            "format": _resolve_aliyun_audio_format(
                request.content_type,
                fallback=self._settings.aliyun_asr_format,
            ),
            "sample_rate": self._settings.aliyun_asr_sample_rate,
            "enable_punctuation_prediction": str(
                self._settings.aliyun_asr_enable_punctuation_prediction
            ).lower(),
            "enable_inverse_text_normalization": str(
                self._settings.aliyun_asr_enable_inverse_text_normalization
            ).lower(),
            "enable_voice_detection": str(
                self._settings.aliyun_asr_enable_voice_detection
            ).lower(),
        }

        async with httpx.AsyncClient(
            timeout=self._settings.aliyun_speech_timeout_seconds
        ) as client:
            response = await client.post(
                self._settings.aliyun_asr_endpoint,
                params=params,
                headers={
                    "X-NLS-Token": token,
                    "Content-Type": "application/octet-stream",
                },
                content=audio_bytes,
            )

        payload = _parse_aliyun_json(response, provider="aliyun_asr")
        if response.status_code >= 400 or payload.get("status") != 20000000:
            raise AppError(
                code="provider_error",
                message=payload.get("message", "阿里云 ASR 调用失败。"),
                status_code=502,
                details={"provider": "aliyun", "status": payload.get("status")},
            )

        transcript = str(payload.get("result") or "").strip()
        return ASRResult(transcript=transcript, confidence=0.85, is_final=True)


class AliyunTTSProvider(TTSProvider):
    def __init__(self, settings: Settings) -> None:
        _ensure_aliyun_speech_config(settings)
        self._settings = settings
        self._token_provider = _AliyunTokenProvider(settings)

    async def synthesize(self, request: TTSRequest) -> TTSResult:
        token = await self._token_provider.get_token()
        audio_format = (request.audio_format or self._settings.aliyun_tts_format).lower()
        payload = {
            "appkey": self._settings.aliyun_app_key,
            "token": token,
            "text": request.text,
            "format": audio_format,
            "sample_rate": self._settings.aliyun_tts_sample_rate,
            "voice": request.voice or self._settings.aliyun_tts_voice,
            "volume": self._settings.aliyun_tts_volume,
            "speech_rate": self._settings.aliyun_tts_speech_rate,
            "pitch_rate": self._settings.aliyun_tts_pitch_rate,
        }

        async with httpx.AsyncClient(
            timeout=self._settings.aliyun_speech_timeout_seconds
        ) as client:
            response = await client.post(
                self._settings.aliyun_tts_endpoint,
                json=payload,
                headers={"Content-Type": "application/json;charset=utf-8"},
            )

        content_type = response.headers.get("content-type", "")
        if content_type.startswith("audio/"):
            return TTSResult(
                audio_base64=base64.b64encode(response.content).decode("utf-8"),
                audio_format=audio_format,
                segments=[request.text],
            )

        error_payload = _parse_aliyun_json(response, provider="aliyun_tts")
        raise AppError(
            code="provider_error",
            message=error_payload.get("message", "阿里云 TTS 调用失败。"),
            status_code=502,
            details={"provider": "aliyun", "status": error_payload.get("status")},
        )


class _AliyunTokenProvider:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._lock = asyncio.Lock()
        self._token: str | None = None
        self._expires_at: int = 0

    async def get_token(self) -> str:
        now = int(time())
        if self._token and now < self._expires_at - _ALIYUN_TOKEN_REFRESH_BUFFER_SECONDS:
            return self._token
        async with self._lock:
            now = int(time())
            if self._token and now < self._expires_at - _ALIYUN_TOKEN_REFRESH_BUFFER_SECONDS:
                return self._token
            token, expires_at = await asyncio.to_thread(self._create_token)
            self._token = token
            self._expires_at = expires_at
            return token

    def _create_token(self) -> tuple[str, int]:
        try:
            client_module = import_module("aliyunsdkcore.client")
            request_module = import_module("aliyunsdkcore.request")
        except ImportError as exc:
            raise AppError(
                code="provider_error",
                message=(
                    "阿里云语音提供商缺少依赖，请安装 `aliyun-python-sdk-core` "
                    "或使用 `pip install -e \".[providers]\"`。"
                ),
                status_code=500,
            ) from exc

        acs_client = client_module.AcsClient(
            self._settings.aliyun_access_key_id,
            self._settings.aliyun_access_key_secret,
            self._settings.aliyun_token_region,
        )
        request = request_module.CommonRequest()
        request.set_method("POST")
        request.set_domain(self._settings.aliyun_token_domain)
        request.set_version("2019-02-28")
        request.set_action_name("CreateToken")

        try:
            response = acs_client.do_action_with_exception(request)
        except Exception as exc:  # pragma: no cover - exercised via AppError branch
            raise AppError(
                code="provider_error",
                message="阿里云语音 Token 获取失败。",
                status_code=502,
            ) from exc

        payload = json.loads(response.decode("utf-8") if isinstance(response, bytes) else response)
        token = payload.get("Token", {}).get("Id")
        expires_at = int(payload.get("Token", {}).get("ExpireTime") or 0)
        if not token or not expires_at:
            raise AppError(
                code="provider_error",
                message="阿里云语音 Token 响应不完整。",
                status_code=502,
            )
        return token, expires_at


def _ensure_aliyun_speech_config(settings: Settings) -> None:
    if (
        settings.aliyun_access_key_id
        and settings.aliyun_access_key_secret
        and settings.aliyun_app_key
    ):
        return
    raise AppError(
        code="provider_error",
        message=(
            "阿里云语音提供商缺少必要配置，请设置 "
            "`CUSTOMER_AI_ALIYUN_ACCESS_KEY_ID`、"
            "`CUSTOMER_AI_ALIYUN_ACCESS_KEY_SECRET` 和 "
            "`CUSTOMER_AI_ALIYUN_APP_KEY`。"
        ),
        status_code=500,
    )


def _decode_audio_base64(audio_base64: str) -> bytes:
    try:
        return base64.b64decode(audio_base64)
    except Exception as exc:  # pragma: no cover - base64 implementation detail
        raise AppError(
            code="validation_error",
            message="音频内容不是合法的 base64 编码。",
            status_code=422,
        ) from exc


def _resolve_aliyun_audio_format(content_type: str, *, fallback: str) -> str:
    normalized = content_type.lower()
    if "wav" in normalized:
        return "wav"
    if "pcm" in normalized:
        return "pcm"
    if "mp3" in normalized or "mpeg" in normalized:
        return "mp3"
    if "opus" in normalized:
        return "opus"
    return fallback


def _parse_aliyun_json(response: httpx.Response, *, provider: str) -> dict[str, Any]:
    try:
        payload = response.json()
    except ValueError as exc:
        raise AppError(
            code="provider_error",
            message=f"{provider} 返回了无法解析的响应。",
            status_code=502,
        ) from exc
    if not isinstance(payload, dict):
        raise AppError(
            code="provider_error",
            message=f"{provider} 返回了无效响应结构。",
            status_code=502,
        )
    return payload
