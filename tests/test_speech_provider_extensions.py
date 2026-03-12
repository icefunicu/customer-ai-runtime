from __future__ import annotations

import base64
import json
from types import SimpleNamespace

import httpx
import pytest

from customer_ai_runtime.application.admin import AdminService
from customer_ai_runtime.application.container import _build_asr_provider, _build_tts_provider
from customer_ai_runtime.core.config import Settings
from customer_ai_runtime.domain.models import ASRRequest, TTSRequest
from customer_ai_runtime.providers.aliyun_provider import AliyunASRProvider, AliyunTTSProvider
from customer_ai_runtime.providers.tencent_provider import TencentASRProvider, TencentTTSProvider


def test_provider_factories_and_health_support_aliyun_and_tencent() -> None:
    aliyun_settings = Settings(
        asr_provider="aliyun",
        tts_provider="aliyun",
        aliyun_access_key_id="ak",
        aliyun_access_key_secret="secret",
        aliyun_app_key="app-key",
    )
    tencent_settings = Settings(
        asr_provider="tencent",
        tts_provider="tencent",
        tencent_secret_id="sid",
        tencent_secret_key="skey",
    )

    assert isinstance(_build_asr_provider(aliyun_settings), AliyunASRProvider)
    assert isinstance(_build_tts_provider(aliyun_settings), AliyunTTSProvider)
    assert isinstance(_build_asr_provider(tencent_settings), TencentASRProvider)
    assert isinstance(_build_tts_provider(tencent_settings), TencentTTSProvider)

    admin_service = AdminService(
        settings=aliyun_settings,
        session_service=SimpleNamespace(),
        knowledge_service=SimpleNamespace(),
        tool_catalog=SimpleNamespace(),
        rtc_service=SimpleNamespace(),
        runtime_config=SimpleNamespace(),
        metrics=SimpleNamespace(),
        diagnostics=SimpleNamespace(),
        plugin_registry=SimpleNamespace(),
    )

    health = admin_service.provider_health()

    assert health["asr"]["provider"] == "aliyun"
    assert health["asr"]["ready"] is True
    assert health["tts"]["provider"] == "aliyun"
    assert health["tts"]["ready"] is True


@pytest.mark.anyio
async def test_aliyun_asr_provider_transcribes_via_rest(monkeypatch: pytest.MonkeyPatch) -> None:
    import customer_ai_runtime.providers.aliyun_provider as aliyun_provider_module

    class FakeAcsClient:
        def __init__(self, access_key_id: str, access_key_secret: str, region: str) -> None:
            assert access_key_id == "ak"
            assert access_key_secret == "secret"
            assert region == "cn-shanghai"

        def do_action_with_exception(self, request: object) -> bytes:
            assert getattr(request, "domain", "") == "nls-meta.cn-shanghai.aliyuncs.com"
            return b'{"Token":{"Id":"aliyun-token","ExpireTime":4102444800}}'

    class FakeCommonRequest:
        def set_method(self, value: str) -> None:
            self.method = value

        def set_domain(self, value: str) -> None:
            self.domain = value

        def set_version(self, value: str) -> None:
            self.version = value

        def set_action_name(self, value: str) -> None:
            self.action = value

    def fake_import_module(name: str) -> object:
        if name == "aliyunsdkcore.client":
            return SimpleNamespace(AcsClient=FakeAcsClient)
        if name == "aliyunsdkcore.request":
            return SimpleNamespace(CommonRequest=FakeCommonRequest)
        raise ImportError(name)

    class FakeAsyncClient:
        def __init__(self, *args: object, **kwargs: object) -> None:
            return None

        async def __aenter__(self) -> FakeAsyncClient:
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:  # type: ignore[no-untyped-def]
            return None

        async def post(
            self,
            url: str,
            *,
            params: dict[str, object],
            headers: dict[str, str],
            content: bytes,
        ) -> httpx.Response:
            assert url.endswith("/stream/v1/asr")
            assert params["appkey"] == "app-key"
            assert params["format"] == "wav"
            assert headers["X-NLS-Token"] == "aliyun-token"
            assert content == b"audio-bytes"
            return httpx.Response(
                200,
                json={"status": 20000000, "result": "阿里云识别成功"},
                request=httpx.Request("POST", url),
                headers={"content-type": "application/json"},
            )

    monkeypatch.setattr(aliyun_provider_module, "import_module", fake_import_module)
    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)

    provider = AliyunASRProvider(
        Settings(
            aliyun_access_key_id="ak",
            aliyun_access_key_secret="secret",
            aliyun_app_key="app-key",
        )
    )

    result = await provider.transcribe(
        ASRRequest(
            tenant_id="demo-tenant",
            audio_base64=base64.b64encode(b"audio-bytes").decode("utf-8"),
            content_type="audio/wav",
        )
    )

    assert result.transcript == "阿里云识别成功"
    assert result.is_final is True


