# 数据库建模边界与 PostGIS 启用策略

## 1. 结论

一期数据库建模采用：

```text
核心表完整登记 + U0-U5 主链路优先落地 + PostGIS 从第一版启用
```

具体决策：

| 问题 | 决策 |
| --- | --- |
| 是否按现有文档完整创建核心表 | 是，但分层实现：先建完整骨架和关键约束，不一次性完成所有业务逻辑 |
| 是否一期先做 U0-U5 主链路表 | 是，U0-U5 是 M1 闭环必需，优先完整实现 |
| 是否启用 PostGIS 空间字段 | 是，从第一版迁移启用，避免后期 GIS 数据迁移返工 |

## 2. 建模原则

数据库建模必须遵循：

1. 核心实体不得随意删减。
2. 所有租户根业务表必须显式包含 `tenant_id`。
3. 子表如不直接包含 `tenant_id`，必须能通过父级实体可靠追溯租户。
4. 状态字段必须使用项目文档固定枚举。
5. 错误码、`feature_code`、状态机不得自造。
6. 写接口幂等必须有数据库约束支撑。
7. 审计日志必须可追溯到租户、用户、资源和状态变化。
8. 媒体、抽帧、数据集、模型制品路径必须体现租户隔离。
9. GIS 能力从第一版预留，不等客户 GIS 数据确认后再补。

## 3. 分层实现策略

### 3.1 L1：U0-U5 主链路表完整实现

U0-U5 是 M1 平台闭环的最小数据链路：

```text
租户 / 用户 / 权限
→ 设备 / 机巢 / 航线 / 任务
→ 媒体入库 / 抽帧
→ 分析任务 / 推理结果
→ 事件 / 工单 / 复核
→ 标注 / 数据集
→ 训练 / 模型版本 / 发布 / 回滚
```

L1 表必须完整实现：

- 字段。
- 外键。
- 状态。
- 唯一约束。
- 租户索引。
- 审计字段。
- 幂等字段。
- 必要 JSONB 字段。
- 必要 PostGIS 字段。

### 3.2 L2：U6/U7 相关表先建骨架

U6/U7 虽然后置，但以下数据必须提前有可追溯位置：

- 真实算法模型。
- 冻结验收集 checksum。
- 离线指标报告。
- 视频回放记录。
- 人工抽检记录。
- NVIDIA runtime artifact。
- 国产后端 runtime artifact。
- 双硬件一致性报告。
- UAT 与系统验收报告。

L2 表先实现：

- 建表。
- 主键。
- 租户字段或父级租户追溯。
- 关键状态。
- checksum。
- 报告 URI。
- JSONB 元数据。

业务逻辑可在 U6/U7 阶段逐步补齐。

### 3.3 L3：待确认外部接口字段用配置或 JSONB 承接

待确认项不得硬编码为生产锁定条件：

- DJI Cloud API 具体版本。
- 证书与回调协议细节。
- 统一身份协议。
- OA / 空域审批接口。
- GIS 数据来源与坐标系。
- 生产对象存储接口。
- 工单平台接口。
- 国产 AI 加速卡型号。
- 一期算法冻结验收集。

这些字段可通过配置表、适配器配置或 JSONB 元数据承接，但必须标注待确认。

## 4. 必建核心表

以下核心表按项目规约不得删减：

| 领域 | 表 |
| --- | --- |
| 租户与权限 | `tenants`, `users`, `roles`, `user_tenant_roles`, `tenant_feature_entitlements`, `tenant_data_grants`, `audit_logs` |
| 设备与资产 | `devices`, `docks`, `road_assets`, `bridge_assets`, `slope_assets`, `coordinate_transforms` |
| 飞控 | `routes`, `route_versions`, `missions`, `mission_approvals`, `flight_events` |
| 媒体 | `media_files`, `media_chunks`, `frame_assets` |
| 算法与推理 | `algorithms`, `algorithm_label_schemas`, `algorithm_thresholds`, `analysis_tasks`, `analysis_task_algorithms`, `inference_jobs`, `detection_results` |
| 事件与工单 | `events`, `event_asset_links`, `review_records`, `feedback_samples`, `work_orders` |
| 标注 | `annotation_tasks`, `annotation_task_samples`, `annotations` |
| 训练与发布 | `datasets`, `training_jobs`, `model_versions`, `runtime_artifacts`, `algorithm_releases` |

## 5. U0-U5 优先完整实现表

