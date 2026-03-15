from __future__ import annotations

import base64
import hashlib
import hmac
import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from customer_ai_runtime.app import create_app
from customer_ai_runtime.application.auth import AuthBridgePlugin
from customer_ai_runtime.application.plugins import PluginDescriptor
from customer_ai_runtime.core.config import get_settings
from customer_ai_runtime.domain.platform import (
    AuthMode,
    AuthRequestContext,
    PluginKind,
    ResolvedAuthContext,
)
from customer_ai_runtime.integration import CustomerAIRuntimeModule

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
            "content": (
                "\u4e03\u5929\u65e0\u7406\u7531\u9000\u6b3e\uff0c"
                "\u552e\u540e\u5de5\u5355 24 \u5c0f\u65f6\u5185\u54cd\u5e94\u3002"
            ),
            "metadata": {"source": "help-center"},
        },
    )
    assert response.status_code == 200


def issue_test_jwt(secret: str, payload: dict[str, object]) -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    encoded_header = base64.urlsafe_b64encode(json.dumps(header).encode()).rstrip(b"=").decode()
    encoded_payload = base64.urlsafe_b64encode(json.dumps(payload).encode()).rstrip(b"=").decode()
    signing_input = f"{encoded_header}.{encoded_payload}".encode()
    signature = hmac.new(secret.encode(), signing_input, hashlib.sha256).digest()
    encoded_signature = base64.urlsafe_b64encode(signature).rstrip(b"=").decode()
    return f"{encoded_header}.{encoded_payload}.{encoded_signature}"


class HeaderBridgePlugin(AuthBridgePlugin):
    def __init__(self) -> None:
        super().__init__(
            PluginDescriptor(
                plugin_id="auth.test_header",
                name="Test Header Bridge",
                kind=PluginKind.AUTH_BRIDGE,
                priority=900,
                capabilities=["custom_header"],
            )
        )

    async def can_handle(self, request_data: AuthRequestContext) -> bool:
        return request_data.headers.get("x-test-host-user") == "user-custom"

    async def authenticate(self, request_data: AuthRequestContext) -> ResolvedAuthContext:
        return ResolvedAuthContext(
            role="customer",
            tenant_ids=["demo-tenant"],
            auth_mode=AuthMode.CUSTOM_BRIDGE,
        )


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
            "message": (
                "\u6211\u7684\u8ba2\u5355 ORD-1001 \u4ec0\u4e48\u65f6\u5019\u53d1\u8d27\uff1f"
            ),
        },
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["route"] == "business"
    assert data["tool_result"]["status"] == "success"


