# API 文档

本文档描述 target state 接口契约。当前仓库基础接口已存在，新增的宿主桥接、插件管理与上下文接口将与本文档保持一致。

## 1. 基本约定

- Base URL: `http://127.0.0.1:8000`
- 内容类型：`application/json`
- 核心标识：`tenant_id`、`session_id`、`knowledge_base_id`

### 1.1 认证方式

任选其一：

- `X-API-Key: <key>`
- `Authorization: Bearer <jwt>`
- `Cookie: host_session=<session-id>`
- `X-Host-Token: <token>`

### 1.2 通用响应

```json
{
  "request_id": "req_xxx",
  "data": {},
  "error": null
}
```

错误：

```json
{
  "request_id": "req_xxx",
  "data": null,
  "error": {
    "code": "validation_error",
    "message": "tenant_id is required",
    "details": {}
  }
}
```

## 2. 健康检查

### `GET /healthz`

- 用途：服务健康检查

## 3. 认证与上下文接口

### `GET /api/v1/auth/context`

- 用途：查看当前请求解析出的认证上下文
- 返回重点：`auth_mode`、`tenant_ids`、`host_auth_context`

### `POST /api/v1/context/resolve`

- 用途：显式解析业务上下文

请求示例：

```json
{
  "tenant_id": "demo-tenant",
  "channel": "web",
  "session_id": null,
  "integration_context": {
    "industry": "ecommerce",
    "page_context": {
      "page_type": "order_detail",
      "order_id": "ORD-1001"
    },
    "business_objects": {
      "order_id": "ORD-1001"
    }
  }
}
```

## 4. 会话接口

### `POST /api/v1/sessions`

- 用途：创建会话

### `GET /api/v1/sessions/{session_id}`

- 用途：查询会话
- 返回重点：`last_route`、`last_intent`、`intent_stack`、`satisfaction_score`、`resolution_status`、`first_response_time`、`avg_response_time`

### `GET /api/v1/sessions/{session_id}/messages?tenant_id=demo-tenant`

- 用途：查询会话消息历史

### `POST /api/v1/sessions/{session_id}/claim-human`

- 用途：人工接管会话

### `POST /api/v1/sessions/{session_id}/messages/human`

- 用途：人工写入回复

### `POST /api/v1/sessions/{session_id}/close`

- 用途：关闭会话
- 支持字段：`satisfaction_score`（1-5，可选）
- 支持字段：`resolution_status`（`resolved` / `unresolved` / `escalated`，可选）

## 5. 文本客服接口

### `POST /api/v1/chat/messages`

- 用途：发起文本客服请求

请求示例：

```json
{
  "tenant_id": "demo-tenant",
  "session_id": null,
  "channel": "web",
  "message": "我的订单 ORD-1001 什么时候发货？",
  "knowledge_base_id": "kb_support",
  "integration_context": {
    "industry": "ecommerce",
    "page_context": {
      "page_type": "order_detail"
    },
    "business_objects": {
      "order_id": "ORD-1001"
    }
  }
}
```

响应重点字段：

- `session_id`
- `route`
- `industry`
- `confidence`
- `route_confidence`
- `route_confidence_band`
- `intent`
- `answer`
- `citations`
- `tool_result`
- `handoff`
- `host_auth_context`
- `route_decision`

其中 `route_decision` 包含：

- `route`
- `confidence`
- `confidence_band`
- `intent`
- `tool_name`
- `reason`
- `matched_signals`

### `POST /api/v1/chat/handoff`

- 用途：显式触发转人工

## 6. 知识库接口

### `POST /api/v1/knowledge-bases`

### `GET /api/v1/knowledge-bases?tenant_id=demo-tenant`

### `GET /api/v1/knowledge-bases/{knowledge_base_id}?tenant_id=demo-tenant`

### `POST /api/v1/knowledge-bases/{knowledge_base_id}/documents`

### `POST /api/v1/knowledge-bases/{knowledge_base_id}/search`

## 7. 业务工具接口

### `POST /api/v1/tools/business-query`

- 用途：显式执行业务工具

请求示例：

```json
{
  "tenant_id": "demo-tenant",
  "tool_name": "order_status",
  "parameters": {
    "order_id": "ORD-1001"
  },
  "integration_context": {
    "industry": "ecommerce"
  }
}
```

## 8. 语音接口

### `POST /api/v1/voice/turn`

- 用途：发起语音轮次请求

请求示例：

```json
{
  "tenant_id": "demo-tenant",
  "session_id": null,
  "channel": "app_voice",
  "audio_base64": "base64-payload",
  "content_type": "text/plain",
  "knowledge_base_id": "kb_support",
  "integration_context": {
    "industry": "ecommerce"
  }
}
```