一期正式开发优先完整实现以下表：

```text
tenants
users
roles
user_tenant_roles
tenant_feature_entitlements
tenant_data_grants
audit_logs
devices
docks
road_assets
bridge_assets
slope_assets
coordinate_transforms
routes
route_versions
missions
mission_approvals
flight_events
media_files
media_chunks
frame_assets
algorithms
algorithm_label_schemas
algorithm_thresholds
analysis_tasks
analysis_task_algorithms
inference_jobs
detection_results
events
event_asset_links
review_records
feedback_samples
work_orders
annotation_tasks
annotation_task_samples
annotations
datasets
training_jobs
model_versions
runtime_artifacts
algorithm_releases
```

说明：

- 虽然 `runtime_artifacts`、`algorithm_releases` 与 U6/U7 强相关，但 U5 发布回滚闭环已经需要这些表，因此应在一期主链路中提前建立。
- U6 真实模型接入前，这些表可以保存模拟后端、待确认硬件和验收报告占位信息，但不得写成真实硬件验收通过。

## 6. PostGIS 启用策略

### 6.1 决策

从第一版数据库迁移启用 PostGIS：

```sql
CREATE EXTENSION IF NOT EXISTS postgis;
```

### 6.2 依据

本项目天然包含 GIS 场景：

- 道路资产。
- 桥梁资产。
- 边坡资产。
- 航线。
- 坐标转换。
- 桩号映射。
- 事件定位。
- 飞行轨迹。
- 遥测点位。
- 图像帧地理提示。

若后期再从普通经纬度字段迁移到 PostGIS，会导致：

- 数据迁移复杂。
- 坐标系不统一。
- 空间查询条件重写。
- 空间索引重建。
- 验收脚本和报表返工。

因此即使一期 GIS 数据源待确认，也应从第一版启用 PostGIS，并允许几何字段为空。

## 7. 空间字段建议

| 表 | 空间字段建议 | 说明 |
| --- | --- | --- |
| `road_assets` | `geom geometry(LineString, 4326)` | 道路、路段、桩号区间 |
| `bridge_assets` | `geom geometry(Geometry, 4326)` | 桥梁可为 Point、LineString 或 Polygon |
| `slope_assets` | `geom geometry(Polygon, 4326)` | 边坡区域 |
| `routes` | `path_geom geometry(LineString, 4326)` | 航线主路径 |
| `route_versions` | `path_geom geometry(LineString, 4326)` | 航线版本路径 |
| `flight_events` | `location geometry(Point, 4326)` | 遥测和异常事件位置，可空 |
| `frame_assets` | `location geometry(Point, 4326)` | 帧地理提示位置，可空 |
| `events` | `location geometry(Point, 4326)` | 告警事件定位点，可空 |
| `event_asset_links` | 不强制空间字段 | 通过 asset_id 关联空间资产 |

所有空间字段必须配套：

- `source_crs` 或坐标来源说明。
- 必要 GiST 索引。
- 对无法自动定位的事件设置 `NEEDS_GEO_REVIEW`。

## 8. JSONB 使用策略

### 8.1 适合 JSONB 的字段

| 数据 | 建议字段 |
| --- | --- |
| DJI 原始回调 | `flight_events.raw_payload` |
| `schema:flight_event_payload` | `flight_events.payload` 或拆字段 + `raw_payload` |
| 帧地理提示 | `frame_assets.geo_hint` |
| 检测几何附加信息 | `detection_results.geometry` |
| 事件证据链 | `events.evidence` |
| 阈值策略 | `algorithm_thresholds.policy` |
| runtime 配置 | `runtime_artifacts.runtime_config` |
| 模型指标 | `model_versions.metrics` |
| 训练参数 | `training_jobs.params` |
| 外部接口待确认字段 | `integration_configs.config` 或业务表 metadata |

### 8.2 不适合 JSONB 的字段

以下字段必须结构化，不得只放 JSONB：

- `tenant_id`
- `status`
- `feature_code`
- `role_code`
- `algorithm_code`
- `owner_tenant_id`
- `grantee_tenant_id`
- `resource_type`
- `resource_id`
- `created_at`
- `updated_at`
- 审计关键字段
- 常用过滤和关联字段

## 9. 索引与约束策略

### 9.1 必须建立的索引