def test_chat_route_uses_page_context_for_contextual_question(client: TestClient) -> None:
    response = client.post(
        "/api/v1/chat/messages",
        headers=CUSTOMER_HEADERS,
        json={
            "tenant_id": "demo-tenant",
            "channel": "web",
            "message": "这个现在到哪里？",
            "integration_context": {
                "industry": "ecommerce",
                "page_context": {"page_type": "order_detail"},
                "business_objects": {"order_id": "ORD-1001"},
            },
        },
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["route"] == "business"
    assert data["route_decision"]["tool_name"] == "order_status"
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
        json={
            "tenant_id": "demo-tenant",
            "content": "\u4eba\u5de5\u5ba2\u670d\u5df2\u63a5\u624b\u5904\u7406",
        },
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


def test_message_feedback_records_upvote_and_updates_summary(client: TestClient) -> None:
    chat = client.post(
        "/api/v1/chat/messages",
        headers=CUSTOMER_HEADERS,
        json={
            "tenant_id": "demo-tenant",
            "channel": "web",
            "message": "鎴戠殑璁㈠崟 ORD-1001 鍙戣揣浜嗗悧",
        },
    )
    assert chat.status_code == 200
    session_id = chat.json()["data"]["session_id"]

    messages = client.get(
        f"/api/v1/sessions/{session_id}/messages",
        headers=CUSTOMER_HEADERS,
        params={"tenant_id": "demo-tenant"},
    )
    assert messages.status_code == 200
    assistant_message = next(
        item for item in messages.json()["data"] if item["role"] == "assistant"
    )

    feedback = client.post(
        f"/api/v1/sessions/{session_id}/messages/{assistant_message['message_id']}/feedback",
        headers=CUSTOMER_HEADERS,
        json={
            "tenant_id": "demo-tenant",
            "feedback_type": "upvote",
            "comment": "这个回答有帮助",
        },
    )
    assert feedback.status_code == 200
    feedback_data = feedback.json()["data"]
    assert feedback_data["message"]["feedback_type"] == "upvote"
    assert feedback_data["message"]["feedback_comment"] == "这个回答有帮助"
    assert feedback_data["message"]["feedback_submitted_at"] is not None

    summary = client.get(
        "/api/v1/admin/metrics/summary",
        headers=ADMIN_HEADERS,
        params={"tenant_id": "demo-tenant"},
    )
    assert summary.status_code == 200
    feedback_summary = summary.json()["data"]["feedback_summary"]
    assert feedback_summary["feedback_count"] == 1
    assert feedback_summary["distribution"]["upvote"] == 1


def test_message_feedback_can_request_human_handoff(client: TestClient) -> None:
    chat = client.post(
        "/api/v1/chat/messages",
        headers=CUSTOMER_HEADERS,
        json={
            "tenant_id": "demo-tenant",
            "channel": "web",
            "message": "閫€娆捐鍒欐槸浠€涔堬紵",
            "knowledge_base_id": "kb_support",
        },
    )
    if chat.status_code != 200:
        seed_knowledge_base(client)
        chat = client.post(
            "/api/v1/chat/messages",
            headers=CUSTOMER_HEADERS,
            json={
                "tenant_id": "demo-tenant",
                "channel": "web",
                "message": "閫€娆捐鍒欐槸浠€涔堬紵",
                "knowledge_base_id": "kb_support",
            },
        )
    assert chat.status_code == 200
    session_id = chat.json()["data"]["session_id"]

    messages = client.get(
        f"/api/v1/sessions/{session_id}/messages",
        headers=CUSTOMER_HEADERS,
        params={"tenant_id": "demo-tenant"},
    )
    assert messages.status_code == 200
    assistant_message = next(
        item for item in messages.json()["data"] if item["role"] == "assistant"
    )

    feedback = client.post(
        f"/api/v1/sessions/{session_id}/messages/{assistant_message['message_id']}/feedback",
        headers=CUSTOMER_HEADERS,
        json={
            "tenant_id": "demo-tenant",
            "feedback_type": "request_human",
            "comment": "杩欎釜鍥炵瓟娌¤В鍐抽棶棰橈紝璇疯浆浜哄伐",
        },
    )
    assert feedback.status_code == 200
    feedback_data = feedback.json()["data"]
    assert feedback_data["message"]["feedback_type"] == "request_human"
    assert feedback_data["session"]["state"] == "waiting_human"
    assert feedback_data["handoff"] is not None


def test_close_session_can_record_satisfaction_score(client: TestClient) -> None:
    chat = client.post(
        "/api/v1/chat/messages",
        headers=CUSTOMER_HEADERS,
        json={
            "tenant_id": "demo-tenant",
            "channel": "web",
            "message": "鎴戠殑璁㈠崟 ORD-1001 鍙戣揣浜嗗悧",
        },
    )
    assert chat.status_code == 200
    session_id = chat.json()["data"]["session_id"]

    close = client.post(
        f"/api/v1/sessions/{session_id}/close",
        headers=ADMIN_HEADERS,
        json={
            "tenant_id": "demo-tenant",
            "channel": "admin",
            "satisfaction_score": 5,
        },
    )
    assert close.status_code == 200
    close_data = close.json()["data"]
    assert close_data["state"] == "closed"
    assert close_data["satisfaction_score"] == 5
    assert close_data["satisfaction_submitted_at"] is not None

    summary = client.get(
        "/api/v1/admin/metrics/summary",
        headers=ADMIN_HEADERS,
        params={"tenant_id": "demo-tenant"},
    )
    assert summary.status_code == 200
    satisfaction_summary = summary.json()["data"]["satisfaction_summary"]
    assert satisfaction_summary["rated_sessions"] == 1
    assert satisfaction_summary["average_score"] == 5.0
    assert satisfaction_summary["distribution"]["5"] == 1


def test_close_session_can_record_resolution_status(client: TestClient) -> None:
    chat = client.post(
        "/api/v1/chat/messages",
        headers=CUSTOMER_HEADERS,
        json={
            "tenant_id": "demo-tenant",
            "channel": "web",
            "message": "我要人工客服",
        },
    )
    assert chat.status_code == 200
    session_id = chat.json()["data"]["session_id"]

    close = client.post(
        f"/api/v1/sessions/{session_id}/close",
        headers=ADMIN_HEADERS,
        json={
            "tenant_id": "demo-tenant",
            "channel": "admin",
            "resolution_status": "escalated",
        },
    )
    assert close.status_code == 200
    close_data = close.json()["data"]
    assert close_data["state"] == "closed"
    assert close_data["resolution_status"] == "escalated"
    assert close_data["resolution_marked_at"] is not None

    summary = client.get(
        "/api/v1/admin/metrics/summary",
        headers=ADMIN_HEADERS,
        params={"tenant_id": "demo-tenant"},
    )
    assert summary.status_code == 200
    resolution_summary = summary.json()["data"]["resolution_summary"]
    assert resolution_summary["marked_sessions"] == 1
    assert resolution_summary["distribution"]["escalated"] == 1


def test_session_tracks_response_timing_for_text_channel(client: TestClient) -> None:
    first = client.post(
        "/api/v1/chat/messages",
        headers=CUSTOMER_HEADERS,
        json={
            "tenant_id": "demo-tenant",
            "channel": "web",
            "message": "鎴戠殑璁㈠崟 ORD-1001 鍙戣揣浜嗗悧",
        },
    )
    assert first.status_code == 200
    session_id = first.json()["data"]["session_id"]

    second = client.post(
        "/api/v1/chat/messages",
        headers=CUSTOMER_HEADERS,
        json={
            "tenant_id": "demo-tenant",
            "session_id": session_id,
            "channel": "web",
            "message": "这个现在到哪里？",
            "integration_context": {
                "industry": "ecommerce",
                "page_context": {"page_type": "order_detail"},
                "business_objects": {"order_id": "ORD-1001"},
            },
        },
    )
    assert second.status_code == 200

    session = client.get(
        f"/api/v1/sessions/{session_id}",
        headers=CUSTOMER_HEADERS,
        params={"tenant_id": "demo-tenant"},
    )
    assert session.status_code == 200
    session_data = session.json()["data"]
    assert session_data["first_response_time"] is not None
    assert session_data["avg_response_time"] is not None
    assert session_data["response_count"] == 2
    assert session_data["first_response_time"] >= 1
    assert session_data["avg_response_time"] >= 1


def test_metrics_summary_includes_response_timing_by_channel(client: TestClient) -> None:
    text_chat = client.post(
        "/api/v1/chat/messages",
        headers=CUSTOMER_HEADERS,
        json={
            "tenant_id": "demo-tenant",
            "channel": "web",
            "message": "璁㈠崟 ORD-1001 鍙戣揣浜嗗悧",
        },
    )
    assert text_chat.status_code == 200

    transcript = "璁㈠崟 ORD-1001 鍙戣揣浜嗗悧"
    voice_turn = client.post(
        "/api/v1/voice/turn",
        headers=CUSTOMER_HEADERS,
        json={
            "tenant_id": "demo-tenant",
            "channel": "app_voice",
            "audio_base64": base64.b64encode(transcript.encode("utf-8")).decode("utf-8"),
            "content_type": "text/plain",
        },
    )
    assert voice_turn.status_code == 200

    summary = client.get(
        "/api/v1/admin/metrics/summary",
        headers=ADMIN_HEADERS,
        params={"tenant_id": "demo-tenant"},
    )
    assert summary.status_code == 200
    response_time_summary = summary.json()["data"]["response_time_summary"]
    assert response_time_summary["tracked_sessions"] >= 2
    assert response_time_summary["first_response_avg_ms"] >= 1
    assert response_time_summary["avg_response_avg_ms"] >= 1
    assert response_time_summary["channel_breakdown"]["web"]["sessions"] >= 1
    assert response_time_summary["channel_breakdown"]["app_voice"]["sessions"] >= 1


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
                    "\u6211\u7684\u8ba2\u5355 ORD-1001 \u53d1\u8d27\u4e86\u5417".encode()
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


def test_admin_runtime_config_hot_update(client: TestClient) -> None:
    response = client.put(
        "/api/v1/admin/runtime-config",
        headers=ADMIN_HEADERS,
        json={
            "prompts": {"fallback_answer": "请先提供订单号。"},
            "policies": {"knowledge_top_k": 6},
            "alerts": {
                "diagnostic_error_threshold": 2,
                "waiting_human_session_threshold": 2,
            },
            "plugin_states": {"route.business_intent": False},
        },
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["prompts"]["fallback_answer"] == "请先提供订单号。"
    assert data["policies"]["knowledge_top_k"] == 6
    assert data["alerts"]["diagnostic_error_threshold"] == 2
    assert data["alerts"]["waiting_human_session_threshold"] == 2
    assert data["plugin_states"]["route.business_intent"] is False

    runtime_config = client.get("/api/v1/admin/runtime-config", headers=ADMIN_HEADERS)
    assert runtime_config.status_code == 200
    assert runtime_config.json()["data"]["policies"]["knowledge_top_k"] == 6
    assert runtime_config.json()["data"]["alerts"]["diagnostic_error_threshold"] == 2

    chat_after_disable = client.post(
        "/api/v1/chat/messages",
        headers=CUSTOMER_HEADERS,
        json={
            "tenant_id": "demo-tenant",
            "channel": "web",
            "message": "璁㈠崟 ORD-1001 鍙戣揣浜嗗悧",
            "integration_context": {"industry": "ecommerce"},
        },
    )
    assert chat_after_disable.status_code == 200
    assert chat_after_disable.json()["data"]["route"] == "fallback"


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


def test_admin_knowledge_health_report(client: TestClient) -> None:
    seed_knowledge_base(client)
    report = client.get(
        "/api/v1/admin/knowledge-bases/kb_support/health",
        headers=ADMIN_HEADERS,
        params={"tenant_id": "demo-tenant"},
    )
    assert report.status_code == 200
    data = report.json()["data"]
    assert data["knowledge_base_id"] == "kb_support"
    assert data["document_count"] >= 1
    assert data["chunk_count"] >= 1
    assert data["health_score"] >= 0


def test_admin_retrieval_miss_report(client: TestClient) -> None:
    seed_knowledge_base(client)
    policy_update = client.put(
        "/api/v1/admin/policies",
        headers=ADMIN_HEADERS,
        json={"knowledge_min_score": 0.99},
    )
    assert policy_update.status_code == 200

    chat = client.post(
        "/api/v1/chat/messages",
        headers=CUSTOMER_HEADERS,
        json={
            "tenant_id": "demo-tenant",
            "channel": "web",
            "message": "Where is the end of the universe?",
            "knowledge_base_id": "kb_support",
        },
    )
    assert chat.status_code == 200

    report = client.get(
        "/api/v1/admin/knowledge/retrieval-misses",
        headers=ADMIN_HEADERS,
        params={"tenant_id": "demo-tenant", "knowledge_base_id": "kb_support"},
    )
    assert report.status_code == 200
    data = report.json()["data"]
    assert data["knowledge_base_id"] == "kb_support"
    assert data["miss_count"] >= 1
    assert any(item["query"] == "Where is the end of the universe?" for item in data["top_queries"])


def test_admin_session_monitor_and_diagnostics_filters(client: TestClient) -> None:
    chat = client.post(
        "/api/v1/chat/messages",
        headers=CUSTOMER_HEADERS,
        json={
            "tenant_id": "demo-tenant",
            "channel": "web",
            "message": "我要人工客服",
        },
    )
    assert chat.status_code == 200
    session_id = chat.json()["data"]["session_id"]

    monitor = client.get(
        f"/api/v1/admin/sessions/{session_id}/monitor",
        headers=ADMIN_HEADERS,
        params={"tenant_id": "demo-tenant"},
    )
    assert monitor.status_code == 200
    monitor_data = monitor.json()["data"]
    assert monitor_data["session"]["session_id"] == session_id
    assert monitor_data["message_count"] >= 2
    assert any(item["code"].startswith("chat.") for item in monitor_data["diagnostics"])

    filtered = client.get(
        "/api/v1/admin/diagnostics",
        headers=ADMIN_HEADERS,
        params={
            "tenant_id": "demo-tenant",
            "session_id": session_id,
            "code_prefix": "chat.",
            "limit": 20,
        },
    )
    assert filtered.status_code == 200
    filtered_data = filtered.json()["data"]
    assert filtered_data
    assert all(item["context"]["session_id"] == session_id for item in filtered_data)
    assert all(item["code"].startswith("chat.") for item in filtered_data)


def test_admin_tool_catalog_filters(client: TestClient) -> None:
    disable = client.post(
        "/api/v1/admin/plugins/tool.order_status/disable",
        headers=ADMIN_HEADERS,
    )
    assert disable.status_code == 200

    filtered = client.get(
        "/api/v1/admin/tools/catalog",
        headers=ADMIN_HEADERS,
        params={
            "tenant_id": "demo-tenant",
            "industry": "ecommerce",
            "include_disabled": "false",
        },
    )
    assert filtered.status_code == 200
    data = filtered.json()["data"]
    assert data
    assert all("ecommerce" in item["industry_scopes"] for item in data)
    assert all(item["enabled"] is True for item in data)
    assert all(item["name"] != "order_status" for item in data)


def test_admin_tool_catalog_categories(client: TestClient) -> None:
    categories = client.get(
        "/api/v1/admin/tools/catalog/categories",
        headers=ADMIN_HEADERS,
        params={"industry": "ecommerce", "include_disabled": "false"},
    )
    assert categories.status_code == 200
    data = categories.json()["data"]
    assert data
    ecommerce = next(item for item in data if item["category"] == "ecommerce")
    assert ecommerce["tool_count"] >= 2
    assert ecommerce["enabled_count"] >= 2
    assert "after_sale_status" in ecommerce["tools"]


def test_admin_metrics_summary_and_alerts(client: TestClient) -> None:
    threshold_update = client.put(
        "/api/v1/admin/runtime-config",
        headers=ADMIN_HEADERS,
        json={"alerts": {"waiting_human_session_threshold": 2}},
    )
    assert threshold_update.status_code == 200

    chat = client.post(
        "/api/v1/chat/messages",
        headers=CUSTOMER_HEADERS,
        json={
            "tenant_id": "demo-tenant",
            "channel": "web",
            "message": "我要转人工",
        },
    )
    assert chat.status_code == 200

    summary = client.get(
        "/api/v1/admin/metrics/summary",
        headers=ADMIN_HEADERS,
        params={"tenant_id": "demo-tenant"},
    )
    assert summary.status_code == 200
    summary_data = summary.json()["data"]
    assert summary_data["session_summary"]["total"] >= 1
    assert "chat_requests" in summary_data["counters"]

    alerts = client.get(
        "/api/v1/admin/alerts",
        headers=ADMIN_HEADERS,
        params={"tenant_id": "demo-tenant"},
    )
    assert alerts.status_code == 200
    alert_codes = {item["code"] for item in alerts.json()["data"]}
    assert "session.waiting_human_threshold" not in alert_codes

    second_chat = client.post(
        "/api/v1/chat/messages",
        headers=CUSTOMER_HEADERS,
        json={
            "tenant_id": "demo-tenant",
            "channel": "web",
            "message": "我要人工客服",
        },
    )
    assert second_chat.status_code == 200

    alerts_after_threshold = client.get(
        "/api/v1/admin/alerts",
        headers=ADMIN_HEADERS,
        params={"tenant_id": "demo-tenant"},
    )
    assert alerts_after_threshold.status_code == 200
    alert_payload = {item["code"]: item for item in alerts_after_threshold.json()["data"]}
    assert "session.waiting_human_threshold" in alert_payload
    assert alert_payload["session.waiting_human_threshold"]["count"] >= 2
    assert alert_payload["session.waiting_human_threshold"]["threshold"] == 2


def test_auth_context_with_api_key(client: TestClient) -> None:
    response = client.get("/api/v1/auth/context", headers=CUSTOMER_HEADERS)
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["auth_mode"] == "api_key"
    assert data["tenant_ids"] == ["demo-tenant"]


def test_context_resolve_with_industry_and_page_context(client: TestClient) -> None:
    response = client.post(
        "/api/v1/context/resolve",
        headers=CUSTOMER_HEADERS,
        json={
            "tenant_id": "demo-tenant",
            "channel": "web",
            "integration_context": {
                "industry": "ecommerce",
                "page_context": {"page_type": "order_detail"},
                "business_objects": {"order_id": "ORD-1001"},
            },
        },
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["industry"] == "ecommerce"
    assert data["page_context"]["page_type"] == "order_detail"
    assert data["business_objects"]["order_id"] == "ORD-1001"


def test_chat_can_return_to_previous_intent_with_session_intent_stack(client: TestClient) -> None:
    seed_knowledge_base(client)
    policy_update = client.put(
        "/api/v1/admin/policies",
        headers=ADMIN_HEADERS,
        json={"intent_return_keywords": ["还是回到刚才的问题"]},
    )
    assert policy_update.status_code == 200
    first = client.post(
        "/api/v1/chat/messages",
        headers=CUSTOMER_HEADERS,
        json={
            "tenant_id": "demo-tenant",
            "channel": "web",
            "message": "我的订单什么时候发货",
            "integration_context": {
                "industry": "ecommerce",
                "page_context": {"page_type": "order_detail"},
                "business_objects": {"order_id": "ORD-1001"},
            },
        },
    )
    assert first.status_code == 200
    session_id = first.json()["data"]["session_id"]
    assert first.json()["data"]["route"] == "business"

    second = client.post(
        "/api/v1/chat/messages",
        headers=CUSTOMER_HEADERS,
        json={
            "tenant_id": "demo-tenant",
            "session_id": session_id,
            "channel": "web",
            "message": "What is the refund policy?",
            "knowledge_base_id": "kb_support",
        },
    )
    assert second.status_code == 200
    assert second.json()["data"]["route"] == "knowledge"

    third = client.post(
        "/api/v1/chat/messages",
        headers=CUSTOMER_HEADERS,
        json={
            "tenant_id": "demo-tenant",
            "session_id": session_id,
            "channel": "web",
            "message": "还是回到刚才的问题",
        },
    )
    assert third.status_code == 200
    third_data = third.json()["data"]
    assert third_data["route"] == "business"
    assert third_data["route_decision"]["tool_name"] == "order_status"
    assert third_data["tool_result"]["status"] == "success"

    session = client.get(
        f"/api/v1/sessions/{session_id}",
        headers=CUSTOMER_HEADERS,
        params={"tenant_id": "demo-tenant"},
    )
    assert session.status_code == 200
    intent_stack = session.json()["data"]["intent_stack"]
    assert len(intent_stack) >= 2
    assert intent_stack[-1]["intent"] == "order_status"


def test_session_auth_bridge_chat_flow(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CUSTOMER_AI_STORAGE_ROOT", str(tmp_path / "storage"))
    monkeypatch.setenv(
        "CUSTOMER_AI_HOST_SESSION_MAP_JSON",
        json.dumps(
            {
                "sess-1": {
                    "tenant_id": "demo-tenant",
                    "principal_id": "user-1",
                    "roles": ["member"],
                    "permissions": ["orders:read"],
                    "source_system": "host-shop",
                }
            }
        ),
    )
    get_settings.cache_clear()
    with TestClient(create_app()) as local_client:
        policy_update = local_client.put(
            "/api/v1/admin/policies",
            headers=ADMIN_HEADERS,
            json={"business_keyword_map": {"order_status": ["order-check"]}},
        )
        assert policy_update.status_code == 200
        local_client.cookies.set("host_session", "sess-1")
        response = local_client.post(
            "/api/v1/chat/messages",
            json={
                "tenant_id": "demo-tenant",
                "channel": "web",
                "message": "order-check ORD-1001",
                "integration_context": {"industry": "ecommerce"},
            },
        )
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["route"] == "business"
        assert data["host_auth_context"]["principal_id"] == "user-1"
        assert data["host_auth_context"]["auth_mode"] == "session"
    get_settings.cache_clear()


def test_jwt_auth_bridge_chat_flow(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    secret = "jwt-secret"
    monkeypatch.setenv("CUSTOMER_AI_STORAGE_ROOT", str(tmp_path / "storage"))
    monkeypatch.setenv("CUSTOMER_AI_HOST_JWT_SECRET", secret)
    token = issue_test_jwt(
        secret,
        {
            "tenant_id": "demo-tenant",
            "principal_id": "user-jwt",
            "roles": ["member"],
            "permissions": ["courses:read"],
            "source_system": "host-education",
        },
    )
    get_settings.cache_clear()
    with TestClient(create_app()) as local_client:
        response = local_client.post(
            "/api/v1/chat/messages",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "tenant_id": "demo-tenant",
                "channel": "web",
                "message": "课程 COURSE-6001 有效期到什么时候",
                "integration_context": {"industry": "education"},
            },
        )
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["host_auth_context"]["principal_id"] == "user-jwt"
        assert data["host_auth_context"]["auth_mode"] == "jwt"
    get_settings.cache_clear()


def test_custom_token_auth_bridge_and_plugin_toggle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CUSTOMER_AI_STORAGE_ROOT", str(tmp_path / "storage"))
    monkeypatch.setenv(
        "CUSTOMER_AI_HOST_TOKEN_MAP_JSON",
        json.dumps(
            {
                "host-token-1": {
                    "tenant_id": "demo-tenant",
                    "principal_id": "user-token",
                    "roles": ["member"],
                    "permissions": ["orders:read"],
                    "source_system": "host-app",
                }
            }
        ),
    )
    get_settings.cache_clear()
    with TestClient(create_app()) as local_client:
        policy_update = local_client.put(
            "/api/v1/admin/policies",
            headers=ADMIN_HEADERS,
            json={"business_keyword_map": {"order_status": ["order-check"]}},
        )
        assert policy_update.status_code == 200
        plugin_list = local_client.get("/api/v1/admin/plugins", headers=ADMIN_HEADERS)
        assert plugin_list.status_code == 200
        plugin_ids = {item["plugin_id"] for item in plugin_list.json()["data"]}
        assert "route.business_intent" in plugin_ids

        disabled = local_client.post(
            "/api/v1/admin/plugins/route.business_intent/disable",
            headers=ADMIN_HEADERS,
        )
        assert disabled.status_code == 200
        assert disabled.json()["data"]["enabled"] is False

        chat_after_disable = local_client.post(
            "/api/v1/chat/messages",
            headers={"X-Host-Token": "host-token-1"},
            json={
                "tenant_id": "demo-tenant",
                "channel": "web",
                "message": "order-check ORD-1001",
                "integration_context": {"industry": "ecommerce"},
            },
        )
        assert chat_after_disable.status_code == 200
        assert chat_after_disable.json()["data"]["route"] == "fallback"

        enabled = local_client.post(
            "/api/v1/admin/plugins/route.business_intent/enable",
            headers=ADMIN_HEADERS,
        )
        assert enabled.status_code == 200
        assert enabled.json()["data"]["enabled"] is True

        chat_after_enable = local_client.post(
            "/api/v1/chat/messages",
            headers={"X-Host-Token": "host-token-1"},
            json={
                "tenant_id": "demo-tenant",
                "channel": "web",
                "message": "order-check ORD-1001",
                "integration_context": {"industry": "ecommerce"},
            },
        )
        assert chat_after_enable.status_code == 200
        data = chat_after_enable.json()["data"]
        assert data["route"] == "business"
        assert data["host_auth_context"]["auth_mode"] == "custom_token"
    get_settings.cache_clear()


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

        plugin_disable = first_client.post(
            "/api/v1/admin/plugins/route.business_intent/disable",
            headers=ADMIN_HEADERS,
        )
        assert plugin_disable.status_code == 200

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

        plugins = second_client.get("/api/v1/admin/plugins", headers=ADMIN_HEADERS)
        assert plugins.status_code == 200
        business_route = next(
            item for item in plugins.json()["data"] if item["plugin_id"] == "route.business_intent"
        )
        assert business_route["enabled"] is False

        fallback_chat = second_client.post(
            "/api/v1/chat/messages",
            headers=CUSTOMER_HEADERS,
            json={
                "tenant_id": "demo-tenant",
                "channel": "web",
                "message": "璁㈠崟 ORD-1001 鍙戣揣浜嗗悧",
                "integration_context": {"industry": "ecommerce"},
            },
        )
        assert fallback_chat.status_code == 200
        assert fallback_chat.json()["data"]["route"] == "fallback"

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


def test_embedded_module_custom_auth_bridge(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CUSTOMER_AI_STORAGE_ROOT", str(tmp_path / "storage"))
    get_settings.cache_clear()
    host_app = FastAPI()
    module = CustomerAIRuntimeModule.create()
    module.register_plugin(HeaderBridgePlugin())
    module.mount_to(host_app, prefix="/embedded/customer-ai")

    with TestClient(host_app) as host_client:
        policy_update = host_client.put(
            "/embedded/customer-ai/api/v1/admin/policies",
            headers=ADMIN_HEADERS,
            json={"human_request_keywords": ["human-agent"]},
        )
        assert policy_update.status_code == 200
        response = host_client.post(
            "/embedded/customer-ai/api/v1/chat/messages",
            headers={"X-Test-Host-User": "user-custom"},
            json={
                "tenant_id": "demo-tenant",
                "channel": "web",
                "message": "human-agent",
            },
        )
        assert response.status_code == 200
        assert response.json()["data"]["route"] == "handoff"
    get_settings.cache_clear()


def test_admin_knowledge_version_snapshot_and_activate(client: TestClient) -> None:
    seed_knowledge_base(client)
    knowledge_base = client.get(
        "/api/v1/knowledge-bases/kb_support",
        headers=CUSTOMER_HEADERS,
        params={"tenant_id": "demo-tenant"},
    )
    assert knowledge_base.status_code == 200
    original_version_id = knowledge_base.json()["data"]["active_version_id"]

    snapshot = client.post(
        "/api/v1/admin/knowledge-bases/kb_support/versions/snapshot",
        headers=ADMIN_HEADERS,
        json={
            "tenant_id": "demo-tenant",
            "description": "snapshot before release",
        },
    )
    assert snapshot.status_code == 200
    snapshot_version_id = snapshot.json()["data"]["version"]["version_id"]
    assert snapshot.json()["data"]["version"]["status"] == "draft"

    versions = client.get(
        "/api/v1/admin/knowledge-bases/kb_support/versions",
        headers=ADMIN_HEADERS,
        params={"tenant_id": "demo-tenant"},
    )
    assert versions.status_code == 200
    assert len(versions.json()["data"]) >= 2

    activate_snapshot = client.post(
        f"/api/v1/admin/knowledge-bases/kb_support/versions/{snapshot_version_id}/activate",
        headers=ADMIN_HEADERS,
        json={"tenant_id": "demo-tenant"},
    )
    assert activate_snapshot.status_code == 200
    assert (
        activate_snapshot.json()["data"]["knowledge_base"]["active_version_id"]
        == snapshot_version_id
    )
    assert activate_snapshot.json()["data"]["version"]["status"] == "active"

    rollback = client.post(
        f"/api/v1/admin/knowledge-bases/kb_support/versions/{original_version_id}/activate",
        headers=ADMIN_HEADERS,
        json={"tenant_id": "demo-tenant"},
    )
    assert rollback.status_code == 200
    assert rollback.json()["data"]["knowledge_base"]["active_version_id"] == original_version_id
    assert rollback.json()["data"]["version"]["status"] == "active"


def test_admin_chunk_optimization_report_and_apply(client: TestClient) -> None:
    seed_knowledge_base(client)
    extra_doc = client.post(
        "/api/v1/knowledge-bases/kb_support/documents",
        headers=CUSTOMER_HEADERS,
        json={
            "tenant_id": "demo-tenant",
            "title": "optimization guide",
            "content": " ".join(
                [
                    (
                        "refund entry is on the order detail page and requests are processed "
                        "within 24 hours."
                    )
                ]
                * 20
            ),
            "metadata": {"source": "help-center"},
        },
    )
    assert extra_doc.status_code == 200

    report = client.get(
        "/api/v1/admin/knowledge-bases/kb_support/chunk-optimization",
        headers=ADMIN_HEADERS,
        params={"tenant_id": "demo-tenant"},
    )
    assert report.status_code == 200
    report_data = report.json()["data"]
    assert report_data["candidates"]
    current_config = report_data["current_config"]
    selected_config = report_data["recommended_config"]
    if selected_config == current_config:
        selected_config = next(
            item["chunk_config"]
            for item in report_data["candidates"]
            if item["chunk_config"] != current_config
        )

    apply_result = client.post(
        "/api/v1/admin/knowledge-bases/kb_support/chunk-optimization/apply",
        headers=ADMIN_HEADERS,
        json={
            "tenant_id": "demo-tenant",
            "max_tokens": selected_config["max_tokens"],
            "overlap": selected_config["overlap"],
            "description": "apply optimized chunk strategy",
            "activate": True,
        },
    )
    assert apply_result.status_code == 200
    apply_data = apply_result.json()["data"]
    assert apply_data["knowledge_base"]["chunk_max_tokens"] == selected_config["max_tokens"]
    assert apply_data["knowledge_base"]["chunk_overlap"] == selected_config["overlap"]
    assert apply_data["version"]["status"] == "active"
    assert apply_data["chunk_count"] >= 1


def test_admin_knowledge_effectiveness_report(client: TestClient) -> None:
    seed_knowledge_base(client)
    hit_chat = client.post(
        "/api/v1/chat/messages",
        headers=CUSTOMER_HEADERS,
        json={
            "tenant_id": "demo-tenant",
            "channel": "web",
            "message": "退款规则是什么？",
            "knowledge_base_id": "kb_support",
        },
    )
    assert hit_chat.status_code == 200
    session_id = hit_chat.json()["data"]["session_id"]

    messages = client.get(
        f"/api/v1/sessions/{session_id}/messages",
        headers=CUSTOMER_HEADERS,
        params={"tenant_id": "demo-tenant"},
    )
    assert messages.status_code == 200
    assistant_message = next(
        item for item in messages.json()["data"] if item["role"] == "assistant"
    )

    feedback = client.post(
        f"/api/v1/sessions/{session_id}/messages/{assistant_message['message_id']}/feedback",
        headers=CUSTOMER_HEADERS,
        json={
            "tenant_id": "demo-tenant",
            "feedback_type": "downvote",
            "comment": "需要更详细的退款步骤",
        },
    )
    assert feedback.status_code == 200

    close = client.post(
        f"/api/v1/sessions/{session_id}/close",
        headers=ADMIN_HEADERS,
        json={
            "tenant_id": "demo-tenant",
            "channel": "admin",
            "satisfaction_score": 4,
        },
    )
    assert close.status_code == 200

    policy_update = client.put(
        "/api/v1/admin/policies",
        headers=ADMIN_HEADERS,
        json={"knowledge_min_score": 0.99},
    )
    assert policy_update.status_code == 200

    miss_chat = client.post(
        "/api/v1/chat/messages",
        headers=CUSTOMER_HEADERS,
        json={
            "tenant_id": "demo-tenant",
            "channel": "web",
            "message": "Where is the end of the universe?",
            "knowledge_base_id": "kb_support",
        },
    )
    assert miss_chat.status_code == 200

    report = client.get(
        "/api/v1/admin/knowledge/effectiveness",
        headers=ADMIN_HEADERS,
        params={"tenant_id": "demo-tenant", "knowledge_base_id": "kb_support"},
    )
    assert report.status_code == 200
    data = report.json()["data"]
    assert data["knowledge_bases"]
    kb_report = data["knowledge_bases"][0]
    assert kb_report["knowledge_base_id"] == "kb_support"
    assert kb_report["query_count"] >= 2
    assert kb_report["effective_hit_count"] >= 1
    assert kb_report["miss_count"] >= 1
    assert kb_report["average_satisfaction"] == 4.0
    assert kb_report["negative_feedback_count"] >= 1
    assert kb_report["recommendation"]
