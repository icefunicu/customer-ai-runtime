from __future__ import annotations

from fastapi import APIRouter, Depends, Header, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse

from customer_ai_runtime.application.container import Container
from customer_ai_runtime.api.schemas import (
    BusinessQueryRequest,
    ChatMessageRequest,
    HandoffRequest,
    HumanReplyRequest,
    KnowledgeBaseCreateRequest,
    KnowledgeDocumentCreateRequest,
    KnowledgeSearchRequest,
    PolicyUpdateRequest,
    PromptUpdateRequest,
    RTCRoomCreateRequest,
    RTCRoomJoinRequest,
    SessionCreateRequest,
    VoiceTurnRequest,
)
from customer_ai_runtime.core.errors import AppError
from customer_ai_runtime.core.responses import success_response


router = APIRouter()


def get_container(request: Request) -> Container:
    return request.app.state.container


def authenticate(request: Request, x_api_key: str = Header(...)) -> dict[str, object]:
    container = get_container(request)
    record = container.settings.get_api_keys().get(x_api_key)
    if not record:
        raise AppError(code="auth_error", message="invalid api key", status_code=401)
    return {"role": record.role, "tenant_ids": record.tenant_ids}


@router.get("/healthz")
async def healthz() -> JSONResponse:
    return success_response({"status": "ok"})


@router.post("/api/v1/sessions")
async def create_session(
    payload: SessionCreateRequest,
    request: Request,
    auth_context: dict[str, object] = Depends(authenticate),
) -> JSONResponse:
    container = get_container(request)
    tenant_id = payload.tenant_id
    container.access_control.validate_tenant_access(auth_context, tenant_id)
    session = container.session_service.get_or_create(tenant_id, None, payload.channel)
    return success_response(session.model_dump(mode="json"))


@router.get("/api/v1/sessions/{session_id}")
async def get_session(
    session_id: str,
    tenant_id: str,
    request: Request,
    auth_context: dict[str, object] = Depends(authenticate),
) -> JSONResponse:
    container = get_container(request)
    container.access_control.validate_tenant_access(auth_context, tenant_id)
    return success_response(container.session_service.get(tenant_id, session_id).model_dump(mode="json"))


@router.get("/api/v1/sessions/{session_id}/messages")
async def get_session_messages(
    session_id: str,
    tenant_id: str,
    request: Request,
    auth_context: dict[str, object] = Depends(authenticate),
) -> JSONResponse:
    container = get_container(request)
    container.access_control.validate_tenant_access(auth_context, tenant_id)
    session = container.session_service.get(tenant_id, session_id)
    return success_response([message.model_dump(mode="json") for message in session.messages])


@router.post("/api/v1/chat/messages")
async def chat_message(
    payload: ChatMessageRequest,
    request: Request,
    auth_context: dict[str, object] = Depends(authenticate),
) -> JSONResponse:
    container = get_container(request)
    tenant_id = payload.tenant_id
    container.access_control.validate_tenant_access(auth_context, tenant_id)
    result = await container.chat_service.process_message(
        tenant_id=tenant_id,
        session_id=payload.session_id,
        channel=payload.channel,
        message=payload.message,
        knowledge_base_id=payload.knowledge_base_id,
        integration_context=payload.integration_context,
    )
    return success_response(result)


@router.post("/api/v1/chat/handoff")
async def handoff_chat(
    payload: HandoffRequest,
    request: Request,
    auth_context: dict[str, object] = Depends(authenticate),
) -> JSONResponse:
    container = get_container(request)
    tenant_id = payload.tenant_id
    container.access_control.validate_tenant_access(auth_context, tenant_id)
    session = container.session_service.get(tenant_id, payload.session_id)
    handoff = container.chat_service.handoff_service.create_package(session, payload.reason)
    container.session_service.save(session)
    return success_response(handoff.model_dump(mode="json"))


