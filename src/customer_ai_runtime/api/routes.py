from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter, Depends, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse

from customer_ai_runtime.api.schemas import (
    BusinessQueryRequest,
    ChatMessageRequest,
    ContextResolveRequest,
    HandoffRequest,
    HumanReplyRequest,
    KnowledgeBaseCreateRequest,
    KnowledgeChunkOptimizationApplyRequest,
    KnowledgeDocumentCreateRequest,
    KnowledgeSearchRequest,
    KnowledgeVersionActivateRequest,
    KnowledgeVersionSnapshotRequest,
    MessageFeedbackRequest,
    PolicyUpdateRequest,
    PromptUpdateRequest,
    RTCRoomCreateRequest,
    RTCRoomJoinRequest,
    RuntimeConfigUpdateRequest,
    SessionCloseRequest,
    SessionCreateRequest,
    VoiceTurnRequest,
)
from customer_ai_runtime.application.container import Container
from customer_ai_runtime.core.errors import AppError
from customer_ai_runtime.core.request_context import reset_request_id, set_request_id
from customer_ai_runtime.core.responses import success_response
from customer_ai_runtime.domain.platform import ResolvedAuthContext

router = APIRouter()


def get_container(request: Request) -> Container:
    return request.app.state.container


async def authenticate(request: Request) -> ResolvedAuthContext:
    return await get_container(request).auth_service.authenticate_request(request)


AUTH_CONTEXT_DEPENDENCY = Depends(authenticate)


def require_admin(auth_context: ResolvedAuthContext) -> None:
    if auth_context.role != "admin":
        raise AppError(code="forbidden", message="admin only", status_code=403)


def require_staff(auth_context: ResolvedAuthContext) -> None:
    if auth_context.role not in {"admin", "operator"}:
        raise AppError(code="forbidden", message="admin/operator only", status_code=403)


@router.get("/healthz")
async def healthz() -> JSONResponse:
    return success_response({"status": "ok"})


@router.get("/api/v1/auth/context")
async def get_auth_context(
    auth_context: ResolvedAuthContext = AUTH_CONTEXT_DEPENDENCY,
) -> JSONResponse:
    return success_response(auth_context.model_dump(mode="json"))


@router.post("/api/v1/context/resolve")
async def resolve_context(
    payload: ContextResolveRequest,
    request: Request,
    auth_context: ResolvedAuthContext = AUTH_CONTEXT_DEPENDENCY,
) -> JSONResponse:
    container = get_container(request)
    container.access_control.validate_tenant_access(auth_context, payload.tenant_id)
    session = None
    if payload.session_id:
        session = container.session_service.get(payload.tenant_id, payload.session_id)
    context = await container.business_context_builder.build(
        tenant_id=payload.tenant_id,
        channel=payload.channel,
        session=session,
        integration_context=payload.integration_context,
        host_auth_context=auth_context.host_auth_context,
    )
    return success_response(context.model_dump(mode="json"))


@router.post("/api/v1/sessions")
async def create_session(
    payload: SessionCreateRequest,
    request: Request,
    auth_context: ResolvedAuthContext = AUTH_CONTEXT_DEPENDENCY,
) -> JSONResponse:
    container = get_container(request)
    container.access_control.validate_tenant_access(auth_context, payload.tenant_id)
    session = container.session_service.get_or_create(payload.tenant_id, None, payload.channel)
    return success_response(session.model_dump(mode="json"))


@router.get("/api/v1/sessions/{session_id}")
async def get_session(
    session_id: str,
    tenant_id: str,
    request: Request,
    auth_context: ResolvedAuthContext = AUTH_CONTEXT_DEPENDENCY,
) -> JSONResponse:
    container = get_container(request)
    container.access_control.validate_tenant_access(auth_context, tenant_id)
    session = container.session_service.get(tenant_id, session_id)
    return success_response(session.model_dump(mode="json"))


