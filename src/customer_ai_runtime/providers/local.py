from __future__ import annotations

import base64
import io
import math
import struct
import wave

from customer_ai_runtime.core.errors import AppError
from customer_ai_runtime.core.text import build_embedding, cosine_similarity
from customer_ai_runtime.domain.models import (
    ASRRequest,
    ASRResult,
    BusinessQuery,
    BusinessResult,
    Citation,
    KnowledgeChunk,
    LLMRequest,
    LLMResponse,
    RetrievalHit,
    TTSRequest,
    TTSResult,
)
from customer_ai_runtime.providers.base import (
    ASRProvider,
    BusinessAdapter,
    LLMProvider,
    TTSProvider,
    VectorStoreProvider,
)


class LocalLLMProvider(LLMProvider):
    async def generate(self, request: LLMRequest) -> LLMResponse:
        if request.route.value in {"handoff", "risk"}:
            return LLMResponse(
                answer="已为您转接人工客服，请稍候，人工客服将参考当前会话摘要继续为您处理。",
                confidence=0.98,
                suggested_actions=["wait_for_human"],
                citations=request.citations,
            )
        if request.tool_result:
            return LLMResponse(
                answer=(
                    f"{request.tool_result.summary} 如果还需要更详细的处理，我可以继续帮您查询，"
                    "或者直接为您转接人工客服。"
                ),
                confidence=0.88 if request.tool_result.status == "success" else 0.52,
                citations=request.citations,
                suggested_actions=["continue_query", "handoff"],
            )
        if request.citations:
            citation_titles = "、".join(citation.title for citation in request.citations[:2])
            return LLMResponse(
                answer=(
                    f"根据知识库《{citation_titles}》的内容，{request.citations[0].excerpt}"
                    " 如果您需要我进一步结合订单或售后状态处理，我可以继续查询业务系统。"
                ),
                confidence=0.79,
                citations=request.citations,
                suggested_actions=["business_query", "handoff"],
            )
        return LLMResponse(
            answer="我暂时没有足够信息给出确定答复，建议补充订单号、售后单号或转人工处理。",
            confidence=0.32,
            suggested_actions=["provide_identifier", "handoff"],
        )


class LocalASRProvider(ASRProvider):
    async def transcribe(self, request: ASRRequest) -> ASRResult:
        if request.transcript_hint:
            return ASRResult(transcript=request.transcript_hint, confidence=0.99)
        raw_bytes = base64.b64decode(request.audio_base64)
        if request.content_type.startswith("text/"):
            return ASRResult(transcript=raw_bytes.decode("utf-8"), confidence=0.95)
        try:
            return ASRResult(transcript=raw_bytes.decode("utf-8"), confidence=0.85)
        except UnicodeDecodeError as exc:
            raise AppError(
                code="provider_error",
                message="默认本地 ASR 提供商仅支持开发环境文本载荷，请切换真实 ASR 提供商处理音频。",
                status_code=422,
                details={"content_type": request.content_type},
            ) from exc


class LocalTTSProvider(TTSProvider):
    async def synthesize(self, request: TTSRequest) -> TTSResult:
        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(16000)
            frames = bytearray()
            for character in request.text[:120]:
                frequency = 280 + (ord(character) % 360)
                frames.extend(_tone_frames(frequency, 0.035))
                frames.extend(_silence_frames(0.005))
            wav_file.writeframes(bytes(frames))
        return TTSResult(
            audio_base64=base64.b64encode(buffer.getvalue()).decode("utf-8"),
            audio_format="wav",
            segments=[request.text],
        )


def _tone_frames(frequency: int, seconds: float, sample_rate: int = 16000) -> bytes:
    frame_count = int(sample_rate * seconds)
    amplitude = 8000
    return b"".join(
        struct.pack(
            "<h",
            int(amplitude * math.sin(2 * math.pi * frequency * (index / sample_rate))),
        )
        for index in range(frame_count)
    )


def _silence_frames(seconds: float, sample_rate: int = 16000) -> bytes:
    frame_count = int(sample_rate * seconds)
    return b"".join(struct.pack("<h", 0) for _ in range(frame_count))


class LocalVectorStoreProvider(VectorStoreProvider):
    def __init__(self) -> None:
        self._chunks: dict[tuple[str, str], list[KnowledgeChunk]] = {}

    async def upsert(self, chunks: list[KnowledgeChunk]) -> None:
        if not chunks:
            return
        key = (chunks[0].tenant_id, chunks[0].knowledge_base_id)
        self._chunks[key] = [chunk.model_copy(deep=True) for chunk in chunks]

    async def search(
        self,
        tenant_id: str,
        knowledge_base_id: str,
        query: str,
        top_k: int,
    ) -> list[RetrievalHit]:
        query_vector = build_embedding(query)
        candidates = self._chunks.get((tenant_id, knowledge_base_id), [])
        hits = [
            RetrievalHit(chunk=chunk, score=cosine_similarity(query_vector, chunk.embedding))
            for chunk in candidates
        ]
        hits.sort(key=lambda item: item.score, reverse=True)
        return [hit for hit in hits[:top_k] if hit.score > 0]