@router.post("/api/v1/sessions/{session_id}/claim-human")
async def claim_session_human(
    session_id: str,
    payload: SessionCreateRequest,
    request: Request,
    auth_context: dict[str, object] = Depends(authenticate),
) -> JSONResponse:
    container = get_container(request)
    container.access_control.validate_tenant_access(auth_context, payload.tenant_id)
    result = container.session_service.claim_human(payload.tenant_id, session_id)
    return success_response(result.model_dump(mode="json"))


@router.post("/api/v1/sessions/{session_id}/messages/human")
async def add_human_reply(
    session_id: str,
    payload: HumanReplyRequest,
    request: Request,
    auth_context: dict[str, object] = Depends(authenticate),
) -> JSONResponse:
    container = get_container(request)
    container.access_control.validate_tenant_access(auth_context, payload.tenant_id)
    result = container.session_service.add_human_reply(payload.tenant_id, session_id, payload.content)
    return success_response(result.model_dump(mode="json"))


@router.post("/api/v1/sessions/{session_id}/close")
async def close_session(
    session_id: str,
    payload: SessionCreateRequest,
    request: Request,
    auth_context: dict[str, object] = Depends(authenticate),
) -> JSONResponse:
    container = get_container(request)
    container.access_control.validate_tenant_access(auth_context, payload.tenant_id)
    result = container.session_service.close_session(payload.tenant_id, session_id)
    return success_response(result.model_dump(mode="json"))


@router.post("/api/v1/knowledge-bases")
async def create_knowledge_base(
    payload: KnowledgeBaseCreateRequest,
    request: Request,
    auth_context: dict[str, object] = Depends(authenticate),
) -> JSONResponse:
    container = get_container(request)
    tenant_id = payload.tenant_id
    container.access_control.validate_tenant_access(auth_context, tenant_id)
    result = await container.knowledge_service.create_knowledge_base(
        tenant_id=tenant_id,
        knowledge_base_id=payload.knowledge_base_id,
        name=payload.name,
        description=payload.description,
    )
    return success_response(result.model_dump(mode="json"))


@router.get("/api/v1/knowledge-bases")
async def list_knowledge_bases(
    tenant_id: str,
    request: Request,
    auth_context: dict[str, object] = Depends(authenticate),
) -> JSONResponse:
    container = get_container(request)
    container.access_control.validate_tenant_access(auth_context, tenant_id)
    result = container.admin_service.list_knowledge_bases(tenant_id)
    return success_response(result)