@router.get("/api/v1/sessions/{session_id}/messages")
async def get_session_messages(
    session_id: str,
    tenant_id: str,
    request: Request,
    auth_context: ResolvedAuthContext = AUTH_CONTEXT_DEPENDENCY,
) -> JSONResponse:
    container = get_container(request)
    container.access_control.validate_tenant_access(auth_context, tenant_id)
    session = container.session_service.get(tenant_id, session_id)
    return success_response([message.model_dump(mode="json") for message in session.messages])


@router.post("/api/v1/chat/messages")
async def chat_message(
    payload: ChatMessageRequest,
    request: Request,
    auth_context: ResolvedAuthContext = AUTH_CONTEXT_DEPENDENCY,
) -> JSONResponse:
    container = get_container(request)
    container.access_control.validate_tenant_access(auth_context, payload.tenant_id)
    result = await container.chat_service.process_message(
        tenant_id=payload.tenant_id,
        session_id=payload.session_id,
        channel=payload.channel,
        message=payload.message,
        knowledge_base_id=payload.knowledge_base_id,
        integration_context=payload.integration_context,
        host_auth_context=auth_context.host_auth_context,
    )
    return success_response(result)


@router.post("/api/v1/chat/handoff")
async def handoff_chat(
    payload: HandoffRequest,
    request: Request,
    auth_context: ResolvedAuthContext = AUTH_CONTEXT_DEPENDENCY,
) -> JSONResponse:
    container = get_container(request)
    container.access_control.validate_tenant_access(auth_context, payload.tenant_id)
    session = container.session_service.get(payload.tenant_id, payload.session_id)
    context = await container.business_context_builder.build(
        tenant_id=payload.tenant_id,
        channel=session.channel,
        session=session,
        integration_context={},
        host_auth_context=auth_context.host_auth_context,
    )
    handoff = await container.chat_service.handoff_service.create_package(
        session,
        payload.reason,
        context,
    )
    container.session_service.save(session)
    return success_response(None if handoff is None else handoff.model_dump(mode="json"))


@router.post("/api/v1/sessions/{session_id}/claim-human")
async def claim_session_human(
    session_id: str,
    payload: SessionCreateRequest,
    request: Request,
    auth_context: ResolvedAuthContext = AUTH_CONTEXT_DEPENDENCY,
) -> JSONResponse:
    container = get_container(request)
    require_admin(auth_context)
    container.access_control.validate_tenant_access(auth_context, payload.tenant_id)
    result = container.session_service.claim_human(payload.tenant_id, session_id)
    return success_response(result.model_dump(mode="json"))


@router.post("/api/v1/sessions/{session_id}/messages/human")
async def add_human_reply(
    session_id: str,
    payload: HumanReplyRequest,
    request: Request,
    auth_context: ResolvedAuthContext = AUTH_CONTEXT_DEPENDENCY,
) -> JSONResponse:
    container = get_container(request)
    require_admin(auth_context)
    container.access_control.validate_tenant_access(auth_context, payload.tenant_id)
    result = container.session_service.add_human_reply(
        payload.tenant_id,
        session_id,
        payload.content,
    )
    return success_response(result.model_dump(mode="json"))


@router.post("/api/v1/sessions/{session_id}/messages/{message_id}/feedback")
async def submit_message_feedback(
    session_id: str,
    message_id: str,
    payload: MessageFeedbackRequest,
    request: Request,
    auth_context: ResolvedAuthContext = AUTH_CONTEXT_DEPENDENCY,
) -> JSONResponse:
    container = get_container(request)
    container.access_control.validate_tenant_access(auth_context, payload.tenant_id)
    session, message = container.session_service.submit_message_feedback(
        payload.tenant_id,
        session_id,
        message_id,
        payload.feedback_type,
        payload.comment,
    )
    handoff = None
    if payload.feedback_type.value == "request_human":
        context = await container.business_context_builder.build(
            tenant_id=payload.tenant_id,
            channel=session.channel,
            session=session,
            integration_context={},
            host_auth_context=auth_context.host_auth_context,
        )
        handoff = await container.chat_service.handoff_service.create_package(
            session,
            payload.comment or "user_feedback_requested_human",
            context,
        )
        container.session_service.save(session)
    return success_response(
        {
            "message": message.model_dump(mode="json"),
            "session": session.model_dump(mode="json"),
            "handoff": None if handoff is None else handoff.model_dump(mode="json"),
        }
    )