响应重点字段：

- `transcript`
- `asr_confidence`
- `audio_response_base64`
- `audio_format`

## 9. RTC 接口

### `POST /api/v1/rtc/rooms`

### `POST /api/v1/rtc/rooms/{room_id}/join`

### `POST /api/v1/rtc/rooms/{room_id}/interrupt`

### `POST /api/v1/rtc/rooms/{room_id}/end`

### `WS /ws/v1/rtc/{room_id}?tenant_id=demo-tenant&session_id=session_xxx`

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

## 10. 插件管理接口

### `GET /api/v1/admin/plugins`

- 用途：查看插件列表、状态、优先级、作用域和能力

### `POST /api/v1/admin/plugins/{plugin_id}/enable`

- 用途：启用插件

### `POST /api/v1/admin/plugins/{plugin_id}/disable`

- 用途：禁用插件

## 11. 管理接口

### `GET /api/v1/admin/metrics`

### `GET /api/v1/admin/metrics/summary`

- 用途：返回指标计数、按路由聚合的统计、会话摘要、满意度摘要和诊断摘要
- 可选查询参数：
  - `tenant_id`
- 返回重点：
  - `satisfaction_summary`
  - `resolution_summary`
  - `response_time_summary`

### `GET /api/v1/admin/sessions?tenant_id=demo-tenant`

### `GET /api/v1/admin/sessions/{session_id}/monitor?tenant_id=demo-tenant`

- 用途：查看单个会话的监控视图
- 返回重点：
  - `session`
  - `message_count`
  - `last_message`
  - `related_rooms`
  - `diagnostics`

### `GET /api/v1/admin/prompts`

### `GET /api/v1/admin/runtime-config`

- 用途：查看运行时热配置快照
- 返回重点：
  - `prompts`
  - `policies`
  - `alerts`
  - `plugin_states`

### `PUT /api/v1/admin/runtime-config`

- 用途：一次性热更新运行时配置
- 支持更新：
  - `prompts`
  - `policies`
  - `alerts`
  - `plugin_states`

### `PUT /api/v1/admin/prompts`

### `GET /api/v1/admin/policies`

### `PUT /api/v1/admin/policies`

路由增强相关策略字段：

- `route_fallback_confidence_threshold`
- `route_handoff_confidence_threshold`
- `intent_stack_max_depth`
- `intent_return_keywords`

### `GET /api/v1/admin/diagnostics`

可选查询参数：

- `tenant_id`
- `session_id`
- `room_id`
- `level`
- `code_prefix`
- `limit`

### `GET /api/v1/admin/rooms?tenant_id=demo-tenant`

### `GET /api/v1/admin/providers/health`

### `GET /api/v1/admin/alerts`

- 用途：查看需要关注的运维告警线索
- 可选查询参数：
  - `tenant_id`
- 告警规则来源：
  - `runtime-config.alerts.provider_not_ready_enabled`
  - `runtime-config.alerts.diagnostic_error_threshold`
  - `runtime-config.alerts.waiting_human_session_threshold`

### `GET /api/v1/admin/tools/catalog`

可选查询参数：

- `tenant_id`
- `industry`
- `channel`
- `include_disabled`

返回当前作用域下的工具目录元数据，包括：

- `name`
- `category`
- `description`
- `required_parameters`
- `optional_parameters`
- `suggested_context_keys`
- `plugin_id`
- `version`
- `priority`
- `enabled`
- `available`
- `tenant_scopes`
- `industry_scopes`
- `channel_scopes`
- `capabilities`

### `GET /api/v1/admin/tools/catalog/categories`

可选查询参数与 `/api/v1/admin/tools/catalog` 一致：

- `tenant_id`
- `industry`
- `channel`
- `include_disabled`

返回按工具分类聚合后的目录摘要，包括：

- `category`
- `tool_count`
- `enabled_count`
- `tools`

## 12. 错误码

- `validation_error`
- `auth_error`
- `host_auth_error`
- `forbidden`
- `not_found`
- `provider_error`
- `policy_blocked`
- `handoff_required`
- `rtc_state_error`
- `plugin_error`

## 13. 接入建议

- 文本客服：`POST /api/v1/chat/messages`
- 语音客服：`POST /api/v1/voice/turn`
- RTC 通话：房间 API + RTC WebSocket
- 宿主挂载：优先用挂载模式并注册 `AuthBridgePlugin`
- 进程内接入：直接调用 facade，并显式传入 `integration_context`
