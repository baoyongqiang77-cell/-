# AGENTS.md

本文件是“无人机智能巡检系统”软件开发项目的最高优先级代理工作规约，供 AI 编码代理、研发人员、测试人员和实施人员共同遵循。

## 0. 项目基线

- 系统名称：无人机智能巡检系统。
- 平台建设、运营、运维单位：江西省交投数智科技有限公司。
- 服务对象：江西省内多个高速公路运营管理分中心。
- 一期目标：完成平台主链路闭环和 14 个视觉算法上线验收。
- 一期里程碑：
  - M1 平台闭环可用：飞控、媒体入库、抽帧、模拟推理、告警、工单、标注、训练、发布流程跑通。
  - M2 一期最终验收：14 个真实算法接入并通过离线指标、回放、人工抽检和双硬件适配验收。
- 一期飞控边界：优先适配大疆机场 3（DJI Dock 3）与 DJI Cloud API；平台负责业务编排，不自研底层飞控安全逻辑。
- 一期部署边界：仅“大疆机场 3 适配网关”允许按白名单访问互联网和 DJI Cloud API，其余业务平台默认运行在政务云内网。
- 一期硬件边界：推理运行时必须保留 NVIDIA GPU 与国产 AI 加速卡双路线适配；国产卡型号未锁定前只能做接口契约和模拟后端验收。

## 1. 文档优先级

开发、测试、接口设计和验收发生冲突时，按以下优先级处理：

1. 客户或项目方后续签字确认的变更记录。
2. `docs/00-baseline/source-originals/无人机智能巡检系统_架构方案内部开发V2.0.md`，对应《无人机智能巡检系统架构方案（内部开发正式定版）V2.0》。
3. `docs/00-baseline/source-originals/无人机智能巡检系统_软件开发功能说明书V2.0.md`，对应《无人机智能巡检系统软件开发功能说明书V2.0》。
4. 本目录生成的 `README.md`、`AGENTS.md`、`docs/README.md`、`docs/00-baseline/PRD.md`、`docs/00-baseline/Architecture.md`、`docs/00-baseline/API.md`、`docs/00-baseline/Roadmap.md`。
5. 代码实现、注释、临时会议口头结论。

未在源文档中确认的事项不得在代码、配置或测试中伪装为已锁定条件。待确认项包括但不限于 DJI Cloud API 具体版本与证书、配套无人机/载荷型号、统一身份协议、OA/空域审批接口、GIS 数据来源与坐标系、生产对象存储接口、工单平台接口、国产 AI 加速卡型号、一期算法冻结验收集。

## 2. 代理工作总原则

- 先读 `README.md` 和本文，再读 `docs/README.md`、`docs/00-baseline/source-originals/` 下的源文档、`docs/00-baseline/PRD.md`、`docs/00-baseline/Architecture.md`、`docs/00-baseline/API.md`、`docs/00-baseline/Roadmap.md`，再改代码。
- 所有核心业务改动必须能映射到 U0-U7 开发单元。
- 不允许绕过多租户、功能授权、数据授权、审计、状态机和网络边界。
- 不允许为了演示把模拟器能力写成生产能力。
- 不允许把客户租户默认赋予训练、模型发布、跨租户统计或平台运维权限。
- 不允许让内网业务服务、分析服务、标注服务、训练服务、AI 服务直接访问互联网。
- 不允许业务平台散落调用 DJI 接口；所有 DJI 能力必须经“大疆机场 3 适配网关”封装。
- 不允许 NVIDIA 后端和国产后端返回不同推理结构；必须实现统一 gRPC `Predict` 契约。
- 不允许各模块自定义错误响应格式；错误响应必须统一为 `code/message/request_id/details`。
- 不允许新增未登记错误码、状态枚举或 `feature_code`。

## 3. 租户与权限硬约束

系统必须采用“平台方租户 + 客户租户”的逻辑多租户模式。

平台方租户：
- tenant_type 必须为 `PLATFORM_OPERATOR`。
- 默认具备飞控、分析、标注、训练、发布、运维审计和跨租户受控运维能力。
- 跨租户操作必须通过角色授权、受控租户切换和审计日志记录。

客户租户：
- tenant_type 必须为 `CUSTOMER_TENANT`。
- 默认只开放本租户范围内的飞控、数据标注、视觉分析结果、告警和工单能力。
- 默认关闭训练任务、模型发布、跨租户统计、平台运维和数据集导出能力。

所有业务表必须显式包含 `tenant_id`，或能通过父级实体可靠追溯 `tenant_id`。列表、详情、导出、WebSocket 订阅、异步任务查询、对象存储路径、消息队列消息体都必须包含或自动继承租户上下文。