@router.post("/api/v1/sessions/{session_id}/close")
async def close_session(
    session_id: str,
    payload: SessionCloseRequest,
    request: Request,
    auth_context: ResolvedAuthContext = AUTH_CONTEXT_DEPENDENCY,
) -> JSONResponse:
    container = get_container(request)
    require_admin(auth_context)
    container.access_control.validate_tenant_access(auth_context, payload.tenant_id)
    result = container.session_service.close_session(
        payload.tenant_id,
        session_id,
        satisfaction_score=payload.satisfaction_score,
        resolution_status=payload.resolution_status,
    )
    return success_response(result.model_dump(mode="json"))


@router.post("/api/v1/knowledge-bases")
async def create_knowledge_base(
    payload: KnowledgeBaseCreateRequest,
    request: Request,
    auth_context: ResolvedAuthContext = AUTH_CONTEXT_DEPENDENCY,
) -> JSONResponse:
    container = get_container(request)
    container.access_control.validate_tenant_access(auth_context, payload.tenant_id)
    result = await container.knowledge_service.create_knowledge_base(
        tenant_id=payload.tenant_id,
        knowledge_base_id=payload.knowledge_base_id,
        name=payload.name,
        description=payload.description,
    )
    return success_response(result.model_dump(mode="json"))


@router.get("/api/v1/knowledge-bases")
async def list_knowledge_bases(
    tenant_id: str,
    request: Request,
    auth_context: ResolvedAuthContext = AUTH_CONTEXT_DEPENDENCY,
) -> JSONResponse:
    container = get_container(request)
    container.access_control.validate_tenant_access(auth_context, tenant_id)
    return success_response(container.admin_service.list_knowledge_bases(tenant_id))


@router.get("/api/v1/knowledge-bases/{knowledge_base_id}")
async def get_knowledge_base(
    knowledge_base_id: str,
    tenant_id: str,
    request: Request,
    auth_context: ResolvedAuthContext = AUTH_CONTEXT_DEPENDENCY,
) -> JSONResponse:
    container = get_container(request)
    container.access_control.validate_tenant_access(auth_context, tenant_id)
    result = container.knowledge_service.get_knowledge_base(tenant_id, knowledge_base_id)
    return success_response(result.model_dump(mode="json"))


@router.post("/api/v1/knowledge-bases/{knowledge_base_id}/documents")
async def add_knowledge_document(
    knowledge_base_id: str,
    payload: KnowledgeDocumentCreateRequest,
    request: Request,
    auth_context: ResolvedAuthContext = AUTH_CONTEXT_DEPENDENCY,
) -> JSONResponse:
    container = get_container(request)
    container.access_control.validate_tenant_access(auth_context, payload.tenant_id)
    result = await container.knowledge_service.add_document(
        tenant_id=payload.tenant_id,
        knowledge_base_id=knowledge_base_id,
        title=payload.title,
        content=payload.content,
        metadata=payload.metadata,
    )
    return success_response(
        {
            "knowledge_base": result["knowledge_base"].model_dump(mode="json"),
            "document": result["document"].model_dump(mode="json"),
            "chunks": [chunk.model_dump(mode="json") for chunk in result["chunks"]],
        }
    )


@router.get("/api/v1/admin/knowledge-bases/{knowledge_base_id}/versions")
async def list_admin_knowledge_versions(
    knowledge_base_id: str,
    tenant_id: str,
    request: Request,
    auth_context: ResolvedAuthContext = AUTH_CONTEXT_DEPENDENCY,
) -> JSONResponse:
    container = get_container(request)
    require_admin(auth_context)
    container.access_control.validate_tenant_access(auth_context, tenant_id)
    return success_response(
        container.admin_service.list_knowledge_versions(tenant_id, knowledge_base_id)
    )


