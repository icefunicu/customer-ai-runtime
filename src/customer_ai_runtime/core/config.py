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

    aliyun_access_key_id: str | None = None
    aliyun_access_key_secret: str | None = None
    aliyun_app_key: str | None = None
    aliyun_token_region: str = "cn-shanghai"
    aliyun_token_domain: str = "nls-meta.cn-shanghai.aliyuncs.com"
    aliyun_asr_endpoint: str = "https://nls-gateway-cn-shanghai.aliyuncs.com/stream/v1/asr"
    aliyun_tts_endpoint: str = "https://nls-gateway-cn-shanghai.aliyuncs.com/stream/v1/tts"
    aliyun_speech_timeout_seconds: float = 30.0
    aliyun_asr_format: str = "wav"
    aliyun_asr_sample_rate: int = 16000
    aliyun_asr_enable_punctuation_prediction: bool = True
    aliyun_asr_enable_inverse_text_normalization: bool = True
    aliyun_asr_enable_voice_detection: bool = False
    aliyun_tts_voice: str = "xiaoyun"
    aliyun_tts_format: str = "wav"
    aliyun_tts_sample_rate: int = 16000
    aliyun_tts_volume: int = 50
    aliyun_tts_speech_rate: int = 0
    aliyun_tts_pitch_rate: int = 0

    tencent_secret_id: str | None = None
    tencent_secret_key: str | None = None
    tencent_region: str = "ap-beijing"
    tencent_asr_engine_model_type: str = "16k_zh"
    tencent_asr_voice_format: str = "wav"
    tencent_tts_voice_type: int = 101001
    tencent_tts_codec: str = "wav"
    tencent_tts_sample_rate: int = 16000
    tencent_tts_speed: float = 0.0
    tencent_tts_volume: float = 1.0
    tencent_tts_enable_subtitle: bool = False

    qdrant_url: str | None = None
    qdrant_api_key: str | None = None
    qdrant_collection_prefix: str = "customer_ai"

    pinecone_api_key: str | None = None
    pinecone_index_host: str | None = None
    pinecone_index_name: str | None = None
    pinecone_namespace_prefix: str = "customer_ai"

    milvus_uri: str | None = None
    milvus_token: str | None = None
    milvus_collection_prefix: str = "customer_ai"

    business_api_base_url: str | None = None
    business_api_key: str | None = None
    business_api_timeout_seconds: float = 8.0
    business_tool_endpoint_map_json: str = "{}"

    business_graphql_endpoint: str | None = None
    business_graphql_api_key: str | None = None
    business_graphql_timeout_seconds: float = 8.0
    business_graphql_query_map_json: str = "{}"
    business_graphql_response_path_map_json: str = "{}"
    business_graphql_headers_json: str = "{}"

    business_grpc_target: str | None = None
    business_grpc_timeout_seconds: float = 8.0
    business_grpc_method_map_json: str = "{}"
    business_grpc_metadata_json: str = "{}"

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
        return self._parse_json_dict(self.business_tool_endpoint_map_json)

    def get_business_graphql_query_map(self) -> dict[str, str]:
        return self._parse_json_dict(self.business_graphql_query_map_json)

    def get_business_graphql_response_path_map(self) -> dict[str, str]:
        return self._parse_json_dict(self.business_graphql_response_path_map_json)

    def get_business_graphql_headers(self) -> dict[str, str]:
        return self._parse_json_dict(self.business_graphql_headers_json)

    def get_business_grpc_method_map(self) -> dict[str, str]:
        return self._parse_json_dict(self.business_grpc_method_map_json)

    def get_business_grpc_metadata(self) -> dict[str, str]:
        return self._parse_json_dict(self.business_grpc_metadata_json)

    def get_host_session_map(self) -> dict[str, dict[str, object]]:
        raw = json.loads(self.host_session_map_json or "{}")
        return {str(key): dict(value) for key, value in raw.items()}

    def get_host_token_map(self) -> dict[str, dict[str, object]]:
        raw = json.loads(self.host_token_map_json or "{}")
        return {str(key): dict(value) for key, value in raw.items()}

    def get_knowledge_domain_map(self) -> dict[str, object]:
        return json.loads(self.knowledge_domain_map_json or "{}")

    def _parse_json_dict(self, raw_value: str) -> dict[str, str]:
        raw = json.loads(raw_value or "{}")
        return {str(key): str(value) for key, value in raw.items()}


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
