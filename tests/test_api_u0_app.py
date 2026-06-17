import sys
import unittest
import warnings
from pathlib import Path

warnings.filterwarnings(
    "ignore",
    message="Using `httpx` with `starlette.testclient` is deprecated.*",
    category=Warning,
    module="fastapi.testclient",
)

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))
sys.path.insert(0, str(ROOT / "src"))

from app.main import create_app


class U0ApiAppTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(create_app())

    def test_me_requires_authorization_and_uses_unified_error_shape(self):
        response = self.client.get("/api/v1/me")

        self.assertEqual(response.status_code, 401)
        body = response.json()
        self.assertEqual(body["code"], "AUTH_401")
        self.assertEqual(body["message"], "未认证或 Token 过期")
        self.assertTrue(body["request_id"].startswith("req_"))
        self.assertEqual(body["details"], {})

    def test_customer_tenant_context_exposes_default_features_only(self):
        response = self.client.get(
            "/api/v1/tenant-context",
            headers={"Authorization": "Bearer demo-customer-a"},
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["tenant"]["id"], "t_customer_001")
        self.assertEqual(body["tenant"]["tenant_type"], "CUSTOMER_TENANT")
        self.assertIn("FLIGHT_CONTROL", body["features"])
        self.assertIn("VISION_ANALYSIS_RESULT", body["features"])
        self.assertIn("DATA_ANNOTATION", body["features"])
        self.assertNotIn("MODEL_TRAINING", body["features"])
        self.assertNotIn("MODEL_RELEASE", body["features"])

    def test_customer_cannot_switch_tenant_with_x_tenant_id(self):
        response = self.client.get(
            "/api/v1/tenant-context",
            headers={
                "Authorization": "Bearer demo-customer-a",
                "X-Tenant-Id": "t_customer_002",
            },
        )

        self.assertEqual(response.status_code, 403)
        body = response.json()
        self.assertEqual(body["code"], "TENANT_403")
        self.assertEqual(body["details"]["target_tenant_id"], "t_customer_002")

    def test_platform_operator_can_switch_to_customer_tenant(self):
        response = self.client.get(
            "/api/v1/tenant-context",
            headers={
                "Authorization": "Bearer demo-platform",
                "X-Tenant-Id": "t_customer_001",
            },
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["tenant"]["id"], "t_customer_001")
        self.assertEqual(body["actor"]["id"], "u_platform_admin")
        self.assertIn("t_customer_002", body["switchable_tenant_ids"])

    def test_openapi_exposes_u0_entrypoints(self):
        response = self.client.get("/openapi.json")

        self.assertEqual(response.status_code, 200)
        paths = response.json()["paths"]
        self.assertIn("/api/v1/me", paths)
        self.assertIn("/api/v1/tenant-context", paths)
        self.assertIn("/api/v1/admin/tenants/{tenant_id}/feature-entitlements", paths)
        self.assertIn("/api/v1/admin/tenant-data-grants", paths)

    def test_platform_can_enable_customer_feature_with_idempotency(self):
        payload = {"feature_code": "MODEL_TRAINING"}
        headers = {
            "Authorization": "Bearer demo-platform",
            "Idempotency-Key": "feature-enable-001",
        }

        first = self.client.post(
            "/api/v1/admin/tenants/t_customer_001/feature-entitlements",
            json=payload,
            headers=headers,
        )
        replay = self.client.post(
            "/api/v1/admin/tenants/t_customer_001/feature-entitlements",
            json=payload,
            headers=headers,
        )

        self.assertEqual(first.status_code, 200)
        self.assertEqual(replay.status_code, 200)
        self.assertEqual(replay.json(), first.json())
        self.assertEqual(first.json()["feature_code"], "MODEL_TRAINING")

        context = self.client.get(
            "/api/v1/tenant-context",
            headers={"Authorization": "Bearer demo-customer-a"},
        )
        self.assertIn("MODEL_TRAINING", context.json()["features"])

    def test_idempotency_key_rejects_conflicting_admin_write(self):
        headers = {
            "Authorization": "Bearer demo-platform",
            "Idempotency-Key": "feature-conflict-001",
        }
        first = self.client.post(
            "/api/v1/admin/tenants/t_customer_001/feature-entitlements",
            json={"feature_code": "MODEL_TRAINING"},
            headers=headers,
        )
        conflict = self.client.post(
            "/api/v1/admin/tenants/t_customer_001/feature-entitlements",
            json={"feature_code": "MODEL_RELEASE"},
            headers=headers,
        )

        self.assertEqual(first.status_code, 200)
        self.assertEqual(conflict.status_code, 409)
        self.assertEqual(conflict.json()["code"], "IDEMP_409")

    def test_platform_can_register_customer_data_grant(self):
        response = self.client.post(
            "/api/v1/admin/tenant-data-grants",
            json={
                "owner_tenant_id": "t_customer_001",
                "grantee_tenant_id": "t_jxjtsz_platform",
                "purpose": ["training", "evaluation"],
                "data_scope": {"sample_ids": ["sample_001", "sample_002"]},
            },
            headers={
                "Authorization": "Bearer demo-platform",
                "Idempotency-Key": "data-grant-001",
            },
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["owner_tenant_id"], "t_customer_001")
        self.assertEqual(body["grantee_tenant_id"], "t_jxjtsz_platform")
        self.assertEqual(body["purpose"], ["evaluation", "training"])
        self.assertEqual(body["sample_ids"], ["sample_001", "sample_002"])

    def test_customer_cannot_use_admin_write_endpoints(self):
        response = self.client.post(
            "/api/v1/admin/tenants/t_customer_001/feature-entitlements",
            json={"feature_code": "MODEL_TRAINING"},
            headers={
                "Authorization": "Bearer demo-customer-a",
                "Idempotency-Key": "customer-denied-001",
            },
        )

        self.assertEqual(response.status_code, 403)
        body = response.json()
        self.assertEqual(body["code"], "PERM_403")
        self.assertEqual(body["details"]["required_tenant_type"], "PLATFORM_OPERATOR")

    def test_invalid_tenant_does_not_poison_idempotency_record(self):
        headers = {
            "Authorization": "Bearer demo-platform",
            "Idempotency-Key": "invalid-tenant-001",
        }
        first = self.client.post(
            "/api/v1/admin/tenants/t_missing/feature-entitlements",
            json={"feature_code": "MODEL_TRAINING"},
            headers=headers,
        )
        replay = self.client.post(
            "/api/v1/admin/tenants/t_missing/feature-entitlements",
            json={"feature_code": "MODEL_TRAINING"},
            headers=headers,
        )

        self.assertEqual(first.status_code, 404)
        self.assertEqual(replay.status_code, 404)
        self.assertEqual(first.json()["code"], "TENANT_404")
        self.assertEqual(replay.json()["code"], "TENANT_404")

    def test_data_grant_requires_existing_tenants(self):
        response = self.client.post(
            "/api/v1/admin/tenant-data-grants",
            json={
                "owner_tenant_id": "t_missing",
                "grantee_tenant_id": "t_jxjtsz_platform",
                "purpose": ["training"],
                "data_scope": {"sample_ids": ["sample_001"]},
            },
            headers={
                "Authorization": "Bearer demo-platform",
                "Idempotency-Key": "missing-grant-tenant-001",
            },
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["code"], "TENANT_404")

    def test_invalid_feature_code_uses_unified_validation_error(self):
        response = self.client.post(
            "/api/v1/admin/tenants/t_customer_001/feature-entitlements",
            json={"feature_code": "UNREGISTERED_FEATURE"},
            headers={
                "Authorization": "Bearer demo-platform",
                "Idempotency-Key": "invalid-feature-001",
            },
        )

        self.assertEqual(response.status_code, 422)
        body = response.json()
        self.assertEqual(body["code"], "MISSION_422")
        self.assertEqual(body["message"], "请求参数不满足接口要求")
        self.assertTrue(body["request_id"].startswith("req_"))
        self.assertIn("field_errors", body["details"])
        self.assertNotIn("detail", body)

    def test_missing_required_body_field_uses_unified_validation_error(self):
        response = self.client.post(
            "/api/v1/admin/tenant-data-grants",
            json={
                "owner_tenant_id": "t_customer_001",
                "grantee_tenant_id": "t_jxjtsz_platform",
                "data_scope": {"sample_ids": ["sample_001"]},
            },
            headers={
                "Authorization": "Bearer demo-platform",
                "Idempotency-Key": "missing-purpose-001",
            },
        )

        self.assertEqual(response.status_code, 422)
        body = response.json()
        self.assertEqual(body["code"], "MISSION_422")
        self.assertEqual(body["message"], "请求参数不满足接口要求")
        self.assertTrue(body["request_id"].startswith("req_"))
        self.assertIn("field_errors", body["details"])
        self.assertNotIn("detail", body)


if __name__ == "__main__":
    unittest.main()