@router.post("/api/v1/admin/knowledge-bases/{knowledge_base_id}/versions/snapshot")
async def create_admin_knowledge_version_snapshot(
    knowledge_base_id: str,
    payload: KnowledgeVersionSnapshotRequest,
    request: Request,
    auth_context: ResolvedAuthContext = AUTH_CONTEXT_DEPENDENCY,
) -> JSONResponse:
    container = get_container(request)
    require_admin(auth_context)
    container.access_control.validate_tenant_access(auth_context, payload.tenant_id)
    return success_response(
        await container.admin_service.create_knowledge_version_snapshot(
            tenant_id=payload.tenant_id,
            knowledge_base_id=knowledge_base_id,
            description=payload.description,
            source_version_id=payload.source_version_id,
        )
    )


@router.post("/api/v1/admin/knowledge-bases/{knowledge_base_id}/versions/{version_id}/activate")
async def activate_admin_knowledge_version(
    knowledge_base_id: str,
    version_id: str,
    payload: KnowledgeVersionActivateRequest,
    request: Request,
    auth_context: ResolvedAuthContext = AUTH_CONTEXT_DEPENDENCY,
) -> JSONResponse:
    container = get_container(request)
    require_admin(auth_context)
    container.access_control.validate_tenant_access(auth_context, payload.tenant_id)
    return success_response(
        container.admin_service.activate_knowledge_version(
            tenant_id=payload.tenant_id,
            knowledge_base_id=knowledge_base_id,
            version_id=version_id,
        )
    )


@router.get("/api/v1/admin/knowledge-bases/{knowledge_base_id}/chunk-optimization")
async def get_admin_knowledge_chunk_optimization(
    knowledge_base_id: str,
    tenant_id: str,
    request: Request,
    auth_context: ResolvedAuthContext = AUTH_CONTEXT_DEPENDENCY,
) -> JSONResponse:
    container = get_container(request)
    require_admin(auth_context)
    container.access_control.validate_tenant_access(auth_context, tenant_id)
    return success_response(
        container.admin_service.get_chunk_optimization_report(tenant_id, knowledge_base_id)
    )


@router.post("/api/v1/admin/knowledge-bases/{knowledge_base_id}/chunk-optimization/apply")
async def apply_admin_knowledge_chunk_optimization(
    knowledge_base_id: str,
    payload: KnowledgeChunkOptimizationApplyRequest,
    request: Request,
    auth_context: ResolvedAuthContext = AUTH_CONTEXT_DEPENDENCY,
) -> JSONResponse:
    container = get_container(request)
    require_admin(auth_context)
    container.access_control.validate_tenant_access(auth_context, payload.tenant_id)
    return success_response(
        await container.admin_service.apply_chunk_optimization(
            tenant_id=payload.tenant_id,
            knowledge_base_id=knowledge_base_id,
            max_tokens=payload.max_tokens,
            overlap=payload.overlap,
            description=payload.description,
            activate=payload.activate,
        )
    )


@router.post("/api/v1/knowledge-bases/{knowledge_base_id}/search")
async def search_knowledge_base(
    knowledge_base_id: str,
    payload: KnowledgeSearchRequest,
    request: Request,
    auth_context: ResolvedAuthContext = AUTH_CONTEXT_DEPENDENCY,
) -> JSONResponse:
    container = get_container(request)
    container.access_control.validate_tenant_access(auth_context, payload.tenant_id)
    policies = container.admin_service.get_policies()
    result = await container.knowledge_service.search(
        tenant_id=payload.tenant_id,
        knowledge_base_id=knowledge_base_id,
        query=payload.query,
        top_k=payload.top_k or policies["knowledge_top_k"],
        min_score=payload.min_score or policies["knowledge_min_score"],
    )
    return success_response(result)


@router.post("/api/v1/tools/business-query")
async def business_query(
    payload: BusinessQueryRequest,
    request: Request,
    auth_context: ResolvedAuthContext = AUTH_CONTEXT_DEPENDENCY,
) -> JSONResponse:
    container = get_container(request)
    container.access_control.validate_tenant_access(auth_context, payload.tenant_id)
    context = await container.business_context_builder.build(
        tenant_id=payload.tenant_id,
        channel="web",
        session=None,
        integration_context=payload.integration_context,
        host_auth_context=auth_context.host_auth_context,
    )
    result = await container.tool_service.execute(
        business_context=context,
        tool_name=payload.tool_name,
        parameters=payload.parameters,
    )
    return success_response(result.model_dump(mode="json"))