固定 `feature_code` 只能使用以下取值：

| feature_code | 功能域 | 客户租户默认 |
| --- | --- | --- |
| FLIGHT_CONTROL | 飞控平台 | 开放，限本租户 |
| VISION_ANALYSIS_RESULT | 视觉分析结果查看 | 开放，限本租户 |
| DATA_ANNOTATION | 数据标注任务处理与样本查看 | 开放，限本租户授权任务 |
| DATASET_EXPORT | 数据集导出 | 默认关闭 |
| MODEL_TRAINING | 训练任务创建与查看 | 默认关闭 |
| MODEL_RELEASE | 模型发布、灰度、回滚 | 默认关闭 |
| CROSS_TENANT_STATS | 跨租户统计与汇聚查询 | 默认关闭 |
| PLATFORM_OPS | 平台运维 | 不开放 |

访问未授权功能统一返回 `FEATURE_403`。客户数据进入平台方训练、评估或跨租户统计前，必须存在有效 `tenant_data_grants`，否则返回 `DATA_GRANT_412`。

## 4. 模块边界

U0 基础工程：
- 交付后端骨架、前端骨架、认证/RBAC、租户初始化、功能授权、数据授权、审计、配置、对象存储、消息队列、异步任务中心、CI/CD、迁移脚本和 OpenAPI。
- 完成定义：可登录、可鉴权、可按租户过滤、可按功能授权控制模块、可写审计、基础服务可一键启动。

U1 飞控平台：
- 交付大疆机场 3 适配网关、模拟器、设备/机巢台账、GIS 最小资产、航线、任务、审批、遥测、异常联动和媒体同步。
- 真实飞行控制和安全返航逻辑由 DJI 设备能力承担，平台只记录设备侧回执。

U2 媒体与分析主链路：
- 交付媒体入库、断点续传、抽帧、分析任务、推理队列、检测结果聚合、告警、工单、人工复核和误报漏报回流。
- M1 可用模拟算法闭环；M2 必须接入真实算法。

U3 推理运行时：
- 交付统一 gRPC 协议、NVIDIA 后端适配器、国产后端适配器或模拟后端、模型制品管理、双后端一致性检查。
- 国产卡型号未锁定时，不得宣称真实国产硬件验收通过。

U4 数据标注平台：
- 交付样本池、标注任务、标注工具、初检/复检、数据集导出、质检统计和样本来源追踪。
- FROZEN 数据集不可修改。

U5 训练与算法库：
- 交付数据集版本、训练任务、指标评估、模型版本、灰度发布、回滚、数据授权校验。
- 未达标模型不得发布；客户租户默认不得训练或发布。

U6 一期 14 算法接入：
- 交付 14 个真实算法模型、阈值、输出 schema、离线评估报告、回放测试记录和人工抽检记录。
- 模拟算法不得计入 M2 通过。

U7 联调验收：
- 交付性能、安全、弱网、断点续传、租户隔离、功能租赁授权、数据训练授权、网络边界、双硬件一致性和 UAT 报告。
- 外部生产接口、真实设备、硬件型号或网络边界未锁定时，不得通过生产验收。

## 5. 飞控与 DJI 适配规则

- 业务平台不得直接调用 DJI Cloud API。
- 所有设备绑定、状态同步、航线上传、任务下发、任务控制、遥测订阅、媒体同步、异常事件必须通过大疆机场 3 适配网关。
- 适配网关必须支持开发模拟器，并与真实 API 使用同一业务接口。
- 关键回调统一转换为 `schema:flight_event_payload`，外层必填字段为 `event_code`、`event_time`、`device_sn`、`raw_payload`。
- 模拟器至少覆盖绑定成功、遥测推送、低电量异常、媒体上传完成，以及凭证错误、设备已绑定、格式错误、超时、设备无响应、checksum 错误等失败分支。
- 所有设备侧动作以 DJI 回执为准，平台不得伪造“已执行”结果。

## 6. 推理与算法规则

一期 14 个算法必须完整登记算法主数据、标签 schema、输出 schema、默认阈值、租户级阈值覆盖、模型版本、评估指标和验收报告。

一期算法编码固定如下：

