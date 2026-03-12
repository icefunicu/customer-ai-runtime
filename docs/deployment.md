# 部署文档

## 1. 当前可部署形态

当前仓库已落地的是单体 FastAPI 运行时，适用于：

- 本地开发与联调
- 单实例测试环境
- 宿主系统挂载验证
- 基于 Docker Compose 的小规模部署

当前事实：

- 已提供 [Dockerfile](/E:/Project/customer-ai-runtime/Dockerfile)
- 已提供 [docker-compose.yml](/E:/Project/customer-ai-runtime/deploy/docker-compose.yml)
- 已提供 `.env` 方式的环境变量配置
- 已提供管理接口用于运行时配置热更新、诊断与指标查看

## 2. Docker Compose 配置

仓库内 Compose 文件包含以下服务：

- `customer-ai-runtime`
  用途：运行时主服务，默认暴露 `8000`
- `qdrant`
  用途：向量检索依赖，默认暴露 `6333/6334`

关键配置点：

- `customer-ai-runtime` 默认通过 `build.args.CUSTOMER_AI_PIP_EXTRAS=providers` 安装可选提供商依赖
- 通过 `env_file: ../.env` 加载环境变量
- 默认挂载命名卷 `customer-ai-data` 持久化 `storage_root`
- 已配置健康检查：`GET /healthz`
- 已配置容器日志轮转：`json-file + max-size/max-file`

启动命令：

```bash
docker compose -f deploy/docker-compose.yml up -d --build
```

停止命令：

```bash
docker compose -f deploy/docker-compose.yml down
```

查看日志：

```bash
docker compose -f deploy/docker-compose.yml logs -f customer-ai-runtime
docker compose -f deploy/docker-compose.yml logs -f qdrant
```

## 3. 环境变量说明

### 3.1 基础运行

- `CUSTOMER_AI_ENV`
  建议：`prod`
- `CUSTOMER_AI_HOST`
  容器内建议：`0.0.0.0`
- `CUSTOMER_AI_PORT`
  默认：`8000`
- `CUSTOMER_AI_LOG_LEVEL`
  建议生产环境：`INFO`
- `CUSTOMER_AI_STORAGE_ROOT`
  容器内建议：`/data`
- `CUSTOMER_AI_API_KEYS_JSON`
  管理与客户调用 API Key 映射，建议通过密钥管理系统注入

### 3.2 提供商选择

- `CUSTOMER_AI_LLM_PROVIDER`
  可选：`local`、`openai`
- `CUSTOMER_AI_ASR_PROVIDER`
  可选：`local`、`openai`、`aliyun`、`tencent`
- `CUSTOMER_AI_TTS_PROVIDER`
  可选：`local`、`openai`、`aliyun`、`tencent`
- `CUSTOMER_AI_VECTOR_PROVIDER`
  可选：`local`、`qdrant`、`pinecone`、`milvus`
- `CUSTOMER_AI_BUSINESS_PROVIDER`
  可选：`local`、`http`、`graphql`、`grpc`

### 3.3 常见提供商凭据

- OpenAI
  `CUSTOMER_AI_OPENAI_API_KEY`
- 阿里云语音
  `CUSTOMER_AI_ALIYUN_ACCESS_KEY_ID`
  `CUSTOMER_AI_ALIYUN_ACCESS_KEY_SECRET`
  `CUSTOMER_AI_ALIYUN_APP_KEY`
- 腾讯云语音
  `CUSTOMER_AI_TENCENT_SECRET_ID`
  `CUSTOMER_AI_TENCENT_SECRET_KEY`
- Qdrant
  `CUSTOMER_AI_QDRANT_URL`
  `CUSTOMER_AI_QDRANT_API_KEY`

### 3.4 宿主桥接与认证

