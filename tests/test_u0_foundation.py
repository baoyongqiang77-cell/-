import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from drone_inspection.constants import FeatureCode
from drone_inspection.errors import DomainError
from drone_inspection.foundation import PlatformState


class U0FoundationTests(unittest.TestCase):
    def setUp(self):
        self.state = PlatformState.bootstrap()

    def test_customer_tenant_has_only_default_customer_features(self):
        customer = self.state.tenant_context("t_customer_001")

        self.assertEqual(customer.tenant_type, "CUSTOMER_TENANT")
        self.assertTrue(customer.has_feature(FeatureCode.FLIGHT_CONTROL))
        self.assertTrue(customer.has_feature(FeatureCode.VISION_ANALYSIS_RESULT))
        self.assertTrue(customer.has_feature(FeatureCode.DATA_ANNOTATION))
        self.assertFalse(customer.has_feature(FeatureCode.MODEL_TRAINING))
        self.assertFalse(customer.has_feature(FeatureCode.MODEL_RELEASE))
        self.assertFalse(customer.has_feature(FeatureCode.PLATFORM_OPS))

    def test_unentitled_customer_feature_returns_feature_403_and_audits(self):
        with self.assertRaises(DomainError) as raised:
            self.state.require_feature(
                tenant_id="t_customer_001",
                feature=FeatureCode.MODEL_TRAINING,
                actor="customer_user",
            )

        self.assertEqual(raised.exception.code, "FEATURE_403")
        self.assertTrue(
            self.state.audit_contains(
                tenant_id="t_customer_001",
                action="feature_denied",
                code="FEATURE_403",
            )
        )

    def test_customer_data_grant_is_required_before_training(self):
        with self.assertRaises(DomainError) as raised:
            self.state.require_data_grant(
                owner_tenant_id="t_customer_001",
                grantee_tenant_id="t_jxjtsz_platform",
                purpose="training",
                sample_ids=["sample_001"],
            )

        self.assertEqual(raised.exception.code, "DATA_GRANT_412")

        self.state.add_data_grant(
            owner_tenant_id="t_customer_001",
            grantee_tenant_id="t_jxjtsz_platform",
            purposes=["training", "evaluation"],
            sample_ids=["sample_001"],
        )
        self.assertTrue(
            self.state.require_data_grant(
                owner_tenant_id="t_customer_001",
                grantee_tenant_id="t_jxjtsz_platform",
                purpose="training",
                sample_ids=["sample_001"],
            )
        )

    def test_idempotency_replays_same_result_and_rejects_conflict(self):
        first = self.state.idempotency.record(
            key="idem-001",
            request_fingerprint="create:mission:A",
            response={"id": "ms_001", "status": "DRAFT"},
        )
        replay = self.state.idempotency.record(
            key="idem-001",
            request_fingerprint="create:mission:A",
            response={"id": "different"},
        )

        self.assertEqual(replay, first)

        with self.assertRaises(DomainError) as raised:
            self.state.idempotency.record(
                key="idem-001",
                request_fingerprint="create:mission:B",
                response={"id": "ms_002"},
            )
        self.assertEqual(raised.exception.code, "IDEMP_409")

    def test_object_storage_path_is_tenant_scoped(self):
        path = self.state.object_path(
            tenant_id="t_customer_001",
            project_id="proj_001",
            mission_id="ms_001",
            filename="media.mp4",
        )

        self.assertEqual(path, "t_customer_001/proj_001/ms_001/media.mp4")


if __name__ == "__main__":
    unittest.main()
