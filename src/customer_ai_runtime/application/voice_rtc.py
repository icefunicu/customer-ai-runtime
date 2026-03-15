from __future__ import annotations

from time import perf_counter
from typing import Any

from customer_ai_runtime.application.chat import ChatService
from customer_ai_runtime.application.runtime import DiagnosticsService, MetricsService, zh
from customer_ai_runtime.application.session import SessionService
from customer_ai_runtime.core.errors import AppError
from customer_ai_runtime.core.limits import AUDIO_BASE64_MAX_CHARS
from customer_ai_runtime.domain.models import (
    ASRRequest,
    Channel,
    DiagnosticLevel,
    RTCRoom,
    RTCState,
    TTSRequest,
    utcnow,
)
from customer_ai_runtime.domain.platform import HostAuthContext
from customer_ai_runtime.providers.base import ASRProvider, TTSProvider
from customer_ai_runtime.repositories.base import RTCRepository


class VoiceService:
    def __init__(
        self,
        asr_provider: ASRProvider,
        tts_provider: TTSProvider,
        chat_service: ChatService,
        metrics: MetricsService,
        diagnostics: DiagnosticsService,
    ) -> None:
        self.asr_provider = asr_provider
        self.tts_provider = tts_provider
        self.chat_service = chat_service
        self.metrics = metrics
        self.diagnostics = diagnostics

    async def process_turn(
        self,
        tenant_id: str,
        session_id: str | None,
        channel: str,
        audio_base64: str,
        content_type: str,
        transcript_hint: str | None,
        knowledge_base_id: str | None,
        integration_context: dict | None = None,
        host_auth_context: HostAuthContext | None = None,
    ) -> dict:
        started_at = perf_counter()
        asr_result = await self.asr_provider.transcribe(
            ASRRequest(
                tenant_id=tenant_id,
                audio_base64=audio_base64,
                content_type=content_type,
                transcript_hint=transcript_hint,
            )
        )
        chat_result = await self.chat_service.process_message(
            tenant_id=tenant_id,
            session_id=session_id,
            channel=channel,
            message=asr_result.transcript,
            knowledge_base_id=knowledge_base_id,
            integration_context=integration_context,
            host_auth_context=host_auth_context,
            track_response_timing=False,
        )
        tts_result = await self.tts_provider.synthesize(
            TTSRequest(tenant_id=tenant_id, text=chat_result["answer"])
        )
        session = self.chat_service.session_service.get(tenant_id, chat_result["session_id"])
        duration_ms = max(1, int((perf_counter() - started_at) * 1000))
        self.chat_service.session_service.record_response_timing(session, duration_ms)
        self.metrics.increment("voice_turns")
        self.diagnostics.record(
            DiagnosticLevel.INFO,
            "voice.turn_completed",
            "voice turn completed",
            {
                "tenant_id": tenant_id,
                "session_id": chat_result["session_id"],
                "channel": channel,
                "duration_ms": duration_ms,
            },
        )
        return {
            **chat_result,
            "transcript": asr_result.transcript,
            "asr_confidence": asr_result.confidence,
            "audio_response_base64": tts_result.audio_base64,
            "audio_format": tts_result.audio_format,
        }


