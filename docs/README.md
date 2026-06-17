# 无人机智能巡检系统文档目录

本目录用于持续软件版本开发迭代。正式开发、测试、验收和客户演示均优先引用本索引中的路径。

## 目录规则

| 目录 | 用途 | 维护原则 |
| --- | --- | --- |
| `00-baseline/` | 源文档、PRD、架构、API、路线图等基线文档 | 作为开发和验收的主依据，变更需形成版本记录 |
| `10-engineering-decisions/` | 技术栈、部署、代码结构、验收优先级等工程决策 | 保留决策结论、依据和后续遵循规则 |
| `20-domain-specs/` | 认证、角色、数据库、GIS、对象存储、算法、外部接口、前端范围等领域规则 | 作为正式编码和测试的输入，不与基线文档冲突 |
| `30-integrations/` | DJI、硬件、外部集成资料 | 未锁定项只能作为候选或待确认输入 |
| `40-delivery-tracking/` | 算法、硬件、验收项等交付跟踪表 | 用于持续闭环缺口，不替代验收报告 |
| `50-demo/` | 本地演示环境、账号、演示顺序 | 仅说明演示边界，不宣称生产能力 |
| `60-test-reports/` | U0-U7 与最终测试报告 | 每次关键迭代后更新测试结论和阻断项 |
| `90-archive/` | 旧版说明、历史材料 | 只作追溯，不作为当前开发入口 |

## 当前核心入口

- 基线：`00-baseline/PRD.md`
- 架构：`00-baseline/Architecture.md`
- API：`00-baseline/API.md`
- 路线图：`00-baseline/Roadmap.md`
- 源架构方案：`00-baseline/source-originals/无人机智能巡检系统_架构方案内部开发V2.0.md`
- 源功能说明书：`00-baseline/source-originals/无人机智能巡检系统_软件开发功能说明书V2.0.md`
- 技术栈：`10-engineering-decisions/本开发项目技术栈选型及依据.md`
- 部署策略：`10-engineering-decisions/部署环境目标与容器编排选型.md`
- 代码结构：`10-engineering-decisions/正式代码结构与服务拆分策略.md`
- 验收推进：`10-engineering-decisions/验收优先级与U0-U7推进策略.md`
- 演示说明：`50-demo/演示环境与账号说明.md`
- 最终测试报告：`60-test-reports/FINAL_TEST_REPORT.md`
- 14 算法跟踪：`40-delivery-tracking/algorithm-delivery-tracker.md`

## 合并与保留规则

1. 不把所有文档合并成一个大文档，避免版本迭代时互相干扰。
2. 同一主题只保留一个当前正式入口，旧版放入 `90-archive/`。
3. 决策类文档保留“建议、依据、执行口径”，便于后续追溯。
4. 测试报告独立存放，避免与需求、架构、演示说明混在一起。
5. 待确认事项必须继续标注“待确认”，不得写成已锁定条件。
