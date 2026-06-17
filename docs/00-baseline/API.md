# 无人机智能巡检系统 API 设计基线

## 1. 总体约定

| 项 | 约定 |
| --- | --- |
| 外部业务接口 | REST + JSON |
| 实时推送 | WebSocket |
| 内部推理 | gRPC |
| API 前缀 | `/api/v1` |
| 租户上下文 | 来自 Token、统一身份映射或受控 `X-Tenant-Id` |
| 幂等 | 所有写接口支持 `Idempotency-Key` |
| 异步任务 | 返回 `task_id`，支持状态查询、取消、重试和失败原因 |
| 审计 | 写操作、审批、发布、删除、越权、跨租户切换均写 `audit_logs` |
| 错误响应 | 统一使用 `code/message/request_id/details` |

普通客户租户不得通过请求体自行传入或覆盖 `tenant_id`。仅平台方授权账号可使用受控 `X-Tenant-Id` 切换服务租户。

## 2. 通用请求头

| Header | 必填 | 说明 |
| --- | --- | --- |
| Authorization | 是 | Bearer Token 或统一身份网关下发的访问凭证 |
| X-Request-Id | 建议 | 链路追踪 ID；未传时服务端生成 |
| X-Tenant-Id | 条件 | 仅平台方授权账号可用于受控切换服务租户 |
| Idempotency-Key | 写接口必填 | 幂等键，相同键重复请求返回同一业务结果 |

## 3. 通用错误响应

所有错误响应必须使用以下结构。成功响应保持业务字段直出，不强制包装。

```json
{
  "code": "TENANT_403",
  "message": "当前用户无目标租户访问权",
  "request_id": "req_8f3a1c2d",
  "details": {
    "resource_type": "mission",
    "resource_id": "m_1024",
    "field_errors": []
  }
}
```

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| code | 是 | 固定错误码，禁止返回未登记错误码 |
| message | 是 | 面向用户的简要说明，不得包含 SQL、堆栈、内部路径 |
| request_id | 是 | 与审计和日志关联 |
| details | 否 | 结构化补充信息，如字段错误、缺失指标、缺失授权范围 |

## 4. 错误码

| 错误码 | 含义 | 处理策略 |
| --- | --- | --- |
| AUTH_401 | 未认证或 Token 过期 | 重新登录或刷新 Token |
| PERM_403 | 权限不足 | 记录审计，提示申请权限 |
| TENANT_403 | 当前用户无目标租户访问权或试图伪造 `tenant_id` | 拒绝请求，记录跨租户审计 |
| TENANT_404 | 资源不存在于当前租户上下文 | 返回不可见，避免泄露其他租户资源存在性 |
| FEATURE_403 | 当前租户未开通目标功能 | 拒绝访问，提示联系平台方开通或调整授权 |
| DATA_GRANT_412 | 数据未获得训练、评估或跨租户统计授权 | 阻断数据集封版、训练或统计任务 |
| IDEMP_409 | 幂等键冲突 | 返回原请求摘要并拒绝不一致请求 |
| STATE_409 | 当前状态不允许目标操作 | 返回当前状态、允许动作、最后变更人 |
| MISSION_422 | 任务参数不满足飞行或审批条件 | 返回字段级校验错误 |
| DJI_502 | DJI 适配层调用失败 | 可重试错误进入补偿队列，不可重试进入人工处理 |
| GIS_422 | 坐标或资产匹配失败 | 进入人工定位复核 |
| MEDIA_415 | 媒体格式不支持 | 拒绝入库并保留失败原因 |
| MEDIA_499 | 分片上传未完成或 checksum 不一致 | 触发续传或重新上传 |
| INFER_504 | 推理超时 | 按算法配置重试，超过阈值标记失败 |
| MODEL_412 | 模型未满足发布准入 | 阻断发布，返回缺失指标 |
| RUNTIME_428 | 指定硬件后端未完成验证 | 阻断切换或发布 |

## 5. 核心 REST 接口

