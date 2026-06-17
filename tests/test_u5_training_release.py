import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from drone_inspection.errors import DomainError
from drone_inspection.foundation import PlatformState
from drone_inspection.training import TrainingReleaseService


class U5TrainingReleaseTests(unittest.TestCase):
    def setUp(self):
        self.state = PlatformState.bootstrap()
        self.service = TrainingReleaseService(self.state)

    def test_customer_training_is_denied_by_default(self):
        with self.assertRaises(DomainError) as raised:
            self.service.create_training_job(
                actor_tenant_id="t_customer_001",
                dataset_owner_tenant_id="t_customer_001",
                sample_ids=["sample_001"],
                algorithm_code="road_crack",
            )
        self.assertEqual(raised.exception.code, "FEATURE_403")

    def test_platform_training_customer_data_requires_data_grant(self):
        with self.assertRaises(DomainError) as raised:
            self.service.create_training_job(
                actor_tenant_id="t_jxjtsz_platform",
                dataset_owner_tenant_id="t_customer_001",
                sample_ids=["sample_001"],
                algorithm_code="road_crack",
            )
        self.assertEqual(raised.exception.code, "DATA_GRANT_412")

        self.state.add_data_grant(
            owner_tenant_id="t_customer_001",
            grantee_tenant_id="t_jxjtsz_platform",
            purposes=["training", "evaluation"],
            sample_ids=["sample_001"],
        )
        job = self.service.create_training_job(
            actor_tenant_id="t_jxjtsz_platform",
            dataset_owner_tenant_id="t_customer_001",
            sample_ids=["sample_001"],
            algorithm_code="road_crack",
        )
        self.assertEqual(job.status, "CREATED")

    def test_model_must_meet_metrics_and_have_dual_artifacts_before_release(self):
        version = self.service.create_model_version(
            algorithm_code="road_crack",
            metrics={"map50": 0.70, "recall": 0.80},
        )
        with self.assertRaises(DomainError) as raised:
            self.service.publish_release(
                actor_tenant_id="t_jxjtsz_platform",
                model_version_id=version.id,
                target_tenant_id="t_customer_001",
            )
        self.assertEqual(raised.exception.code, "MODEL_412")

        ready = self.service.create_model_version(
            algorithm_code="road_crack",
            metrics={"map50": 0.76, "recall": 0.81},
        )
        self.service.add_runtime_artifact(ready.id, backend="nvidia", image_digest="sha256:nv")
        self.service.add_runtime_artifact(ready.id, backend="domestic", image_digest="sha256:dm")
        release = self.service.publish_release(
            actor_tenant_id="t_jxjtsz_platform",
            model_version_id=ready.id,
            target_tenant_id="t_customer_001",
        )
        rollback = self.service.rollback_release(release.id, actor_tenant_id="t_jxjtsz_platform")

        self.assertEqual(release.status, "ACTIVE")
        self.assertEqual(rollback.status, "ROLLED_BACK")
        self.assertTrue(
            self.state.audit_contains(
                tenant_id="t_jxjtsz_platform",
                action="model_release",
                code=None,
            )
        )


if __name__ == "__main__":
    unittest.main()