class LocalBusinessAdapter(BusinessAdapter):
    def __init__(self) -> None:
        self._orders = {
            "ORD-1001": {"status": "已发货", "tracking_no": "YT-2001", "eta": "2026-03-14"},
            "ORD-1002": {"status": "待支付", "tracking_no": "", "eta": ""},
        }
        self._after_sales = {
            "AS-2001": {"status": "审核中", "updated_at": "2026-03-11 10:30"},
            "AS-2002": {"status": "退款完成", "updated_at": "2026-03-10 14:20"},
        }
        self._logistics = {
            "YT-2001": {"status": "运输中", "latest": "2026-03-12 08:30 已到达杭州转运中心"},
        }
        self._accounts = {
            "ACC-3001": {"level": "gold", "points": 1580, "status": "active"},
        }

    async def execute(self, query: BusinessQuery) -> BusinessResult:
        parameters = query.parameters
        tool_name = query.tool_name
        if tool_name == "order_status":
            order_id = parameters.get("order_id")
            if not order_id:
                return BusinessResult(
                    tool_name=tool_name,
                    status="missing_parameter",
                    summary="请提供订单号，例如 ORD-1001，我才能继续为您查询订单状态。",
                )
            order = self._orders.get(order_id)
            if not order:
                return BusinessResult(
                    tool_name=tool_name,
                    status="not_found",
                    summary=f"未查询到订单 {order_id}，请核对订单号后重试。",
                )
            return BusinessResult(
                tool_name=tool_name,
                status="success",
                summary=(
                    f"订单 {order_id} 当前状态为 {order['status']}，"
                    f"预计送达时间 {order['eta'] or '暂无'}，"
                    f"物流单号 {order['tracking_no'] or '暂无'}。"
                ),
                data=order,
                integration_context=query.integration_context,
            )
        if tool_name == "after_sale_status":
            after_sale_id = parameters.get("after_sale_id")
            if not after_sale_id:
                return BusinessResult(
                    tool_name=tool_name,
                    status="missing_parameter",
                    summary="请提供售后单号，例如 AS-2001。",
                )
            result = self._after_sales.get(after_sale_id)
            if not result:
                return BusinessResult(
                    tool_name=tool_name,
                    status="not_found",
                    summary=f"未找到售后单 {after_sale_id}。",
                )
            return BusinessResult(
                tool_name=tool_name,
                status="success",
                summary=(
                    f"售后单 {after_sale_id} 当前状态为 {result['status']}，"
                    f"最近更新时间 {result['updated_at']}。"
                ),
                data=result,
                integration_context=query.integration_context,
            )
        if tool_name == "logistics_tracking":
            tracking_no = parameters.get("tracking_no")
            if not tracking_no:
                return BusinessResult(
                    tool_name=tool_name,
                    status="missing_parameter",
                    summary="请提供物流单号，例如 YT-2001。",
                )
            result = self._logistics.get(tracking_no)
            if not result:
                return BusinessResult(
                    tool_name=tool_name,
                    status="not_found",
                    summary=f"未找到物流单 {tracking_no}。",
                )
            return BusinessResult(
                tool_name=tool_name,
                status="success",
                summary=(
                    f"物流单 {tracking_no} 当前状态为 {result['status']}，"
                    f"最新轨迹：{result['latest']}。"
                ),
                data=result,
                integration_context=query.integration_context,
            )
        if tool_name == "account_lookup":
            account_id = parameters.get("account_id")
            if not account_id:
                return BusinessResult(
                    tool_name=tool_name,
                    status="missing_parameter",
                    summary="请提供账号编号，例如 ACC-3001。",
                )
            result = self._accounts.get(account_id)
            if not result:
                return BusinessResult(
                    tool_name=tool_name,
                    status="not_found",
                    summary=f"未找到账号 {account_id}。",
                )
            return BusinessResult(
                tool_name=tool_name,
                status="success",
                summary=(
                    f"账号 {account_id} 当前状态 {result['status']}，"
                    f"会员等级 {result['level']}，积分 {result['points']}。"
                ),
                data=result,
                integration_context=query.integration_context,
            )
        raise AppError(code="validation_error", message=f"不支持的工具：{tool_name}", status_code=400)


def citations_from_hits(hits: list[RetrievalHit]) -> list[Citation]:
    return [
        Citation(
            knowledge_base_id=hit.chunk.knowledge_base_id,
            document_id=hit.chunk.document_id,
            title=hit.chunk.title,
            chunk_id=hit.chunk.chunk_id,
            score=round(hit.score, 4),
            excerpt=hit.chunk.content,
        )
        for hit in hits
    ]
