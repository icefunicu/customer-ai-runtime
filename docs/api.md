# API 文档

本文档描述当前参考实现对外暴露的文本客服、语音客服、RTC、知识库、业务工具、人工协同与管理端接口。

## 1. 基本约定

- Base URL：`http://127.0.0.1:8000`
- 鉴权头：`X-API-Key: <key>`
- 内容类型：`application/json`
- 多租户主键：`tenant_id`

默认示例密钥：

- 客户接口：`demo-public-key`
- 管理接口：`demo-admin-key`

## 2. 通用响应结构

```json
{
  "request_id": "req_123",
  "data": {},
  "error": null
}
```

错误响应：

```json
{
  "request_id": "req_123",
  "data": null,
  "error": {
    "code": "validation_error",
    "message": "tenant_id is required"
  }
}
```

## 3. 健康检查

### `GET /healthz`

用途：服务健康检查

## 4. 会话接口

### `POST /api/v1/sessions`

用途：创建会话

请求体：

```json
{
  "tenant_id": "demo-tenant",
  "channel": "web"
}
```

### `GET /api/v1/sessions/{session_id}`

用途：查询会话详情

### `GET /api/v1/sessions/{session_id}/messages?tenant_id=demo-tenant`

用途：查询会话消息历史

### `POST /api/v1/sessions/{session_id}/claim-human`

用途：人工客服正式接管会话，状态切换为 `human_in_service`

### `POST /api/v1/sessions/{session_id}/messages/human`

用途：由人工客服写入回复消息

### `POST /api/v1/sessions/{session_id}/close`

用途：关闭会话，状态切换为 `closed`

## 5. 文本客服接口

### `POST /api/v1/chat/messages`

用途：发起一次文本客服请求

请求体：

```json
{
  "tenant_id": "demo-tenant",
  "session_id": null,
  "channel": "web",
  "message": "我的订单什么时候发货？",
  "knowledge_base_id": "kb_support"
}
```

响应重点字段：

- `session_id`
- `route`
- `confidence`
- `answer`
- `citations`
- `handoff`
- `tool_result`

## 6. 人工协同接口

### `POST /api/v1/chat/handoff`

用途：主动触发转人工

请求体：

```json
{
  "tenant_id": "demo-tenant",
  "session_id": "session_xxx",
  "reason": "user_requested_human"
}
```

## 7. 知识库接口

### `POST /api/v1/knowledge-bases`

用途：创建知识库

### `GET /api/v1/knowledge-bases/{knowledge_base_id}?tenant_id=demo-tenant`

用途：查询知识库

### `GET /api/v1/knowledge-bases?tenant_id=demo-tenant`

用途：列出当前租户下的全部知识库

### `POST /api/v1/knowledge-bases/{knowledge_base_id}/documents`

用途：导入文档并建立切片索引

请求体：

```json
{
  "tenant_id": "demo-tenant",
  "title": "退款政策",
  "content": "7 天无理由退款，售后工单 24 小时内响应。",
  "metadata": {
    "source": "help-center"
  }
}
```

### `POST /api/v1/knowledge-bases/{knowledge_base_id}/search`

用途：执行知识检索

## 8. 业务工具接口

### `POST /api/v1/tools/business-query`

用途：显式调用业务工具

请求体：

```json
{
  "tenant_id": "demo-tenant",
  "tool_name": "order_status",
  "parameters": {
    "order_id": "ORD-1001"
  }
}
```

支持工具：

- `order_status`
- `after_sale_status`
- `logistics_tracking`
- `account_lookup`

## 9. 语音客服接口

### `POST /api/v1/voice/turn`

用途：发起一次语音客服轮次

请求体：

```json
{
  "tenant_id": "demo-tenant",
  "session_id": null,
  "channel": "app_voice",
  "audio_base64": "5L2g5aW977yM5oiR55qE6K6i5Y2V5Y+35Y+R6LSn5LqG",
  "content_type": "text/plain",
  "knowledge_base_id": "kb_support"
}
```

说明：

- 默认本地 ASR 提供商支持直接传 UTF-8 文本的 base64，用于开发环境验证链路。
- 若配置真实 ASR 提供商，可直接上传真实音频。
- 默认本地 TTS 提供商返回 `wav` 预览音频，用于链路联调。

响应额外字段：

- `transcript`
- `audio_response_base64`
- `audio_format`

## 10. RTC 接口

### `POST /api/v1/rtc/rooms`

用途：创建 RTC 房间

### `POST /api/v1/rtc/rooms/{room_id}/join`

用途：加入房间并绑定 `session_id`

### `POST /api/v1/rtc/rooms/{room_id}/interrupt`

用途：发送打断控制

### `POST /api/v1/rtc/rooms/{room_id}/end`

用途：结束通话

### `WS /ws/v1/rtc/{room_id}?tenant_id=demo-tenant&session_id=session_xxx`

用途：RTC 控制与媒体事件通道

客户端事件：

- `join`
- `user_audio`
- `interrupt`
- `request_human`
- `end`

服务端事件：

- `room_joined`
- `transcript`
- `assistant_message`
- `assistant_audio`
- `state_changed`
- `handoff`
- `ended`
- `error`

## 11. 管理端接口

### `GET /api/v1/admin/metrics`

用途：查看关键指标

### `GET /api/v1/admin/sessions?tenant_id=demo-tenant`

用途：按租户筛选会话

### `GET /api/v1/admin/prompts`

用途：查看运行时 Prompt 模板

### `PUT /api/v1/admin/prompts`

用途：更新 Prompt 模板

### `GET /api/v1/admin/policies`

用途：查看运行时路由/人工协同策略

### `PUT /api/v1/admin/policies`

用途：更新运行时策略

### `GET /api/v1/admin/diagnostics`

用途：查看近期故障诊断事件

### `GET /api/v1/admin/rooms?tenant_id=demo-tenant`

用途：查看当前租户的 RTC 房间列表

### `GET /api/v1/admin/providers/health`

用途：查看 LLM、ASR、TTS、向量库、业务系统、RTC 提供商的当前配置就绪状态

### `GET /api/v1/admin/tools/catalog`

用途：查看标准业务工具目录、必填参数和推荐的集成上下文字段

## 12. 错误码

- `validation_error`
- `auth_error`
- `forbidden`
- `not_found`
- `provider_error`
- `policy_blocked`
- `handoff_required`
- `rtc_state_error`

## 13. 接入建议

- 文本/H5/小程序：直接使用 HTTP API
- App 语音：先走 `/voice/turn`，后续需要实时通话时再接 RTC
- 电话或实时语音：接入房间 API + WebSocket RTC 协议
- 第三方业务系统：通过业务工具接口或替换业务适配器
- 宿主 FastAPI 系统：使用 `CustomerAIRuntimeModule.mount_to()` 挂载子应用
- 宿主进程内调用：使用 `CustomerAIRuntimeModule.chat()` 和 `voice_turn()`

## 14. 当前验证状态

- 已通过自动化测试：文本客服、业务查询、人工转接、人工接管、语音链路、RTC WebSocket、管理策略与管理查询接口、重启后本地持久化恢复、宿主系统模块挂载与进程内调用
- 外部 OpenAI/Qdrant/HTTP 业务系统适配器代码已提供，但当前未配置真实环境，联调不可验证