@pytest.mark.anyio
async def test_aliyun_tts_provider_returns_audio(monkeypatch: pytest.MonkeyPatch) -> None:
    import customer_ai_runtime.providers.aliyun_provider as aliyun_provider_module

    class FakeAcsClient:
        def __init__(self, access_key_id: str, access_key_secret: str, region: str) -> None:
            return None

        def do_action_with_exception(self, request: object) -> bytes:
            return b'{"Token":{"Id":"aliyun-token","ExpireTime":4102444800}}'

    class FakeCommonRequest:
        def set_method(self, value: str) -> None:
            self.method = value

        def set_domain(self, value: str) -> None:
            self.domain = value

        def set_version(self, value: str) -> None:
            self.version = value

        def set_action_name(self, value: str) -> None:
            self.action = value

    def fake_import_module(name: str) -> object:
        if name == "aliyunsdkcore.client":
            return SimpleNamespace(AcsClient=FakeAcsClient)
        if name == "aliyunsdkcore.request":
            return SimpleNamespace(CommonRequest=FakeCommonRequest)
        raise ImportError(name)

    class FakeAsyncClient:
        def __init__(self, *args: object, **kwargs: object) -> None:
            return None

        async def __aenter__(self) -> FakeAsyncClient:
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:  # type: ignore[no-untyped-def]
            return None

        async def post(
            self,
            url: str,
            *,
            json: dict[str, object],
            headers: dict[str, str],
        ) -> httpx.Response:
            assert url.endswith("/stream/v1/tts")
            assert json["voice"] == "xiaoyun"
            assert json["token"] == "aliyun-token"
            return httpx.Response(
                200,
                content=b"wav-bytes",
                request=httpx.Request("POST", url),
                headers={"content-type": "audio/wav"},
            )

    monkeypatch.setattr(aliyun_provider_module, "import_module", fake_import_module)
    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)

    provider = AliyunTTSProvider(
        Settings(
            aliyun_access_key_id="ak",
            aliyun_access_key_secret="secret",
            aliyun_app_key="app-key",
        )
    )

    result = await provider.synthesize(TTSRequest(tenant_id="demo-tenant", text="你好"))

    assert base64.b64decode(result.audio_base64) == b"wav-bytes"
    assert result.audio_format == "wav"


@pytest.mark.anyio
async def test_tencent_speech_providers_use_official_sdk(monkeypatch: pytest.MonkeyPatch) -> None:
    import customer_ai_runtime.providers.tencent_provider as tencent_provider_module

    captured: dict[str, dict[str, object]] = {}
    encoded_audio = base64.b64encode(b"tts-audio").decode("utf-8")

    class FakeCredential:
        def __init__(self, secret_id: str, secret_key: str) -> None:
            assert secret_id == "sid"
            assert secret_key == "skey"

    class FakeAsrRequest:
        def from_json_string(self, raw: str) -> None:
            captured["asr_request"] = json.loads(raw)

    class FakeTtsRequest:
        def from_json_string(self, raw: str) -> None:
            captured["tts_request"] = json.loads(raw)

    class FakeAsrClient:
        def __init__(self, credential: object, region: str) -> None:
            assert region == "ap-beijing"

        def SentenceRecognition(self, request: FakeAsrRequest) -> object:
            return SimpleNamespace(
                to_json_string=lambda: json.dumps(
                    {"Response": {"Result": "腾讯云识别成功", "RequestId": "req-asr"}}
                )
            )

    class FakeTtsClient:
        def __init__(self, credential: object, region: str) -> None:
            assert region == "ap-beijing"

        def TextToVoice(self, request: FakeTtsRequest) -> object:
            return SimpleNamespace(
                to_json_string=lambda: json.dumps(
                    {"Response": {"Audio": encoded_audio, "RequestId": "req-tts"}}
                )
            )

    def fake_import_module(name: str) -> object:
        mapping = {
            "tencentcloud.common.credential": SimpleNamespace(Credential=FakeCredential),
            "tencentcloud.asr.v20190614.asr_client": SimpleNamespace(AsrClient=FakeAsrClient),
            "tencentcloud.asr.v20190614.models": SimpleNamespace(
                SentenceRecognitionRequest=FakeAsrRequest
            ),
            "tencentcloud.tts.v20190823.tts_client": SimpleNamespace(TtsClient=FakeTtsClient),
            "tencentcloud.tts.v20190823.models": SimpleNamespace(TextToVoiceRequest=FakeTtsRequest),
        }
        if name not in mapping:
            raise ImportError(name)
        return mapping[name]

    monkeypatch.setattr(tencent_provider_module, "import_module", fake_import_module)

    asr_provider = TencentASRProvider(
        Settings(
            tencent_secret_id="sid",
            tencent_secret_key="skey",
        )
    )
    tts_provider = TencentTTSProvider(
        Settings(
            tencent_secret_id="sid",
            tencent_secret_key="skey",
        )
    )

    asr_result = await asr_provider.transcribe(
        ASRRequest(
            tenant_id="demo-tenant",
            audio_base64=base64.b64encode(b"pcm-audio").decode("utf-8"),
            content_type="audio/wav",
        )
    )
    tts_result = await tts_provider.synthesize(
        TTSRequest(
            tenant_id="demo-tenant",
            text="你好，欢迎使用腾讯云语音",
            voice="101002",
        )
    )

    assert asr_result.transcript == "腾讯云识别成功"
    assert captured["asr_request"]["VoiceFormat"] == "wav"
    assert captured["asr_request"]["DataLen"] == len(b"pcm-audio")
    assert tts_result.audio_base64 == encoded_audio
    assert captured["tts_request"]["VoiceType"] == 101002
    assert captured["tts_request"]["Codec"] == "wav"
