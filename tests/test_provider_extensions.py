from __future__ import annotations

from types import SimpleNamespace

import httpx
import pytest

from customer_ai_runtime.application.admin import AdminService
from customer_ai_runtime.application.container import _build_business_adapter
from customer_ai_runtime.core.config import Settings
from customer_ai_runtime.domain.models import BusinessQuery
from customer_ai_runtime.providers.graphql_business_provider import GraphQLBusinessAdapter
from customer_ai_runtime.providers.grpc_business_provider import GrpcBusinessAdapter


def test_settings_parse_extended_provider_maps() -> None:
    settings = Settings(
        business_graphql_query_map_json='{"order_status":"query OrderStatus { orderStatus }"}',
        business_graphql_response_path_map_json='{"order_status":"orderStatus"}',
        business_graphql_headers_json='{"X-Tenant":"demo-tenant"}',
        business_grpc_method_map_json='{"order_status":"/runtime.Business/OrderStatus"}',
        business_grpc_metadata_json='{"x-tenant":"demo-tenant"}',
    )

    assert settings.get_business_graphql_query_map()["order_status"].startswith("query")
    assert settings.get_business_graphql_response_path_map()["order_status"] == "orderStatus"
    assert settings.get_business_graphql_headers()["X-Tenant"] == "demo-tenant"
    assert (
        settings.get_business_grpc_method_map()["order_status"] == "/runtime.Business/OrderStatus"
    )
    assert settings.get_business_grpc_metadata()["x-tenant"] == "demo-tenant"


@pytest.mark.anyio
async def test_graphql_business_adapter_executes_query(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {
                "data": {
                    "orderStatus": {
                        "status": "success",
                        "summary": "order resolved by graphql",
                        "data": {"order_id": "ORD-1001"},
                    }
                }
            }

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
        ) -> FakeResponse:
            assert url == "https://graphql.example.com"
            assert "query" in json
            assert headers["Authorization"] == "Bearer secret"
            return FakeResponse()

    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)
    settings = Settings(
        business_graphql_endpoint="https://graphql.example.com",
        business_graphql_api_key="secret",
        business_graphql_query_map_json=(
            '{"order_status":"query OrderStatus($parameters: JSON) { orderStatus }"}'
        ),
        business_graphql_response_path_map_json='{"order_status":"orderStatus"}',
    )
    adapter = GraphQLBusinessAdapter(settings)

    result = await adapter.execute(
        BusinessQuery(
            tenant_id="demo-tenant",
            tool_name="order_status",
            parameters={"order_id": "ORD-1001"},
        )
    )

    assert result.status == "success"
    assert result.summary == "order resolved by graphql"
    assert result.data["order_id"] == "ORD-1001"


def test_business_provider_factory_supports_graphql_and_grpc() -> None:
    graphql_settings = Settings(
        business_provider="graphql",
        business_graphql_endpoint="https://graphql.example.com",
        business_graphql_query_map_json='{"order_status":"query OrderStatus { orderStatus }"}',
    )
    grpc_settings = Settings(
        business_provider="grpc",
        business_grpc_target="127.0.0.1:50051",
        business_grpc_method_map_json='{"order_status":"/runtime.Business/OrderStatus"}',
    )

    assert isinstance(_build_business_adapter(graphql_settings), GraphQLBusinessAdapter)
    assert isinstance(_build_business_adapter(grpc_settings), GrpcBusinessAdapter)


def test_admin_provider_health_supports_extended_providers() -> None:
    settings = Settings(
        vector_provider="pinecone",
        pinecone_api_key="pc-key",
        pinecone_index_name="customer-ai",
        business_provider="graphql",
        business_graphql_endpoint="https://graphql.example.com",
    )
    admin_service = AdminService(
        settings=settings,
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

    assert health["vector"]["provider"] == "pinecone"
    assert health["vector"]["ready"] is True
    assert health["business"]["provider"] == "graphql"
    assert health["business"]["ready"] is True
