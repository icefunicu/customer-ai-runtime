from __future__ import annotations

import json
from functools import lru_cache
from typing import Literal

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


Role = Literal["customer", "operator", "admin"]


class ApiKeyRecord(BaseModel):
    role: Role
    tenant_ids: list[str] = Field(default_factory=list)


DEFAULT_API_KEYS = {
    "demo-public-key": {"role": "customer", "tenant_ids": ["demo-tenant"]},
    "demo-admin-key": {"role": "admin", "tenant_ids": ["demo-tenant"]},
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="CUSTOMER_AI_",
        env_file=".env",
        extra="ignore",
    )

    env: str = "dev"
    host: str = "127.0.0.1"
    port: int = 8000
    log_level: str = "INFO"
    storage_root: str = "storage"
    default_tenant_id: str = "demo-tenant"
    llm_provider: str = "local"
    asr_provider: str = "local"
    tts_provider: str = "local"
    vector_provider: str = "local"
    rtc_provider: str = "local"
    business_provider: str = "local"
    openai_api_key: str | None = None
    openai_base_url: str | None = None
    openai_chat_model: str = "gpt-4.1-mini"
    openai_transcription_model: str = "gpt-4o-mini-transcribe"
    openai_tts_model: str = "gpt-4o-mini-tts"
    openai_tts_voice: str = "alloy"
    qdrant_url: str | None = None
    qdrant_api_key: str | None = None
    qdrant_collection_prefix: str = "customer_ai"
    business_api_base_url: str | None = None
    business_api_key: str | None = None
    business_api_timeout_seconds: float = 8.0
    business_tool_endpoint_map_json: str = "{}"
    host_session_cookie_name: str = "host_session"
    host_session_map_json: str = "{}"
    host_token_map_json: str = "{}"
    host_jwt_secret: str | None = None
    host_jwt_issuer: str | None = None
    host_jwt_audience: str | None = None
    knowledge_domain_map_json: str = "{}"
    api_keys_json: str = Field(default_factory=lambda: json.dumps(DEFAULT_API_KEYS))

    def get_api_keys(self) -> dict[str, ApiKeyRecord]:
        raw = json.loads(self.api_keys_json or "{}")
        return {key: ApiKeyRecord.model_validate(value) for key, value in raw.items()}

    def get_business_tool_endpoint_map(self) -> dict[str, str]:
        return json.loads(self.business_tool_endpoint_map_json or "{}")

    def get_host_session_map(self) -> dict[str, dict[str, object]]:
        return json.loads(self.host_session_map_json or "{}")

    def get_host_token_map(self) -> dict[str, dict[str, object]]:
        return json.loads(self.host_token_map_json or "{}")

    def get_knowledge_domain_map(self) -> dict[str, object]:
        return json.loads(self.knowledge_domain_map_json or "{}")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
