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
- U1-F04 航线主档、航线版本、版本资产绑定和最小路径几何校验。
- U1-F05 飞行任务创建、`DRAFT` 初始状态、同租户设备/航线/资产校验和媒体策略校验。

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

### U1-F04 航线管理

| 用例 | 结果 |
| --- | --- |
| `routes/route_versions` 迁移 upgrade/downgrade/upgrade | PASS |
| 航线列表、详情、版本列表和版本详情始终按当前服务租户过滤 | PASS |
| 客户租户只能读取本租户航线，跨租户详情统一返回 `TENANT_404` 并审计 | PASS |
| 仅平台管理员可新增、修改航线并创建版本，客户写入返回 `PERM_403` 并审计 | PASS |
| 写请求必须携带 `Idempotency-Key`，幂等范围按目标租户隔离 | PASS |
| 航线版本可绑定同租户道路、桥梁或边坡资产，跨租户资产绑定返回 `TENANT_404` | PASS |
| 非 `LineString` 路径几何返回 `GIS_422`，非法 checksum 和重复版本返回 `MISSION_422` | PASS |
| U1-F04 API 与持久化聚焦测试共 18 项 | PASS |

### U1-F05 任务创建

| 用例 | 结果 |
| --- | --- |
| `missions` 迁移 upgrade/downgrade | PASS |
| 客户租户可在本租户 `FLIGHT_CONTROL` 授权下创建 `DRAFT` 任务 | PASS |
| 任务创建校验同租户航线、航线版本、设备、机巢和巡检资产 | PASS |
| 任务列表和详情始终按当前服务租户过滤，跨租户详情返回 `TENANT_404` 并审计 | PASS |
| 写请求必须携带 `Idempotency-Key`，重复请求重放原结果 | PASS |
| 请求体禁止覆盖 `tenant_id/status` 等服务端管理字段 | PASS |
| 空媒体策略返回 `MISSION_422`，跨租户设备返回 `TENANT_404` | PASS |
| U1-F05 API 与持久化聚焦测试共 13 项 | PASS |

### U1-F06 Mission Approval

| Check | Result |
| --- | --- |
| `mission_approvals` table, tenant-scoped mission FK, fixed approval statuses | PASS |
| Submit approval moves mission `DRAFT -> PENDING_APPROVAL` and writes audit | PASS |
| Built-in approve/reject moves mission `PENDING_APPROVAL -> APPROVED/REJECTED` and writes audit | PASS |
| Cross-tenant approval access returns `TENANT_404` without revealing resource existence | PASS |
| Approval write APIs require `Idempotency-Key` and reject conflicting replays with `IDEMP_409` | PASS |
| U1-F05/F06 API and persistence focused tests total 23 cases | PASS |

U1-F06 only implements built-in approval persistence and manual trace fields for pending OA/airspace integration. It does not call a real OA or airspace system, does not upload routes, does not dispatch to DJI, and does not write `flight_events`.

### U1-F07 Mission Dispatch

| Check | Result |
| --- | --- |
| `mission_dispatch_receipts` table, tenant-scoped mission FK, fixed gateway modes | PASS |
| Dispatch requires `APPROVED` mission status and rejects other states with `STATE_409` | PASS |
| Dispatch builds `DispatchMissionCommand`, calls the DJI gateway adapter, and records receipt | PASS |
| Accepted simulator receipt moves mission `APPROVED -> DISPATCHING -> DISPATCHED` | PASS |
| Gateway `DJI_502` failure rolls back dispatch state and preserves approved mission | PASS |
| Cross-tenant dispatch access returns `TENANT_404` without revealing resource existence | PASS |
| U1-F05/F06/F07 API and persistence focused tests total 33 cases | PASS |

U1-F07 only dispatches through the existing gateway simulator contract. Simulator receipts keep `raw_payload.execution_proof = SIMULATED_ONLY`; this is not real DJI execution proof and does not mean a real aircraft accepted or flew the task.

### U1-F08 Telemetry Events

| Check | Result |
| --- | --- |
| `flight_events` table with tenant-scoped mission FK and normalized gateway payload columns | PASS |
| Simulator/normalized telemetry ingestion requires `FLIGHT_CONTROL` and `Idempotency-Key` | PASS |
| Event payload preserves `schema:flight_event_payload` outer fields: `event_code`, `event_time`, `device_sn`, `raw_payload` | PASS |
| Telemetry list, WebSocket snapshot, and in-process realtime fan-out are scoped to the current service tenant | PASS |
| Persisted simulator telemetry events are broadcast as typed WebSocket `event` messages | PASS |
| Tenants without `FLIGHT_CONTROL` receive WebSocket `FEATURE_403` and are not subscribed | PASS |
| Cross-tenant telemetry access returns `TENANT_404` without revealing resource existence | PASS |
| U1-F05/F06/F07/F08 API and persistence focused tests total 43 cases | PASS |

U1-F08 records simulator or caller-provided normalized telemetry events, exposes a WebSocket snapshot endpoint, and provides an in-process simulator realtime fan-out path. It does not subscribe to real DJI Cloud API topics, does not provide distributed production pub/sub or guaranteed 1-second real device telemetry, does not update mission state from telemetry payloads, and does not implement U1-F09 abnormal event linkage.

### U1-F09 Flight Exceptions

| Check | Result |
| --- | --- |
| `flight_exception_links` table with tenant-scoped mission FK and one exception per source flight event | PASS |
| Fixed abnormal event mapping covers `low_battery`, `device_unresponsive`, `lost_link`, and `timeout` | PASS |
| Link API requires `FLIGHT_CONTROL` and `Idempotency-Key` | PASS |
| Unsupported source events return `MISSION_422` | PASS |
| Cross-tenant exception access returns `TENANT_404` without revealing resource existence | PASS |
| Successful linkage writes `flight_exception_linked` audit records | PASS |