- `CUSTOMER_AI_HOST_SESSION_COOKIE_NAME`
- `CUSTOMER_AI_HOST_SESSION_MAP_JSON`
- `CUSTOMER_AI_HOST_TOKEN_MAP_JSON`
- `CUSTOMER_AI_HOST_JWT_SECRET`
- `CUSTOMER_AI_HOST_JWT_ISSUER`
- `CUSTOMER_AI_HOST_JWT_AUDIENCE`

## 4. 生产环境配置建议

### 4.1 入口与网络

- 在运行时前面放置反向代理或 API Gateway，统一处理 TLS、限流、来源 IP 和审计
- 仅暴露应用入口端口，不直接对公网暴露内部向量库
- 若使用 Docker Compose，建议将 Qdrant 仅绑定在内网网络，不映射宿主端口

### 4.2 密钥与配置

- 不要把真实密钥写入 Git
- 优先通过 CI/CD Secret、Kubernetes Secret、云 Secret Manager 或宿主机注入环境变量
- 管理员 API Key 与客户 API Key 分离，最少权限分配

### 4.3 存储与持久化

- 生产环境不要依赖临时文件系统
- 至少挂载持久卷保存 `storage/state/*.json`
- 当会话量和知识量增长时，应迁移到外部持久化存储，不建议长期使用本地 JSON 作为主存储

### 4.4 外部依赖保护

- 为 LLM、ASR、TTS、业务 API 和向量库设置合理超时
- 通过管理接口观察 `providers/health`，在未就绪时阻断流量切换
- 对计费型提供商单独设置调用配额和告警

## 5. 监控与日志配置

当前仓库已落地的观测能力：

- 应用日志：标准输出日志，格式由 [logging.py](/E:/Project/customer-ai-runtime/src/customer_ai_runtime/core/logging.py) 配置
- 指标计数：内存计数器，可通过管理接口获取
- 诊断事件：持久化到 `storage/state/diagnostics.json`
- 提供商健康：可通过管理接口查看配置就绪态

建议接入方式：

- 日志采集
  通过 Docker `json-file` 或宿主日志采集器接入 ELK / Loki / 云日志服务
- 指标采集
  通过 `GET /api/v1/admin/metrics` 和 `GET /api/v1/admin/metrics/summary` 采集业务计数
- 诊断排障
  通过 `GET /api/v1/admin/diagnostics` 和 `GET /api/v1/admin/sessions/{session_id}/monitor` 定位会话异常
- 告警拉取
  通过 `GET /api/v1/admin/alerts` 拉取 provider 未就绪、错误诊断、等待人工会话等告警线索
  告警阈值可通过 `PUT /api/v1/admin/runtime-config` 的 `alerts` 字段热更新

## 6. 部署后验证

基础健康检查：

```bash
curl http://127.0.0.1:8000/healthz
```

管理面检查：

```bash
curl -H "X-API-Key: demo-admin-key" http://127.0.0.1:8000/api/v1/admin/providers/health
curl -H "X-API-Key: demo-admin-key" http://127.0.0.1:8000/api/v1/admin/metrics/summary
curl -H "X-API-Key: demo-admin-key" http://127.0.0.1:8000/api/v1/admin/alerts
```

预期结果：

- `/healthz` 返回 `status=ok`
- `providers/health` 返回各提供商 `ready` 状态
- `metrics/summary` 返回计数器、会话摘要和诊断摘要
- `alerts` 返回需要运维关注的问题列表；无异常时可为空数组

## 7. 当前限制

当前可验证限制：

- 观测能力以管理接口和本地持久化事件为主，尚未内建 Prometheus exporter
- Docker Compose 适合单机或小规模环境，不等同于高可用生产集群方案
- 当前存储层仍以本地 JSON 仓储为主，更适合开发、演示和轻量部署

## 8. Future Target

以下属于未来目标，不代表当前仓库已落地：

- 多实例无状态部署与共享持久化后端
- Prometheus / Grafana 原生指标暴露
- 专用告警推送通道（Webhook、短信、IM）
- 更细粒度的审计日志与租户级运维视图
