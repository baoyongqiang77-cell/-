# U1 飞控平台功能测试文档

## 验收范围

- U1-F01 `DjiGateway` 统一业务协议与大疆机场 3 适配层模拟器。
- 设备绑定、状态同步、任务下发、遥测、异常和媒体同步六项能力。
- 模拟设备动作回执、请求幂等和确定性故障注入。
- `schema:flight_event_payload` 回调字段规范。
- 飞行任务状态机与非法跳转拒绝。
- 仅大疆机场 3 适配网关允许访问互联网的网络边界规则。
- U1-F02 大疆机场 3、无人机、载荷、边缘节点与机巢持久化台账。
- 设备与机巢的租户隔离查询、平台管理员写入、幂等和审计。
- 归一化 `ONLINE/OFFLINE` 状态同步与机巢环境快照白名单。
- U1-F03 道路、桥梁、边坡和坐标转换配置的 GIS 最小资产台账。
- GIS 资产的租户隔离查询、平台管理员写入、幂等、审计和 `GIS_422` 校验边界。

## 自动化用例

| 用例 | 结果 |
| --- | --- |
| 模拟器满足 `DjiGateway` 协议且模式固定为 `SIMULATOR` | PASS |
| 命令、回执和事件使用不可变契约对象 | PASS |
| 设备绑定与任务下发返回已接受回执，并明确标记 `SIMULATED_ONLY` | PASS |
| 相同幂等请求重放原回执，不同指纹返回 `IDEMP_409` | PASS |
| 绑定、遥测、低电量、媒体上传完成均转换为统一 payload | PASS |
| 回调外层严格限定为 `event_code/event_time/device_sn/raw_payload`，且 `event_time` 必须包含时区 | PASS |
| 模拟器覆盖凭证错误、设备已绑定、格式错误、超时、设备无响应、checksum 错误 | PASS |
| 六类故障复用 `DJI_502`/`MEDIA_499`，可重试属性固定且详情不泄露凭证 | PASS |
| 飞行任务按文档状态合法流转，非法跳转返回 `STATE_409` | PASS |
| 设备拒绝回执仅通过状态机从 `DISPATCHING` 进入 `DISPATCH_FAILED` | PASS |
| 仅 `dji_gateway` 可访问互联网，业务服务被阻断 | PASS |
| U1-F01 与现有飞控规则共 19 项聚焦测试 | PASS |

### U1-F02 设备与机巢台账

| 用例 | 结果 |
| --- | --- |
| 设备与机巢列表、详情始终按当前服务租户过滤 | PASS |
| 客户租户只能读取本租户台账，跨租户详情统一返回 `TENANT_404` 并审计 | PASS |
| 仅平台管理员可新增、修改设备与机巢，拒绝操作写独立事务审计 | PASS |
| 写请求必须携带 `Idempotency-Key`，幂等范围按目标租户隔离 | PASS |
| 请求体禁止覆盖 `tenant_id`、`status` 等服务端管理字段 | PASS |
| 设备序列号全局唯一，同一机巢设备不可重复建档 | PASS |
| 机巢、绑定无人机和边缘节点由数据库组合外键约束为同租户 | PASS |
| `device_bound` 不设置在线状态，只有规范 `device_status` 更新 `ONLINE/OFFLINE` | PASS |
| `ONLINE` 更新时间，`OFFLINE` 保留最后在线时间，非法状态返回 `DJI_502` | PASS |
| 机巢环境快照只持久化 `dock_door/charging/weather/payload_status` | PASS |
| U1-F02 API 与持久化聚焦测试共 39 项 | PASS |
| 全项目自动化测试共 120 项 | PASS |
| Python 源码编译与 `git diff --check` | PASS |
| Linux PostgreSQL 迁移脚本静态语法校验 | PASS |
| 云端 PostgreSQL `upgrade/downgrade/upgrade` 实测 | PASS：2026-06-26 在 `8.163.127.126:/opt/drone-u1-f02-migration-test` 通过，测试端口 `55433` |

