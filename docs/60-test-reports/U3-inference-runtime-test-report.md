# U3 推理运行时兼容测试文档

## 验收范围

- `PredictRequest.backend` 仅允许 `nvidia` 或 `domestic`。
- `image_data` 与 `image_uri` 二选一。
- `PredictResponse.backend` 不静默切换。
- `Detection.geometry` 在 `bbox`、`mask`、`polyline` 中三选一。
- 双后端输出差异超过阈值时阻断发布。

## 自动化用例

| 用例 | 结果 |
| --- | --- |
| 非法 backend 返回 `RUNTIME_428` | PASS |
| 缺少输入源返回 `INFER_504` | PASS |
| 推理响应保留请求 backend | PASS |
| detection geometry 多选时拒绝 | PASS |
| NVIDIA 与国产后端置信度差异超过阈值时返回发布阻断 | PASS |

## 验收结论

U3 gRPC 契约规则级验收通过。当前国产后端为模拟/契约门禁，不代表真实国产 AI 加速卡适配完成；真实型号、驱动、SDK、镜像和性能基线未锁定前，不得进入硬件验收。
