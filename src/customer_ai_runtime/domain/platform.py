from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from customer_ai_runtime.domain.models import IntentFrame


class IndustryType(StrEnum):
    ECOMMERCE = "ecommerce"
    SAAS = "saas"
    EDUCATION = "education"
    LOGISTICS = "logistics"
    CRM = "crm"
    CUSTOM = "custom"


class PluginKind(StrEnum):
    ROUTE_STRATEGY = "route_strategy"
    BUSINESS_TOOL = "business_tool"
    HUMAN_HANDOFF = "human_handoff"
    INDUSTRY_ADAPTER = "industry_adapter"
    AUTH_BRIDGE = "auth_bridge"
    CONTEXT_ENRICHER = "context_enricher"
    RESPONSE_POST_PROCESSOR = "response_post_processor"


class AuthMode(StrEnum):
    API_KEY = "api_key"
    SESSION = "session"
    JWT = "jwt"
    CUSTOM_TOKEN = "custom_token"
    CUSTOM_BRIDGE = "custom_bridge"


class HostAuthContext(BaseModel):
    tenant_id: str
    principal_id: str
    principal_type: str = "user"
    roles: list[str] = Field(default_factory=list)
    permissions: list[str] = Field(default_factory=list)
    source_system: str = "host-system"
    auth_mode: AuthMode
    session_claims: dict[str, Any] = Field(default_factory=dict)
    business_scope: dict[str, Any] = Field(default_factory=dict)
    extra_context: dict[str, Any] = Field(default_factory=dict)


class ResolvedAuthContext(BaseModel):
    role: str
    tenant_ids: list[str]
    auth_mode: AuthMode
    host_auth_context: HostAuthContext | None = None


class AuthRequestContext(BaseModel):
    method: str
    path: str
    headers: dict[str, str] = Field(default_factory=dict)
    cookies: dict[str, str] = Field(default_factory=dict)
    query_params: dict[str, str] = Field(default_factory=dict)
    body: dict[str, Any] = Field(default_factory=dict)


class BusinessContext(BaseModel):
    tenant_id: str
    channel: str
    session_id: str | None = None
    industry: str | None = None
    host_auth_context: HostAuthContext | None = None
    integration_context: dict[str, Any] = Field(default_factory=dict)
    page_context: dict[str, Any] = Field(default_factory=dict)
    business_objects: dict[str, Any] = Field(default_factory=dict)
    user_profile: dict[str, Any] = Field(default_factory=dict)
    behavior_signals: dict[str, Any] = Field(default_factory=dict)
    session_summary: str = ""
    intent_stack: list[IntentFrame] = Field(default_factory=list)
    permissions: list[str] = Field(default_factory=list)
    extra: dict[str, Any] = Field(default_factory=dict)


class PluginDescriptor(BaseModel):
    plugin_id: str
    name: str
    version: str = "1.0.0"
    kind: PluginKind
    priority: int = 100
    enabled: bool = True
    description: str = ""
    tenant_scopes: list[str] = Field(default_factory=list)
    industry_scopes: list[str] = Field(default_factory=list)
    channel_scopes: list[str] = Field(default_factory=list)
    capabilities: list[str] = Field(default_factory=list)


class PluginContext(BaseModel):
    tenant_id: str
    channel: str
    session_id: str | None = None
    user_message: str | None = None
    industry: str | None = None
    integration_context: dict[str, Any] = Field(default_factory=dict)
    host_auth_context: HostAuthContext | None = None
    business_context: BusinessContext | None = None
    route: str | None = None
    response: dict[str, Any] = Field(default_factory=dict)
    extra: dict[str, Any] = Field(default_factory=dict)


class IndustryMatchResult(BaseModel):
    matched: bool = False
    industry: str | None = None
    confidence: float = 0.0
    context: dict[str, Any] = Field(default_factory=dict)


class RoutePluginResult(BaseModel):
    matched: bool = False
    route: str | None = None
    confidence: float = 0.0
    reason: str = ""
    intent: str | None = None
    tool_name: str | None = None
    requires_handoff: bool = False
    matched_signals: list[str] = Field(default_factory=list)


class HandoffDecision(BaseModel):
    should_handoff: bool = False
    reason: str = ""
    priority: int = 0
