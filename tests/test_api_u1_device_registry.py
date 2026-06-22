import sys
import unittest
import warnings
from pathlib import Path
from tempfile import TemporaryDirectory

from sqlalchemy import delete, select

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

from app.bootstrap import bootstrap_u0
from app.database import build_session_factory
from app.main import create_app
from app.models import (
    AuditLogModel,
    Base,
    DeviceModel,
    DockModel,
    TenantFeatureEntitlementModel,
)


class DeviceRegistryReadApiTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = TemporaryDirectory()
        database_path = (Path(self.temp_dir.name) / "api.db").as_posix()
        self.database_url = f"sqlite+pysqlite:///{database_path}"
        self.session_factory = build_session_factory(self.database_url)
        Base.metadata.create_all(self.session_factory.kw["bind"])
        with self.session_factory() as session:
            bootstrap_u0(session)
            session.add_all(
                [
                    DeviceModel(
                        id="dev_a",
                        tenant_id="t_customer_001",
                        device_type="DOCK",
                        name="Customer A Dock",
                        manufacturer="DJI",
                        model="DJI Dock 3",
                        serial_number="DOCK-A-001",
                    ),
                    DeviceModel(
                        id="dev_b",
                        tenant_id="t_customer_002",
                        device_type="DOCK",
                        name="Customer B Dock",
                        manufacturer="DJI",
                        model="DJI Dock 3",
                        serial_number="DOCK-B-001",
                    ),
                ]
            )
            session.flush()
            session.add_all(
                [
                    DockModel(
                        id="dock_a",
                        tenant_id="t_customer_001",
                        device_id="dev_a",
                    ),
                    DockModel(
                        id="dock_b",
                        tenant_id="t_customer_002",
                        device_id="dev_b",
                    ),
                ]
            )
            session.commit()
        self.client = TestClient(create_app(database_url_override=self.database_url))

    def tearDown(self):
        self.client.close()
        self.client.app.state.session_factory.kw["bind"].dispose()
        self.session_factory.kw["bind"].dispose()
        self.temp_dir.cleanup()

    def test_customer_lists_only_own_devices_and_docks(self):
        headers = {"Authorization": "Bearer demo-customer-a"}

        devices = self.client.get("/api/v1/devices", headers=headers)
        docks = self.client.get("/api/v1/docks", headers=headers)

        self.assertEqual(devices.status_code, 200)
        self.assertEqual([item["id"] for item in devices.json()["items"]], ["dev_a"])
        self.assertEqual(docks.status_code, 200)
        self.assertEqual([item["id"] for item in docks.json()["items"]], ["dock_a"])

    def test_customer_reads_own_device_and_dock_details(self):
        headers = {"Authorization": "Bearer demo-customer-a"}

        device = self.client.get("/api/v1/devices/dev_a", headers=headers)
        dock = self.client.get("/api/v1/docks/dock_a", headers=headers)

        self.assertEqual(device.status_code, 200)
        self.assertEqual(device.json()["tenant_id"], "t_customer_001")
        self.assertEqual(dock.status_code, 200)
        self.assertEqual(dock.json()["device_id"], "dev_a")

    def test_platform_can_switch_tenant_for_registry_reads(self):
        response = self.client.get(
            "/api/v1/devices",
            headers={
                "Authorization": "Bearer demo-platform",
                "X-Tenant-Id": "t_customer_002",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual([item["id"] for item in response.json()["items"]], ["dev_b"])

    def test_customer_cannot_switch_tenant_for_registry_reads(self):
        response = self.client.get(
            "/api/v1/devices",
            headers={
                "Authorization": "Bearer demo-customer-a",
                "X-Tenant-Id": "t_customer_002",
            },
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["code"], "TENANT_403")

    def test_cross_tenant_detail_does_not_reveal_resource(self):
        response = self.client.get(
            "/api/v1/devices/dev_b",
            headers={
                "Authorization": "Bearer demo-customer-a",
                "X-Request-Id": "req_cross_tenant_device",
            },
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["code"], "TENANT_404")
        with self.session_factory() as session:
            audit = session.scalar(
                select(AuditLogModel).where(
                    AuditLogModel.request_id == "req_cross_tenant_device"
                )
            )
        self.assertEqual(audit.action, "registry_read_denied")
        self.assertEqual(audit.tenant_id, "t_customer_001")
        self.assertEqual(audit.code, "TENANT_404")

    def test_registry_read_requires_flight_control_entitlement(self):
        with self.session_factory() as session:
            session.execute(
                delete(TenantFeatureEntitlementModel).where(
                    TenantFeatureEntitlementModel.tenant_id == "t_customer_001",
                    TenantFeatureEntitlementModel.feature_code == "FLIGHT_CONTROL",
                )
            )
            session.commit()

        response = self.client.get(
            "/api/v1/docks",
            headers={
                "Authorization": "Bearer demo-customer-a",
                "X-Request-Id": "req_feature_denied",
            },
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["code"], "FEATURE_403")
        with self.session_factory() as session:
            audit = session.scalar(
                select(AuditLogModel).where(
                    AuditLogModel.request_id == "req_feature_denied"
                )
            )
        self.assertEqual(audit.action, "feature_denied")
        self.assertEqual(audit.resource_id, "FLIGHT_CONTROL")

    def test_openapi_exposes_registry_read_paths(self):
        paths = self.client.get("/openapi.json").json()["paths"]

        self.assertIn("/api/v1/devices", paths)
        self.assertIn("/api/v1/devices/{device_id}", paths)
        self.assertIn("/api/v1/docks", paths)
        self.assertIn("/api/v1/docks/{dock_id}", paths)


if __name__ == "__main__":
    unittest.main()
