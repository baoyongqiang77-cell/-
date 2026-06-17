# U0 基础工程与权限审计测试文档

## 验收范围

- 平台方租户 `PLATFORM_OPERATOR` 与客户租户 `CUSTOMER_TENANT` 初始化。
- 客户租户默认功能授权：飞控、视觉分析结果、数据标注开放；训练、发布、平台运维默认关闭。
- `FEATURE_403`、`DATA_GRANT_412`、`IDEMP_409` 统一错误码。
- 审计日志、幂等键、对象存储租户路径。

## 自动化用例

| 用例 | 结果 |
| --- | --- |
| 客户租户仅具备默认客户功能 | PASS |
| 客户访问未授权训练返回 `FEATURE_403` 并写审计 | PASS |
| 客户数据进入平台方训练前必须有 `tenant_data_grants` | PASS |
| 相同 `Idempotency-Key` 重放原结果，不一致请求返回 `IDEMP_409` | PASS |
| 对象存储路径包含 `tenant_id/project_id/mission_id` | PASS |

## 验收结论

U0 规则级自动化验收通过。当前实现为本地验收骨架，不包含生产统一身份、数据库迁移和真实 OpenAPI 服务，这些仍需在正式应用工程中补齐。