| 模块 | 方法与路径 | 说明 | 幂等 | 异步 | 客户租户默认可用 |
| --- | --- | --- | --- | --- | --- |
| 认证 | `GET /api/v1/me` | 获取当前用户、角色、权限 | 否 | 否 | 是 |
| 租户 | `GET /api/v1/tenant-context` | 获取当前租户、租户类型、功能授权、可切换租户列表 | 否 | 否 | 是 |
| 租户 | `POST /api/v1/admin/tenants/{id}/feature-entitlements` | 平台方配置客户租户功能授权 | 是 | 否 | 否 |
| 租户 | `POST /api/v1/admin/tenant-data-grants` | 平台方登记客户数据训练/评估授权 | 是 | 否 | 否 |
| 飞控 | `POST /api/v1/missions` | 创建飞行任务 | 是 | 否 | 是 |
| 飞控 | `POST /api/v1/missions/{id}/submit-approval` | 提交审批 | 是 | 是 | 是 |
| 飞控 | `POST /api/v1/missions/{id}/dispatch` | 下发任务到 DJI 适配层 | 是 | 是 | 是 |
| 飞控 | `GET /api/v1/missions/{id}/telemetry/ws` | 实时遥测 WebSocket | 否 | 是 | 是 |
| 媒体 | `POST /api/v1/media/ingest-events` | 媒体入库事件 | 是 | 是 | 是 |
| 媒体 | `POST /api/v1/media/{id}/frame-jobs` | 创建抽帧任务 | 是 | 是 | 是 |
| 分析 | `POST /api/v1/analysis/tasks` | 创建分析任务 | 是 | 是 | 视授权 |
| 分析 | `GET /api/v1/analysis/tasks/{id}` | 查询分析任务状态 | 否 | 否 | 是 |
| 告警 | `POST /api/v1/events/{id}/review` | 人工确认、驳回、修正定位 | 是 | 否 | 视授权 |
| 工单 | `POST /api/v1/events/{id}/dispatch-work-order` | 派发工单 | 是 | 是 | 视授权 |
| 算法 | `GET /api/v1/algorithms` | 查询算法主数据 | 否 | 否 | 是 |
| 算法 | `POST /api/v1/algorithms/{id}/thresholds` | 配置阈值策略 | 是 | 否 | 视授权 |
| 标注 | `POST /api/v1/annotation/tasks` | 创建标注任务 | 是 | 否 | 视授权 |
| 数据集 | `POST /api/v1/datasets/{id}/freeze` | 数据集封版 | 是 | 是 | 视授权 |
| 训练 | `POST /api/v1/training/jobs` | 创建训练任务 | 是 | 是 | 否 |
| 模型 | `POST /api/v1/model-versions/{id}/evaluate` | 离线评估与硬件适配检查 | 是 | 是 | 否 |
| 发布 | `POST /api/v1/algorithm-releases` | 模型灰度/发布/回滚 | 是 | 是 | 否 |

## 6. 关键请求示例

### 6.1 创建飞行任务

`POST /api/v1/missions`

```json
{
  "route_id": "rt_001",
  "device_id": "dock_001",
  "schedule_time": "2026-06-16T09:00:00Z",
  "inspection_targets": ["road_asset_001", "bridge_asset_002"],
  "media_policy": {
    "video": true,
    "image_interval_sec": 2
  }
}
```

响应：

```json
{
  "id": "ms_20260616_0007",
  "status": "DRAFT"
}
```

### 6.2 媒体入库事件

`POST /api/v1/media/ingest-events`

```json
{
  "mission_id": "ms_20260616_0007",
  "source_type": "DJI_DOCK_3",
  "storage_uri": "t_customer_001/proj_001/ms_20260616_0007/media/med_8841.mp4",
  "checksum": "sha256:9f2c...",
  "captured_at": "2026-06-16T10:05:30Z"
}
```

响应：

```json
{
  "task_id": "task_media_ingest_001",
  "media_file_id": "med_8841"
}
```

### 6.3 创建分析任务

`POST /api/v1/analysis/tasks`

```json
{
  "media_file_id": "med_8841",
  "algorithm_codes": ["road_crack", "road_pothole"],
  "priority": "NORMAL"
}
```

响应：

```json
{
  "task_id": "task_analysis_001",
  "analysis_task_id": "ana_001",
  "status": "CREATED"
}
```

### 6.4 登记数据授权

`POST /api/v1/admin/tenant-data-grants`

```json
{
  "owner_tenant_id": "t_customer_001",
  "grantee_tenant_id": "t_jxjtsz_platform",
  "data_scope": {
    "asset_types": ["road", "bridge"],
    "sample_ids": ["sample_001", "sample_002"]
  },
  "purpose": ["training", "evaluation"],
  "effective_from": "2026-06-16T00:00:00Z",
  "expires_at": "2027-06-16T00:00:00Z"
}
```

