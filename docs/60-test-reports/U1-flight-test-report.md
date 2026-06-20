# U1 飞控平台功能测试文档

## 验收范围

- U1-F01 `DjiGateway` 统一业务协议与大疆机场 3 适配层模拟器。
- 设备绑定、状态同步、任务下发、遥测、异常和媒体同步六项能力。
- 模拟设备动作回执、请求幂等和确定性故障注入。
- `schema:flight_event_payload` 回调字段规范。
- 飞行任务状态机与非法跳转拒绝。
- 仅大疆机场 3 适配网关允许访问互联网的网络边界规则。

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

## 自动化命令

```powershell
& '.\.venv\Scripts\python.exe' -m unittest tests.test_u1_dji_gateway_contract tests.test_u1_flight -v
```

## 未纳入本增量

- DJI Cloud API 版本、凭证、回调签名、配套无人机和载荷型号仍待确认。
- 模拟器仅作为 M1 开发证据，不能满足真实飞行或生产验收。
- 设备、航线、任务、审批、遥测 WebSocket 和 `flight_events` 持久化属于后续 U1 增量。

## 验收结论

U1-F01 网关契约、开发模拟器和状态机规则级验收通过。当前结果证明统一接口和模拟闭环可用，不代表真实 DJI 飞控或生产网络验收通过。
