# U0 基础工程与权限审计测试文档

## 验收范围

- 平台方租户 `PLATFORM_OPERATOR` 与客户租户 `CUSTOMER_TENANT` 初始化。
- 客户租户默认功能授权：飞控、视觉分析结果、数据标注开放；训练、发布、平台运维默认关闭。
- `FEATURE_403`、`DATA_GRANT_412`、`IDEMP_409` 统一错误码。
- 审计日志、幂等键、对象存储租户路径。
- FastAPI U0 API 骨架：`/api/v1/me`、`/api/v1/tenant-context`、平台方 admin 写接口、OpenAPI 暴露。

## 自动化用例

| 用例 | 结果 |
| --- | --- |
| 客户租户仅具备默认客户功能 | PASS |
| 客户访问未授权训练返回 `FEATURE_403` 并写审计 | PASS |
| 客户数据进入平台方训练前必须有 `tenant_data_grants` | PASS |
| 相同 `Idempotency-Key` 重放原结果，不一致请求返回 `IDEMP_409` | PASS |
| 对象存储路径包含 `tenant_id/project_id/mission_id` | PASS |
| `/api/v1/me` 未认证返回统一 `AUTH_401` 错误响应 | PASS |
| `/api/v1/tenant-context` 返回当前租户类型、功能授权和可切换租户 | PASS |
| 客户租户伪造 `X-Tenant-Id` 跨租户切换返回 `TENANT_403` | PASS |
| 平台方可通过 admin API 配置客户租户功能授权 | PASS |
| 平台方可通过 admin API 登记客户数据训练/评估授权 | PASS |
| 客户租户访问 admin 写接口返回 `PERM_403` | PASS |
| 无效租户写请求返回 `TENANT_404` 且不污染幂等记录 | PASS |
| 数据授权登记要求授权方和被授权方租户均存在 | PASS |
| OpenAPI 暴露 U0 当前入口 | PASS |

## 自动化命令

```powershell
& 'C:\Users\baoyongqiang\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m unittest discover -s tests -v
```

## 验收结论

U0 规则级自动化验收通过，并已开始落地正式 FastAPI API 骨架。当前实现仍使用演示 Token 与内存态领域对象，不包含生产统一身份、数据库迁移、持久化审计日志和真实部署配置；这些仍需在后续 U0 增量中补齐。
