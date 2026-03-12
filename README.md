# Customer AI Runtime

`customer-ai-runtime` 是一个面向真实业务场景的智能客服能力平台。它不是单一 RAG 问答服务，而是一个可挂载、可插件化、可行业增强、可复用宿主登录态的客服平台参考实现。

## 当前事实

- 当前仓库已经具备可运行能力：文本客服、语音轮次、RTC 房间与事件、知识库、业务工具、人工接手、管理接口、示例接入与自动化测试。
- 当前仓库已补齐平台级核心能力：`Auth Bridge`、插件注册中心、行业适配器、上下文构造、知识域管理、回复后处理与插件管理接口。
- 当前仓库仍然是单体参考实现，未来拆分为多服务属于 future target，不宣称当前已拆分。

## 产品目标

平台要解决的不是“如何把 FAQ 接到大模型”，而是以下真实问题：

- 用统一路由把知识问答、实时业务查询、高风险问题和人工协同分流。
- 把行业静态知识、实时业务数据和宿主上下文联合编排，而不是全部塞进 RAG。
- 在宿主系统挂载模式下复用 Session / Cookie / JWT / SSO / 自定义 Token，不强制接入方改造成 `X-API-Key`。
- 通过插件扩展路由、工具、行业增强、鉴权桥接、上下文增强、回复后处理与人工协同。

## 架构分层

```text
渠道接入层
  HTTP Chat / Voice / Admin API
  RTC WebSocket
  宿主挂载模块 / SDK facade

核心客服引擎层
  Session 管理
  Route Orchestrator
  Knowledge / Business / Human Handoff 编排
  Voice / RTC 状态机

业务增强层
  Industry Adapter
  Business Context Builder
  Knowledge Domain Manager
  Real-time Business Data Provider
  Response Enhancement Orchestrator

宿主桥接层
  Auth Bridge
  Host Auth Context Mapper
  Host Context Injection

插件平台层
  Plugin Registry
  Route / Tool / Auth / Industry / Handoff / Context / Response 插件

提供商适配层
  LLM / ASR / TTS / RTC / Vector Store / Business API

运营管理层
  Prompt / Policy / Knowledge / Diagnostics / Metrics / Plugin Admin
```

## 目录结构

```text
src/customer_ai_runtime/
  api/                  FastAPI 路由、请求模型、宿主挂载入口
  application/          核心编排、业务增强、Auth Bridge、插件装配
  core/                 配置、日志、响应、错误、基础工具
  domain/               领域模型、状态机、插件与鉴权值对象
  providers/            LLM / ASR / TTS / 向量库 / 业务系统适配
  repositories/         本地持久化仓储
docs/                   业务、架构、模块、API、增强、鉴权、插件、部署、测试文档
examples/               宿主挂载与客户端接入示例
scripts/                启动、测试、种子数据脚本
tests/                  单元、集成、关键链路测试
deploy/                 Docker Compose 与部署模板
```

## 快速启动

```powershell
.venv\Scripts\python.exe -m pip install -e .[dev]
.venv\Scripts\python.exe -m customer_ai_runtime
```

默认地址：`http://127.0.0.1:8000`

## 测试

```powershell
.venv\Scripts\python.exe -m pytest
```

说明：

- 当前仓库的测试结果只以你本地本次执行结果为准，不在文档中虚构“始终通过”。
- 关键测试范围见 `docs/testing.md`。

## 接入模式

支持以下模式：

- 独立 API 服务
- 宿主 FastAPI 子应用挂载
- 宿主进程内 facade / SDK 调用
- Web / H5 / App / 小程序文本接入
- App 语音轮次接入
- RTC 实时通话接入

## 认证模式

平台设计支持以下认证方式：

- `X-API-Key`
- `Cookie / Session`
- `Authorization: Bearer <JWT>`
- `X-Host-Token`
- 通过注册自定义 `AuthBridge` 实现宿主票据换票或内部鉴权

## 文档索引

- `docs/project-overview.md`
- `docs/business-requirements.md`
- `docs/architecture.md`
- `docs/module-design.md`
- `docs/business-enhancement.md`
- `docs/adapter-design.md`
- `docs/auth-bridge.md`
- `docs/plugin-system.md`
- `docs/roadmap.md`
- `docs/progress-control.md`
- `docs/api.md`
- `docs/testing.md`
- `docs/deployment.md`

## 示例

- `examples/http-demo.http`
- `examples/python_client.py`
- `examples/host_fastapi_integration.py`
- `examples/host_custom_auth_bridge.py`

## 开发约束

- 设计与接口变更必须先改文档，再改代码。
- 禁止把实时业务数据粗暴写入通用知识库后假装支持业务增强。
- 插件与鉴权桥接属于主架构，不是可有可无的附加补丁。
