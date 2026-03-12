from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fastapi import FastAPI

from customer_ai_runtime.app import create_app
from customer_ai_runtime.application.container import Container, ContainerOverrides, build_container
from customer_ai_runtime.core.config import Settings, get_settings


@dataclass
class CustomerAIRuntimeModule:
    container: Container
    route_prefix: str = ""

    @classmethod
    def create(
        cls,
        settings: Settings | None = None,
        overrides: ContainerOverrides | None = None,
        route_prefix: str = "",
    ) -> "CustomerAIRuntimeModule":
        resolved_settings = settings or get_settings()
        container = build_container(resolved_settings, overrides=overrides)
        return cls(container=container, route_prefix=route_prefix)

    def as_fastapi_app(self) -> FastAPI:
        return create_app(container=self.container, route_prefix=self.route_prefix)

    def mount_to(self, host_app: FastAPI, prefix: str = "/customer-ai") -> None:
        host_app.mount(prefix, self.as_fastapi_app())

    async def chat(
        self,
        tenant_id: str,
        message: str,
        session_id: str | None = None,
        channel: str = "web",
        knowledge_base_id: str | None = None,
        integration_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return await self.container.chat_service.process_message(
            tenant_id=tenant_id,
            session_id=session_id,
            channel=channel,
            message=message,
            knowledge_base_id=knowledge_base_id,
            integration_context=integration_context,
        )

    async def voice_turn(
        self,
        tenant_id: str,
        audio_base64: str,
        session_id: str | None = None,
        channel: str = "app_voice",
        content_type: str = "text/plain",
        transcript_hint: str | None = None,
        knowledge_base_id: str | None = None,
        integration_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return await self.container.voice_service.process_turn(
            tenant_id=tenant_id,
            session_id=session_id,
            channel=channel,
            audio_base64=audio_base64,
            content_type=content_type,
            transcript_hint=transcript_hint,
            knowledge_base_id=knowledge_base_id,
            integration_context=integration_context,
        )

