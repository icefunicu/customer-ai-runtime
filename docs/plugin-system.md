# 插件系统设计

## 1. 设计目标

插件系统不是形式化空壳，而是平台主流程的一部分。以下扩展点必须可注册、可启停、可替换：

- 路由策略
- 业务工具
- 人工协同策略
- 行业适配
- 鉴权桥接
- 上下文增强
- 回复后处理

## 2. 核心抽象

```python
class Plugin(ABC):
    descriptor: PluginDescriptor
    async def startup(self) -> None: ...
    async def shutdown(self) -> None: ...

class PluginRegistry:
    def register(self, plugin: Plugin) -> None: ...
    def unregister(self, plugin_id: str) -> None: ...
    def enable(self, plugin_id: str) -> None: ...
    def disable(self, plugin_id: str) -> None: ...
    def resolve(self, kind: PluginKind, tenant_id: str, industry: str | None) -> list[Plugin]: ...
```

## 3. 扩展点

### 3.1 RouteStrategyPlugin

- 请求分类
- 行业识别提示
- 工具调用决策
- 转人工决策
- 风险处理

### 3.2 BusinessToolPlugin

- 订单、商品、会员、物流、工单、课程、自定义查询

### 3.3 HumanHandoffPlugin

- 转人工条件
- 会话摘要
- 推荐回复
- 升级策略

### 3.4 IndustryAdapterPlugin

- ecommerce / saas / education / logistics / crm / custom

### 3.5 AuthBridgePlugin

- API Key / Session / JWT / SSO / Custom Host Auth

### 3.6 ContextEnricherPlugin

- 页面上下文
- 宿主对象上下文
- 用户画像
- 历史行为

### 3.7 ResponsePostProcessorPlugin

- 格式化
- 审查
- 脱敏
- 多语言
- 风格增强
- 结构化输出

## 4. 元数据与装配

插件元数据至少包含：

- `plugin_id`
- `name`
- `version`
- `kind`
- `priority`
- `enabled`
- `tenant_scopes`
- `industry_scopes`
- `channel_scopes`
- `capabilities`

## 5. 生命周期

1. register
2. startup
3. resolve
4. execute
5. disable / enable
6. shutdown
7. unregister

当前仓库已支持：

- FastAPI 生命周期内自动 `startup / shutdown`
- 插件启停状态持久化到运行时配置
- 服务重启后恢复启用 / 禁用状态

## 6. 执行原则

- 同类插件按 `priority` 从高到低执行。
- 租户与行业不匹配的插件不参与执行。
- 任意插件失败时必须记录诊断并回退，不允许拖垮主流程。

## 7. 多租户 / 多行业装配

- 平台保留全局默认插件。
- 租户可在默认插件之上覆盖启停与优先级。
- 行业插件只对匹配行业生效。

## 8. 管理接口

目标支持：

- 查询插件列表
- 查询插件能力
- 启用插件
- 禁用插件
- 查看装配结果

## 9. 当前事实与 Target State

### 当前事实

- 当前仓库已具备完整平台插件框架，已接入路由、业务工具、人工协同、行业适配、鉴权桥接、上下文增强和回复后处理。

### Target State

- 在现有插件框架上继续扩展更细粒度的租户装配、灰度发布与远程插件分发能力。