## 7. WebSocket

### 7.1 任务遥测

`GET /api/v1/missions/{id}/telemetry/ws`

服务端消息：

```json
{
  "mission_id": "ms_20260616_0007",
  "status": "EXECUTING",
  "location": {
    "lat": 28.6829,
    "lng": 115.8582,
    "alt": 120.5,
    "source_crs": "WGS84"
  },
  "battery": 76,
  "signal": -62,
  "timestamp": "2026-06-16T09:20:01Z"
}
```

订阅前必须校验租户上下文。客户租户只能订阅本租户任务遥测。

## 8. DJI 适配层回调

所有 DJI 或模拟器回调统一转换为 `schema:flight_event_payload`：

```json
{
  "event_code": "media_upload_completed",
  "event_time": "2026-06-16T10:05:30Z",
  "device_sn": "1581F6Q8D24CA00G123",
  "raw_payload": {
    "mission_id": "ms_20260616_0007",
    "media_id": "med_8841",
    "storage_uri": "t_customer_001/proj_001/ms_20260616_0007/media/med_8841.mp4",
    "checksum": "sha256:9f2c...",
    "chunk_total": 12,
    "chunk_completed": 12
  }
}
```

落库要求：
- `event_code`、`event_time`、`device_sn`、`raw_payload` 必填。
- 设备动作以 DJI 回执为准。
- 重复回调必须幂等。
- checksum 不一致返回或记录 `MEDIA_499`。

## 9. gRPC 推理接口

```protobuf
syntax = "proto3";
package inference.v1;

service InferenceService {
  rpc Predict (PredictRequest) returns (PredictResponse);
  rpc HealthCheck (HealthRequest) returns (HealthResponse);
}

message PredictRequest {
  string inference_job_id = 1;
  string algorithm_id = 2;
  string model_version_id = 3;
  string frame_asset_id = 4;
  bytes image_data = 5;
  string image_uri = 6;
  int32 image_width = 7;
  int32 image_height = 8;
  string backend = 9;
  map<string, string> runtime_params = 10;
}

message PredictResponse {
  string inference_job_id = 1;
  string status = 2;
  string error_code = 3;
  repeated Detection detections = 4;
  int32 latency_ms = 5;
  string backend = 6;
  string model_version_id = 7;
}

message Detection {
  string label = 1;
  double confidence = 2;
  oneof geometry {
    BBox bbox = 3;
    Mask mask = 4;
    Polyline polyline = 5;
  }
  map<string, string> attributes = 6;
}

message BBox { double x = 1; double y = 2; double width = 3; double height = 4; }
message Mask { string encoding = 1; bytes data = 2; }
message Polyline { repeated Point points = 1; }
message Point { double x = 1; double y = 2; }
```

约束：
- `image_data` 与 `image_uri` 二选一。
- `backend` 取值为 `nvidia` 或 `domestic`。
- `PredictResponse.status` 取值为 `SUCCEEDED`、`FAILED`、`TIMEOUT`。
- `error_code` 复用统一错误码。
- 输出落库到 `detection_results` 前必须转换为 `schema:detection_geometry`。
- `PredictResponse.backend` 必须与请求后端一致，不允许静默切换。

## 10. 功能授权矩阵

| feature_code | 保护接口示例 |
| --- | --- |
| FLIGHT_CONTROL | `/missions`, `/missions/{id}/dispatch`, `/missions/{id}/telemetry/ws` |
| VISION_ANALYSIS_RESULT | `/analysis/tasks`, `/events`, `/work-orders` |
| DATA_ANNOTATION | `/annotation/tasks`, `/annotations` |
| DATASET_EXPORT | `/datasets/{id}/export`, `/datasets/{id}/freeze` |
| MODEL_TRAINING | `/training/jobs` |
| MODEL_RELEASE | `/algorithm-releases`, `/model-versions/{id}/evaluate` |
| CROSS_TENANT_STATS | `/admin/stats/*` |
| PLATFORM_OPS | `/admin/*`, 全局配置和跨租户运维接口 |

未登记或未授权的 `feature_code` 统一按未开通处理，返回 `FEATURE_403`。
