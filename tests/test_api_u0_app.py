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


if __name__ == "__main__":
    unittest.main()
