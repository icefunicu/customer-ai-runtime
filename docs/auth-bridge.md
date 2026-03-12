# 宿主桥接与鉴权设计

## 1. 目标

平台必须支持宿主系统挂载模式，并允许宿主复用自己的登录态、身份体系和权限体系，不强制统一成 `X-API-Key`。

## 2. 认证边界

必须明确区分四层：

1. 平台访问认证
2. 宿主用户身份认证
3. 宿主业务权限校验
4. 客服内部会话身份上下文

## 3. Host Auth Context

统一模型建议包含：

- `tenant_id`
- `principal_id`
- `principal_type`
- `roles`
- `permissions`
- `source_system`
- `auth_mode`
- `session_claims`
- `business_scope`
- `extra_context`

## 4. Auth Bridge 抽象

```python
class AuthBridgePlugin(Plugin):
    async def can_handle(self, request_data: AuthRequestContext) -> bool: ...
    async def authenticate(self, request_data: AuthRequestContext) -> HostAuthContext: ...
```

## 5. 支持模式

### 5.1 API Key 模式

- Header: `X-API-Key`
- 适用于独立 API 模式

### 5.2 Session / Cookie 模式

- 读取宿主 Cookie，如 `host_session`
- 通过宿主会话映射或自定义桥接器解析身份

### 5.3 JWT / Bearer 模式

- Header: `Authorization: Bearer <jwt>`
- 通过平台内置 JWT Bridge 或宿主自定义桥接器校验并映射

### 5.4 Custom Token 模式

- Header: `X-Host-Token`
- 适用于宿主内部签名票据或网关透传票据

### 5.5 Custom Bridge 模式

- 宿主可注册任意 `AuthBridgePlugin`
- 例如：SSO 票据换票、内部鉴权接口 introspection、双向签名校验

## 6. 认证顺序

1. 若携带 `X-API-Key`，优先走 API Key。
2. 否则按已启用 `AuthBridgePlugin` 优先级依次尝试。
3. 首个成功桥接器产出统一 `HostAuthContext`。
4. `HostAuthContext` 再映射为内部 `AuthContext`。

## 7. 挂载模式如何接入

### 7.1 子应用挂载

- 宿主系统挂载 `/customer-ai`
- 宿主保留自己的登录态 Cookie 或 Bearer Token
- 客服平台通过 `AuthBridge` 读取并映射

### 7.2 进程内 facade

- 宿主直接调用 Python facade
- 直接传入 `integration_context` 与显式 `host_auth_context`

### 7.3 SDK / iframe / Web Component

- 前端保留宿主登录态
- 网关层透传 Cookie / Token
- 平台在后端完成桥接

## 8. 宿主如何注册桥接器

推荐方式：

1. 在模块初始化时调用插件注册接口。
2. 提供 `plugin_id`、优先级、支持渠道与解析逻辑。
3. 将宿主票据映射为统一 `HostAuthContext`。

当前仓库已支持：

- `CustomerAIRuntimeModule.register_plugin(plugin)`
- 在挂载前注入自定义 `AuthBridgePlugin`
- 示例见 `examples/host_custom_auth_bridge.py`

## 9. 错误处理与安全策略

- 未携带有效凭证：`401 auth_error`
- 宿主票据无法解析：`401 host_auth_error`
- 宿主身份与请求租户不匹配：`403 forbidden`
- 宿主权限不足：`403 forbidden`
- 日志中不得输出完整票据、Cookie、JWT 原文

## 10. 当前事实与 Target State

### 当前事实

- 当前仓库已支持 API Key、Session / Cookie、JWT / Bearer、Custom Token 四种桥接模式。
- 宿主挂载支持 HTTP/子应用/进程内接入，并可通过插件注册自定义桥接器。

### Target State

- API 模式与挂载模式共用同一 `AuthService`。
- 后续可继续扩展 SSO / introspection / 企业网关换票等自定义桥接模式。
