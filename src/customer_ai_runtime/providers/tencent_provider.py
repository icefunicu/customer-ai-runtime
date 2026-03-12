from __future__ import annotations

import asyncio
import json
from base64 import b64decode
from importlib import import_module
from typing import Any
from uuid import uuid4

from customer_ai_runtime.core.config import Settings
from customer_ai_runtime.core.errors import AppError
from customer_ai_runtime.domain.models import ASRRequest, ASRResult, TTSRequest, TTSResult
from customer_ai_runtime.providers.base import ASRProvider, TTSProvider


class TencentASRProvider(ASRProvider):
    def __init__(self, settings: Settings) -> None:
        _ensure_tencent_speech_config(settings)
        self._settings = settings

    async def transcribe(self, request: ASRRequest) -> ASRResult:
        audio_bytes = _decode_audio_base64(request.audio_base64)
        payload = {
            "ProjectId": 0,
            "SubServiceType": 2,
            "EngSerViceType": self._settings.tencent_asr_engine_model_type,
            "SourceType": 1,
            "VoiceFormat": _resolve_tencent_audio_format(
                request.content_type,
                fallback=self._settings.tencent_asr_voice_format,
            ),
            "UsrAudioKey": uuid4().hex,
            "Data": request.audio_base64,
            "DataLen": len(audio_bytes),
            "FilterDirty": 0,
            "FilterModal": 0,
            "FilterPunc": 0,
            "ConvertNumMode": 1,
            "WordInfo": 0,
        }
        response = await asyncio.to_thread(
            self._invoke_asr,
            payload,
        )
        transcript = str(response.get("Result") or response.get("AudioText") or "").strip()
        if not transcript:
            raise AppError(
                code="provider_error",
                message="腾讯云 ASR 未返回识别结果。",
                status_code=502,
            )
        return ASRResult(transcript=transcript, confidence=0.85, is_final=True)

    def _invoke_asr(self, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            credential_module = import_module("tencentcloud.common.credential")
            asr_client_module = import_module("tencentcloud.asr.v20190614.asr_client")
            asr_models_module = import_module("tencentcloud.asr.v20190614.models")
        except ImportError as exc:
            raise AppError(
                code="provider_error",
                message=(
                    "腾讯云语音提供商缺少依赖，请安装 "
                    "`tencentcloud-sdk-python-asr`、`tencentcloud-sdk-python-tts` "
                    "或使用 `pip install -e \".[providers]\"`。"
                ),
                status_code=500,
            ) from exc

        credential = credential_module.Credential(
            self._settings.tencent_secret_id,
            self._settings.tencent_secret_key,
        )
        client = asr_client_module.AsrClient(credential, self._settings.tencent_region)
        request = asr_models_module.SentenceRecognitionRequest()
        request.from_json_string(json.dumps(payload))

        try:
            response = client.SentenceRecognition(request)
        except Exception as exc:  # pragma: no cover - network/SDK branch
            raise AppError(
                code="provider_error",
                message="腾讯云 ASR 调用失败。",
                status_code=502,
            ) from exc

        payload = json.loads(response.to_json_string()).get("Response", {})
        if payload.get("Error"):
            raise AppError(
                code="provider_error",
                message=payload["Error"].get("Message", "腾讯云 ASR 调用失败。"),
                status_code=502,
                details={"provider": "tencent", "request_id": payload.get("RequestId")},
            )
        return payload


class TencentTTSProvider(TTSProvider):
    def __init__(self, settings: Settings) -> None:
        _ensure_tencent_speech_config(settings)
        self._settings = settings

    async def synthesize(self, request: TTSRequest) -> TTSResult:
        payload = {
            "SessionId": uuid4().hex,
            "Text": request.text,
            "VoiceType": _resolve_tencent_voice_type(
                request.voice,
                fallback=self._settings.tencent_tts_voice_type,
            ),
            "Codec": (request.audio_format or self._settings.tencent_tts_codec).lower(),
            "SampleRate": self._settings.tencent_tts_sample_rate,
            "Speed": self._settings.tencent_tts_speed,
            "Volume": self._settings.tencent_tts_volume,
            "EnableSubtitle": self._settings.tencent_tts_enable_subtitle,
        }
        response = await asyncio.to_thread(
            self._invoke_tts,
            payload,
        )
        audio = response.get("Audio")
        if not audio:
            raise AppError(
                code="provider_error",
                message="腾讯云 TTS 未返回音频数据。",
                status_code=502,
            )
        return TTSResult(
            audio_base64=audio,
            audio_format=payload["Codec"],
            segments=[request.text],
        )

    def _invoke_tts(self, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            credential_module = import_module("tencentcloud.common.credential")
            tts_client_module = import_module("tencentcloud.tts.v20190823.tts_client")
            tts_models_module = import_module("tencentcloud.tts.v20190823.models")
        except ImportError as exc:
            raise AppError(
                code="provider_error",
                message=(
                    "腾讯云语音提供商缺少依赖，请安装 "
                    "`tencentcloud-sdk-python-asr`、`tencentcloud-sdk-python-tts` "
                    "或使用 `pip install -e \".[providers]\"`。"
                ),
                status_code=500,
            ) from exc

        credential = credential_module.Credential(
            self._settings.tencent_secret_id,
            self._settings.tencent_secret_key,
        )
        client = tts_client_module.TtsClient(credential, self._settings.tencent_region)
        request = tts_models_module.TextToVoiceRequest()
        request.from_json_string(json.dumps(payload))

        try:
            response = client.TextToVoice(request)
        except Exception as exc:  # pragma: no cover - network/SDK branch
            raise AppError(
                code="provider_error",
                message="腾讯云 TTS 调用失败。",
                status_code=502,
            ) from exc

        payload = json.loads(response.to_json_string()).get("Response", {})
        if payload.get("Error"):
            raise AppError(
                code="provider_error",
                message=payload["Error"].get("Message", "腾讯云 TTS 调用失败。"),
                status_code=502,
                details={"provider": "tencent", "request_id": payload.get("RequestId")},
            )
        return payload


def _ensure_tencent_speech_config(settings: Settings) -> None:
    if settings.tencent_secret_id and settings.tencent_secret_key:
        return
    raise AppError(
        code="provider_error",
        message=(
            "腾讯云语音提供商缺少必要配置，请设置 "
            "`CUSTOMER_AI_TENCENT_SECRET_ID` 和 `CUSTOMER_AI_TENCENT_SECRET_KEY`。"
        ),
        status_code=500,
    )


def _decode_audio_base64(audio_base64: str) -> bytes:
    try:
        return b64decode(audio_base64)
    except Exception as exc:  # pragma: no cover - base64 implementation detail
        raise AppError(
            code="validation_error",
            message="音频内容不是合法的 base64 编码。",
            status_code=422,
        ) from exc


def _resolve_tencent_audio_format(content_type: str, *, fallback: str) -> str:
    normalized = content_type.lower()
    if "wav" in normalized:
        return "wav"
    if "pcm" in normalized:
        return "pcm"
    if "mp3" in normalized or "mpeg" in normalized:
        return "mp3"
    if "speex" in normalized:
        return "speex"
    return fallback


def _resolve_tencent_voice_type(voice: str | None, *, fallback: int) -> int:
    if voice is None:
        return fallback
    try:
        return int(voice)
    except ValueError as exc:
        raise AppError(
            code="validation_error",
            message="腾讯云 TTS 的 voice 必须是合法的数字 VoiceType。",
            status_code=422,
        ) from exc
