from __future__ import annotations

import base64
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from customer_ai_runtime.app import create_app
from customer_ai_runtime.integration import CustomerAIRuntimeModule
from customer_ai_runtime.core.config import get_settings


CUSTOMER_HEADERS = {"X-API-Key": "demo-public-key"}
ADMIN_HEADERS = {"X-API-Key": "demo-admin-key"}


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("CUSTOMER_AI_STORAGE_ROOT", str(tmp_path / "storage"))
    get_settings.cache_clear()
    with TestClient(create_app()) as test_client:
        yield test_client
    get_settings.cache_clear()


def seed_knowledge_base(client: TestClient) -> None:
    response = client.post(
        "/api/v1/knowledge-bases",
        headers=CUSTOMER_HEADERS,
        json={
            "tenant_id": "demo-tenant",
            "knowledge_base_id": "kb_support",
            "name": "support",
            "description": "support kb",
        },
    )
    assert response.status_code == 200
    response = client.post(
        "/api/v1/knowledge-bases/kb_support/documents",
        headers=CUSTOMER_HEADERS,
        json={
            "tenant_id": "demo-tenant",
            "title": "\u9000\u6b3e\u89c4\u5219",
            "content": "\u4e03\u5929\u65e0\u7406\u7531\u9000\u6b3e\uff0c\u552e\u540e\u5de5\u5355 24 \u5c0f\u65f6\u5185\u54cd\u5e94\u3002",
            "metadata": {"source": "help-center"},
        },
    )
    assert response.status_code == 200


