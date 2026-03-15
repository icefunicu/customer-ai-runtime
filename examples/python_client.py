from __future__ import annotations

import base64

import httpx

BASE_URL = "http://127.0.0.1:8000"
# 本示例默认使用开发环境 demo key；生产环境请使用 CUSTOMER_AI_API_KEYS_JSON 配置真实 Key。
HEADERS = {"X-API-Key": "demo-public-key"}


def main() -> None:
    with httpx.Client(base_url=BASE_URL, headers=HEADERS, timeout=10.0) as client:
        client.post(
            "/api/v1/knowledge-bases",
            json={
                "tenant_id": "demo-tenant",
                "knowledge_base_id": "kb_support",
                "name": "support",
                "description": "support knowledge base",
            },
        )
        client.post(
            "/api/v1/knowledge-bases/kb_support/documents",
            json={
                "tenant_id": "demo-tenant",
                "title": "refund policy",
                "content": "7-day refund supported. after-sale tickets are answered in 24 hours.",
                "metadata": {"source": "example"},
            },
        )
        chat = client.post(
            "/api/v1/chat/messages",
            json={
                "tenant_id": "demo-tenant",
                "channel": "web",
                "message": "What is the refund policy?",
                "knowledge_base_id": "kb_support",
            },
        )
        print(chat.json())
        voice = client.post(
            "/api/v1/voice/turn",
            json={
                "tenant_id": "demo-tenant",
                "channel": "app_voice",
                "audio_base64": base64.b64encode(b"order ORD-1001 status").decode("utf-8"),
                "content_type": "text/plain",
            },
        )
        print(voice.json())


if __name__ == "__main__":
    main()