@router.post("/api/v1/voice/turn")
async def voice_turn(
    payload: VoiceTurnRequest,
    request: Request,
    auth_context: ResolvedAuthContext = AUTH_CONTEXT_DEPENDENCY,
) -> JSONResponse:
    container = get_container(request)
    container.access_control.validate_tenant_access(auth_context, payload.tenant_id)
    result = await container.voice_service.process_turn(
        tenant_id=payload.tenant_id,
        session_id=payload.session_id,
        channel=payload.channel,
        audio_base64=payload.audio_base64,
        content_type=payload.content_type,
        transcript_hint=payload.transcript_hint,
        knowledge_base_id=payload.knowledge_base_id,
        integration_context=payload.integration_context,
        host_auth_context=auth_context.host_auth_context,
    )
    return success_response(result)


@router.post("/api/v1/rtc/rooms")
async def create_rtc_room(
    payload: RTCRoomCreateRequest,
    request: Request,
    auth_context: ResolvedAuthContext = AUTH_CONTEXT_DEPENDENCY,
) -> JSONResponse:
    container = get_container(request)
    container.access_control.validate_tenant_access(auth_context, payload.tenant_id)
    room = container.rtc_service.create_room(payload.tenant_id)
    return success_response(room.model_dump(mode="json"))


@router.post("/api/v1/rtc/rooms/{room_id}/join")
async def join_rtc_room(
    room_id: str,
    payload: RTCRoomJoinRequest,
    request: Request,
    auth_context: ResolvedAuthContext = AUTH_CONTEXT_DEPENDENCY,
) -> JSONResponse:
    container = get_container(request)
    container.access_control.validate_tenant_access(auth_context, payload.tenant_id)
    room = container.rtc_service.join_room(payload.tenant_id, room_id, payload.session_id)
    return success_response(room.model_dump(mode="json"))


@router.post("/api/v1/rtc/rooms/{room_id}/interrupt")
async def interrupt_rtc_room(
    room_id: str,
    payload: RTCRoomCreateRequest,
    request: Request,
    auth_context: ResolvedAuthContext = AUTH_CONTEXT_DEPENDENCY,
) -> JSONResponse:
    container = get_container(request)
    container.access_control.validate_tenant_access(auth_context, payload.tenant_id)
    room = container.rtc_service.interrupt(payload.tenant_id, room_id)
    return success_response(room.model_dump(mode="json"))


@router.post("/api/v1/rtc/rooms/{room_id}/end")
async def end_rtc_room(
    room_id: str,
    payload: RTCRoomCreateRequest,
    request: Request,
    auth_context: ResolvedAuthContext = AUTH_CONTEXT_DEPENDENCY,
) -> JSONResponse:
    container = get_container(request)
    container.access_control.validate_tenant_access(auth_context, payload.tenant_id)
    room = container.rtc_service.end_room(payload.tenant_id, room_id)
    return success_response(room.model_dump(mode="json"))


@router.get("/api/v1/admin/metrics")
async def admin_metrics(
    request: Request,
    auth_context: ResolvedAuthContext = AUTH_CONTEXT_DEPENDENCY,
) -> JSONResponse:
    require_staff(auth_context)
    return success_response(get_container(request).admin_service.get_metrics())


@router.get("/api/v1/admin/metrics/summary")
async def admin_metrics_summary(
    request: Request,
    tenant_id: str | None = Query(default=None, min_length=1, max_length=64),
    auth_context: ResolvedAuthContext = AUTH_CONTEXT_DEPENDENCY,
) -> JSONResponse:
    container = get_container(request)
    require_staff(auth_context)
    if tenant_id is not None:
        container.access_control.validate_tenant_access(auth_context, tenant_id)
    return success_response(container.admin_service.get_metrics_summary(tenant_id=tenant_id))


