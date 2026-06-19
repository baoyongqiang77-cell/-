# U0 基础工程与持久化测试报告

## 验收范围

- 平台方租户与客户租户初始化、持久化用户和 RBAC。
- 客户租户默认功能授权及平台方受控功能授权。
- 有效期、用途、资产类型和样本范围受控的数据授权。
- 请求关联审计、拒绝操作独立审计事务和租户过滤。
- 按租户、方法、路由和键共同限定的持久化幂等。
- Alembic 八张 U0 表、可逆迁移、启动版本校验和应用重启持久化。

## 自动化证据

| 验证项 | 结果 |
| --- | --- |
| SQLAlchemy 元数据仅包含计划内八张 U0 表 | PASS |
| SQLite Alembic 升级、降级、再次升级 | PASS |
| 未迁移数据库被 API 启动校验拒绝 | PASS |
| 初始化脚本重复执行不产生重复租户、角色或授权 | PASS |
| 用户角色从当前租户的持久化关系加载 | PASS |
| 客户租户越权写入和跨租户切换被拒绝并审计 | PASS |
| 功能授权与幂等响应在应用重启后仍然保留 | PASS |
| 幂等键跨路由隔离，请求指纹冲突返回 `IDEMP_409` | PASS |
| 数据授权校验有效期、用途、资产类型和样本范围 | PASS |
| 无效或过期数据授权返回 `DATA_GRANT_412` | PASS |
| 错误响应保留请求级 `request_id` | PASS |
| 拒绝操作回滚业务事务并独立提交审计 | PASS |
| 36 项 U0 持久化与 API 聚焦测试 | PASS |
| 66 项项目全量自动化回归 | PASS |
| Alembic 迁移、显式初始化、Uvicorn 启动及 OpenAPI 探测 | PASS |
| PostgreSQL 16 Alembic 冒烟脚本语法检查 | PASS |
| PostgreSQL 16 实机迁移冒烟 | PASS：云端 Docker 测试环境，2026-06-19 |

## 云端 PostgreSQL 实测证据

- 环境：Ubuntu 24.04.2 LTS、Docker 29.1.3、Docker Compose 2.40.3、PostgreSQL 16 Alpine。
- 网络：数据库端口仅绑定 `127.0.0.1:55432`，未暴露到公网。
- 迁移：`upgrade head -> downgrade base -> upgrade head` 全流程退出码为 0。
- 降级后仅保留 `alembic_version`；再次升级后包含八张 U0 业务表及 `alembic_version`。
- 最终 Alembic revision：`20260618_0001 (head)`；PostgreSQL 容器状态为 `healthy`。
- Docker Hub 在该云网络中解析异常，测试镜像通过可访问镜像代理拉取；此问题不影响迁移结果，但生产镜像源仍需按部署基线锁定。

## 复现命令

```powershell
& '.\.venv\Scripts\python.exe' -m unittest tests.test_u0_persistence tests.test_api_u0_app -v
& '.\.venv\Scripts\python.exe' -m unittest discover -s tests -v
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File '.\scripts\test_postgres_migrations.ps1'
```

## 尚未关闭的边界

- 生产统一身份协议仍待确认。
- 通用数据库 5xx 错误码需要签字基线变更后才能新增。
- PostgreSQL 冒烟成功也不代表政务云生产数据库验收通过。
- 客户租户自助审计查询留待后续 U0 增量。

## 结论

U0 持久化增量已完成 SQLite 自动化、应用重启及 PostgreSQL 16 实机迁移验证，具备继续开发后续 U0 单元的代码基础。该结果属于测试环境兼容性证据，不替代政务云生产数据库验收。
