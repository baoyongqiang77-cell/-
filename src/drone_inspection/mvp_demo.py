from __future__ import annotations

from .flight import DjiDock3Simulator, MissionStateMachine
from .media_analysis import MediaAnalysisPipeline


TEST_COMMAND = (
    "& 'C:\\Users\\baoyongqiang\\.cache\\codex-runtimes\\codex-primary-runtime"
    "\\dependencies\\python\\python.exe' -m unittest discover -s tests -v"
)


def _unit_progress() -> list[dict[str, str]]:
    return [
        {
            "unit": "U0",
            "name": "基础工程",
            "code_status": "规则验收骨架已实现",
            "test_status": "PASS",
            "production_status": "待正式 API/数据库/统一身份工程化",
        },
        {
            "unit": "U1",
            "name": "飞控平台",
            "code_status": "DJI 模拟器、状态机、网络边界规则已实现",
            "test_status": "PASS",
            "production_status": "真实 DJI 设备/证书/API 待确认",
        },
        {
            "unit": "U2",
            "name": "媒体与分析主链路",
            "code_status": "媒体入库、抽帧、分析、事件、工单闭环已实现",
            "test_status": "PASS",
            "production_status": "真实对象存储、弱网和性能环境待集成",
        },
        {
            "unit": "U3",
            "name": "推理运行时",
            "code_status": "Predict 契约和双后端一致性门禁已实现",
            "test_status": "PASS",
            "production_status": "国产卡仍是候选硬件池，未最终锁定",
        },
        {
            "unit": "U4",
            "name": "数据标注平台",
            "code_status": "标注、复检、FROZEN 数据集、导出授权规则已实现",
            "test_status": "PASS",
            "production_status": "真实标注工具和导出包待工程化",
        },
        {
            "unit": "U5",
            "name": "训练与算法库",
            "code_status": "训练授权、模型指标、发布/回滚门禁已实现",
            "test_status": "PASS",
            "production_status": "真实训练环境和模型仓库待接入",
        },
        {
            "unit": "U6",
            "name": "一期 14 算法接入",
            "code_status": "14 算法清单和验收门禁已实现",
            "test_status": "PASS",
            "production_status": "BLOCKED",
        },
        {
            "unit": "U7",
            "name": "联调验收",
            "code_status": "系统级验收门禁已实现",
            "test_status": "PASS",
            "production_status": "BLOCKED",
        },
    ]


def _run_m1_workflow() -> list[dict[str, str]]:
    mission = MissionStateMachine(mission_id="ms_demo_001", tenant_id="t_customer_001")
    mission.transition("PENDING_APPROVAL", actor="pilot")
    mission.transition("APPROVED", actor="approver")
    mission.transition("DISPATCHING", actor="pilot")
    mission.apply_device_ack(accepted=True, actor="dji_gateway")

    simulator = DjiDock3Simulator()
    callback = simulator.bind_device("t_customer_001", "dock-demo-001")

    pipeline = MediaAnalysisPipeline()
    media = pipeline.ingest_media(
        tenant_id="t_customer_001",
        mission_id="ms_demo_001",
        storage_uri="t_customer_001/proj_demo/ms_demo_001/media/med_demo_001.mp4",
        checksum="sha256:demo",
        idempotency_key="demo-media-001",
    )
    frames = pipeline.extract_frames(media.id, count=1)
    task = pipeline.create_analysis_task(
        tenant_id="t_customer_001",
        media_file_id=media.id,
        algorithm_codes=["road_crack", "road_pothole"],
        priority="NORMAL",
    )
    event = pipeline.complete_analysis_with_detection(
        task_id=task.id,
        frame_asset_id=frames[0].id,
        label="road_crack",
        confidence=0.88,
    )
    work_order = pipeline.dispatch_work_order(event.id, actor="reviewer")

    return [
        {"name": "创建飞行任务", "status": mission.status, "evidence": "ms_demo_001"},
        {
            "name": "DJI 模拟回调",
            "status": callback.payload["event_code"],
            "evidence": callback.payload["device_sn"],
        },
        {"name": "媒体入库", "status": media.status, "evidence": media.id},
        {"name": "抽帧", "status": frames[0].status, "evidence": frames[0].id},
        {"name": "创建分析任务", "status": task.status, "evidence": task.id},
        {"name": "生成事件", "status": event.status, "evidence": event.id},
        {"name": "派发工单", "status": work_order.status, "evidence": work_order.id},
    ]


def build_demo_summary() -> dict:
    return {
        "scope": "内部验收型 MVP",
        "limitations": "不是完整产品级 Web MVP；不包含真实 DJI、真实 14 算法、真实国产卡实测和生产 Web 前端。",
        "test_command": TEST_COMMAND,
        "unit_progress": _unit_progress(),
        "m1_workflow": _run_m1_workflow(),
        "artifacts": [
            "docs/60-test-reports/FINAL_TEST_REPORT.md",
            "docs/40-delivery-tracking/algorithm-delivery-tracker.md",
            "docs/30-integrations/视觉算法计划支持显卡清单20260617.md",
        ],
    }


def format_demo_summary(summary: dict) -> str:
    lines = [
        "# 无人机智能巡检系统 MVP 展示",
        "",
        f"展示口径：{summary['scope']}",
        f"边界说明：{summary['limitations']}",
        "",
        "## 单元进度",
        "| 单元 | 名称 | 代码进展 | 测试 | 生产/真实验收 |",
        "| --- | --- | --- | --- | --- |",
    ]
    for item in summary["unit_progress"]:
        lines.append(
            "| {unit} | {name} | {code_status} | {test_status} | {production_status} |".format(
                **item
            )
        )

    lines.extend(
        [
            "",
            "## M1 模拟闭环",
            "| 步骤 | 状态 | 证据 |",
            "| --- | --- | --- |",
        ]
    )
    for step in summary["m1_workflow"]:
        lines.append("| {name} | {status} | {evidence} |".format(**step))

    lines.extend(
        [
            "",
            "## 自动化测试",
            "```powershell",
            summary["test_command"],
            "```",
            "",
            "## 展示材料",
        ]
    )
    lines.extend(f"- {artifact}" for artifact in summary["artifacts"])
    return "\n".join(lines)
