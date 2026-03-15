# 性能口径与 SLO（当前事实 + 建议口径）

## 1. 当前已记录的数据

- 会话级：`first_response_time`、`avg_response_time`（见会话模型字段）
- 诊断级：部分事件包含 `duration_ms`（例如 `chat.completed`、`voice.turn_completed`）
- 管理接口汇总：`GET /api/v1/admin/metrics/summary` 的 `response_time_summary`

说明：分位数统计（p50/p95）当前基于“最近诊断样本”（受查询上限影响），用于快速排障与趋势观察，不等同于全量离线统计口径。

## 2. 建议的稳定口径（对齐验收）

- `turn_duration_ms`：从收到请求到返回响应（文本/语音/RTC）端到端耗时
- 分位数：至少输出 p50、p95，并明确：
  - 统计窗口（最近 N 条 / 最近 5 分钟）
  - 稳态还是冷启动
  - 是否包含外部 provider 耗时

