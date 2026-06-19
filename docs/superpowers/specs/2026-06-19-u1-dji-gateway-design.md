# U1-F01 DJI 适配网关与模拟器设计

## 1. 目标与依据

本增量实现 U1-F01“大疆机场 3 适配网关”的统一业务契约和开发模拟器，为后续设备、航线、任务、遥测和媒体模块提供唯一 DJI 能力入口。

设计遵循以下基线：

- 业务平台不得直接调用 DJI Cloud API。
- 模拟器与未来真实 DJI 客户端必须实现同一业务接口。
- 设备动作结果以网关回执为准，平台不得伪造“已执行”。
- 回调外层固定为 `event_code`、`event_time`、`device_sn`、`raw_payload`。
- DJI Cloud API 版本、证书、无人机和载荷型号仍为待确认项。

## 2. 范围

### 2.1 本增量包含

- 独立于 FastAPI 路由的 `DjiGateway` 协议。
- 设备绑定、设备状态同步、任务下发、遥测事件、异常事件和媒体完成事件契约。
- `DjiDock3Simulator` 开发实现。
- 设备动作回执与标准化回调事件。
- 凭证错误、设备已绑定、格式错误、超时、设备无响应和 checksum 错误六类失败分支。
- 模拟器幂等重放、请求冲突和确定性故障注入。
- 网络出口策略契约与自动化测试。

### 2.2 本增量不包含

- 真实 DJI SDK、Cloud API 地址、证书和生产签名算法。
- 设备、机巢、航线、任务和飞行事件数据库表。
- 飞行任务 REST API、审批 API 和遥测 WebSocket。
- 真实设备、真实飞行或生产网络验收。
- 自研返航、避障、失联保护等底层飞控安全逻辑。

上述内容分别进入后续 U1 增量或真实设备专项联调。

## 3. 方案选择

采用“独立网关契约 + 进程内模拟器”。契约位于领域包中，业务服务只依赖协议，不依赖模拟器实现或未来 DJI SDK。当前模拟器在测试和开发环境进程内运行；真实接入时由 DMZ 网关服务实现同一协议，并通过受控服务间通信提供能力。

不采用以下方案：

- 直接在 FastAPI 路由中调用 DJI：会破坏网络边界并造成供应商逻辑散落。
- 立即建设完整网关微服务：当前缺少已确认的 DJI API、凭证和部署参数，会提前引入无验收依据的基础设施。

## 4. 组件与职责

### 4.1 `DjiGateway`

协议只描述业务能力：

- `bind_device(command)`：绑定设备并返回设备侧回执。
- `sync_device_status(command)`：读取并转换设备状态事件。
- `dispatch_mission(command)`：提交任务并返回设备是否接受的回执。
- `publish_telemetry(command)`：生成或转换标准遥测事件。
- `publish_exception(command)`：生成或转换标准异常事件。
- `complete_media_sync(command)`：生成或转换媒体完成事件。

所有写命令包含 `tenant_id`、`request_id` 和 `idempotency_key`；涉及设备时必须包含 `device_sn`。任务下发还包含 `mission_id` 和 `route_version_id`。

### 4.2 `GatewayReceipt`

设备动作返回不可变回执，字段为：

- `operation`
- `request_id`
- `device_sn`
- `accepted`
- `external_request_id`
- `received_at`
- `raw_payload`
- `mode`

`mode` 在当前实现固定为 `SIMULATOR`。只有 `accepted=true` 才允许业务层推进到设备已接受状态；模拟器不得返回或暗示生产执行证明。

### 4.3 `FlightEvent`

标准事件只暴露固定外层字段：

```json
{
  "event_code": "telemetry",
  "event_time": "2026-06-19T05:00:00Z",
  "device_sn": "dock-sn-001",
  "raw_payload": {}
}
```

事件时间必须为 UTC ISO 8601。`raw_payload` 保留供应商或模拟器原始字段，不提升不稳定字段为固定外层契约。

### 4.4 `DjiDock3Simulator`

模拟器维护最小内存状态：已绑定设备、请求幂等记录和故障注入规则。它用于开发闭环，不持久化生产数据，也不访问互联网。

同一操作、租户和 `idempotency_key` 的同一请求重复调用时重放原回执；请求指纹不一致时返回 `IDEMP_409`。重复绑定使用不同幂等键时进入“设备已绑定”失败分支。

### 4.5 `GatewayFailure`

内部失败包含 `scenario`、`retryable` 和安全详情，向领域层映射固定错误码：

| 场景 | 错误码 | 可重试 |
| --- | --- | --- |
| credential_error | `DJI_502` | 否 |
| device_already_bound | `DJI_502` | 否 |
| format_error | `DJI_502` | 否 |
| timeout | `DJI_502` | 是 |
| device_no_response | `DJI_502` | 是 |
| checksum_error | `MEDIA_499` | 是 |

错误详情不得包含凭证、签名、完整供应商响应或其他秘密。

## 5. 数据流

### 5.1 设备动作

1. 业务层完成租户、角色、功能授权、状态机和幂等前置校验。
2. 业务层构造网关命令并调用 `DjiGateway`。
3. 网关实现调用模拟器或未来真实 DJI 客户端。
4. 网关返回 `GatewayReceipt` 或固定 `DomainError`。
5. 业务层仅依据已接受回执推进状态，并记录回执和审计。

### 5.2 回调事件

1. 模拟器或未来真实适配器接收原始事件。
2. 适配器校验必填字段与格式。
3. 适配器转换为 `FlightEvent`，原始内容保留在 `raw_payload`。
4. 后续 U1 事件处理器负责租户解析、重复回调幂等、状态更新和 `flight_events` 落库。

本增量不把回调直接写入 U0 数据库，避免在 U1 数据模型设计前形成临时表结构。

## 6. 网络与安全

- 领域业务服务只导入 `DjiGateway` 协议，不导入 HTTP 客户端或 DJI SDK。
- `DjiDock3Simulator` 禁止建立外网连接。
- 未来真实实现只能部署在大疆机场 3 适配网关网络区。
- 网络策略测试继续证明 `flight_service`、`analysis_service` 和 `training_service` 无互联网访问资格。
- 凭证只允许从运行环境秘密配置注入，不进入命令、事件、回执、日志或仓库。

## 7. 验证策略

采用测试驱动开发，至少覆盖：

- 协议运行时可检查性和模拟器接口一致性。
- 四类基线事件：绑定成功、遥测、低电量、媒体上传完成。
- 任务下发只在回执接受时标记成功。
- 六类规定失败分支及错误码、可重试属性。
- 固定四字段事件外层、UTC 时间和原始载荷保留。
- 同请求幂等重放、不同指纹冲突和不同路由键隔离。
- 模拟器模式显式为 `SIMULATOR`。
- 业务服务不能直接获得互联网访问资格。
- 现有 66 项项目回归测试无退化。

## 8. 完成定义

- 新协议与模拟器均有自动化测试，并完成逐项 RED-GREEN 证据。
- 现有 U1 规则测试迁移到新契约后继续通过。
- 没有引入真实 DJI API 假实现、生产凭证或未经登记的错误码。
- 文档和代码明确区分模拟能力与生产能力。
- 分支通过全量测试并形成独立提交，供后续 U1 数据模型和 API 增量复用。