U1-F09 converts selected simulator or normalized `flight_events` into U1 flight-control exception records. It does not create U2 visual-analysis `events`, `event_asset_links`, `review_records`, `feedback_samples`, or `work_orders`; it does not call real DJI Cloud API or prove production abnormal-event topic integration.

### U1-F10 Media Sync

| Check | Result |
| --- | --- |
| `media_files` table with tenant-scoped mission FK and one media record per source flight event | PASS |
| `media_upload_completed` event sync creates `READY` mission media records | PASS |
| Sync API requires `FLIGHT_CONTROL` and `Idempotency-Key` | PASS |
| Bad checksum returns `MEDIA_499` | PASS |
| Unsupported source events return `MISSION_422` | PASS |
| Cross-tenant media access returns `TENANT_404` without revealing resource existence | PASS |
| Successful sync writes `media_file_synced` audit records | PASS |

U1-F10 records simulator or normalized DJI media-upload completion events as U1 mission media records. It does not perform U2 media ingest, chunk upload, breakpoint resume, frame extraction, object storage verification, analysis task creation, alert creation, work-order creation, or production DJI media callback verification.

## 自动化命令

```powershell
& '.\.venv\Scripts\python.exe' -m unittest tests.test_u1_dji_gateway_contract tests.test_u1_flight -v
& '.\.venv\Scripts\python.exe' -m unittest tests.test_api_u1_device_registry tests.test_u1_device_registry_persistence -v
& '.\.venv\Scripts\python.exe' -m unittest tests.test_u1_gis_assets_persistence tests.test_api_u1_gis_assets -v
& '.\.venv\Scripts\python.exe' -m unittest tests.test_u1_route_management_persistence tests.test_api_u1_route_management -v
& '.\.venv\Scripts\python.exe' -m unittest tests.test_u1_mission_creation_persistence tests.test_api_u1_mission_creation -v
& '.\.venv\Scripts\python.exe' -m unittest discover -s tests -v
& '.\.venv\Scripts\python.exe' -m compileall -q src apps/api/app
# 云端：U0_POSTGRES_TEST_PORT=55433 ./scripts/test_postgres_migrations.sh
# 云端：U0_POSTGRES_TEST_PORT=55434 ./scripts/test_postgres_migrations.sh
```

## 未纳入本增量

- DJI Cloud API 版本、凭证、回调签名、配套无人机和载荷型号仍待确认。
- 模拟器仅作为 M1 开发证据，不能满足真实飞行或生产验收。
- 真实 DJI 航线上传、任务、审批和生产连续遥测 WebSocket 属于后续 U1 增量；U1-F08 仅完成模拟/规范化 `flight_events` 持久化与快照读取。
- U1-F04 仅保存航线版本文件 URI、checksum、路径几何和资产绑定，不执行真实 DJI 航线格式转换、上传、飞行安全校验或设备侧回执确认。
- U1-F05 仅创建 `DRAFT` 任务，不提交审批、不调用 OA/空域系统、不下发 DJI、不写 `flight_events`、不声明天气/空域真实校验已完成。
- U1-F06 仅实现内置审批流和人工/外部审批追踪字段，不调用真实 OA/空域系统、不下发 DJI、不写 `flight_events`、不声明生产审批联调完成。
- U1-F07 仅通过现有 DJI 网关模拟器记录下发回执，不直连 DJI Cloud API、不证明真实设备接收或执行、不写 `flight_events`、不声明真实飞行能力完成。
- U1-F08 仅接收模拟器或调用方提供的规范化遥测事件，并通过进程内 hub 完成模拟实时推送闭环；不直连 DJI Cloud API、不订阅真实设备遥测主题、不声明 1 秒级连续生产遥测完成。
- U1-F09 仅把模拟/规范化飞控异常事件联动为 U1 异常记录，不生成 U2 视觉分析告警、工单或真实 DJI 异常生产接入证明。
- 真实 GIS 数据来源、权威坐标系、更新频率、桩号映射、客户 GIS REST/数据库视图对接和离线 GeoJSON 批量导入仍待确认。
- U1-F03 仅保存 `geom_json` 和 CRS 元数据，不执行真实 PostGIS 空间计算、自动坐标转换、最近资产匹配或 L2/L3 精确定位。
- 云端 PostgreSQL 迁移实测已完成；远端通过本机确认的 ED25519 SSH 主机指纹后接入，Docker Hub 直连不可达时使用国内镜像源预拉取同一 `postgres:16-alpine` 镜像。

## 验收结论

U1-F01 网关契约、开发模拟器和状态机规则级验收通过；U1-F02 设备与机巢台账、U1-F03 GIS 最小资产台账、U1-F04 航线管理、U1-F05 任务创建、U1-F06 内置任务审批、U1-F07 模拟网关任务下发、U1-F08 模拟/规范化遥测事件入库、快照读取与进程内实时推送闭环、U1-F09 飞控异常事件联动的本地自动化验收通过，U1-F02/U1-F03 云端 PostgreSQL 迁移 `upgrade/downgrade/upgrade` 实测通过。当前结果不代表真实 DJI 设备、DJI Cloud API、配套无人机/载荷型号、真实 OA/空域审批、真实航线上传、真实飞行、生产网络、生产连续遥测、真实 DJI 异常主题、真实 GIS 数据源或精确空间定位验收通过。
