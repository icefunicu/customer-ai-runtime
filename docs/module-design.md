# 模块设计与接口设计

## 1. 设计原则

- 模块低耦合、高内聚
- 抽象接口与提供商实现分离
- 所有入口统一做租户、参数和范围校验
- 所有状态变更都记录诊断事件与关键指标

## 2. 核心领域对象

### 2.1 Session

- 标识：`tenant_id`、`session_id`
- 属性：渠道、当前状态、历史消息、摘要、最近意图、是否等待人工
- 状态：
  - `active`
  - `waiting_human`
  - `human_in_service`
  - `closed`

### 2.2 RTC Session

- 标识：`tenant_id`、`session_id`、`room_id`
- 状态：
  - `created`
  - `joined`
  - `listening`
  - `thinking`
  - `speaking`
  - `waiting_human`
  - `ended`

### 2.3 Knowledge Base

- 标识：`tenant_id`、`knowledge_base_id`
- 属性：名称、描述、文档集、切片索引、检索参数

## 3. 模块职责

## 3.1 Session 模块

输入：

- 新消息
- 语音识别结果
- RTC 房间控制事件

输出：

- 会话创建/恢复结果
- 历史上下文
- 状态变更

错误处理：

- 缺失 `tenant_id` 或非法 `session_id` 返回 `400`
- 访问不存在会话返回 `404`
- 跨租户访问返回 `403`

## 3.2 Route / Policy 模块

输入：

- 用户消息
- 渠道类型
- 会话上下文
- 运行时策略配置

输出：

- `knowledge`
- `business`
- `handoff`
- `risk`
- `fallback`

规则：

- 用户要求人工、投诉、退款争议、法律/安全等高风险优先转人工
- 命中订单/物流/售后/账号意图时优先走业务工具
- FAQ、规则说明、政策说明优先走 RAG

## 3.3 RAG 模块

输入：

- 文档内容
- 知识库配置
- 查询文本

输出：

- 文档切片
- 检索命中结果
- 引用来源
- 拼接后的上下文

错误处理：

- 空文档/超大文档返回 `400`
- 不存在知识库返回 `404`
- 未命中时显式返回空检索分支

## 3.4 LLM 编排模块

输入：

- 路由结果
- Prompt 模板
- 会话历史
- RAG 结果
- 工具结果

输出：

- 文本回复
- 置信度
- 下一步动作
- 引用来源

职责：

- Prompt 组装
- 检索与工具结果融合
- 流式或分段回复
- 低置信度兜底

## 3.5 ASR 模块

输入：

- 音频字节或音频片段
- 内容类型
- 可选转录提示

输出：

- 识别文本
- 识别置信度
- 是否为增量结果

## 3.6 TTS 模块

输入：

- 回复文本
- 语音参数

输出：

- 音频字节
- 音频编码格式
- 分片列表

## 3.7 RTC 模块

输入：

- 房间创建/加入/退出事件
- 音频输入
- 打断/超时/结束事件

输出：

- 房间状态
- 事件回推
- 通话摘要

关键约束：

- 音频热路径只通过 WebSocket/RTC 控制通道处理
- 事件总线不承载实时音频分片

## 3.8 业务 API / 工具模块

输入：

- 标准化业务查询请求
- 业务实体标识

输出：

- 结构化业务结果
- 对用户可读的安全摘要

工具范围：

- `order_status`
- `after_sale_status`
- `logistics_tracking`
- `account_lookup`

## 3.9 Operator / Console 模块

输入：

- Prompt 配置变更
- 路由阈值变更
- 会话筛选条件

输出：

- 当前配置
- 指标统计
- 故障诊断结果

## 4. 抽象接口契约

### 4.1 LLM Provider

```python
async def generate(request: LLMRequest) -> LLMResponse
```

### 4.2 ASR Provider

```python
async def transcribe(request: ASRRequest) -> ASRResult
```

### 4.3 TTS Provider

```python
async def synthesize(request: TTSRequest) -> TTSResult
```

### 4.4 Vector Store Provider

```python
async def upsert(chunks: list[KnowledgeChunk]) -> None
async def search(query: str, top_k: int, tenant_id: str, knowledge_base_id: str) -> list[RetrievalHit]
```

### 4.5 Business Adapter

```python
async def execute(query: BusinessQuery) -> BusinessResult
```

## 5. 错误码策略

- `validation_error`: 参数校验失败
- `auth_error`: 鉴权失败
- `not_found`: 对象不存在
- `provider_error`: 外部提供商调用失败
- `policy_blocked`: 被策略拒绝
- `handoff_required`: 必须转人工
- `rtc_state_error`: RTC 状态非法

## 6. 状态机设计

### 6.1 文本/语音会话状态机

```text
active -> waiting_human -> human_in_service -> closed
active -> closed
```

### 6.2 RTC 通话状态机

```text
created -> joined -> listening -> thinking -> speaking -> listening
listening/thinking/speaking -> waiting_human
任意非 ended 状态 -> ended
```

## 7. 扩展方式

- 增加新 LLM/ASR/TTS/RTC 提供商时，只实现对应抽象接口并在工厂注册
- 增加新业务工具时，在 `ToolService` 注册工具名与输入校验
- 增加新渠道时，复用统一 `MessageProcessingService`