@router.get("/api/v1/admin/sessions")
async def admin_sessions(
    tenant_id: str,
    request: Request,
    auth_context: ResolvedAuthContext = AUTH_CONTEXT_DEPENDENCY,
) -> JSONResponse:
    container = get_container(request)
    require_staff(auth_context)
    container.access_control.validate_tenant_access(auth_context, tenant_id)
    return success_response(container.admin_service.list_sessions(tenant_id))


@router.get("/api/v1/admin/prompts")
async def get_admin_prompts(
    request: Request,
    auth_context: ResolvedAuthContext = AUTH_CONTEXT_DEPENDENCY,
) -> JSONResponse:
    require_staff(auth_context)
    return success_response(get_container(request).admin_service.get_prompts())


@router.get("/api/v1/admin/runtime-config")
async def get_admin_runtime_config(
    request: Request,
    auth_context: ResolvedAuthContext = AUTH_CONTEXT_DEPENDENCY,
) -> JSONResponse:
    require_staff(auth_context)
    return success_response(get_container(request).admin_service.get_runtime_config())


@router.put("/api/v1/admin/runtime-config")
async def update_admin_runtime_config(
    payload: RuntimeConfigUpdateRequest,
    request: Request,
    auth_context: ResolvedAuthContext = AUTH_CONTEXT_DEPENDENCY,
) -> JSONResponse:
    require_admin(auth_context)
    return success_response(
        get_container(request).admin_service.update_runtime_config(
            payload.model_dump(exclude_none=True)
        )
    )


@router.put("/api/v1/admin/prompts")
async def update_admin_prompts(
    payload: PromptUpdateRequest,
    request: Request,
    auth_context: ResolvedAuthContext = AUTH_CONTEXT_DEPENDENCY,
) -> JSONResponse:
    require_admin(auth_context)
    return success_response(
        get_container(request).admin_service.update_prompts(payload.model_dump(exclude_none=True))
    )


@router.get("/api/v1/admin/policies")
async def get_admin_policies(
    request: Request,
    auth_context: ResolvedAuthContext = AUTH_CONTEXT_DEPENDENCY,
) -> JSONResponse:
    require_staff(auth_context)
    return success_response(get_container(request).admin_service.get_policies())


@router.put("/api/v1/admin/policies")
async def update_admin_policies(
    payload: PolicyUpdateRequest,
    request: Request,
    auth_context: ResolvedAuthContext = AUTH_CONTEXT_DEPENDENCY,
) -> JSONResponse:
    require_admin(auth_context)
    return success_response(
        get_container(request).admin_service.update_policies(payload.model_dump(exclude_none=True))
    )


@router.get("/api/v1/admin/diagnostics")
async def get_admin_diagnostics(
    request: Request,
    tenant_id: str | None = Query(default=None, min_length=1, max_length=64),
    session_id: str | None = Query(default=None, min_length=1, max_length=64),
    room_id: str | None = Query(default=None, min_length=1, max_length=64),
    level: str | None = Query(default=None, pattern="^(info|warning|error)$"),
    code_prefix: str | None = Query(default=None, min_length=1, max_length=128),
    limit: int = Query(default=100, ge=1, le=200),
    auth_context: ResolvedAuthContext = AUTH_CONTEXT_DEPENDENCY,
) -> JSONResponse:
    container = get_container(request)
    require_staff(auth_context)
    if tenant_id is not None:
        container.access_control.validate_tenant_access(auth_context, tenant_id)
    return success_response(
        container.admin_service.diagnostics(
            tenant_id=tenant_id,
            session_id=session_id,
            room_id=room_id,
            level=level,
            code_prefix=code_prefix,
            limit=limit,
        )
    )


@router.get("/api/v1/admin/sessions/{session_id}/monitor")
async def get_admin_session_monitor(
    session_id: str,
    tenant_id: str,
    request: Request,
    auth_context: ResolvedAuthContext = AUTH_CONTEXT_DEPENDENCY,
) -> JSONResponse:
    container = get_container(request)
    require_staff(auth_context)
    container.access_control.validate_tenant_access(auth_context, tenant_id)
    return success_response(container.admin_service.get_session_monitor(tenant_id, session_id))


