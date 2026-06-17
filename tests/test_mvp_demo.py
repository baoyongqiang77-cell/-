import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from drone_inspection.mvp_demo import build_demo_summary


class MvpDemoTests(unittest.TestCase):
    def test_demo_summary_declares_internal_mvp_scope_and_artifacts(self):
        summary = build_demo_summary()

        self.assertEqual(summary["scope"], "内部验收型 MVP")
        self.assertIn("不是完整产品级 Web MVP", summary["limitations"])
        self.assertIn("python", summary["test_command"])
        self.assertIn("docs/60-test-reports/FINAL_TEST_REPORT.md", summary["artifacts"])
        self.assertIn("docs/40-delivery-tracking/algorithm-delivery-tracker.md", summary["artifacts"])

    def test_demo_summary_contains_u0_to_u7_progress_and_m1_workflow(self):
        summary = build_demo_summary()
        progress = summary["unit_progress"]
        workflow = summary["m1_workflow"]

        self.assertEqual([item["unit"] for item in progress], [f"U{i}" for i in range(8)])
        self.assertEqual(progress[6]["production_status"], "BLOCKED")
        self.assertEqual(progress[7]["production_status"], "BLOCKED")
        self.assertEqual(
            [step["name"] for step in workflow],
            [
                "创建飞行任务",
                "DJI 模拟回调",
                "媒体入库",
                "抽帧",
                "创建分析任务",
                "生成事件",
                "派发工单",
            ],
        )
        self.assertEqual(workflow[-1]["status"], "DISPATCHED")


if __name__ == "__main__":
    unittest.main()
