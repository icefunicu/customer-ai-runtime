# 模块设计

## 1. 模块总览

| 模块 | 职责 | 输入 | 输出 |
| --- | --- | --- | --- |
| Session Service | 会话创建、恢复、状态流转 | `tenant_id`、`session_id`、消息 | `Session` |
| Route Orchestrator | 路由分类与策略编排 | 消息、上下文、行业 | `RouteDecision` |
| Knowledge Service | 知识库、切片、检索 | 文档、查询、知识域 | Chunk / Citation |
| Tool Service | 业务工具调度 | 工具名、参数、上下文 | `BusinessResult` |
| Voice Service | ASR + 文本链路 + TTS | 音频载荷 | 文本结果 + 音频结果 |
| RTC Service | 房间与通话状态机 | RTC 事件 | RTC 输出事件 |
| Handoff Service | 转人工策略与交接包 | 会话、原因、策略 | `HandoffPackage` |
| Auth Service | API Key / Host Bridge 认证 | Header / Cookie / Token | `AuthContext` |
| Plugin Registry | 插件注册、发现、启停、优先级 | 插件元数据 | 可执行插件集合 |
| Business Context Builder | 合并宿主、页面、行为、会话上下文 | 请求与宿主上下文 | `BusinessContext` |
| Knowledge Domain Manager | 解析知识域与知识库选择 | 租户、行业、场景 | 域配置 |
| Response Enhancement Orchestrator | 回复后处理与结构化输出 | 原始回复、上下文 | 增强后回复 |

## 2. 领域对象

### 2.1 核心标识

- `tenant_id`
- `session_id`
- `knowledge_base_id`
- `room_id`
- `plugin_id`

### 2.2 关键模型

- `Session`
- `IntentFrame`
- `Message`
- `RouteDecision`
- `KnowledgeBase`
- `KnowledgeDocument`
- `KnowledgeChunk`
- `BusinessResult`
- `HandoffPackage`
- `RTCRoom`
- `HostAuthContext`
- `BusinessContext`
- `PluginDescriptor`

## 3. 会话管理模块

### 输入

- `tenant_id`
- `session_id`
- `channel`
- `message`

### 输出

- 当前会话
- 消息历史
- 当前状态
- `last_route`
- `last_intent`
- `intent_stack`
- `satisfaction_score`
- `resolution_status`

### 状态机

- `active`
- `waiting_human`
- `human_in_service`
- `closed`

### 异常处理

- 缺失 `tenant_id` 返回 `validation_error`
- 非法 `session_id` 返回 `not_found`
- 越权访问返回 `forbidden`

## 4. 路由模块

### 输入

- 用户消息
- 行业类型
- 宿主上下文
- 历史摘要
- `page_context`
- `business_objects`
- `intent_stack`

### 输出

- `knowledge`
- `business`
- `handoff`
- `risk`
- `plugin`
- `fallback`
- `confidence`
- `confidence_band`
- `intent`
- `matched_signals`

### 扩展方式

- `RouteStrategyPlugin`
- 行业适配器可提供路由提示
- 风险插件可覆盖默认路由结果
- `Route Orchestrator` 会聚合插件候选结果，而不是只依赖单次命中
- 结合 `page_context`、`business_objects` 和 `intent_stack` 对候选路由做动态加权
- 当置信度低于 `route_fallback_confidence_threshold` 时进入澄清兜底
- 当低于 `route_handoff_confidence_threshold` 或连续低置信度时升级为转人工

## 5. RAG 模块

### 输入

- `tenant_id`
- `knowledge_base_id`
- `query`
- `top_k`
- `min_score`

### 输出

- 切片结果
- 检索命中
- 引用列表

### 扩展方式

- 向量库适配层
- 知识域管理器
- 不同行业可使用不同知识域组合

## 6. 业务工具模块

### 输入

- 工具名
- 参数
- 行业
- 宿主身份
- 页面 / 业务对象上下文

### 输出

- 结构化业务结果
- 可向用户展示的摘要
- 是否建议转人工

### 扩展方式

- `BusinessToolPlugin`
- `BusinessAdapter`
- 行业适配器提供默认工具集合

## 7. 语音模块

### 输入

- `audio_base64`
- `content_type`
- `transcript_hint`

### 输出

- `transcript`
- `asr_confidence`
- `audio_response_base64`
- `audio_format`

### 状态

- 接收音频
- ASR 识别
- 文本链路处理
- TTS 输出

## 8. RTC 模块

### 输入事件

- `join`
- `user_audio`
- `interrupt`
- `request_human`
- `end`

### 输出事件

- `room_joined`
- `transcript`
- `assistant_message`
- `assistant_audio`
- `state_changed`
- `handoff`
- `ended`
- `error`

### 状态机

- `created`
- `joined`
- `listening`
- `thinking`
- `speaking`
- `waiting_human`
- `ended`

## 9. Auth Bridge 模块

### 输入

- Header
- Cookie
- Query
- 宿主票据

### 输出

- `HostAuthContext`
- 平台访问角色
- 宿主身份与权限映射结果

### 支持模式

- API Key
- Session / Cookie
- JWT / Bearer
- Custom Token
- 自定义桥接插件

### 失败策略

- 未认证返回 `auth_error`
- 租户不匹配返回 `forbidden`
- 宿主票据解析失败返回 `host_auth_error`

## 10. 插件系统模块

### 核心抽象

- `Plugin`
- `PluginRegistry`
- `PluginContext`
- `RouteStrategyPlugin`
- `BusinessToolPlugin`
- `HumanHandoffPlugin`
- `IndustryAdapterPlugin`
- `AuthBridgePlugin`
- `ContextEnricherPlugin`
- `ResponsePostProcessorPlugin`

### 生命周期

- 注册
- 启用
- 禁用
- 卸载
- 启动
- 关闭

### 插件执行原则

- 按优先级排序
- 支持租户、行业、渠道装配
- 插件失败时回退到默认实现

## 11. 业务增强模块

### Business Context Builder

- 合并宿主身份、页面上下文、业务对象、用户画像、最近行为、会话摘要、`intent_stack`

### Knowledge Domain Manager

- 维护 `tenant_id + industry + scenario -> knowledge domains`

### Real-time Business Data Provider

- 通过工具插件或业务适配器读取动态数据

### Response Enhancement Orchestrator

- 回复格式化
- 引用附加
- 脱敏
- 多语言
- 结构化输出

## 12. 管理模块

### 管理对象

- Prompt
- Policy
- Metrics
- Diagnostics
- Plugin 状态
- Provider 健康状态

### 失败方式

- 非管理员返回 `forbidden`
- 配置校验失败返回 `validation_error`

## 13. 与 Future Target 的边界

- 当前交付以单体参考实现为主。
- 文档中的多服务拆分、独立控制台等属于 future target，不宣称当前仓库已落地。
