# 总体架构设计

## 1. 设计目标

平台目标是在统一客服引擎上，支持文本、语音、RTC、多行业增强、宿主系统挂载、自定义鉴权桥接和插件化扩展。

## 2. 当前事实与 Target State

### 2.1 当前事实

- 已有单体参考实现，可运行文本、语音、RTC、知识库、基础工具与人工协同。
- 运行模式支持独立 FastAPI 与宿主 FastAPI 挂载。

### 2.2 Target State

- 在现有单体参考实现上，引入平台级 `Auth Bridge`、插件平台和业务增强层。
- 保持单体可运行，同时保留未来拆分为多服务的边界。

## 3. 分层架构

```text
┌──────────────────────────────────────────────────────────────┐
│ 渠道接入层                                                   │
│ HTTP Chat / Voice / Admin API | RTC WebSocket | SDK / 挂载  │
└──────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌──────────────────────────────────────────────────────────────┐
│ 宿主桥接层                                                   │
│ Auth Bridge | Host Auth Context Mapper | Host Context Proxy │
└──────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌──────────────────────────────────────────────────────────────┐
│ 核心客服引擎层                                               │
│ Session | Route Orchestrator | LLM Orchestrator             │
│ Voice Runtime | RTC State Machine | Handoff Orchestrator    │
└──────────────────────────────────────────────────────────────┘
            │                          │
            ▼                          ▼
┌─────────────────────────────┐  ┌─────────────────────────────┐
│ 业务增强层                  │  │ 插件平台层                  │
│ Industry Adapter            │  │ Plugin Registry             │
│ Business Context Builder    │  │ Route / Tool / Auth /       │
│ Knowledge Domain Manager    │  │ Industry / Handoff /        │
│ Real-time Data Provider     │  │ Context / Response Plugins  │
│ Response Enhancement        │  │ Lifecycle / Priority        │
└─────────────────────────────┘  └─────────────────────────────┘
            │                          │
            └──────────────┬───────────┘
                           ▼
┌──────────────────────────────────────────────────────────────┐
│ 提供商适配层                                                 │
│ LLM | ASR | TTS | RTC | Vector Store | Business API         │
└──────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌──────────────────────────────────────────────────────────────┐
│ 运营管理层                                                   │
│ Prompt | Policy | Knowledge | Plugin Admin | Metrics        │
│ Diagnostics | 灰度与回滚                                     │
└──────────────────────────────────────────────────────────────┘
```

## 4. 关键模块关系

### 4.1 渠道接入层

- 负责把文本、语音、RTC 输入标准化为统一请求模型。
- 负责从 HTTP Header / Cookie / Query / Body 中收集宿主上下文。

### 4.2 宿主桥接层

- 优先处理认证入口。
- 当缺失 `X-API-Key` 时，允许通过 `Auth Bridge` 完成宿主身份认证。
- 产出统一 `HostAuthContext`。

### 4.3 核心客服引擎层

- `Session` 管理会话生命周期。
- `Route Orchestrator` 决定知识、业务、人工、高风险、插件路线。
- `LLM Orchestrator` 融合检索结果、实时数据和上下文。
- `RTC` 服务直接处理实时热路径，不通过事件总线。

### 4.4 业务增强层

- `Business Context Builder` 合并页面、用户、宿主对象、会话摘要。
- `Knowledge Domain Manager` 管理不同租户、行业下的知识域。
- `Real-time Business Data Provider` 通过业务工具插件读取动态数据。
- `Response Enhancement Orchestrator` 统一做引用、风格、脱敏和结构化输出后处理。

### 4.5 插件平台层

- 插件是主流程的一部分，不是可有可无的边车。
- 路由、业务工具、人工协同、行业适配、鉴权桥接、上下文增强、回复后处理都通过插件接入。

## 5. 典型调用链

### 5.1 文本请求

1. 接收 HTTP 请求。
2. `AuthService` 通过 API Key 或 Auth Bridge 解析身份。
3. `Business Context Builder` 合并宿主与页面上下文。
4. `Industry Adapter` 识别行业。
5. `Route Strategy Plugins` 决定走知识、业务、人工或高风险。
6. 若为知识型：`Knowledge Domain Manager` 解析知识域并检索。
7. 若为业务型：`Business Tool Plugins` 或 `BusinessAdapter` 调实时接口。
8. `LLM / Response Enhancement` 生成回复。
9. `Human Handoff Plugins` 判断是否转人工。
10. `Response Post Processor Plugins` 完成脱敏、格式化、多语言或结构化输出。

### 5.2 语音请求

1. ASR 产出文本。
2. 进入统一文本链路。
3. TTS 输出音频。

### 5.3 RTC 请求

1. 建房/入房。
2. WebSocket 收用户音频事件。
3. 直接走 RTC 状态机与语音链路。
4. 返回 `transcript`、`assistant_message`、`assistant_audio`、`state_changed`、`handoff` 等事件。

## 6. API 模式与挂载模式

### 6.1 API 模式

- 独立部署。
- 主要通过 `X-API-Key` 或宿主桥接 Header / Cookie 调用。

### 6.2 挂载模式

- 宿主系统把运行时作为子应用挂载，或在进程内直接调用 facade。
- 宿主系统可以注册自定义 `AuthBridgePlugin`。
- 平台复用宿主登录态与租户/权限上下文。

## 7. 部署形态

### 7.1 当前交付形态

- 单体 FastAPI 参考实现
- 本地 JSON 持久化
- 可选 OpenAI / Qdrant / HTTP Business Adapter

### 7.2 Future Target

- API Gateway / Channel Gateway
- Core Orchestrator
- Voice Runtime
- RTC Gateway
- Ops API / Console
- 独立知识与向量服务

## 8. 关键原则

- 主对象统一使用 `tenant_id`、`session_id`、`knowledge_base_id`。
- `session` 承载可恢复上下文，不与 `conversation` 混用。
- 实时语音热路径不经过事件总线。
- 静态知识与实时业务数据必须分离处理。
- 认证与上下文映射必须插件化，不把宿主逻辑写死到主流程。
