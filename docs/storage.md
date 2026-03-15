# 存储与多实例说明（当前事实 + 迁移建议）

## 1. 当前实现（当前事实）

当前仓库默认使用本地 JSON 进行状态持久化（适合开发/演示/单实例）：

- 会话：`<storage_root>/state/sessions.json`
- 知识库：`<storage_root>/state/knowledge.json`
- RTC 房间：`<storage_root>/state/rtc_rooms.json`
- 诊断事件：`<storage_root>/state/diagnostics.json`
- 运行时配置：`<storage_root>/state/runtime_config.json`

## 2. 已知限制

- 不适合多实例并发写入与强一致需求
- 缺少事务与索引，数据量大时查询与写入会退化

## 3. 迁移建议（future target）

- 抽象 repository 接口并新增可选实现（Postgres/Redis），保留 JSON 作为 dev fallback
- 采用可回滚迁移策略：
  - 只读迁移或双写一段时间
  - 明确回滚开关与数据一致性检查