class RTCService:
    def __init__(
        self,
        repository: RTCRepository,
        session_service: SessionService,
        voice_service: VoiceService,
        metrics: MetricsService,
        diagnostics: DiagnosticsService,
    ) -> None:
        self.repository = repository
        self.session_service = session_service
        self.voice_service = voice_service
        self.metrics = metrics
        self.diagnostics = diagnostics

    def create_room(self, tenant_id: str) -> RTCRoom:
        room = RTCRoom(tenant_id=tenant_id)
        self.repository.save(room)
        self.metrics.increment("rtc_rooms_created")
        self.diagnostics.record(
            DiagnosticLevel.INFO,
            "rtc.room_created",
            "rtc room created",
            {"tenant_id": tenant_id, "room_id": room.room_id},
        )
        return room

    def join_room(self, tenant_id: str, room_id: str, session_id: str | None) -> RTCRoom:
        room = self.get_room(tenant_id, room_id)
        session = self.session_service.get_or_create(tenant_id, session_id, Channel.RTC.value)
        room.session_id = session.session_id
        room.state = RTCState.JOINED
        if "user" not in room.participants:
            room.participants.append("user")
        room.updated_at = utcnow()
        self.repository.save(room)
        self.metrics.increment("rtc_rooms_joined")
        self.diagnostics.record(
            DiagnosticLevel.INFO,
            "rtc.room_joined",
            "rtc room joined",
            {"tenant_id": tenant_id, "room_id": room_id, "session_id": room.session_id},
        )
        return room

    def interrupt(self, tenant_id: str, room_id: str) -> RTCRoom:
        room = self.get_room(tenant_id, room_id)
        if room.state == RTCState.ENDED:
            raise AppError(
                code="rtc_state_error",
                message=zh("\\u623f\\u95f4\\u5df2\\u7ed3\\u675f"),
                status_code=409,
            )
        room.state = RTCState.LISTENING
        room.updated_at = utcnow()
        self.repository.save(room)
        self.metrics.increment("rtc_interrupts")
        self.diagnostics.record(
            DiagnosticLevel.WARNING,
            "rtc.interrupted",
            "rtc room interrupted",
            {"tenant_id": tenant_id, "room_id": room_id},
        )
        return room

    def end_room(self, tenant_id: str, room_id: str) -> RTCRoom:
        room = self.get_room(tenant_id, room_id)
        room.state = RTCState.ENDED
        room.updated_at = utcnow()
        self.repository.save(room)
        self.metrics.increment("rtc_rooms_ended")
        self.diagnostics.record(
            DiagnosticLevel.INFO,
            "rtc.room_ended",
            "rtc room ended",
            {"tenant_id": tenant_id, "room_id": room_id},
        )
        return room

    async def handle_event(
        self,
        tenant_id: str,
        room_id: str,
        payload: dict[str, Any],
        host_auth_context: HostAuthContext | None = None,
    ) -> list[dict]:
        room = self.get_room(tenant_id, room_id)
        event_type = payload.get("type")
        if event_type == "join":
            room = self.join_room(tenant_id, room_id, payload.get("session_id"))
            return [{"type": "room_joined", "room": room.model_dump(mode="json")}]
        if event_type == "interrupt":
            room = self.interrupt(tenant_id, room_id)
            return [{"type": "state_changed", "state": room.state.value}]
        if event_type == "request_human":
            room.state = RTCState.WAITING_HUMAN
            room.handoff_requested = True
            self.repository.save(room)
            self.diagnostics.record(
                DiagnosticLevel.WARNING,
                "rtc.handoff_requested",
                "rtc room requested human handoff",
                {"tenant_id": tenant_id, "room_id": room_id},
            )
            return [{"type": "handoff", "reason": "user_requested_human"}]
        if event_type == "end":
            room = self.end_room(tenant_id, room_id)
            return [{"type": "ended", "room": room.model_dump(mode="json")}]
        if event_type != "user_audio":
            raise AppError(
                code="validation_error",
                message=zh("\\u4e0d\\u652f\\u6301\\u7684 RTC \\u4e8b\\u4ef6"),
                status_code=400,
            )

        audio_base64 = payload.get("audio_base64")
        if not isinstance(audio_base64, str) or not audio_base64.strip():
            raise AppError(
                code="validation_error",
                message=zh("\\u7f3a\\u5c11\\u97f3\\u9891\\u8f7d\\u8377"),
                status_code=400,
                details={"field": "audio_base64"},
            )
        if len(audio_base64) > AUDIO_BASE64_MAX_CHARS:
            raise AppError(
                code="payload_too_large",
                message=zh("\\u97f3\\u9891\\u8f7d\\u8377\\u8fc7\\u5927"),
                status_code=413,
                details={"field": "audio_base64", "max_chars": AUDIO_BASE64_MAX_CHARS},
            )
        content_type = payload.get("content_type", "text/plain")
        if not isinstance(content_type, str) or not content_type or len(content_type) > 128:
            raise AppError(
                code="validation_error",
                message=zh("\\u97f3\\u9891\\u7c7b\\u578b\\u4e0d\\u5408\\u6cd5"),
                status_code=400,
                details={"field": "content_type"},
            )
        transcript_hint = payload.get("transcript_hint")
        if transcript_hint is not None and (
            not isinstance(transcript_hint, str) or len(transcript_hint) > 4000
        ):
            raise AppError(
                code="validation_error",
                message=zh(
                    "\\u63d0\\u793a\\u6587\\u672c\\u8fc7\\u957f\\u6216\\u7c7b\\u578b\\u4e0d\\u5408\\u6cd5"
                ),
                status_code=400,
                details={"field": "transcript_hint"},
            )
        integration_context = payload.get("integration_context")
        if integration_context is not None and not isinstance(integration_context, dict):
            raise AppError(
                code="validation_error",
                message=zh("\\u4e0a\\u4e0b\\u6587\\u7c7b\\u578b\\u4e0d\\u5408\\u6cd5"),
                status_code=400,
                details={"field": "integration_context"},
            )
        knowledge_base_id = payload.get("knowledge_base_id")
        if knowledge_base_id is not None and (
            not isinstance(knowledge_base_id, str) or len(knowledge_base_id) > 64
        ):
            raise AppError(
                code="validation_error",
                message=zh("\\u77e5\\u8bc6\\u5e93 ID \\u4e0d\\u5408\\u6cd5"),
                status_code=400,
                details={"field": "knowledge_base_id"},
            )

        room.state = RTCState.THINKING
        room.updated_at = utcnow()
        self.repository.save(room)
        voice_result = await self.voice_service.process_turn(
            tenant_id=tenant_id,
            session_id=room.session_id,
            channel=Channel.RTC.value,
            audio_base64=audio_base64,
            content_type=content_type,
            transcript_hint=transcript_hint,
            knowledge_base_id=knowledge_base_id,
            integration_context=integration_context,
            host_auth_context=host_auth_context,
        )
        room.last_transcript = voice_result["transcript"]
        room.state = RTCState.WAITING_HUMAN if voice_result["handoff"] else RTCState.SPEAKING
        room.updated_at = utcnow()
        self.repository.save(room)
        events = [
            {"type": "transcript", "text": voice_result["transcript"]},
            {
                "type": "assistant_message",
                "text": voice_result["answer"],
                "route": voice_result["route"],
            },
            {
                "type": "assistant_audio",
                "audio_base64": voice_result["audio_response_base64"],
                "audio_format": voice_result["audio_format"],
            },
            {"type": "state_changed", "state": room.state.value},
        ]
        if voice_result["handoff"]:
            events.append({"type": "handoff", "payload": voice_result["handoff"]})
        room.state = RTCState.LISTENING if room.state == RTCState.SPEAKING else room.state
        room.updated_at = utcnow()
        self.repository.save(room)
        self.diagnostics.record(
            DiagnosticLevel.INFO,
            "rtc.audio_processed",
            "rtc audio event processed",
            {
                "tenant_id": tenant_id,
                "room_id": room_id,
                "session_id": room.session_id,
                "handoff": bool(voice_result["handoff"]),
            },
        )
        return events

    def get_room(self, tenant_id: str, room_id: str) -> RTCRoom:
        room = self.repository.get(tenant_id, room_id)
        if not room:
            raise AppError(
                code="not_found",
                message=zh("\\u623f\\u95f4\\u4e0d\\u5b58\\u5728"),
                status_code=404,
            )
        return room

    def list_rooms(self, tenant_id: str) -> list[RTCRoom]:
        return self.repository.list_by_tenant(tenant_id)
