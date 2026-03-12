# Customer AI Runtime

[![Python](https://img.shields.io/badge/Python-3.13+-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.135+-green.svg)](https://fastapi.tiangolo.com/)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

> 面向真实业务场景的智能客服能力平台，支持文本、语音、RTC实时通话，可挂载、可插件化、可行业增强。

`customer-ai-runtime` 是一个企业级智能客服平台参考实现。它不是简单的 RAG 问答服务，而是一个能够处理知识问答、实时业务查询、AI/人工协同的完整客服引擎。

## 核心特性

![Multimodal](https://img.shields.io/badge/Multimodal-文本%20|%20语音%20|%20RTC-blue)
![Plugin](https://img.shields.io/badge/Plugin-可插件化架构-green)
![Host](https://img.shields.io/badge/Host-宿主系统挂载-orange)
![Industry](https://img.shields.io/badge/Industry-行业增强-purple)

- **多模态客服** - 支持文本、语音轮次、RTC 实时通话三种接入模式
- **宿主系统挂载** - 可作为 FastAPI 子应用挂载，复用宿主登录态（Session/Cookie/JWT/SSO）
- **插件化架构** - 路由策略、业务工具、行业适配、鉴权桥接、回复后处理均可插件扩展
- **行业增强** - 内置电商、SaaS、教育、物流、CRM 等行业适配器，支持自定义行业
- **RAG 知识增强** - 多租户知识库管理，支持向量检索与引用溯源
- **实时业务数据** - 通过业务工具插件查询订单、物流、工单等动态数据
- **AI/人工协同** - 智能路由决策，支持高风险识别与人工接管
- **运营管理** - Prompt/Policy 管理、会话监控、诊断接口、插件管理

## 架构概览

```
┌─────────────────────────────────────────────────────────────┐
│ 渠道接入层                                                   │
│ HTTP Chat │ Voice API │ RTC WebSocket │ Host Mount / SDK    │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│ 宿主桥接层                                                   │
│ Auth Bridge │ Host Auth Context Mapper │ Context Injection   │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│ 核心客服引擎层                                               │
│ Session │ Route Orchestrator │ LLM Orchestrator            │
│ Voice Runtime │ RTC State Machine │ Handoff Orchestrator    │
└─────────────────────────────────────────────────────────────┘
            │                          │
            ▼                          ▼
┌─────────────────────────┐  ┌──────────────────────────────┐
│ 业务增强层              │  │ 插件平台层                   │
│ Industry Adapter        │  │ Plugin Registry              │
│ Business Context Builder│  │ Route / Tool / Auth /        │
│ Knowledge Domain Manager│  │ Industry / Handoff /         │
│ Real-time Data Provider │  │ Context / Response Plugins   │
└─────────────────────────┘  └──────────────────────────────┘
            │                          │
            └──────────────┬───────────┘
                           ▼
┌─────────────────────────────────────────────────────────────┐
│ 提供商适配层                                                 │
│ LLM │ ASR │ TTS │ RTC │ Vector Store │ Business API        │
└─────────────────────────────────────────────────────────────┘
```

## 快速开始

### 环境要求

- Python 3.13+
- 可选：OpenAI API Key、Qdrant 向量数据库

### 提供商扩展

当前仓库已落地的可选提供商包括：

- 语音识别（ASR）：`local`、`openai`、`aliyun`、`tencent`
- 语音合成（TTS）：`local`、`openai`、`aliyun`、`tencent`
- 向量库：`local`、`qdrant`、`pinecone`、`milvus`
- 业务适配器：`local`、`http`、`graphql`、`grpc`

其中语音提供商的最小配置如下：

- 阿里云：`CUSTOMER_AI_ASR_PROVIDER=aliyun` / `CUSTOMER_AI_TTS_PROVIDER=aliyun`，并填写 `CUSTOMER_AI_ALIYUN_ACCESS_KEY_ID`、`CUSTOMER_AI_ALIYUN_ACCESS_KEY_SECRET`、`CUSTOMER_AI_ALIYUN_APP_KEY`
- 腾讯云：`CUSTOMER_AI_ASR_PROVIDER=tencent` / `CUSTOMER_AI_TTS_PROVIDER=tencent`，并填写 `CUSTOMER_AI_TENCENT_SECRET_ID`、`CUSTOMER_AI_TENCENT_SECRET_KEY`

### 安装

```bash
# 克隆仓库
git clone https://github.com/your-org/customer-ai-runtime.git
cd customer-ai-runtime

# 创建虚拟环境
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
# 或 .venv\Scripts\activate  # Windows

# 安装依赖
pip install -e ".[dev]"

# 若需 Pinecone / Milvus / gRPC / 阿里云 / 腾讯云 提供商
pip install -e ".[dev,providers]"
```

### 配置

```bash
cp .env.example .env
# 编辑 .env 文件，配置你的 API Key 和数据库连接
```

阿里云语音默认走官方智能语音交互 RESTful 接口，一句话识别与语音合成都使用 `AppKey + Token` 链路，运行时会在服务端自动换取短期 Token。腾讯云语音默认走官方 Python SDK，请确保已安装 `providers` extra。

### 启动服务

```bash
# 方式1：直接运行
python -m customer_ai_runtime

# 方式2：使用脚本（Windows）
.\scripts\run-dev.ps1

# 方式3：Docker
docker-compose -f deploy/docker-compose.yml up
```

服务默认运行在 `http://127.0.0.1:8000`

### 验证安装

```bash
# 健康检查
curl http://127.0.0.1:8000/healthz

# 查看 API 文档
open http://127.0.0.1:8000/docs
```

## 使用示例

### 文本客服

```python
import httpx

response = httpx.post("http://127.0.0.1:8000/api/v1/chat/messages", json={
    "tenant_id": "demo-tenant",
    "channel": "web",
    "message": "我的订单什么时候发货？",
    "knowledge_base_id": "kb_support",
    "integration_context": {
        "industry": "ecommerce",
        "page_context": {"page_type": "order_detail"},
        "business_objects": {"order_id": "ORD-1001"}
    }
}, headers={"X-API-Key": "your-api-key"})

print(response.json())
```

### 宿主系统挂载

```python
from fastapi import FastAPI
from customer_ai_runtime.integration import CustomerAIRuntimeModule

app = FastAPI()

# 挂载客服平台
runtime = CustomerAIRuntimeModule()
app.mount("/customer-ai", runtime.app)

# 注册自定义鉴权桥接
runtime.register_plugin(MyAuthBridgePlugin())
```

更多示例见 [examples/](examples/) 目录。

## 插件扩展

平台提供以下扩展点：

| 插件类型 | 用途 | 示例 |
|---------|------|------|
| `RouteStrategyPlugin` | 路由决策 | 自定义分流策略 |
| `BusinessToolPlugin` | 业务工具 | 订单查询、物流追踪 |
| `IndustryAdapterPlugin` | 行业适配 | 电商、SaaS、教育 |
| `AuthBridgePlugin` | 鉴权桥接 | SSO、自定义Token |
| `ContextEnricherPlugin` | 上下文增强 | 用户画像注入 |
| `ResponsePostProcessorPlugin` | 回复后处理 | 脱敏、多语言 |
| `HumanHandoffPlugin` | 人工协同 | 转人工策略 |

### 注册插件示例

```python
from customer_ai_runtime.domain.platform import Plugin, PluginDescriptor

class OrderStatusTool(Plugin):
    descriptor = PluginDescriptor(
        plugin_id="order_status_tool",
        name="订单状态查询",
        kind="business_tool",
        priority=100
    )
    
    async def execute(self, parameters, context):
        order_id = parameters.get("order_id")
        # 查询订单状态...
        return {"status": "shipped", "tracking_no": "SF123456"}

# 注册插件
runtime.register_plugin(OrderStatusTool())
```

## 文档

| 文档 | 说明 |
|------|------|
| [docs/project-overview.md](docs/project-overview.md) | 项目总览与目标 |
| [docs/architecture.md](docs/architecture.md) | 总体架构设计 |
| [docs/module-design.md](docs/module-design.md) | 模块详细设计 |
| [docs/api.md](docs/api.md) | API 接口文档 |
| [docs/business-enhancement.md](docs/business-enhancement.md) | 业务增强设计 |
| [docs/auth-bridge.md](docs/auth-bridge.md) | 宿主桥接与鉴权 |
| [docs/plugin-system.md](docs/plugin-system.md) | 插件系统设计 |
| [docs/roadmap.md](docs/roadmap.md) | 实施路线图 |
| [docs/deployment.md](docs/deployment.md) | 部署指南 |

## 测试

```bash
# 运行所有测试
pytest

# 运行特定测试
pytest tests/test_runtime_api.py -v

# 覆盖率报告
pytest --cov=src/customer_ai_runtime --cov-report=html
```

## 行业支持

内置行业适配器：

- **电商 (ecommerce)** - 订单、商品、物流、售后、会员
- **SaaS** - 账号、组织、订阅、工单、权限
- **教育** - 课程、学习进度、考试、证书
- **物流** - 运单、轨迹、异常、签收、赔付
- **CRM** - 客户档案、服务记录、工单、跟进

## 认证方式

支持多种认证模式：

- `X-API-Key` - 平台 API Key
- `Cookie / Session` - 复用宿主会话
- `Authorization: Bearer <JWT>` - JWT Token
- `X-Host-Token` - 宿主自定义票据
- **自定义桥接** - 通过 `AuthBridgePlugin` 实现任意鉴权逻辑

## 项目结构

```
customer-ai-runtime/
├── src/customer_ai_runtime/    # 核心源码
│   ├── api/                    # FastAPI 路由与模型
│   ├── application/            # 业务编排与插件
│   ├── core/                   # 配置、日志、工具
│   ├── domain/                 # 领域模型
│   ├── providers/              # 外部服务适配
│   └── repositories/           # 数据持久化
├── docs/                       # 设计文档
├── examples/                   # 接入示例
├── tests/                      # 测试用例
├── deploy/                     # 部署配置
└── scripts/                    # 开发脚本
```

## 贡献指南

1. Fork 本仓库
2. 创建特性分支 (`git checkout -b feature/amazing-feature`)
3. 提交更改 (`git commit -m 'feat: add amazing feature'`)
4. 推送到分支 (`git push origin feature/amazing-feature`)
5. 创建 Pull Request

### 开发规范

- 遵循 [Conventional Commits](https://www.conventionalcommits.org/) 提交规范
- 代码风格使用 `ruff` 进行格式化
- 类型检查使用 `mypy`
- 所有功能需包含测试用例

```bash
# 代码格式化
ruff format .
ruff check .

# 类型检查
mypy src
```

## 许可证

本项目采用 [MIT](LICENSE) 许可证。

## 致谢

- [FastAPI](https://fastapi.tiangolo.com/) - 高性能 Web 框架
- [Pydantic](https://docs.pydantic.dev/) - 数据验证
- [OpenAI](https://openai.com/) - LLM 能力
- [Qdrant](https://qdrant.tech/) - 向量数据库

---

> **注意**：当前仓库为单体参考实现，具备完整运行能力。未来拆分为多服务架构属于 roadmap 规划，当前尚未落地。