def test_chat_knowledge_flow(client: TestClient) -> None:
    seed_knowledge_base(client)
    response = client.post(
        "/api/v1/chat/messages",
        headers=CUSTOMER_HEADERS,
        json={
            "tenant_id": "demo-tenant",
            "channel": "web",
            "message": "\u9000\u6b3e\u89c4\u5219\u662f\u4ec0\u4e48\uff1f",
            "knowledge_base_id": "kb_support",
        },
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["route"] == "knowledge"
    assert data["citations"]


def test_chat_business_flow(client: TestClient) -> None:
    response = client.post(
        "/api/v1/chat/messages",
        headers=CUSTOMER_HEADERS,
        json={
            "tenant_id": "demo-tenant",
            "channel": "web",
            "message": "\u6211\u7684\u8ba2\u5355 ORD-1001 \u4ec0\u4e48\u65f6\u5019\u53d1\u8d27\uff1f",
        },
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["route"] == "business"
    assert data["tool_result"]["status"] == "success"


def test_handoff_flow(client: TestClient) -> None:
    response = client.post(
        "/api/v1/chat/messages",
        headers=CUSTOMER_HEADERS,
        json={
            "tenant_id": "demo-tenant",
            "channel": "web",
            "message": "\u6211\u8981\u8f6c\u4eba\u5de5\u5ba2\u670d",
        },
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["handoff"] is not None
    assert data["state"] == "waiting_human"

    claim = client.post(
        f"/api/v1/sessions/{data['session_id']}/claim-human",
        headers=ADMIN_HEADERS,
        json={"tenant_id": "demo-tenant", "channel": "admin"},
    )
    assert claim.status_code == 200
    assert claim.json()["data"]["state"] == "human_in_service"

    human_reply = client.post(
        f"/api/v1/sessions/{data['session_id']}/messages/human",
        headers=ADMIN_HEADERS,
        json={"tenant_id": "demo-tenant", "content": "\u4eba\u5de5\u5ba2\u670d\u5df2\u63a5\u624b\u5904\u7406"},
    )
    assert human_reply.status_code == 200
    assert human_reply.json()["data"]["messages"][-1]["role"] == "human"

    close = client.post(
        f"/api/v1/sessions/{data['session_id']}/close",
        headers=ADMIN_HEADERS,
        json={"tenant_id": "demo-tenant", "channel": "admin"},
    )
    assert close.status_code == 200
    assert close.json()["data"]["state"] == "closed"


def test_voice_turn_flow(client: TestClient) -> None:
    transcript = "\u8ba2\u5355 ORD-1001 \u53d1\u8d27\u4e86\u5417"
    response = client.post(
        "/api/v1/voice/turn",
        headers=CUSTOMER_HEADERS,
        json={
            "tenant_id": "demo-tenant",
            "channel": "app_voice",
            "audio_base64": base64.b64encode(transcript.encode("utf-8")).decode("utf-8"),
            "content_type": "text/plain",
        },
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["transcript"] == transcript
    assert data["audio_response_base64"]


def test_rtc_websocket_flow(client: TestClient) -> None:
    room_response = client.post(
        "/api/v1/rtc/rooms",
        headers=CUSTOMER_HEADERS,
        json={"tenant_id": "demo-tenant"},
    )
    assert room_response.status_code == 200
    room_id = room_response.json()["data"]["room_id"]
    join_response = client.post(
        f"/api/v1/rtc/rooms/{room_id}/join",
        headers=CUSTOMER_HEADERS,
        json={"tenant_id": "demo-tenant"},
    )
    assert join_response.status_code == 200

    with client.websocket_connect(
        f"/ws/v1/rtc/{room_id}?tenant_id=demo-tenant",
        headers=CUSTOMER_HEADERS,
    ) as websocket:
        websocket.send_json(
            {
                "type": "user_audio",
                "audio_base64": base64.b64encode(
                    "\u6211\u7684\u8ba2\u5355 ORD-1001 \u53d1\u8d27\u4e86\u5417".encode("utf-8")
                ).decode("utf-8"),
                "content_type": "text/plain",
            }
        )
        events = [websocket.receive_json() for _ in range(4)]
    event_types = {event["type"] for event in events}
    assert "transcript" in event_types
    assert "assistant_audio" in event_types


def test_admin_policy_update(client: TestClient) -> None:
    response = client.put(
        "/api/v1/admin/policies",
        headers=ADMIN_HEADERS,
        json={"knowledge_top_k": 5},
    )
    assert response.status_code == 200
    assert response.json()["data"]["knowledge_top_k"] == 5


def test_admin_room_and_knowledge_listing(client: TestClient) -> None:
    seed_knowledge_base(client)
    kb_list = client.get(
        "/api/v1/knowledge-bases",
        headers=CUSTOMER_HEADERS,
        params={"tenant_id": "demo-tenant"},
    )
    assert kb_list.status_code == 200
    assert len(kb_list.json()["data"]) == 1

    room = client.post(
        "/api/v1/rtc/rooms",
        headers=CUSTOMER_HEADERS,
        json={"tenant_id": "demo-tenant"},
    )
    assert room.status_code == 200
    rooms = client.get(
        "/api/v1/admin/rooms",
        headers=ADMIN_HEADERS,
        params={"tenant_id": "demo-tenant"},
    )
    assert rooms.status_code == 200
    assert len(rooms.json()["data"]) == 1

    diagnostics = client.get("/api/v1/admin/diagnostics", headers=ADMIN_HEADERS)
    assert diagnostics.status_code == 200
    assert diagnostics.json()["data"]


def test_persistence_across_app_restart(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    storage_root = tmp_path / "storage"
    monkeypatch.setenv("CUSTOMER_AI_STORAGE_ROOT", str(storage_root))
    get_settings.cache_clear()

    with TestClient(create_app()) as first_client:
        seed_knowledge_base(first_client)
        chat = first_client.post(
            "/api/v1/chat/messages",
            headers=CUSTOMER_HEADERS,
            json={
                "tenant_id": "demo-tenant",
                "channel": "web",
                "message": "\u6211\u8981\u8f6c\u4eba\u5de5",
            },
        )
        assert chat.status_code == 200
        session_id = chat.json()["data"]["session_id"]

        policy_update = first_client.put(
            "/api/v1/admin/policies",
            headers=ADMIN_HEADERS,
            json={"knowledge_top_k": 4},
        )
        assert policy_update.status_code == 200

    get_settings.cache_clear()

    with TestClient(create_app()) as second_client:
        sessions = second_client.get(
            "/api/v1/admin/sessions",
            headers=ADMIN_HEADERS,
            params={"tenant_id": "demo-tenant"},
        )
        assert sessions.status_code == 200
        assert any(item["session_id"] == session_id for item in sessions.json()["data"])

        policies = second_client.get("/api/v1/admin/policies", headers=ADMIN_HEADERS)
        assert policies.status_code == 200
        assert policies.json()["data"]["knowledge_top_k"] == 4

        kb_list = second_client.get(
            "/api/v1/knowledge-bases",
            headers=CUSTOMER_HEADERS,
            params={"tenant_id": "demo-tenant"},
        )
        assert kb_list.status_code == 200
        assert kb_list.json()["data"]

        provider_health = second_client.get(
            "/api/v1/admin/providers/health",
            headers=ADMIN_HEADERS,
        )
        assert provider_health.status_code == 200
        assert provider_health.json()["data"]["llm"]["ready"] is True

        tool_catalog = second_client.get(
            "/api/v1/admin/tools/catalog",
            headers=ADMIN_HEADERS,
        )
        assert tool_catalog.status_code == 200
        assert tool_catalog.json()["data"]

    get_settings.cache_clear()


@pytest.mark.anyio
async def test_embedded_module_direct_call(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CUSTOMER_AI_STORAGE_ROOT", str(tmp_path / "storage"))
    get_settings.cache_clear()
    module = CustomerAIRuntimeModule.create()
    await module.container.knowledge_service.create_knowledge_base(
        tenant_id="demo-tenant",
        knowledge_base_id="kb_support",
        name="support",
        description="support knowledge base",
    )
    await module.container.knowledge_service.add_document(
        tenant_id="demo-tenant",
        knowledge_base_id="kb_support",
        title="refund policy",
        content="7-day refund supported and after-sale tickets answered in 24 hours.",
        metadata={"source": "embedded"},
    )
    result = await module.chat(
        tenant_id="demo-tenant",
        message="What is the refund policy?",
        knowledge_base_id="kb_support",
        integration_context={"source_system": "host-app", "shop_id": "SHOP-1"},
    )
    assert result["answer"]
    assert result["citations"]
    get_settings.cache_clear()


def test_embedded_module_mount_to_host(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CUSTOMER_AI_STORAGE_ROOT", str(tmp_path / "storage"))
    get_settings.cache_clear()
    host_app = FastAPI()
    module = CustomerAIRuntimeModule.create()
    module.mount_to(host_app, prefix="/embedded/customer-ai")

    with TestClient(host_app) as host_client:
        response = host_client.get("/embedded/customer-ai/healthz")
        assert response.status_code == 200
        assert response.json()["data"]["status"] == "ok"
    get_settings.cache_clear()