@router.get("/api/v1/admin/rooms")
async def get_admin_rooms(
    tenant_id: str,
    request: Request,
    auth_context: ResolvedAuthContext = AUTH_CONTEXT_DEPENDENCY,
) -> JSONResponse:
    container = get_container(request)
    require_staff(auth_context)
    container.access_control.validate_tenant_access(auth_context, tenant_id)
    return success_response(container.admin_service.list_rooms(tenant_id))


@router.get("/api/v1/admin/knowledge-bases/{knowledge_base_id}/health")
async def get_admin_knowledge_health(
    knowledge_base_id: str,
    tenant_id: str,
    request: Request,
    auth_context: ResolvedAuthContext = AUTH_CONTEXT_DEPENDENCY,
) -> JSONResponse:
    container = get_container(request)
    require_staff(auth_context)
    container.access_control.validate_tenant_access(auth_context, tenant_id)
    return success_response(
        container.admin_service.get_knowledge_health_report(tenant_id, knowledge_base_id)
    )


@router.get("/api/v1/admin/knowledge/retrieval-misses")
async def get_admin_retrieval_miss_report(
    request: Request,
    tenant_id: str,
    knowledge_base_id: str | None = Query(default=None, min_length=1, max_length=64),
    limit: int = Query(default=20, ge=1, le=100),
    auth_context: ResolvedAuthContext = AUTH_CONTEXT_DEPENDENCY,
) -> JSONResponse:
    container = get_container(request)
    require_staff(auth_context)
    container.access_control.validate_tenant_access(auth_context, tenant_id)
    return success_response(
        container.admin_service.get_retrieval_miss_report(
            tenant_id=tenant_id,
            knowledge_base_id=knowledge_base_id,
            limit=limit,
        )
    )


@router.get("/api/v1/admin/knowledge/effectiveness")
async def get_admin_knowledge_effectiveness_report(
    request: Request,
    tenant_id: str,
    knowledge_base_id: str | None = Query(default=None, min_length=1, max_length=64),
    auth_context: ResolvedAuthContext = AUTH_CONTEXT_DEPENDENCY,
) -> JSONResponse:
    container = get_container(request)
    require_staff(auth_context)
    container.access_control.validate_tenant_access(auth_context, tenant_id)
    return success_response(
        container.admin_service.get_knowledge_effectiveness_report(
            tenant_id=tenant_id,
            knowledge_base_id=knowledge_base_id,
        )
    )


@router.get("/api/v1/admin/providers/health")
async def get_admin_provider_health(
    request: Request,
    auth_context: ResolvedAuthContext = AUTH_CONTEXT_DEPENDENCY,
) -> JSONResponse:
    require_staff(auth_context)
    return success_response(get_container(request).admin_service.provider_health())


@router.get("/api/v1/admin/alerts")
async def get_admin_alerts(
    request: Request,
    tenant_id: str | None = Query(default=None, min_length=1, max_length=64),
    auth_context: ResolvedAuthContext = AUTH_CONTEXT_DEPENDENCY,
) -> JSONResponse:
    container = get_container(request)
    require_staff(auth_context)
    if tenant_id is not None:
        container.access_control.validate_tenant_access(auth_context, tenant_id)
    return success_response(container.admin_service.get_alerts(tenant_id=tenant_id))


@router.get("/api/v1/admin/tools/catalog")
async def get_admin_tool_catalog(
    request: Request,
    tenant_id: str | None = Query(default=None, min_length=1, max_length=64),
    industry: str | None = Query(default=None, min_length=1, max_length=64),
    channel: str | None = Query(default=None, min_length=1, max_length=64),
    include_disabled: bool = Query(default=True),
    auth_context: ResolvedAuthContext = AUTH_CONTEXT_DEPENDENCY,
) -> JSONResponse:
    container = get_container(request)
    require_staff(auth_context)
    if tenant_id is not None:
        container.access_control.validate_tenant_access(auth_context, tenant_id)
    return success_response(
        container.admin_service.tool_catalog_items(
            tenant_id=tenant_id,
            industry=industry,
            channel=channel,
            include_disabled=include_disabled,
        )
    )


