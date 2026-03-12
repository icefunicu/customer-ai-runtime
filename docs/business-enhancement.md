# 业务增强设计

## 1. 为什么业务增强不是“多塞文档”

单纯 RAG 只能处理静态知识命中问题。真实客服平台需要同时处理：

- 静态规则解释
- 实时订单 / 物流 / 工单 / 账号查询
- 当前页面与业务对象上下文
- 不同行业的话术、规则和数据结构差异

因此业务增强必须是联合编排机制，而不是“把订单状态写成文档后再检索”。

## 2. 四类信息模型

### 2.1 通用静态知识

- 平台规则
- 产品说明
- 帮助文档
- FAQ

处理方式：RAG

### 2.2 行业静态知识

- 电商订单与售后规则
- SaaS 套餐与权限规则
- 教育课程与学习规则
- 物流赔付与签收规则
- CRM 服务等级规则

处理方式：行业知识域 + RAG

### 2.3 实时业务数据

- 订单状态
- 物流轨迹
- 会员等级
- 工单状态
- 学习进度
- 订阅状态

处理方式：业务工具插件 / 业务适配器 / 实时 API

### 2.4 当前会话与页面上下文

- 当前页面
- 当前商品 / 订单 / 工单 / 课程 / 运单标识
- 当前用户角色与租户
- 最近用户行为
- 当前会话摘要

处理方式：宿主注入 + Context Enricher

## 3. 联合增强流程

1. `IndustryAdapterPlugin` 识别行业。
2. `BusinessContextBuilder` 合并宿主身份、页面、对象、行为上下文。
3. `RouteStrategyPlugin` 判断知识、业务、人工、高风险或插件路由。
4. 知识型问题走 `KnowledgeDomainManager + RAG`。
5. 业务型问题走 `Real-time Business Data Provider`。
6. `Response Enhancement Orchestrator` 合并知识引用、动态数据和上下文。
7. `ResponsePostProcessorPlugin` 做格式化、脱敏、多语言和结构化转换。

## 4. 行业增强策略

### 4.1 ecommerce

- 业务实体：订单、商品、会员、优惠券、物流、售后
- 页面上下文：商品详情页、订单详情页、售后页
- 默认工具：`order_status`、`after_sale_status`、`logistics_tracking`

### 4.2 saas

- 业务实体：账号、组织、角色、权限、套餐、订阅、工单
- 页面上下文：控制台、权限页、账单页、工单页
- 默认工具：`account_lookup`、`subscription_lookup`、`ticket_lookup`

### 4.3 education

- 业务实体：课程、班级、学习进度、考试、证书、有效期
- 页面上下文：课程详情、学习页、考试页
- 默认工具：`course_lookup`、`progress_lookup`

### 4.4 logistics

- 业务实体：运单、状态节点、异常、签收、赔付
- 页面上下文：运单追踪页、异常申诉页
- 默认工具：`waybill_lookup`、`claim_lookup`

### 4.5 crm / service

- 业务实体：客户档案、服务记录、工单、服务等级、跟进状态
- 页面上下文：客户档案页、工单页、服务台
- 默认工具：`crm_profile`、`ticket_lookup`

## 5. 设计约束

- 不能把行业逻辑散落在主流程 `if/else` 中。
- 行业规则必须通过行业适配器与插件声明。
- 同一租户可装配多个行业插件，但单次请求只使用一个主行业上下文。
- 实时业务数据不得写入通用知识库代替实时查询。
