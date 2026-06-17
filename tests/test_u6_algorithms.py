import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from drone_inspection.algorithms import AlgorithmEvidence, AlgorithmRegistry


class U6AlgorithmTests(unittest.TestCase):
    def test_registry_contains_exactly_the_fixed_14_phase_one_algorithms(self):
        registry = AlgorithmRegistry.phase_one()

        self.assertEqual(
            registry.codes(),
            [
                "traffic_congestion",
                "pedestrian_intrusion",
                "two_wheeler_intrusion",
                "road_obstacle",
                "road_construction",
                "road_crack",
                "road_pothole",
                "road_water",
                "marking_blur",
                "helmet_missing",
                "vest_missing",
                "guardrail_damage",
                "barrier_damage",
                "bridge_under_space_stacking",
            ],
        )

    def test_simulated_algorithm_cannot_count_toward_m2_acceptance(self):
        registry = AlgorithmRegistry.phase_one()
        result = registry.validate_evidence(
            "road_crack",
            AlgorithmEvidence(
                real_model=False,
                metrics={"map50": 0.99, "recall": 0.99},
                frozen_dataset_checksum="sha256:frozen",
                replay_record_uri="reports/replay-road-crack.md",
                manual_sampling_record_uri="reports/manual-road-crack.md",
            ),
        )

        self.assertFalse(result.passed)
        self.assertIn("模拟算法不得计入 M2", result.reason)

    def test_real_algorithm_evidence_must_meet_metrics_and_records(self):
        registry = AlgorithmRegistry.phase_one()
        result = registry.validate_evidence(
            "road_crack",
            AlgorithmEvidence(
                real_model=True,
                metrics={"map50": 0.76, "recall": 0.81},
                frozen_dataset_checksum="sha256:frozen",
                replay_record_uri="reports/replay-road-crack.md",
                manual_sampling_record_uri="reports/manual-road-crack.md",
            ),
        )

        self.assertTrue(result.passed)

        all_result = registry.validate_all({})
        self.assertFalse(all_result.passed)
        self.assertIn("缺少 14 算法验收证据", all_result.reason)


if __name__ == "__main__":
    unittest.main()