| code | 算法 |
| --- | --- |
| traffic_congestion | 交通拥堵 |
| pedestrian_intrusion | 行人闯入 |
| two_wheeler_intrusion | 两轮车闯入 |
| road_obstacle | 路面障碍物 |
| road_construction | 道路施工 |
| road_crack | 路面裂缝 |
| road_pothole | 路面坑槽 |
| road_water | 路面积水 |
| marking_blur | 路面标线模糊 |
| helmet_missing | 施工人员未戴安全帽 |
| vest_missing | 施工人员未穿反光衣 |
| guardrail_damage | 护栏钢结构破损 |
| barrier_damage | 隔离栏破损 |
| bridge_under_space_stacking | 桥下空间堆积物 |

统一推理接口必须满足：
- 内部推理采用 gRPC。
- `PredictRequest.backend` 只能是 `nvidia` 或 `domestic`。
- `PredictResponse.status` 只能是 `SUCCEEDED`、`FAILED`、`TIMEOUT`。
- `PredictResponse.error_code` 必须复用统一错误码，如 `INFER_504`、`RUNTIME_428`。
- `Detection.geometry` 只能在 `bbox`、`mask`、`polyline` 中三选一。
- 同一 `frame_asset_id`、同一 `model_version_id` 在 NVIDIA 与国产后端输出差异超过阈值时，必须阻断发布。

## 7. 状态机规则

不得简化或自造核心状态。飞行任务状态必须使用：

`DRAFT`、`PENDING_APPROVAL`、`APPROVED`、`DISPATCHING`、`DISPATCHED`、`EXECUTING`、`PAUSED`、`RETURNING`、`LOST_LINK`、`COMPLETED`、`ABORTED`、`MEDIA_SYNCING`、`PARTIAL_MEDIA_READY`、`MEDIA_READY`、`ANALYSIS_READY`、`CANCELLED`、`REJECTED`、`EXPIRED`、`DISPATCH_FAILED`、`SYNC_FAILED`、`ARCHIVED`。

其他对象状态必须使用源文档状态枚举：
- `media_files/frame_assets`：`CAPTURED`、`UPLOADING`、`UPLOAD_FAILED`、`REGISTERING`、`READY`、`REJECTED`、`FRAME_EXTRACTING`、`FRAME_READY`、`ARCHIVED`、`DELETED`。
- `analysis_task`：`CREATED`、`QUEUED`、`RUNNING`、`WAITING_RESOURCE`、`PARTIAL_SUCCESS`、`FAILED`、`COMPLETED`、`CANCELLED`。
- `inference_job`：`QUEUED`、`RUNNING`、`RETRYING`、`FAILED`、`SUCCEEDED`、`TIMEOUT`。
- `event`：`CANDIDATE`、`NEEDS_REVIEW`、`NEEDS_GEO_REVIEW`、`CONFIRMED`、`REJECTED`、`DISPATCHED`、`CLOSED`。
- `annotation_task`：`CREATED`、`ASSIGNED`、`ANNOTATING`、`SUBMITTED`、`REVIEWING`、`RETURNED`、`PASSED`、`FINAL_PASSED`、`CANCELLED`。
- `dataset`：`DRAFT`、`BUILDING`、`FROZEN`、`DEPRECATED`、`ARCHIVED`。
- `training_job`：`CREATED`、`QUEUED`、`RUNNING`、`EVALUATING`、`FAILED`、`SUCCEEDED`、`CANCELLED`。
- `model_version`：`CREATED`、`CONVERTING`、`VALIDATING`、`READY`、`BLOCKED`、`DEPRECATED`。
- `algorithm_release`：`DRAFT`、`PENDING_APPROVAL`、`GRAY`、`ACTIVE`、`ROLLED_BACK`、`RETIRED`。

所有状态跳转必须校验当前状态、目标状态、操作者权限、租户上下文、设备回执或异步任务结果，并写审计。

## 8. API 规则

- 外部业务接口采用 REST + JSON。
- 实时遥测和任务进度采用 WebSocket。
- 内部推理采用 gRPC。
- 所有写接口必须支持 `Idempotency-Key`。
- 所有异步写接口返回 `task_id`，并提供状态查询、取消、重试和失败原因。
- 普通客户租户不得通过请求体自行指定或覆盖 `tenant_id`。
- 仅平台方授权账号可通过受控 `X-Tenant-Id` 切换服务租户。
- 成功响应可直接返回业务字段；错误响应必须统一为：

```json
{
  "code": "TENANT_403",
  "message": "当前用户无目标租户访问权",
  "request_id": "req_8f3a1c2d",
  "details": {}
}
```

固定错误码：

`AUTH_401`、`PERM_403`、`TENANT_403`、`TENANT_404`、`FEATURE_403`、`DATA_GRANT_412`、`IDEMP_409`、`STATE_409`、`MISSION_422`、`DJI_502`、`GIS_422`、`MEDIA_415`、`MEDIA_499`、`INFER_504`、`MODEL_412`、`RUNTIME_428`。

