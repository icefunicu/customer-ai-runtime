from __future__ import annotations

import pytest

from customer_ai_runtime.application.business import ResponseEnhancementOrchestrator
from customer_ai_runtime.application.plugins import PluginRegistry, ResponsePostProcessorPlugin
from customer_ai_runtime.domain.platform import (
    BusinessContext,
    PluginContext,
    PluginDescriptor,
    PluginKind,
)


class SuffixPostProcessorPlugin(ResponsePostProcessorPlugin):
    def __init__(self) -> None:
        super().__init__(
            PluginDescriptor(
                plugin_id="response.test_suffix",
                name="Test Suffix Post Processor",
                kind=PluginKind.RESPONSE_POST_PROCESSOR,
                priority=1000,
            )
        )

    async def process(
        self,
        context: PluginContext,
        response: dict[str, object],
    ) -> dict[str, object]:
        updated = dict(response)
        updated["answer"] = f"{updated.get('answer', '')} [plugin]"
        updated["plugin_processed"] = True
        return updated


@pytest.mark.anyio
async def test_response_enhancement_builtin_logic_without_plugins() -> None:
    orchestrator = ResponseEnhancementOrchestrator(PluginRegistry())
    context = BusinessContext(
        tenant_id="demo-tenant",
        channel="web",
        integration_context={"response_format": "structured"},
    )

    result = await orchestrator.enhance(
        {
            "route": "knowledge",
            "answer": " 请联系 13812345678 处理退款\n\n",
            "industry": "ecommerce",
            "citations": [
                {
                    "knowledge_base_id": "kb_support",
                    "document_id": "doc_1",
                    "title": "退款规则",
                    "score": 0.96,
                }
            ],
            "tool_result": {"summary": " 订单已发货 "},
            "handoff": {"summary": " 联系手机号 13812345678 ", "recommended_reply": " 好的 "},
        },
        context,
    )

    assert result["answer"] == "请联系 138****5678 处理退款 参考：退款规则。"
    assert result["references"] == [
        {
            "title": "退款规则",
            "knowledge_base_id": "kb_support",
            "document_id": "doc_1",
            "score": 0.96,
        }
    ]
    assert result["tool_result"]["summary"] == "订单已发货"
    assert result["handoff"]["summary"] == "联系手机号 138****5678"
    assert result["structured_output"]["references"] == result["references"]
    assert result["structured_output"]["answer"] == result["answer"]


@pytest.mark.anyio
async def test_response_enhancement_runs_post_processor_plugins() -> None:
    registry = PluginRegistry()
    registry.register(SuffixPostProcessorPlugin())
    orchestrator = ResponseEnhancementOrchestrator(registry)
    context = BusinessContext(
        tenant_id="demo-tenant",
        channel="web",
        integration_context={"response_format": "structured"},
    )

    result = await orchestrator.enhance(
        {
            "route": "knowledge",
            "answer": "答案",
            "industry": "ecommerce",
            "citations": [
                {
                    "knowledge_base_id": "kb_support",
                    "document_id": "doc_1",
                    "title": "售后说明",
                    "score": 0.88,
                }
            ],
        },
        context,
    )

    assert result["plugin_processed"] is True
    assert result["answer"] == "答案 参考：售后说明。 [plugin]"
    assert result["structured_output"]["answer"] == result["answer"]