@router.get("/api/v1/admin/tools/catalog/categories")
async def get_admin_tool_catalog_categories(
    request: Request,
    tenant_id: str | None = Query(default=None, min_length=1, max_length=64),
    industry: str | None = Query(default=None, min_length=1, max_length=64),
    channel: str | None = Query(default=None, min_length=1, max_length=64),
    include_disabled: bool = Query(default=True),
    auth_context: ResolvedAuthContext = AUTH_CONTEXT_DEPENDENCY,
) -> JSONResponse:
    container = get_container(request)
    require_staff(auth_context)
    if tenant_id is not None:
        container.access_control.validate_tenant_access(auth_context, tenant_id)
    return success_response(
        container.admin_service.tool_category_items(
            tenant_id=tenant_id,
            industry=industry,
            channel=channel,
            include_disabled=include_disabled,
        )
    )


@router.get("/api/v1/admin/plugins")
async def get_admin_plugins(
    request: Request,
    auth_context: ResolvedAuthContext = AUTH_CONTEXT_DEPENDENCY,
) -> JSONResponse:
    require_staff(auth_context)
    return success_response(get_container(request).admin_service.list_plugins())


@router.post("/api/v1/admin/plugins/{plugin_id}/enable")
async def enable_admin_plugin(
    plugin_id: str,
    request: Request,
    auth_context: ResolvedAuthContext = AUTH_CONTEXT_DEPENDENCY,
) -> JSONResponse:
    require_admin(auth_context)
    return success_response(get_container(request).admin_service.enable_plugin(plugin_id))


@router.post("/api/v1/admin/plugins/{plugin_id}/disable")
async def disable_admin_plugin(
    plugin_id: str,
    request: Request,
    auth_context: ResolvedAuthContext = AUTH_CONTEXT_DEPENDENCY,
) -> JSONResponse:
    require_admin(auth_context)
    return success_response(get_container(request).admin_service.disable_plugin(plugin_id))


@router.websocket("/ws/v1/rtc/{room_id}")
async def rtc_websocket(websocket: WebSocket, room_id: str) -> None:
    await websocket.accept()
    container: Container = websocket.app.state.container
    request_id_token = None
    try:
        auth_context = await container.auth_service.authenticate_websocket(websocket)
        connection_request_id = websocket.headers.get("x-request-id") or f"wsreq_{uuid4().hex[:12]}"
        request_id_token = set_request_id(connection_request_id)
        tenant_id = websocket.query_params.get("tenant_id")
        if not tenant_id:
            await websocket.send_json({"type": "error", "message": "missing tenant_id"})
            await websocket.close(code=4400)
            return
        container.access_control.validate_tenant_access(auth_context, tenant_id)
        while True:
            payload = await websocket.receive_json()
            if not isinstance(payload, dict):
                await websocket.send_json(
                    {
                        "type": "error",
                        "code": "validation_error",
                        "message": "invalid event payload",
                    }
                )
                continue
            # Optional per-message override for better correlation.
            message_request_id = payload.get("request_id")
            message_token = None
            if isinstance(message_request_id, str) and message_request_id.strip():
                message_token = set_request_id(message_request_id.strip())
            try:
                events = await container.rtc_service.handle_event(
                    tenant_id,
                    room_id,
                    payload,
                    auth_context.host_auth_context,
                )
            except AppError as exc:
                await websocket.send_json(
                    {
                        "type": "error",
                        "code": exc.code,
                        "message": exc.message,
                        "details": exc.details or {},
                    }
                )
                if exc.status_code == 401:
                    await websocket.close(code=4401)
                    return
                if exc.status_code == 403:
                    await websocket.close(code=4403)
                    return
                continue
            finally:
                if message_token is not None:
                    reset_request_id(message_token)
            for event in events:
                await websocket.send_json(event)
    except WebSocketDisconnect:
        return
    except AppError as exc:
        await websocket.send_json({"type": "error", "message": exc.message, "code": exc.code})
        await websocket.close(code=4401 if exc.status_code == 401 else 4400)
        return
    finally:
        if request_id_token is not None:
            reset_request_id(request_id_token)