## 9. 数据模型规则

核心实体不得随意删减，至少包括：

`tenants`、`users`、`roles`、`user_tenant_roles`、`tenant_feature_entitlements`、`tenant_data_grants`、`audit_logs`、`devices`、`docks`、`road_assets`、`bridge_assets`、`slope_assets`、`routes`、`route_versions`、`coordinate_transforms`、`missions`、`mission_approvals`、`flight_events`、`media_files`、`media_chunks`、`frame_assets`、`algorithms`、`algorithm_label_schemas`、`algorithm_thresholds`、`analysis_tasks`、`analysis_task_algorithms`、`inference_jobs`、`detection_results`、`events`、`event_asset_links`、`review_records`、`feedback_samples`、`work_orders`、`annotation_tasks`、`annotation_task_samples`、`annotations`、`datasets`、`training_jobs`、`model_versions`、`runtime_artifacts`、`algorithm_releases`。

JSON Schema 最小约束：

| Schema | 必填字段 |
| --- | --- |
| `schema:flight_event_payload` | event_code, event_time, device_sn, raw_payload |
| `schema:frame_geo_hint` | mission_id, frame_time, drone_location, altitude, heading, source_crs |
| `schema:detection_geometry` | type, bbox, mask, polyline, image_width, image_height |
| `schema:event_evidence` | frame_asset_ids, detection_result_ids, snapshot_uri, algorithm_versions |
| `schema:algorithm_threshold_policy` | default_threshold, per_label_thresholds, min_consecutive_frames, review_band |
| `schema:runtime_config` | backend, device_model, driver_version, sdk_version, image_digest, batch_size |

## 10. 测试与验收要求

每个开发单元必须提供对应自动化测试、接口测试和验收证据。

最低测试要求：
- U0：登录、RBAC、租户过滤、功能授权、数据授权、审计、幂等、OpenAPI。
- U1：DJI 模拟器全流程、状态跳转、遥测 WebSocket、异常事件、网关出口策略。
- U2：弱网断点续传、重复回调、checksum、抽帧、分析任务、告警工单、租户路径隔离。
- U3：gRPC 契约、NVIDIA/国产后端输出 schema 一致性、真实硬件与模拟后端边界。
- U4：标注、退回、复检、封版、客户租户样本越权拒绝。
- U5：训练、评估、发布、回滚、未授权客户数据阻断。
- U6：14 算法离线指标、回放测试、人工抽检、冻结验收集 checksum。
- U7：性能、安全、弱网、租户隔离、功能授权、数据授权、网络边界、UAT。

关键非功能指标：
- 实时分析延迟：P95 <= 3 秒，失败率 < 1%。
- NVIDIA 离线吞吐：每卡 >= 1000 帧/分钟，或按已锁定 GPU 型号给出更高基线。
- 并发飞行监控：20 架次同时在线，1 秒级遥测，Web P95 响应 < 2 秒。
- 告警到工单：P95 <= 10 秒，不含人工复核等待时间。
- 审计日志保留策略：>= 180 天。
- 租户隔离：未授权访问必须返回 `TENANT_403` 或 `TENANT_404`，且不能泄露其他租户资源存在性。

## 11. 待确认项处理

遇到以下事项，不要自行做最终决策：

- DJI Cloud API 具体版本、证书、回调协议细节。
- 配套无人机、载荷、媒体格式和遥测字段。
- 统一身份协议：LDAP、CAS、OAuth2、OIDC。
- OA/空域审批接口模式。
- GIS 资产来源、坐标系、更新频率和桩号映射。
- 对象存储生产接口。
- 工单平台生产接口。
- 国产 AI 加速卡型号、驱动、SDK、容器镜像、性能基线。
- 一期算法冻结验收集。

处理规则：
- 可以先做适配器接口、模拟器、配置占位和契约测试。
- 必须在代码、配置、文档、测试报告中标注“待确认”。
- 不得把待确认项写入生产验收通过条件。

## 12. 完成定义

任何功能被声明完成前，必须满足：

- 有对应需求或架构条目。
- 有租户、权限、功能授权和数据授权校验。
- 有状态机约束和非法状态测试。
- 有统一错误码和错误响应。
- 有审计日志。
- 有幂等设计，若为写接口。
- 有异步任务状态，若为耗时任务。
- 有对象路径租户隔离，若涉及文件、抽帧、数据集或模型制品。
- 有单元测试、接口测试或验收脚本。
- 没有把模拟能力误写成生产能力。
