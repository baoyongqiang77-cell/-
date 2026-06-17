import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from drone_inspection.acceptance import AcceptanceInputs, SystemAcceptanceGate, p95


class U7AcceptanceTests(unittest.TestCase):
    def test_m1_passes_only_when_u0_to_u5_reports_pass(self):
        gate = SystemAcceptanceGate()
        inputs = AcceptanceInputs(
            unit_results={
                "U0": True,
                "U1": True,
                "U2": True,
                "U3": True,
                "U4": True,
                "U5": True,
            },
            locked_external_interfaces=False,
            locked_domestic_hardware=False,
            locked_network_boundary=True,
            algorithm_evidence_complete=False,
        )

        result = gate.evaluate_m1(inputs)
        self.assertTrue(result.passed)

        inputs.unit_results["U2"] = False
        self.assertFalse(gate.evaluate_m1(inputs).passed)

    def test_u7_production_acceptance_blocks_unlocked_dependencies(self):
        gate = SystemAcceptanceGate()
        inputs = AcceptanceInputs(
            unit_results={f"U{i}": True for i in range(0, 7)},
            locked_external_interfaces=False,
            locked_domestic_hardware=False,
            locked_network_boundary=True,
            algorithm_evidence_complete=True,
        )

        result = gate.evaluate_u7(inputs)
        self.assertFalse(result.passed)
        self.assertIn("外部生产接口未锁定", result.reason)
        self.assertIn("国产 AI 加速卡未锁定", result.reason)

    def test_performance_metrics_are_checked_with_p95_and_failure_rate(self):
        gate = SystemAcceptanceGate()

        self.assertEqual(p95([1, 2, 3, 4, 5]), 5)
        ok = gate.check_realtime_analysis(latencies_ms=[900, 1200, 2400, 2500], failures=0)
        slow = gate.check_realtime_analysis(latencies_ms=[900, 1200, 2400, 3500], failures=0)
        failing = gate.check_realtime_analysis(latencies_ms=[900] * 100, failures=2)

        self.assertTrue(ok.passed)
        self.assertFalse(slow.passed)
        self.assertFalse(failing.passed)


if __name__ == "__main__":
    unittest.main()
