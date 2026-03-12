# 部署文档

## 1. 当前交付形态

当前仓库交付的是单体 FastAPI 参考实现，适用于：

- 本地开发
- 接口联调
- 宿主挂载验证
- 平台能力演示

## 2. 运行前准备

- Python `>=3.13`
- 可选外部依赖：OpenAI、Qdrant、宿主业务 API
- 环境变量配置 `.env`

## 3. 本地启动

```powershell
.venv\Scripts\python.exe -m pip install -e .[dev]
.venv\Scripts\python.exe -m customer_ai_runtime
```

## 4. Docker

仓库提供：

- `Dockerfile`
- `deploy/docker-compose.yml`

## 5. 配置项

### 当前基础配置

- `CUSTOMER_AI_HOST`
- `CUSTOMER_AI_PORT`
- `CUSTOMER_AI_STORAGE_ROOT`
- `CUSTOMER_AI_LLM_PROVIDER`
- `CUSTOMER_AI_ASR_PROVIDER`
- `CUSTOMER_AI_TTS_PROVIDER`
- `CUSTOMER_AI_VECTOR_PROVIDER`
- `CUSTOMER_AI_BUSINESS_PROVIDER`
- `CUSTOMER_AI_API_KEYS_JSON`

### 本轮新增目标配置

- Auth Bridge 配置
- JWT Secret / Issuer / Audience
- Host Session Map / Host Token Map
- 插件装配配置
- 知识域映射配置

## 6. 生产部署建议

- 将 API Gateway 与宿主网关对齐，统一做 TLS、限流和审计
- 真实生产优先使用外部持久化存储，避免本地 JSON
- 对外部模型与业务 API 设置超时、重试和熔断
- 日志、指标、诊断接入统一观测平台

## 7. Future Target

未来可拆分：

- Channel Gateway
- Core Orchestrator
- Voice Runtime
- RTC Gateway
- Knowledge Service
- Ops API

以上为 future target，不代表当前仓库已经拆分。
