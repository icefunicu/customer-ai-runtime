from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from customer_ai_runtime.app import create_app
from customer_ai_runtime.core.config import get_settings


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("CUSTOMER_AI_STORAGE_ROOT", str(tmp_path / "storage"))
    monkeypatch.setenv("CUSTOMER_AI_RATE_LIMIT_ENABLED", "true")
    # Deterministic behavior: allow the first token, then never refill within the test.
    monkeypatch.setenv("CUSTOMER_AI_RATE_LIMIT_PER_MINUTE", "0")
    monkeypatch.setenv("CUSTOMER_AI_RATE_LIMIT_BURST", "1")
    get_settings.cache_clear()
    with TestClient(create_app()) as test_client:
        yield test_client
    get_settings.cache_clear()


def test_rate_limit_isolated_by_api_key(client: TestClient) -> None:
    first = client.get("/healthz", headers={"X-API-Key": "demo-public-key"})
    assert first.status_code == 200

    second = client.get("/healthz", headers={"X-API-Key": "demo-public-key"})
    assert second.status_code == 429
    assert second.json()["error"]["code"] == "rate_limited"

    third = client.get("/healthz", headers={"X-API-Key": "demo-admin-key"})
    assert third.status_code == 200
