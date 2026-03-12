from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

ChannelType = Literal["web", "app", "h5", "mini_program", "app_voice", "rtc", "admin"]


class TenantScopedRequest(BaseModel):
    tenant_id: str = Field(min_length=1, max_length=64)


class SessionCreateRequest(TenantScopedRequest):
    channel: ChannelType = "web"


class SessionCloseRequest(TenantScopedRequest):
    channel: ChannelType = "admin"
    satisfaction_score: int | None = Field(default=None, ge=1, le=5)


class ChatMessageRequest(TenantScopedRequest):
    session_id: str | None = None
    channel: ChannelType = "web"
    message: str = Field(min_length=1, max_length=4000)
    knowledge_base_id: str | None = None
    integration_context: dict[str, Any] = Field(default_factory=dict)


class HandoffRequest(TenantScopedRequest):
    session_id: str = Field(min_length=1, max_length=64)
    reason: str = Field(min_length=1, max_length=256)


class HumanReplyRequest(TenantScopedRequest):
    content: str = Field(min_length=1, max_length=4000)


class KnowledgeBaseCreateRequest(TenantScopedRequest):
    knowledge_base_id: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=128)
    description: str = Field(default="", max_length=2000)


class KnowledgeDocumentCreateRequest(TenantScopedRequest):
    title: str = Field(min_length=1, max_length=256)
    content: str = Field(min_length=1, max_length=50000)
    metadata: dict[str, Any] = Field(default_factory=dict)


class KnowledgeSearchRequest(TenantScopedRequest):
    query: str = Field(min_length=1, max_length=4000)
    top_k: int | None = Field(default=None, ge=1, le=10)
    min_score: float | None = Field(default=None, ge=0.0, le=1.0)


class BusinessQueryRequest(TenantScopedRequest):
    tool_name: Literal[
        "order_status",
        "after_sale_status",
        "logistics_tracking",
        "account_lookup",
        "subscription_lookup",
        "ticket_lookup",
        "course_lookup",
        "progress_lookup",
        "waybill_lookup",
        "claim_lookup",
        "crm_profile",
    ]
    parameters: dict[str, Any] = Field(default_factory=dict)
    integration_context: dict[str, Any] = Field(default_factory=dict)


class VoiceTurnRequest(TenantScopedRequest):
    session_id: str | None = None
    channel: ChannelType = "app_voice"
    audio_base64: str = Field(min_length=1)
    content_type: str = Field(default="text/plain", min_length=1, max_length=128)
    transcript_hint: str | None = Field(default=None, max_length=4000)
    knowledge_base_id: str | None = None
    integration_context: dict[str, Any] = Field(default_factory=dict)

    @field_validator("channel")
    @classmethod
    def validate_voice_channel(cls, value: str) -> str:
        if value not in {"app_voice", "rtc"}:
            raise ValueError("voice request channel must be app_voice or rtc")
        return value


class RTCRoomCreateRequest(TenantScopedRequest):
    pass


class RTCRoomJoinRequest(TenantScopedRequest):
    session_id: str | None = None


class PromptUpdateRequest(BaseModel):
    knowledge_answer: str | None = Field(default=None, max_length=4000)
    business_answer: str | None = Field(default=None, max_length=4000)
    fallback_answer: str | None = Field(default=None, max_length=4000)
    handoff_summary: str | None = Field(default=None, max_length=4000)


class PolicyUpdateRequest(BaseModel):
    knowledge_top_k: int | None = Field(default=None, ge=1, le=10)
    knowledge_min_score: float | None = Field(default=None, ge=0.0, le=1.0)
    handoff_confidence_threshold: float | None = Field(default=None, ge=0.0, le=1.0)
    route_fallback_confidence_threshold: float | None = Field(default=None, ge=0.0, le=1.0)
    route_handoff_confidence_threshold: float | None = Field(default=None, ge=0.0, le=1.0)
    intent_stack_max_depth: int | None = Field(default=None, ge=1, le=20)
    risk_keywords: list[str] | None = None
    human_request_keywords: list[str] | None = None
    intent_return_keywords: list[str] | None = None
    business_keyword_map: dict[str, list[str]] | None = None


class AlertRuleUpdateRequest(BaseModel):
    provider_not_ready_enabled: bool | None = None
    diagnostic_error_threshold: int | None = Field(default=None, ge=1, le=200)
    diagnostic_error_sample_limit: int | None = Field(default=None, ge=1, le=200)
    waiting_human_session_threshold: int | None = Field(default=None, ge=1, le=200)
    waiting_human_session_sample_limit: int | None = Field(default=None, ge=1, le=200)


class RuntimeConfigUpdateRequest(BaseModel):
    prompts: PromptUpdateRequest | None = None
    policies: PolicyUpdateRequest | None = None
    alerts: AlertRuleUpdateRequest | None = None
    plugin_states: dict[str, bool] | None = None


class ContextResolveRequest(TenantScopedRequest):
    session_id: str | None = None
    channel: ChannelType = "web"
    integration_context: dict[str, Any] = Field(default_factory=dict)
