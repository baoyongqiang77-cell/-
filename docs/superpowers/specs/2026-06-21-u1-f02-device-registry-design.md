# U1-F02 设备与机巢台账设计

## 1. 目标

U1-F02 为大疆机场 3、无人机、载荷和边缘节点提供持久化台账、租户隔离的查询 API、平台方管理 API、幂等写入和审计证据。该单元承接 U1-F01 的 DJI 网关契约，为后续航线、任务、遥测和媒体同步提供可引用的设备主数据。

## 2. 基线映射

- 开发单元：U1-F02 设备/机巢台账。
- 功能基线：管理大疆机场 3、无人机、载荷、边缘节点、固件和在线状态。
- 验收基线：设备必须归属 `tenant_id`，客户租户只能查看本租户设备。
- 功能授权：所有读操作要求 `FLIGHT_CONTROL`。
- 网络边界：本单元不访问互联网或 DJI Cloud API；真实 DJI 交互仍只允许经过 U1-F01 网关。

## 3. 范围

### 3.1 本单元包含

- `devices` 和 `docks` SQLAlchemy 模型及 Alembic 迁移。
- 设备与机巢 Repository 和领域服务。
- 租户隔离的设备、机巢列表与详情 REST API。
- 仅平台方可用的创建、修改 REST API。
- 写接口幂等、统一错误响应和审计日志。
- DJI 标准状态事件更新在线状态、最后在线时间和机巢环境数据的内部服务入口。
- SQLite 自动化测试、PostgreSQL 迁移兼容验证入口和 U1 测试报告。

### 3.2 本单元不包含

- 真实 DJI Cloud API、真实设备绑定或设备控制。
- 自研底层飞控、安全返航算法或无人机固件。
- GIS 资产、航线、任务、审批、WebSocket 遥测和媒体同步业务。
- 设备物理删除、生命周期状态机和客户租户设备写权限。
- 配套无人机和载荷真实型号验收。型号未锁定时仅保存平台登记值，不作为生产兼容结论。

## 4. 架构

采用“通用设备表 + 机巢扩展表”结构：

- `devices` 保存所有设备共有的身份、归属、型号、固件和在线信息。
- `docks` 通过 `device_id` 一对一扩展机巢信息，并关联同租户的无人机和边缘节点。
- Repository 只处理持久化与租户过滤。
- `DeviceRegistryService` 负责权限之外的业务校验、幂等执行和审计协调。
- FastAPI 路由复用 U0 的认证、租户上下文、功能授权、错误响应和审计模式。
- `DeviceStatusService.apply_event(event, request_meta)` 接收 U1-F01 标准 `FlightEvent` 和网关请求上下文，不调用 DJI 接口。

## 5. 数据模型

### 5.1 `devices`

| 字段 | 类型 | 约束 |
| --- | --- | --- |
| `id` | string | 主键，由服务端生成 |
| `tenant_id` | string | 非空，外键到 `tenants.id`，建立索引 |
| `device_type` | string | 非空，仅 `DOCK`、`DRONE`、`PAYLOAD`、`EDGE_NODE` |
| `name` | string | 非空，租户内用于展示 |
| `manufacturer` | string | 非空；大疆设备使用 `DJI` |
| `model` | string/null | 允许为空；真实无人机/载荷型号未锁定 |
| `serial_number` | string | 非空，全局唯一 |
| `firmware_version` | string/null | 允许为空 |
| `status` | string/null | 仅 `ONLINE`、`OFFLINE`；登记后尚未同步时为 `null` |
| `last_seen_at` | datetime/null | 必须为带时区时间 |
| `created_at` | datetime | 非空，UTC |
| `updated_at` | datetime | 非空，UTC |

`device_type` 是 U1-F02 已登记的设备分类，不是生命周期状态。`status` 仅规范化正式源架构已经登记的 `online/offline` 状态，不扩展其他设备状态；`null` 表示尚无设备状态同步证据。

为支持数据库级租户完整性，`devices` 额外建立 `(tenant_id, id)` 唯一约束，供 `docks` 的复合外键引用。

### 5.2 `docks`

| 字段 | 类型 | 约束 |
| --- | --- | --- |
| `id` | string | 主键，由服务端生成 |
| `tenant_id` | string | 非空，外键到 `tenants.id`，建立索引 |
| `device_id` | string | 非空、唯一，必须指向同租户 `DOCK` 设备 |
| `bound_drone_device_id` | string/null | 必须指向同租户 `DRONE` 设备 |
| `edge_node_device_id` | string/null | 必须指向同租户 `EDGE_NODE` 设备 |
| `environment_json` | JSON | 非空，默认空对象，仅保存标准化机巢环境快照 |
| `created_at` | datetime | 非空，UTC |
| `updated_at` | datetime | 非空，UTC |

`docks` 对 `device_id`、`bound_drone_device_id` 和 `edge_node_device_id` 分别使用 `(tenant_id, *_device_id)` 到 `devices(tenant_id, id)` 的复合外键。数据库层强制同租户引用，领域服务再校验设备类型，避免任何写入路径绕过租户边界。

## 6. API 设计

### 6.1 读取接口

- `GET /api/v1/devices`
- `GET /api/v1/devices/{device_id}`
- `GET /api/v1/docks`
- `GET /api/v1/docks/{dock_id}`

读取接口要求 `FLIGHT_CONTROL`。客户租户固定使用令牌中的租户；平台方只有通过受控 `X-Tenant-Id` 才能查询目标客户租户。列表始终按服务租户过滤，不接受请求参数覆盖 `tenant_id`。

