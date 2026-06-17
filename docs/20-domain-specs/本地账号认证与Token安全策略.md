# 本地账号认证与 Token 安全策略

## 1. 结论

一期正式开发先采用：

```text
本地账号 + JWT Access Token + Refresh Token
```

后续预留：

```text
LDAP / CAS / OAuth2 / OIDC 统一身份适配器
```

核心原则：

- Access Token 短有效期。
- Refresh Token 服务端存储、可吊销、可轮换。
- 密码不可明文存储。
- 高权限角色更严格。
- 登录、失败、锁定、改密、Token 异常均写审计。

## 2. 认证方案

| 项目 | 建议 |
| --- | --- |
| 登录方式 | 本地账号密码 |
| Access Token | JWT，短有效期 |
| Refresh Token | 服务端存储，可吊销、可轮换 |
| Token 传输 | `Authorization: Bearer <token>` |
| 密码存储 | Argon2id 优先，bcrypt 可接受，禁止明文 |
| 会话吊销 | 服务端维护 refresh token 状态 |
| 生产统一身份 | 预留 LDAP/CAS/OAuth2/OIDC 适配器 |

## 3. Token 有效期

| Token / 场景 | 建议有效期 | 说明 |
| --- | --- | --- |
| 普通 Access Token | 30 分钟 | 降低泄露后的可用窗口，适合后台系统 |
| 高权限角色 Access Token | 15 分钟 | 平台管理员、平台运维员、算法工程师等风险更高 |
| Refresh Token | 7 天 | 兼顾安全和使用便利 |
| 演示环境 Refresh Token | 14 天 | 减少客户演示期间频繁登录 |
| 长时间无人操作 | 30 分钟自动过期 | 后台系统安全基线 |

高权限角色包括但不限于：

- 平台管理员。
- 平台运维员。
- 算法工程师。
- 具备模型发布能力的用户。
- 具备跨租户运维能力的用户。
- 具备数据集导出能力的用户。

## 4. 登录响应结构

登录成功后返回：

```json
{
  "access_token": "eyJ...",
  "refresh_token": "rt_...",
  "expires_in": 1800,
  "token_type": "Bearer"
}
```

说明：

- `expires_in` 单位为秒。
- `token_type` 固定为 `Bearer`。
- Access Token 中必须包含用户 ID、当前租户 ID、角色摘要、权限版本号、签发时间和过期时间。
- Access Token 不应包含密码、密钥、完整权限清单、敏感个人信息。

## 5. Refresh Token 刷新机制

### 5.1 基本流程

1. 用户登录成功后，服务端生成 Access Token 与 Refresh Token。
2. 服务端只保存 Refresh Token 哈希，不保存明文。
3. 前端在 Access Token 过期前 2 分钟发起刷新。
4. 刷新成功后，服务端签发新的 Access Token 和新的 Refresh Token。
5. 旧 Refresh Token 立即失效。

### 5.2 轮换机制

Refresh Token 必须采用轮换机制：

- 每次刷新都会生成新 Refresh Token。
- 旧 Refresh Token 立即标记为 `ROTATED` 或 `REVOKED`。
- 若旧 Refresh Token 再次出现，判定为疑似泄露。
- 疑似泄露时吊销该用户当前设备会话，并写安全审计。

### 5.3 服务端存储字段

建议 `refresh_tokens` 表包含：

| 字段 | 说明 |
| --- | --- |
| id | Token ID |
| user_id | 用户 ID |
| tenant_id | 当前租户 ID |
| token_hash | Refresh Token 哈希 |
| status | ACTIVE / ROTATED / REVOKED / EXPIRED |
| issued_at | 签发时间 |
| expires_at | 过期时间 |
| last_used_at | 最后使用时间 |
| rotated_from_id | 来源 Token ID |
| user_agent | 客户端信息 |
| ip_address | 登录 IP |
| device_fingerprint | 设备指纹，可选 |

## 6. 吊销规则

以下场景必须吊销相关 Refresh Token：

| 场景 | 处理 |
| --- | --- |
| 用户主动登出 | 吊销当前 refresh token |
| 修改密码 | 吊销该用户全部 refresh token |
| 管理员重置密码 | 吊销该用户全部 refresh token |
| 用户被禁用 | 吊销该用户全部 refresh token |
| 角色被回收 | 吊销相关租户会话或提升权限版本号 |
| 功能授权被回收 | 吊销相关租户会话或提升权限版本号 |
| Refresh Token 重放 | 吊销当前设备会话，记录疑似泄露 |
| 账号异常锁定 | 吊销当前活跃会话 |

权限版本号建议：

- 用户、角色、功能授权、租户范围发生变化时，递增 `permission_version`。
- Access Token 中包含签发时的 `permission_version`。
- 请求进入时校验 Token 中版本与服务端版本是否一致。
- 不一致时要求重新登录或刷新授权上下文。

## 7. 密码策略

