# 诊断事件与埋点约定（当前事实）

本仓库通过 `DiagnosticsService` 记录诊断事件，并可通过管理接口查询：

- `GET /api/v1/admin/diagnostics`（需要 `admin` 权限）

## 1. 通用字段

每条事件包含：

- `event_id`：事件唯一标识
- `level`：`info` / `warning` / `error`
- `code`：事件码（稳定标识）
- `message`：事件描述（面向排障）
- `created_at`：UTC 时间
- `context`：结构化上下文（默认会做脱敏与截断）

`context` 中常见字段：

- `tenant_id`
- `session_id`
- `room_id`
- `channel`
- `request_id`（若来自 HTTP 请求）

## 2. 已落地的核心事件码（示例）

以下为当前代码中已出现的事件码集合（非穷尽），用于对接运营看板/排障流程时的稳定参考：

- `chat.route_decided`：路由决策完成
- `chat.tool_executed`：业务工具已执行
- `chat.knowledge_retrieved`：知识检索完成（包含 `effective_hit`）
- `knowledge.retrieve_miss`：知识检索未命中有效引用（warning）
- `chat.handoff_required`：需要转人工（warning）
- `chat.completed`：一次聊天请求完成（包含 `duration_ms`）
- `voice.turn_completed`：一次语音轮次完成（包含 `duration_ms`）
- `rtc.room_created` / `rtc.room_joined` / `rtc.audio_processed`
- `session.satisfaction_recorded` / `session.resolution_recorded`
- `message.feedback_recorded` / `message.feedback_request_human`

## 3. 注意事项

- 诊断事件默认会对自由文本做截断/脱敏，不保证保留原文。
- 事件属于“诊断面”而非实时音频热路径；RTC 热路径中的事件以 WebSocket 消息为主。

## 4. 导出（当前实现）

可选配置 `CUSTOMER_AI_DIAGNOSTICS_EXPORT_PATH`（相对路径会落在 `storage_root` 下），启用后会把每条诊断事件以 JSON Lines 方式追加写入该文件，便于外部采集器摄取。
