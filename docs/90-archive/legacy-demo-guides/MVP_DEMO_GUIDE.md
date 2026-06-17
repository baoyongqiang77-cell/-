# MVP 展示说明

## 1. 展示口径

当前可展示的是“内部验收型 MVP”，用于说明平台主链路规则、租户权限边界、M1 模拟闭环和 U6/U7 门禁，不是完整产品级 Web MVP。

可以展示：

- U0-U7 当前代码进展和测试进展。
- M1 模拟链路：飞行任务、DJI 模拟回调、媒体入库、抽帧、分析、事件、工单。
- 客户租户默认权限边界。
- 训练、发布、数据授权、双硬件一致性和 14 算法验收门禁。
- 最终测试文档与 14 算法交付跟踪表。

不能承诺：

- 真实 DJI 飞控已接入。
- 真实 14 算法模型已验收。
- 国产卡已最终锁定或已完成实测。
- 生产 Web 前端、生产 API、生产数据库和外部系统已完成。

## 2. 展示命令

在项目根目录执行：

```powershell
& 'C:\Users\baoyongqiang\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' scripts\mvp_demo.py
```

输出内容包括：

- 展示口径和边界说明。
- U0-U7 单元进度表。
- M1 模拟闭环步骤和证据 ID。
- 自动化测试命令。
- 关键展示材料路径。

## 3. 验证命令

展示前建议先跑全量测试：

```powershell
& 'C:\Users\baoyongqiang\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m unittest discover -s tests -v
```

预期结果：

- 自动化测试全部通过。
- 如测试数量变化，以最新命令输出为准。

## 4. 展示顺序建议

1. 打开 `docs/tests/FINAL_TEST_REPORT.md`，说明当前结论：规则级通过，真实生产验收仍有阻断项。
2. 执行 `scripts\mvp_demo.py`，展示 U0-U7 进度和 M1 模拟闭环。
3. 打开 `docs/algorithm-delivery-tracker.md`，说明 14 算法真实模型交付缺口如何逐项闭合。
4. 打开 `docs/视觉算法计划支持显卡清单20260617.md`，说明它是候选硬件池，不是最终硬件锁定结论。
5. 最后说明下一阶段：接入真实 API 服务、前端页面、真实算法模型、冻结验收集和最终国产卡测试机。

## 5. 关键材料

- `scripts/mvp_demo.py`
- `src/drone_inspection/mvp_demo.py`
- `docs/tests/FINAL_TEST_REPORT.md`
- `docs/algorithm-delivery-tracker.md`
- `docs/视觉算法计划支持显卡清单20260617.md`