| 项目 | 策略 |
| --- | --- |
| 最小长度 | 12 位 |
| 复杂度 | 至少包含大写、小写、数字、特殊字符中的 3 类 |
| 默认密码 | 首次登录必须修改 |
| 密码历史 | 最近 5 次不可重复 |
| 密码有效期 | 90 天，可按客户安全要求调整 |
| 登录失败锁定 | 5 次失败锁定 15 分钟 |
| 弱密码字典 | 禁止常见弱密码、账号名、手机号、单位名 |
| 管理员重置密码 | 生成临时密码，首次登录强制修改 |
| 存储方式 | Argon2id 优先，bcrypt 可接受 |
| 审计 | 登录成功、失败、锁定、改密、重置均写审计 |

## 8. 密码存储

禁止：

- 明文存储密码。
- 可逆加密存储密码。
- 使用 MD5、SHA1、无盐 SHA256 等普通摘要算法直接存储密码。

建议：

- 优先使用 Argon2id。
- 若部署环境暂不支持 Argon2id，可使用 bcrypt。
- 每个密码必须有独立 salt。
- 哈希参数应可配置，方便后续提高强度。

参考：

- OWASP Password Storage Cheat Sheet：https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html

## 9. 审计要求

以下认证相关操作必须写 `audit_logs`：

| 操作 | 审计内容 |
| --- | --- |
| 登录成功 | user_id、tenant_id、IP、user_agent、时间 |
| 登录失败 | username、IP、失败原因、时间 |
| 账号锁定 | username、IP、锁定原因、解锁时间 |
| 登出 | user_id、tenant_id、token_id、时间 |
| Token 刷新 | user_id、tenant_id、token_id、IP、时间 |
| Refresh Token 重放 | user_id、tenant_id、token_id、IP、风险等级 |
| 修改密码 | user_id、操作者、时间 |
| 管理员重置密码 | target_user_id、operator_id、时间 |
| 用户禁用 | target_user_id、operator_id、原因 |
| 角色回收 | target_user_id、role_id、tenant_id、operator_id |

审计日志不得记录：

- 明文密码。
- 明文 Refresh Token。
- Access Token 完整内容。
- 密钥或签名材料。

## 10. 前端存储建议

演示和正式开发阶段建议：

- Access Token 可存于内存状态。
- Refresh Token 优先使用 `HttpOnly`、`Secure`、`SameSite` Cookie。
- 如暂时采用 localStorage，必须标注为开发/演示过渡方案，不作为最终生产策略。

生产环境建议：

- HTTPS 强制开启。
- Cookie 设置 `HttpOnly`、`Secure`、`SameSite=Lax` 或按实际跨域策略调整。
- 前端主动监听 401 并触发刷新或重新登录。

## 11. 高风险操作二次确认

以下操作建议二次确认或重新验证密码 / MFA 预留：

- 跨租户切换。
- 功能授权变更。
- 数据授权变更。
- 数据集导出。
- 模型发布。
- 模型回滚。
- 用户禁用。
- 管理员重置密码。

一期可先实现二次确认和审计，MFA 作为统一身份或后续安全增强项预留。

## 12. 与统一身份的关系

本地账号是一期可开发、可演示、可验收的基础认证方式。生产环境如客户要求统一身份，应通过适配器接入：

- LDAP。
- CAS。
- OAuth2。
- OIDC。

无论接入哪种统一身份，系统内部仍需保留：

- 租户上下文。
- 角色映射。
- `user_tenant_roles`。
- `tenant_feature_entitlements`。
- `tenant_data_grants`。
- 审计日志。

统一身份只解决“用户是谁”，不替代本系统内部租户、权限、功能授权和数据授权。

## 13. 依据

本策略依据：

1. 项目是多租户系统，平台方具备受控跨租户运维能力。
2. 客户租户数据隔离要求高。
3. 训练、模型发布、数据集导出、跨租户统计属于高风险能力。
4. 项目规约要求写操作、审批、发布、删除、越权、跨租户切换写审计。
5. 前后端分离架构需要标准 Bearer Token 认证。
6. 权限变更需要能及时失效旧会话，因此 Refresh Token 必须服务端可控。
7. OWASP 建议使用 Argon2id、bcrypt 等专用密码哈希算法，禁止明文或普通摘要存储密码。

## 14. 正式开发执行原则

后续 U0 认证开发遵循：

1. 先实现本地账号登录。
2. Access Token 默认 30 分钟，高权限角色 15 分钟。
3. Refresh Token 默认 7 天，演示环境可配置为 14 天。
4. Refresh Token 服务端哈希存储，支持轮换与吊销。
5. 用户禁用、改密、角色回收、功能授权回收时必须使相关会话失效。
6. 密码哈希使用 Argon2id 或 bcrypt。
7. 登录失败锁定、弱密码拦截、首次登录改密必须实现。
8. 所有认证相关安全事件写审计。
9. 预留统一身份适配器，但不阻塞本地账号阶段开发。
