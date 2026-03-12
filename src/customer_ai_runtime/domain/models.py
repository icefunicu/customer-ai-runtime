from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


def utcnow() -> datetime:
    return datetime.now(UTC)


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:12]}"


class Channel(str, Enum):
    WEB = "web"
    APP = "app"
    H5 = "h5"
    MINI_PROGRAM = "mini_program"
    APP_VOICE = "app_voice"
    RTC = "rtc"
    ADMIN = "admin"


class MessageRole(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"
    HUMAN = "human"
    SYSTEM = "system"


class SessionState(str, Enum):
    ACTIVE = "active"
    WAITING_HUMAN = "waiting_human"
    HUMAN_IN_SERVICE = "human_in_service"
    CLOSED = "closed"


class RouteType(str, Enum):
    KNOWLEDGE = "knowledge"
    BUSINESS = "business"
    HANDOFF = "handoff"
    RISK = "risk"
    PLUGIN = "plugin"
    FALLBACK = "fallback"


class RTCState(str, Enum):
    CREATED = "created"
    JOINED = "joined"
    LISTENING = "listening"
    THINKING = "thinking"
    SPEAKING = "speaking"
    WAITING_HUMAN = "waiting_human"
    ENDED = "ended"


class DiagnosticLevel(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class Message(BaseModel):
    message_id: str = Field(default_factory=lambda: new_id("msg"))
    role: MessageRole
    content: str
    created_at: datetime = Field(default_factory=utcnow)
    metadata: dict[str, Any] = Field(default_factory=dict)


class IntentFrame(BaseModel):
    intent: str
    route: RouteType
    tool_name: str | None = None
    confidence: float = 0.0
    confidence_band: str = "low"
    low_confidence_count: int = 0
    matched_signals: list[str] = Field(default_factory=list)
    context_snapshot: dict[str, Any] = Field(default_factory=dict)
    last_user_message: str = ""
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class Session(BaseModel):
    tenant_id: str
    session_id: str = Field(default_factory=lambda: new_id("session"))
    channel: str
    state: SessionState = SessionState.ACTIVE
    messages: list[Message] = Field(default_factory=list)
    summary: str = ""
    last_intent: str | None = None
    last_route: RouteType | None = None
    intent_stack: list[IntentFrame] = Field(default_factory=list)
    waiting_human: bool = False
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class Citation(BaseModel):
    knowledge_base_id: str
    document_id: str
    title: str
    chunk_id: str
    score: float
    excerpt: str


class KnowledgeBase(BaseModel):
    tenant_id: str
    knowledge_base_id: str
    name: str
    description: str = ""
    document_count: int = 0
    chunk_count: int = 0
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class KnowledgeDocument(BaseModel):
    tenant_id: str
    knowledge_base_id: str
    document_id: str = Field(default_factory=lambda: new_id("doc"))
    title: str
    content: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utcnow)


class KnowledgeChunk(BaseModel):
    tenant_id: str
    knowledge_base_id: str
    document_id: str
    title: str
    chunk_id: str = Field(default_factory=lambda: new_id("chunk"))
    content: str
    position: int
    embedding: list[float] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utcnow)


class RetrievalHit(BaseModel):
    chunk: KnowledgeChunk
    score: float


class RouteDecision(BaseModel):
    route: RouteType
    confidence: float
    reason: str
    intent: str | None = None
    confidence_band: str = "low"
    tool_name: str | None = None
    requires_handoff: bool = False
    matched_signals: list[str] = Field(default_factory=list)
    context_snapshot: dict[str, Any] = Field(default_factory=dict)


class BusinessQuery(BaseModel):
    tenant_id: str
    tool_name: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    session_id: str | None = None
    integration_context: dict[str, Any] = Field(default_factory=dict)


class BusinessResult(BaseModel):
    tool_name: str
    status: str
    summary: str
    data: dict[str, Any] = Field(default_factory=dict)
    requires_handoff: bool = False
    integration_context: dict[str, Any] = Field(default_factory=dict)


class HandoffPackage(BaseModel):
    tenant_id: str
    session_id: str
    reason: str
    summary: str
    intent: str
    recommended_reply: str
    history: list[Message] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utcnow)


class LLMRequest(BaseModel):
    tenant_id: str
    session_id: str
    route: RouteType
    user_message: str
    history: list[Message] = Field(default_factory=list)
    citations: list[Citation] = Field(default_factory=list)
    tool_result: BusinessResult | None = None
    prompt_template: str
    business_context: dict[str, Any] = Field(default_factory=dict)


class LLMResponse(BaseModel):
    answer: str
    confidence: float
    citations: list[Citation] = Field(default_factory=list)
    suggested_actions: list[str] = Field(default_factory=list)


class ASRRequest(BaseModel):
    tenant_id: str
    audio_base64: str
    content_type: str = "application/octet-stream"
    transcript_hint: str | None = None


class ASRResult(BaseModel):
    transcript: str
    confidence: float
    is_final: bool = True


class TTSRequest(BaseModel):
    tenant_id: str
    text: str
    voice: str | None = None
    audio_format: str = "wav"


class TTSResult(BaseModel):
    audio_base64: str
    audio_format: str
    segments: list[str] = Field(default_factory=list)


class PromptConfig(BaseModel):
    knowledge_answer: str
    business_answer: str
    fallback_answer: str
    handoff_summary: str


class PolicyConfig(BaseModel):
    knowledge_top_k: int = 3
    knowledge_min_score: float = 0.18
    handoff_confidence_threshold: float = 0.45
    route_fallback_confidence_threshold: float = 0.55
    route_handoff_confidence_threshold: float = 0.3
    intent_stack_max_depth: int = 6
    risk_keywords: list[str] = Field(
        default_factory=lambda: ["投诉", "仲裁", "监管", "律师", "报警", "安全事故"]
    )
    human_request_keywords: list[str] = Field(
        default_factory=lambda: ["人工", "真人", "客服", "转接人工", "投诉专员"]
    )
    intent_return_keywords: list[str] = Field(
        default_factory=lambda: [
            "回到刚才的问题",
            "还是回到刚才的问题",
            "继续刚才的问题",
            "还是那个问题",
            "继续刚才那个",
        ]
    )
    business_keyword_map: dict[str, list[str]] = Field(
        default_factory=lambda: {
            "order_status": ["订单", "发货", "订单状态", "快递单号"],
            "after_sale_status": ["售后", "退款进度", "退货", "工单"],
            "logistics_tracking": ["物流", "快递", "配送", "轨迹"],
            "account_lookup": ["账号", "会员", "积分", "账户"],
        }
    )


class AlertRuleConfig(BaseModel):
    provider_not_ready_enabled: bool = True
    diagnostic_error_threshold: int = 1
    diagnostic_error_sample_limit: int = 20
    waiting_human_session_threshold: int = 1
    waiting_human_session_sample_limit: int = 10


class DiagnosticEvent(BaseModel):
    event_id: str = Field(default_factory=lambda: new_id("diag"))
    level: DiagnosticLevel
    code: str
    message: str
    context: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utcnow)


class RTCRoom(BaseModel):
    tenant_id: str
    room_id: str = Field(default_factory=lambda: new_id("room"))
    session_id: str | None = None
    state: RTCState = RTCState.CREATED
    participants: list[str] = Field(default_factory=list)
    last_transcript: str = ""
    handoff_requested: bool = False
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