### U1-F03 GIS 最小资产台账

| 用例 | 结果 |
| --- | --- |
| `road_assets/bridge_assets/slope_assets/coordinate_transforms` 迁移 upgrade/downgrade/upgrade | PASS |
| 道路、桥梁、边坡和坐标转换配置列表、详情始终按当前服务租户过滤 | PASS |
| 客户租户只能读取本租户 GIS 资产，跨租户详情统一返回 `TENANT_404` 并审计 | PASS |
| 仅平台管理员可新增、修改 GIS 资产，客户写入返回 `PERM_403` 并审计 | PASS |
| 写请求必须携带 `Idempotency-Key`，幂等范围按目标租户隔离 | PASS |
| 请求体禁止覆盖 `tenant_id/created_at/updated_at` 等服务端管理字段 | PASS |
| 非法几何类型、坐标系和桩号范围返回 `GIS_422` | PASS |
| 重复道路范围、桥梁编码、边坡编码或坐标转换版本返回 `MISSION_422` | PASS |
| U1-F03 API 与持久化聚焦测试共 37 项 | PASS |
| 全项目自动化测试共 157 项 | PASS |
| Python 源码编译与 `git diff --check` | PASS |
| Linux PostgreSQL 迁移脚本静态语法校验 | PASS |
| 云端 PostgreSQL `upgrade/downgrade/upgrade` 实测 | PASS：2026-06-27 在 `8.163.127.126:/opt/drone-u1-f03-gis-assets-migration-test` 通过，测试端口 `55434` |

## 自动化命令

```powershell
& '.\.venv\Scripts\python.exe' -m unittest tests.test_u1_dji_gateway_contract tests.test_u1_flight -v
& '.\.venv\Scripts\python.exe' -m unittest tests.test_api_u1_device_registry tests.test_u1_device_registry_persistence -v
& '.\.venv\Scripts\python.exe' -m unittest tests.test_u1_gis_assets_persistence tests.test_api_u1_gis_assets -v
& '.\.venv\Scripts\python.exe' -m unittest discover -s tests -v
& '.\.venv\Scripts\python.exe' -m compileall -q src apps/api/app
# 云端：U0_POSTGRES_TEST_PORT=55433 ./scripts/test_postgres_migrations.sh
# 云端：U0_POSTGRES_TEST_PORT=55434 ./scripts/test_postgres_migrations.sh
```

## 未纳入本增量

- DJI Cloud API 版本、凭证、回调签名、配套无人机和载荷型号仍待确认。
- 模拟器仅作为 M1 开发证据，不能满足真实飞行或生产验收。
- 航线、任务、审批、遥测 WebSocket 和 `flight_events` 持久化属于后续 U1 增量。
- 真实 GIS 数据来源、权威坐标系、更新频率、桩号映射、客户 GIS REST/数据库视图对接和离线 GeoJSON 批量导入仍待确认。
- U1-F03 仅保存 `geom_json` 和 CRS 元数据，不执行真实 PostGIS 空间计算、自动坐标转换、最近资产匹配或 L2/L3 精确定位。
- 云端 PostgreSQL 迁移实测已完成；远端通过本机确认的 ED25519 SSH 主机指纹后接入，Docker Hub 直连不可达时使用国内镜像源预拉取同一 `postgres:16-alpine` 镜像。

## 验收结论

U1-F01 网关契约、开发模拟器和状态机规则级验收通过；U1-F02 设备与机巢台账、U1-F03 GIS 最小资产台账的本地自动化验收和云端 PostgreSQL 迁移 `upgrade/downgrade/upgrade` 实测均通过。当前结果不代表真实 DJI 设备、DJI Cloud API、配套无人机/载荷型号、真实飞行、生产网络、真实 GIS 数据源或精确空间定位验收通过。