| 类型 | 建议 |
| --- | --- |
| 租户索引 | 所有租户根表建立 `tenant_id` 索引 |
| 状态索引 | 任务、媒体、分析、事件、标注、训练、发布表建立 `(tenant_id, status)` 索引 |
| 时间索引 | 审计、任务、媒体、事件表建立 `created_at` 或 `event_time` 索引 |
| 空间索引 | PostGIS geometry 字段建立 GiST 索引 |
| 对象路径索引 | 媒体、帧、数据集、模型制品路径建立必要索引 |
| 幂等索引 | 幂等键表或业务写接口记录建立唯一索引 |

### 9.2 必须建立的唯一约束

| 表 | 约束 |
| --- | --- |
| `tenants` | `code` 唯一 |
| `users` | `username` 唯一 |
| `roles` | `code` 唯一 |
| `tenant_feature_entitlements` | `(tenant_id, feature_code)` 唯一 |
| `tenant_data_grants` | 建议按授权范围生成唯一业务键或授权编号 |
| `algorithms` | `code` 唯一 |
| `model_versions` | `(algorithm_id, version)` 唯一 |
| `algorithm_thresholds` | `(tenant_id, algorithm_id)` 或 `(tenant_id, algorithm_id, label)` 唯一 |
| `runtime_artifacts` | `(model_version_id, backend)` 唯一 |
| `algorithm_releases` | 同租户同算法同状态活跃发布需约束 |

### 9.3 状态约束

状态字段必须使用固定枚举或 CHECK 约束，至少覆盖：

- `missions.status`
- `media_files.status`
- `frame_assets.status`
- `analysis_tasks.status`
- `inference_jobs.status`
- `events.status`
- `annotation_tasks.status`
- `datasets.status`
- `training_jobs.status`
- `model_versions.status`
- `algorithm_releases.status`

## 10. 审计与分区

`audit_logs` 必须包含：

- `tenant_id`
- `actor_user_id`
- `action`
- `resource_type`
- `resource_id`
- `before_status`
- `after_status`
- `error_code`
- `ip_address`
- `user_agent`
- `created_at`
- `details`

审计日志保留策略不少于 180 天。

建议：

- 初期建立 `tenant_id`、`created_at`、`resource_type/resource_id` 索引。
- 数据量增长后按月或季度分区。
- 越权拒绝也必须写审计。

## 11. 待确认项处理

待确认项不得写成生产已锁定字段。

| 待确认项 | 数据库处理 |
| --- | --- |
| DJI Cloud API 版本 | `integration_configs` 或 `dji_gateway_configs` 中标注 |
| DJI 证书 | 不入库明文，使用密钥服务或环境变量 |
| 统一身份协议 | `identity_provider_configs` 预留 |
| OA / 空域审批 | `approval_integrations` 预留 |
| GIS 数据来源 | `coordinate_transforms`、资产表 `source_crs/source_system` |
| 生产对象存储 | `storage_configs` 预留 |
| 工单平台 | `work_order_integrations` 预留 |
| 国产 AI 加速卡型号 | `runtime_artifacts.runtime_config` 和硬件配置表预留 |
| 冻结验收集 | `datasets.checksum`、`datasets.status=FROZEN` |

## 12. 与 U0-U7 的关系

| 单元 | 数据库重点 |
| --- | --- |
| U0 | 租户、用户、角色、功能授权、数据授权、审计、幂等 |
| U1 | 设备、机巢、资产、航线、任务、审批、飞行事件 |
| U2 | 媒体、分片、抽帧、分析任务、推理结果、事件、工单 |
| U3 | 推理任务、模型版本、runtime_artifacts、双后端一致性 |
| U4 | 样本、标注任务、标注结果、数据集 |
| U5 | 训练任务、模型评估、模型版本、发布、回滚 |
| U6 | 真实算法、冻结验收集、评估报告、回放记录、人工抽检 |
| U7 | 性能、安全、网络边界、UAT、系统验收报告 |

## 13. 正式开发执行原则

后续数据库迁移和 ORM 模型按本文件执行：

1. 第一版迁移启用 PostGIS。
2. 第一版迁移创建核心表骨架。
3. U0-U5 表字段、约束、索引和状态完整落地。
4. U6/U7 相关表先建可追溯骨架。
5. `tenant_id`、状态、错误码、feature_code 不得只放 JSONB。
6. JSONB 只用于原始回调、策略、证据、配置、指标等半结构化数据。
7. 所有写操作和越权拒绝可写审计。
8. 模拟能力和待确认项必须在数据中标注，不得伪装为生产已完成。
