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
    RoadAssetModel,
    TenantFeatureEntitlementModel,
)


class RouteManagementApiTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = TemporaryDirectory()
        database_path = (Path(self.temp_dir.name) / "api.db").as_posix()
        self.database_url = f"sqlite+pysqlite:///{database_path}"
        self.session_factory = build_session_factory(self.database_url)
        Base.metadata.create_all(self.session_factory.kw["bind"])
        models = __import__("app.models", fromlist=["RouteModel", "RouteVersionModel"])
        with self.session_factory() as session:
            bootstrap_u0(session)
            session.add_all(
                [
                    RoadAssetModel(
                        id="road_a",
                        tenant_id="t_customer_001",
                        route_code="G60",
                        road_name="G60 Main",
                        direction="UP",
                        start_stake=1000,
                        end_stake=2000,
                        geom_json={"type": "LineString", "coordinates": []},
                    ),
                    models.RouteModel(
                        id="route_a",
                        tenant_id="t_customer_001",
                        route_code="G60-DAILY",
                        name="G60 daily",
                        description="A route",
                    ),
                    models.RouteModel(
                        id="route_b",
                        tenant_id="t_customer_002",
                        route_code="G60-B",
                        name="G60 other tenant",
                    ),
                    models.RouteVersionModel(
                        id="rv_a",
                        tenant_id="t_customer_001",
                        route_id="route_a",
                        version="v1",
                        route_file_uri="t_customer_001/routes/g60/v1.wpml",
                        route_format="DJI_WPML",
                        checksum="sha256:" + "a" * 64,
                        path_geom_json={"type": "LineString", "coordinates": []},
                        asset_bindings=[{"asset_type": "road", "asset_id": "road_a"}],
                        validation_report={"simulated": True},
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

    def test_customer_lists_and_reads_own_routes_and_versions(self):
        headers = {"Authorization": "Bearer demo-customer-a"}

        routes = self.client.get("/api/v1/routes", headers=headers)
        route = self.client.get("/api/v1/routes/route_a", headers=headers)
        versions = self.client.get("/api/v1/routes/route_a/versions", headers=headers)
        version = self.client.get(
            "/api/v1/routes/route_a/versions/rv_a",
            headers=headers,
        )

        self.assertEqual(routes.status_code, 200)
        self.assertEqual([item["id"] for item in routes.json()["items"]], ["route_a"])
        self.assertEqual(route.status_code, 200)
        self.assertEqual(route.json()["route_code"], "G60-DAILY")
        self.assertEqual(versions.status_code, 200)
        self.assertEqual([item["id"] for item in versions.json()["items"]], ["rv_a"])
        self.assertEqual(version.status_code, 200)
        self.assertEqual(version.json()["version"], "v1")

    def test_cross_tenant_route_detail_returns_tenant_404_and_audits(self):
        response = self.client.get(
            "/api/v1/routes/route_b",
            headers={
                "Authorization": "Bearer demo-customer-a",
                "X-Request-Id": "req_cross_tenant_route",
            },
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["code"], "TENANT_404")
        with self.session_factory() as session:
            audit = session.scalar(
                select(AuditLogModel).where(
                    AuditLogModel.request_id == "req_cross_tenant_route"
                )
            )
        self.assertEqual(audit.action, "route_read_denied")

    def test_route_read_requires_flight_control_entitlement(self):
        with self.session_factory() as session:
            session.execute(
                delete(TenantFeatureEntitlementModel).where(
                    TenantFeatureEntitlementModel.tenant_id == "t_customer_001",
                    TenantFeatureEntitlementModel.feature_code == "FLIGHT_CONTROL",
                )
            )
            session.commit()

        response = self.client.get(
            "/api/v1/routes",
            headers={
                "Authorization": "Bearer demo-customer-a",
                "X-Request-Id": "req_route_feature_denied",
            },
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["code"], "FEATURE_403")

    def test_platform_admin_creates_route_and_version_once(self):
        route = self.client.post(
            "/api/v1/admin/routes",
            json={
                "route_code": "G35-DAILY",
                "name": "G35 daily",
                "description": "M1 route",
            },
            headers=self._platform_headers("create-route-g35"),
        )
        replay = self.client.post(
            "/api/v1/admin/routes",
            json={
                "route_code": "G35-DAILY",
                "name": "G35 daily",
                "description": "M1 route",
            },
            headers=self._platform_headers("create-route-g35"),
        )

        self.assertEqual(route.status_code, 200)
        self.assertEqual(replay.json(), route.json())
        version = self.client.post(
            f"/api/v1/admin/routes/{route.json()['id']}/versions",
            json={
                "version": "v1",
                "route_file_uri": "t_customer_001/routes/g35/v1.wpml",
                "route_format": "DJI_WPML",
                "checksum": "sha256:" + "e" * 64,
                "path_geom_json": {"type": "LineString", "coordinates": []},
                "asset_bindings": [{"asset_type": "road", "asset_id": "road_a"}],
                "validation_report": {"simulated": True},
            },
            headers=self._platform_headers("create-route-g35-v1"),
        )

        self.assertEqual(version.status_code, 200)
        self.assertEqual(version.json()["route_id"], route.json()["id"])

    def test_customer_cannot_write_route_and_denial_is_audited(self):
        response = self.client.post(
            "/api/v1/admin/routes",
            json={"route_code": "G45-DAILY", "name": "G45 daily"},
            headers={
                "Authorization": "Bearer demo-customer-a",
                "Idempotency-Key": "customer-route-write-denied",
                "X-Request-Id": "req_customer_route_write_denied",
            },
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["code"], "PERM_403")
        with self.session_factory() as session:
            audit = session.scalar(
                select(AuditLogModel).where(
                    AuditLogModel.request_id == "req_customer_route_write_denied"
                )
            )
        self.assertEqual(audit.action, "route_write_denied")

    def test_route_write_requires_idempotency_key(self):
        response = self.client.post(
            "/api/v1/admin/routes",
            json={"route_code": "G50-DAILY", "name": "G50 daily"},
            headers={
                "Authorization": "Bearer demo-platform",
                "X-Tenant-Id": "t_customer_001",
            },
        )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["code"], "IDEMP_409")

    def test_invalid_route_version_geometry_returns_gis_422(self):
        response = self.client.post(
            "/api/v1/admin/routes/route_a/versions",
            json={
                "version": "bad-geom",
                "route_file_uri": "t_customer_001/routes/bad/v1.wpml",
                "route_format": "DJI_WPML",
                "checksum": "sha256:" + "f" * 64,
                "path_geom_json": {"type": "Polygon", "coordinates": []},
            },
            headers=self._platform_headers("bad-version-geom"),
        )

        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["code"], "GIS_422")

    def test_openapi_exposes_route_paths(self):
        paths = self.client.get("/openapi.json").json()["paths"]

        self.assertIn("/api/v1/routes", paths)
        self.assertIn("/api/v1/routes/{route_id}", paths)
        self.assertIn("/api/v1/routes/{route_id}/versions", paths)
        self.assertIn("/api/v1/routes/{route_id}/versions/{version_id}", paths)
        self.assertIn("/api/v1/admin/routes", paths)
        self.assertIn("/api/v1/admin/routes/{route_id}", paths)
        self.assertIn("/api/v1/admin/routes/{route_id}/versions", paths)

    def _platform_headers(self, idempotency_key: str) -> dict[str, str]:
        return {
            "Authorization": "Bearer demo-platform",
            "X-Tenant-Id": "t_customer_001",
            "Idempotency-Key": idempotency_key,
        }


if __name__ == "__main__":
    unittest.main()
