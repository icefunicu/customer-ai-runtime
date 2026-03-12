# 部署文档

## 1. 部署方式

当前仓库提供两种部署方式：

- 本地开发部署
- Docker 单容器部署

## 2. 本地开发部署

```powershell
copy .env.example .env
.venv\Scripts\python.exe -m pip install -e .[dev]
.venv\Scripts\python.exe -m customer_ai_runtime
```

## 3. Docker 部署

```powershell
docker build -t customer-ai-runtime:latest .
docker run --rm -p 8000:8000 --env-file .env customer-ai-runtime:latest
```

## 4. 关键环境变量

- `CUSTOMER_AI_ENV`
- `CUSTOMER_AI_STORAGE_ROOT`
- `CUSTOMER_AI_DEFAULT_TENANT_ID`
- `CUSTOMER_AI_LLM_PROVIDER`
- `CUSTOMER_AI_ASR_PROVIDER`
- `CUSTOMER_AI_TTS_PROVIDER`
- `CUSTOMER_AI_VECTOR_PROVIDER`
- `CUSTOMER_AI_RTC_PROVIDER`
- `CUSTOMER_AI_OPENAI_API_KEY`
- `CUSTOMER_AI_OPENAI_BASE_URL`
- `CUSTOMER_AI_BUSINESS_PROVIDER`
- `CUSTOMER_AI_BUSINESS_API_BASE_URL`
- `CUSTOMER_AI_BUSINESS_API_KEY`

## 5. 生产建议

- 使用正式 API Key 管理，不使用示例密钥
- 将知识库、会话仓储和指标存储迁移到持久化设施
- 为 OpenAI/Qdrant/业务 API 配置专用网络出口与超时重试
- 用反向代理或 API Gateway 管理 TLS、限流和审计

## 5.1 当前本地持久化说明

- 默认仓储文件写入 `storage/state/`
- 运行时会生成：
  - `sessions.json`
  - `knowledge.json`
  - `rtc_rooms.json`
  - `diagnostics.json`
  - `runtime_config.json`
- 删除这些文件会清空本地状态

## 6. 当前可验证事实

- 本地单体部署当前可验证
- Docker 文件会随代码一并交付，当前是否构建成功需要在本地 Docker 环境中单独验证
