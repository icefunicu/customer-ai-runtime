# Customer AI Runtime

`customer-ai-runtime` 是一个面向真实业务场景的模块化智能客服平台参考实现，覆盖文本客服、语音客服、RTC 实时通话、RAG 知识增强、业务系统联动、AI/人工协同、运营管理和多提供商适配。

当前仓库已按真实工程流程建立：

- 业务需求分析
- 总体架构设计
- 模块与接口设计
- 开发路线图
- 项目进展控制文档
- 可运行工程骨架与核心服务实现
- 测试、部署与接入文档

当前默认仓储已支持基于 `storage/state/` 的本地 JSON 持久化，服务重启后可恢复会话、知识库、RTC 房间、诊断事件和运行时 Prompt/Policy 配置。

该系统也支持作为模块被宿主系统接入：

- 作为独立服务部署
- 作为 FastAPI 子应用挂载到宿主系统
- 作为宿主进程内 facade 直接调用

## 项目目标

平台不是简单 RAG Demo，而是一个可接入任意业务系统的客服能力层，解决以下问题：

- 提高问题解决率和首轮解决率
- 降低人工客服重复咨询量
- 缩短文本与语音响应时间
- 用知识库、工具调用和策略路由区分知识型问题与业务型问题
- 在低置信度、高风险、投诉或用户主动要求时无缝转人工
- 提供文本、语音、RTC 三种接入方式
- 通过提供商适配层支持多厂商替换

## 当前实现范围

- 文本客服闭环：会话、路由、RAG、工具调用、人工转接
- 语音客服闭环：ASR 抽象、本地 ASR 开发提供商、TTS 音频输出
- RTC 通话闭环：房间、状态机、WebSocket 事件协议、打断/结束/转人工
- 知识库管理：创建知识库、导入文档、切片、检索
- 管理能力：提示词、策略、指标、会话检索、故障诊断事件
- 多提供商适配：本地提供商默认可跑，OpenAI/Qdrant 适配器可按环境变量启用

当前本地默认 TTS 提供商输出 `wav` 预览音频，用于链路验证；如需自然语音播报，可切换到已配置密钥的真实 TTS 提供商。

## 快速启动

```powershell
.venv\Scripts\python.exe -m pip install -e .[dev]
.venv\Scripts\python.exe -m customer_ai_runtime
```

服务默认启动在 `http://127.0.0.1:8000`。

## 测试

```powershell
.venv\Scripts\python.exe -m pytest
```

当前已验证结果：`10 passed`

## 项目结构

```text
src/customer_ai_runtime/
  api/                 FastAPI 路由与鉴权
  application/         业务编排与服务层
  domain/              领域模型、状态机、值对象
  providers/           LLM/ASR/TTS/RTC/向量库/业务系统适配
  repositories/        默认进程内仓储
  core/                配置、日志、异常、指标
docs/                  业务、架构、模块、API、测试、部署文档
tests/                 单元、集成、契约测试
examples/              HTTP 与 Python 接入示例
scripts/               启动、测试、示例导入脚本
deploy/                Docker 与环境模板
```

## 关键文档

- [业务需求](docs/business-requirements.md)
- [总体架构](docs/architecture.md)
- [模块设计](docs/module-design.md)
- [开发路线图](docs/roadmap.md)
- [进展控制](docs/progress-control.md)
- [API 文档](docs/api.md)
- [项目说明](docs/project-overview.md)
- [测试文档](docs/testing.md)
- [部署文档](docs/deployment.md)

## 接入说明

- 文本客服：调用 `POST /api/v1/chat/messages`
- 语音客服：调用 `POST /api/v1/voice/turn`
- RTC 客服：先创建房间，再连接 `WS /ws/v1/rtc/{room_id}`
- 知识库导入：调用 `POST /api/v1/knowledge-bases/{knowledge_base_id}/documents`
- 管理端：查看 `GET /api/v1/admin/*`
- 宿主系统挂载示例：`examples/host_fastapi_integration.py`

默认示例 API Key：

- 客户侧：`demo-public-key`
- 管理侧：`demo-admin-key`

仅用于本地演示，生产环境必须改为安全密钥并接入正式鉴权。