@router.get("/api/v1/knowledge-bases/{knowledge_base_id}")
async def get_knowledge_base(
    knowledge_base_id: str,
    tenant_id: str,
    request: Request,
    auth_context: dict[str, object] = Depends(authenticate),
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
    auth_context: dict[str, object] = Depends(authenticate),
) -> JSONResponse:
    container = get_container(request)
    tenant_id = payload.tenant_id
    container.access_control.validate_tenant_access(auth_context, tenant_id)
    result = await container.knowledge_service.add_document(
        tenant_id=tenant_id,
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


@router.post("/api/v1/knowledge-bases/{knowledge_base_id}/search")
async def search_knowledge_base(
    knowledge_base_id: str,
    payload: KnowledgeSearchRequest,
    request: Request,
    auth_context: dict[str, object] = Depends(authenticate),
) -> JSONResponse:
    container = get_container(request)
    tenant_id = payload.tenant_id
    container.access_control.validate_tenant_access(auth_context, tenant_id)
    policies = container.admin_service.get_policies()
    result = await container.knowledge_service.search(
        tenant_id=tenant_id,
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
    auth_context: dict[str, object] = Depends(authenticate),
) -> JSONResponse:
    container = get_container(request)
    tenant_id = payload.tenant_id
    container.access_control.validate_tenant_access(auth_context, tenant_id)
    result = await container.tool_service.execute(
        tenant_id=tenant_id,
        tool_name=payload.tool_name,
        parameters=payload.parameters,
        integration_context=payload.integration_context,
    )
    return success_response(result.model_dump(mode="json"))


@router.post("/api/v1/voice/turn")
async def voice_turn(
    payload: VoiceTurnRequest,
    request: Request,
    auth_context: dict[str, object] = Depends(authenticate),
) -> JSONResponse:
    container = get_container(request)
    tenant_id = payload.tenant_id
    container.access_control.validate_tenant_access(auth_context, tenant_id)
    result = await container.voice_service.process_turn(
        tenant_id=tenant_id,
        session_id=payload.session_id,
        channel=payload.channel,
        audio_base64=payload.audio_base64,
        content_type=payload.content_type,
        transcript_hint=payload.transcript_hint,
        knowledge_base_id=payload.knowledge_base_id,
        integration_context=payload.integration_context,
    )
    return success_response(result)


@router.post("/api/v1/rtc/rooms")
async def create_rtc_room(
    payload: RTCRoomCreateRequest,
    request: Request,
    auth_context: dict[str, object] = Depends(authenticate),
) -> JSONResponse:
    container = get_container(request)
    tenant_id = payload.tenant_id
    container.access_control.validate_tenant_access(auth_context, tenant_id)
    return success_response(container.rtc_service.create_room(tenant_id).model_dump(mode="json"))


@router.post("/api/v1/rtc/rooms/{room_id}/join")
async def join_rtc_room(
    room_id: str,
    payload: RTCRoomJoinRequest,
    request: Request,
    auth_context: dict[str, object] = Depends(authenticate),
) -> JSONResponse:
    container = get_container(request)
    tenant_id = payload.tenant_id
    container.access_control.validate_tenant_access(auth_context, tenant_id)
    room = container.rtc_service.join_room(tenant_id, room_id, payload.session_id)
    return success_response(room.model_dump(mode="json"))


@router.post("/api/v1/rtc/rooms/{room_id}/interrupt")
async def interrupt_rtc_room(
    room_id: str,
    payload: RTCRoomCreateRequest,
    request: Request,
    auth_context: dict[str, object] = Depends(authenticate),
) -> JSONResponse:
    container = get_container(request)
    tenant_id = payload.tenant_id
    container.access_control.validate_tenant_access(auth_context, tenant_id)
    room = container.rtc_service.interrupt(tenant_id, room_id)
    return success_response(room.model_dump(mode="json"))


@router.post("/api/v1/rtc/rooms/{room_id}/end")
async def end_rtc_room(
    room_id: str,
    payload: RTCRoomCreateRequest,
    request: Request,
    auth_context: dict[str, object] = Depends(authenticate),
) -> JSONResponse:
    container = get_container(request)
    tenant_id = payload.tenant_id
    container.access_control.validate_tenant_access(auth_context, tenant_id)
    room = container.rtc_service.end_room(tenant_id, room_id)
    return success_response(room.model_dump(mode="json"))


@router.get("/api/v1/admin/metrics")
async def admin_metrics(
    request: Request,
    auth_context: dict[str, object] = Depends(authenticate),
) -> JSONResponse:
    if auth_context["role"] != "admin":
        raise AppError(code="forbidden", message="admin only", status_code=403)
    return success_response(get_container(request).admin_service.get_metrics())


@router.get("/api/v1/admin/sessions")
async def admin_sessions(
    tenant_id: str,
    request: Request,
    auth_context: dict[str, object] = Depends(authenticate),
) -> JSONResponse:
    container = get_container(request)
    container.access_control.validate_tenant_access(auth_context, tenant_id)
    return success_response(container.admin_service.list_sessions(tenant_id))


@router.get("/api/v1/admin/prompts")
async def get_admin_prompts(
    request: Request,
    auth_context: dict[str, object] = Depends(authenticate),
) -> JSONResponse:
    if auth_context["role"] != "admin":
        raise AppError(code="forbidden", message="admin only", status_code=403)
    return success_response(get_container(request).admin_service.get_prompts())


@router.put("/api/v1/admin/prompts")
async def update_admin_prompts(
    payload: PromptUpdateRequest,
    request: Request,
    auth_context: dict[str, object] = Depends(authenticate),
) -> JSONResponse:
    if auth_context["role"] != "admin":
        raise AppError(code="forbidden", message="admin only", status_code=403)
    return success_response(
        get_container(request).admin_service.update_prompts(payload.model_dump(exclude_none=True))
    )


@router.get("/api/v1/admin/policies")
async def get_admin_policies(
    request: Request,
    auth_context: dict[str, object] = Depends(authenticate),
) -> JSONResponse:
    if auth_context["role"] != "admin":
        raise AppError(code="forbidden", message="admin only", status_code=403)
    return success_response(get_container(request).admin_service.get_policies())


@router.put("/api/v1/admin/policies")
async def update_admin_policies(
    payload: PolicyUpdateRequest,
    request: Request,
    auth_context: dict[str, object] = Depends(authenticate),
) -> JSONResponse:
    if auth_context["role"] != "admin":
        raise AppError(code="forbidden", message="admin only", status_code=403)
    return success_response(
        get_container(request).admin_service.update_policies(payload.model_dump(exclude_none=True))
    )


@router.get("/api/v1/admin/diagnostics")
async def get_admin_diagnostics(
    request: Request,
    auth_context: dict[str, object] = Depends(authenticate),
) -> JSONResponse:
    if auth_context["role"] != "admin":
        raise AppError(code="forbidden", message="admin only", status_code=403)
    return success_response(get_container(request).admin_service.diagnostics())


@router.get("/api/v1/admin/rooms")
async def get_admin_rooms(
    tenant_id: str,
    request: Request,
    auth_context: dict[str, object] = Depends(authenticate),
) -> JSONResponse:
    container = get_container(request)
    container.access_control.validate_tenant_access(auth_context, tenant_id)
    return success_response(container.admin_service.list_rooms(tenant_id))


@router.get("/api/v1/admin/providers/health")
async def get_admin_provider_health(
    request: Request,
    auth_context: dict[str, object] = Depends(authenticate),
) -> JSONResponse:
    if auth_context["role"] != "admin":
        raise AppError(code="forbidden", message="admin only", status_code=403)
    return success_response(get_container(request).admin_service.provider_health())


@router.get("/api/v1/admin/tools/catalog")
async def get_admin_tool_catalog(
    request: Request,
    auth_context: dict[str, object] = Depends(authenticate),
) -> JSONResponse:
    if auth_context["role"] != "admin":
        raise AppError(code="forbidden", message="admin only", status_code=403)
    return success_response(get_container(request).admin_service.tool_catalog_items())


@router.websocket("/ws/v1/rtc/{room_id}")
async def rtc_websocket(websocket: WebSocket, room_id: str) -> None:
    await websocket.accept()
    x_api_key = websocket.headers.get("x-api-key")
    tenant_id = websocket.query_params.get("tenant_id")
    if not x_api_key or not tenant_id:
        await websocket.send_json({"type": "error", "message": "missing api key or tenant_id"})
        await websocket.close(code=4401)
        return
    container: Container = websocket.app.state.container
    record = container.settings.get_api_keys().get(x_api_key)
    if not record:
        await websocket.send_json({"type": "error", "message": "invalid api key"})
        await websocket.close(code=4401)
        return
    container.access_control.validate_tenant_access(
        {"role": record.role, "tenant_ids": record.tenant_ids},
        tenant_id,
    )
    try:
        while True:
            payload = await websocket.receive_json()
            for event in await container.rtc_service.handle_event(tenant_id, room_id, payload):
                await websocket.send_json(event)
    except WebSocketDisconnect:
        return
