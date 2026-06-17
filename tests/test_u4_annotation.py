import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from drone_inspection.constants import FeatureCode
from drone_inspection.errors import DomainError
from drone_inspection.foundation import PlatformState
from drone_inspection.annotation import AnnotationService


class U4AnnotationTests(unittest.TestCase):
    def setUp(self):
        self.state = PlatformState.bootstrap()
        self.service = AnnotationService(self.state)

    def test_customer_can_only_annotate_assigned_samples_in_own_tenant(self):
        own = self.service.add_sample("t_customer_001", "frm_001")
        other = self.service.add_sample("t_customer_002", "frm_002")

        task = self.service.create_task(
            tenant_id="t_customer_001",
            algorithm_code="road_crack",
            sample_ids=[own.id],
            assignee="annotator_a",
        )
        annotation = self.service.submit_annotation(
            task_id=task.id,
            sample_id=own.id,
            annotation_type="polyline",
            actor="annotator_a",
        )
        self.service.review(task.id, passed=False, actor="reviewer", reason="line too short")
        self.service.submit_annotation(
            task_id=task.id,
            sample_id=own.id,
            annotation_type="polyline",
            actor="annotator_a",
        )
        self.service.review(task.id, passed=True, actor="reviewer", reason="ok")

        self.assertEqual(annotation.tenant_id, "t_customer_001")
        self.assertEqual(self.service.tasks[task.id].status, "FINAL_PASSED")

        with self.assertRaises(DomainError) as raised:
            self.service.create_task(
                tenant_id="t_customer_001",
                algorithm_code="road_crack",
                sample_ids=[other.id],
                assignee="annotator_a",
            )
        self.assertEqual(raised.exception.code, "TENANT_403")

    def test_frozen_dataset_is_immutable_and_customer_export_needs_feature(self):
        sample = self.service.add_sample("t_customer_001", "frm_001")
        dataset = self.service.create_dataset("t_customer_001", "road_crack", [sample.id])
        self.service.freeze_dataset(dataset.id)

        with self.assertRaises(DomainError) as raised:
            self.service.add_sample_to_dataset(dataset.id, sample.id)
        self.assertEqual(raised.exception.code, "STATE_409")

        with self.assertRaises(DomainError) as raised:
            self.service.export_dataset(dataset.id, actor="customer_user")
        self.assertEqual(raised.exception.code, "FEATURE_403")

        self.state.enable_feature("t_customer_001", FeatureCode.DATASET_EXPORT)
        exported = self.service.export_dataset(dataset.id, actor="customer_user")
        self.assertTrue(exported.startswith("t_customer_001/datasets/"))


if __name__ == "__main__":
    unittest.main()