### 6.2 管理接口

- `POST /api/v1/admin/devices`
- `PATCH /api/v1/admin/devices/{device_id}`
- `POST /api/v1/admin/docks`
- `PATCH /api/v1/admin/docks/{dock_id}`

管理接口只允许平台方角色调用，并要求 `Idempotency-Key`。请求体不得包含 `tenant_id`；目标租户来自当前受控租户上下文。客户账号调用返回 `PERM_403`。

设备管理 API 可修改名称、厂商、型号和固件版本，不允许直接修改 `status` 或 `last_seen_at`。机巢管理 API 可修改同租户的绑定无人机和边缘节点，不允许直接写入遥测产生的环境快照。

本单元不提供删除接口。后续业务对象引用设备后仍能保留主数据和审计链路。

## 7. 数据流

### 7.1 平台登记

1. 平台方账号选择或受控切换到目标租户。
2. API 校验平台角色、`FLIGHT_CONTROL` 和 `Idempotency-Key`。
3. 服务校验设备分类、序列号和关联设备租户。
4. Repository 在事务中写入台账与审计日志。
5. 幂等作用域固定为“目标租户 + HTTP 方法 + 稳定路由标识 + `Idempotency-Key`”。请求指纹包含目标资源 ID 和规范化请求体；相同指纹返回原响应，不同指纹返回 `IDEMP_409`。

### 7.2 状态同步

1. U1-F01 网关产生标准 `FlightEvent`，网关入口同时向状态服务传入 `RequestMeta`。
2. `DeviceStatusService` 根据 `device_sn` 在台账中定位设备，内部审计操作者固定为 `dji_gateway`，请求 ID 使用网关入口生成或继承的 `RequestMeta.request_id`。
3. `device_bound` 只证明绑定成功，不改变设备在线状态。
4. 只有 `event_code=device_status` 且 `raw_payload.status` 为 `ONLINE` 或 `OFFLINE` 时才更新 `devices.status`；`ONLINE` 同时更新 `last_seen_at`，`OFFLINE` 保留最后一次在线时间。
5. 同一 `device_status` 事件中的标准化机巢环境字段写入 `docks.environment_json`，原始回调仍由后续 `flight_events` 能力负责留存。

状态服务不伪造设备侧执行结果，不把模拟事件描述为真实设备证据。

## 8. 权限、租户与审计

- 客户租户只能读取本租户设备与机巢。
- 客户租户默认拥有的 `FLIGHT_CONTROL` 被关闭时，读取返回 `FEATURE_403`。
- 平台方跨租户操作必须使用已有受控租户切换逻辑。
- 详情资源不属于当前服务租户时返回 `TENANT_404`，不泄露资源存在性。
- 所有成功写入、写入拒绝、跨租户详情拒绝和状态同步均记录审计。
- 审计记录包含操作者、服务租户、动作、资源类型、资源 ID、结果和请求 ID。

## 9. 错误处理

沿用统一响应 `code/message/request_id/details`，不新增错误码：

- `AUTH_401`：缺少或无效认证。
- `PERM_403`：客户账号调用平台管理接口。
- `FEATURE_403`：租户未开通飞控功能。
- `TENANT_403`：非法租户切换。
- `TENANT_404`：详情资源不属于服务租户或目标租户不存在。
- `IDEMP_409`：幂等键缺失或请求指纹冲突。
- `MISSION_422`：当前 U0 统一请求验证处理器对字段格式、设备类型、同租户内关联类型和唯一性冲突使用的临时固定错误码。

跨租户关联始终返回 `TENANT_404`。其他设备请求校验暂时复用现有 `MISSION_422`，不新增错误码；该命名与设备领域不完全匹配，只有客户或项目方签字确认通用验证错误码后才能替换。

## 10. 测试与验收

### 10.1 自动化测试

- Alembic 升级、降级、再次升级包含 `devices` 和 `docks`。
- 模型约束覆盖序列号唯一、机巢一对一、复合外键和数据库级跨租户关联阻断。
- Repository 的列表、详情、创建和更新始终带租户条件。
- 平台方创建设备/机巢、更新固件与绑定关系、幂等重放通过。
- 客户读取本租户通过，客户写入返回 `PERM_403`。
- 关闭 `FLIGHT_CONTROL` 后读取返回 `FEATURE_403`。
- 平台受控租户切换通过，客户切换返回 `TENANT_403`。
- 跨租户详情返回 `TENANT_404`，且响应不泄露资源存在性。
- 机巢关联错误类型或其他租户设备被拒绝。
- 标准 DJI 模拟状态事件更新 `ONLINE/OFFLINE`、最后在线时间和环境快照；绑定事件不改变在线状态。
- 状态同步审计使用 `dji_gateway` 操作者和网关入口 `request_id`。
- 成功、拒绝和状态同步审计可查询。
- OpenAPI 包含 U1-F02 八个接口且写接口声明 `Idempotency-Key`。

### 10.2 验收证据

- U1-F02 聚焦测试结果。
- 全量自动化回归结果。
- SQLite 迁移回归与 PostgreSQL 迁移烟测结果。
- `docs/60-test-reports/U1-flight-test-report.md` 增补 U1-F02 结论。

## 11. 完成边界

U1-F02 完成只代表设备与机巢台账、权限、租户隔离、审计、幂等和模拟状态同步通过。配套无人机/载荷型号、DJI Cloud API 版本、凭证和真实设备环境尚未锁定，因此不得宣称真实设备接入或生产验收通过。
