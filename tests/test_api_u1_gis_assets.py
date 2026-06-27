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
    BridgeAssetModel,
    CoordinateTransformModel,
    RoadAssetModel,
    SlopeAssetModel,
    TenantFeatureEntitlementModel,
)


class GisAssetReadApiTests(unittest.TestCase):
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
                    RoadAssetModel(
                        id="road_a",
                        tenant_id="t_customer_001",
                        route_code="G60",
                        road_name="G60 A",
                        direction="UP",
                        start_stake=1000,
                        end_stake=2000,
                        geom_json={"type": "LineString", "coordinates": []},
                    ),
                    RoadAssetModel(
                        id="road_b",
                        tenant_id="t_customer_002",
                        route_code="G60",
                        road_name="G60 B",
                        direction="DOWN",
                        start_stake=1000,
                        end_stake=2000,
                        geom_json={"type": "LineString", "coordinates": []},
                    ),
                    BridgeAssetModel(
                        id="bridge_a",
                        tenant_id="t_customer_001",
                        bridge_code="BR-A",
                        bridge_name="Bridge A",
                        route_code="G60",
                        stake_no=1500,
                        geom_json={"type": "Point", "coordinates": [0, 0]},
                        structure_parts=["deck"],
                    ),
                    SlopeAssetModel(
                        id="slope_a",
                        tenant_id="t_customer_001",
                        slope_code="SL-A",
                        route_code="G60",
                        start_stake=1600,
                        end_stake=1700,
                        side="LEFT",
                        geom_json={"type": "Polygon", "coordinates": []},
                    ),
                    CoordinateTransformModel(
                        id="ctr_a",
                        tenant_id="t_customer_001",
                        source_crs="WGS84",
                        target_crs="CGCS2000",
                        method="CONFIG_ONLY",
                        params_json={"note": "pending"},
                        version="v1",
                        status="PENDING_CONFIRMATION",
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

    def test_customer_lists_only_own_gis_assets(self):
        headers = {"Authorization": "Bearer demo-customer-a"}

        roads = self.client.get("/api/v1/gis/road-assets", headers=headers)
        bridges = self.client.get("/api/v1/gis/bridge-assets", headers=headers)
        slopes = self.client.get("/api/v1/gis/slope-assets", headers=headers)

        self.assertEqual(roads.status_code, 200)
        self.assertEqual([item["id"] for item in roads.json()["items"]], ["road_a"])
        self.assertEqual(bridges.status_code, 200)
        self.assertEqual([item["id"] for item in bridges.json()["items"]], ["bridge_a"])
        self.assertEqual(slopes.status_code, 200)
        self.assertEqual([item["id"] for item in slopes.json()["items"]], ["slope_a"])

    def test_customer_reads_own_asset_details_and_transform(self):
        headers = {"Authorization": "Bearer demo-customer-a"}

        road = self.client.get("/api/v1/gis/road-assets/road_a", headers=headers)
        transform = self.client.get(
            "/api/v1/gis/coordinate-transforms/ctr_a",
            headers=headers,
        )

        self.assertEqual(road.status_code, 200)
        self.assertEqual(road.json()["tenant_id"], "t_customer_001")
        self.assertEqual(transform.status_code, 200)
        self.assertEqual(transform.json()["source_crs"], "WGS84")

    def test_cross_tenant_detail_returns_tenant_404_and_audits(self):
        response = self.client.get(
            "/api/v1/gis/road-assets/road_b",
            headers={
                "Authorization": "Bearer demo-customer-a",
                "X-Request-Id": "req_cross_tenant_road",
            },
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["code"], "TENANT_404")
        with self.session_factory() as session:
            audit = session.scalar(
                select(AuditLogModel).where(
                    AuditLogModel.request_id == "req_cross_tenant_road"
                )
            )
        self.assertEqual(audit.action, "gis_asset_read_denied")
        self.assertEqual(audit.tenant_id, "t_customer_001")

    def test_platform_can_switch_tenant_for_reads(self):
        response = self.client.get(
            "/api/v1/gis/road-assets",
            headers={
                "Authorization": "Bearer demo-platform",
                "X-Tenant-Id": "t_customer_002",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual([item["id"] for item in response.json()["items"]], ["road_b"])

    def test_customer_cannot_switch_tenant_for_reads(self):
        response = self.client.get(
            "/api/v1/gis/road-assets",
            headers={
                "Authorization": "Bearer demo-customer-a",
                "X-Tenant-Id": "t_customer_002",
            },
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["code"], "TENANT_403")

    def test_gis_read_requires_flight_control_entitlement(self):
        with self.session_factory() as session:
            session.execute(
                delete(TenantFeatureEntitlementModel).where(
                    TenantFeatureEntitlementModel.tenant_id == "t_customer_001",
                    TenantFeatureEntitlementModel.feature_code == "FLIGHT_CONTROL",
                )
            )
            session.commit()

        response = self.client.get(
            "/api/v1/gis/bridge-assets",
            headers={
                "Authorization": "Bearer demo-customer-a",
                "X-Request-Id": "req_gis_feature_denied",
            },
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["code"], "FEATURE_403")
        with self.session_factory() as session:
            audit = session.scalar(
                select(AuditLogModel).where(
                    AuditLogModel.request_id == "req_gis_feature_denied"
                )
            )
        self.assertEqual(audit.action, "feature_denied")

    def test_openapi_exposes_gis_asset_paths(self):
        paths = self.client.get("/openapi.json").json()["paths"]

        self.assertIn("/api/v1/gis/road-assets", paths)
        self.assertIn("/api/v1/gis/road-assets/{asset_id}", paths)
        self.assertIn("/api/v1/gis/bridge-assets", paths)
        self.assertIn("/api/v1/gis/bridge-assets/{asset_id}", paths)
        self.assertIn("/api/v1/gis/slope-assets", paths)
        self.assertIn("/api/v1/gis/slope-assets/{asset_id}", paths)
        self.assertIn("/api/v1/gis/coordinate-transforms", paths)
        self.assertIn("/api/v1/gis/coordinate-transforms/{transform_id}", paths)


class GisAssetWriteApiTests(GisAssetReadApiTests):
    def test_platform_admin_creates_road_asset_once_for_target_tenant(self):
        payload = {
            "route_code": "G35",
            "road_name": "G35 Main",
            "direction": "UP",
            "start_stake": 100,
            "end_stake": 300,
            "geom_json": {"type": "LineString", "coordinates": []},
            "source": "MANUAL_IMPORT",
            "crs": "PENDING_CONFIRMATION",
            "data_version": "manual-v1",
        }
        headers = self._platform_headers("create-road-g35")

        first = self.client.post(
            "/api/v1/admin/gis/road-assets",
            json=payload,
            headers=headers,
        )
        replay = self.client.post(
            "/api/v1/admin/gis/road-assets",
            json=payload,
            headers=headers,
        )

        self.assertEqual(first.status_code, 200)
        self.assertEqual(replay.json(), first.json())
        self.assertEqual(first.json()["tenant_id"], "t_customer_001")

    def test_customer_cannot_write_gis_asset_and_denial_is_audited(self):
        response = self.client.post(
            "/api/v1/admin/gis/road-assets",
            json=self._road_create_payload("G45"),
            headers={
                "Authorization": "Bearer demo-customer-a",
                "Idempotency-Key": "customer-gis-write-denied",
                "X-Request-Id": "req_customer_gis_write_denied",
            },
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["code"], "PERM_403")
        with self.session_factory() as session:
            audit = session.scalar(
                select(AuditLogModel).where(
                    AuditLogModel.request_id == "req_customer_gis_write_denied"
                )
            )
        self.assertEqual(audit.action, "gis_asset_write_denied")
        self.assertEqual(audit.code, "PERM_403")

    def test_gis_write_requires_idempotency_key(self):
        response = self.client.post(
            "/api/v1/admin/gis/road-assets",
            json=self._road_create_payload("G50"),
            headers={
                "Authorization": "Bearer demo-platform",
                "X-Tenant-Id": "t_customer_001",
            },
        )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["code"], "IDEMP_409")

    def test_gis_write_rejects_conflicting_idempotency_payload(self):
        headers = self._platform_headers("gis-conflict-key")
        first = self.client.post(
            "/api/v1/admin/gis/road-assets",
            json=self._road_create_payload("G51"),
            headers=headers,
        )
        conflict = self.client.post(
            "/api/v1/admin/gis/road-assets",
            json=self._road_create_payload("G52"),
            headers=headers,
        )

        self.assertEqual(first.status_code, 200)
        self.assertEqual(conflict.status_code, 409)
        self.assertEqual(conflict.json()["code"], "IDEMP_409")

    def test_gis_write_rejects_server_managed_fields(self):
        payload = self._road_create_payload("G53")
        payload.update({"tenant_id": "t_customer_002", "created_at": "2026-01-01T00:00:00Z"})

        response = self.client.post(
            "/api/v1/admin/gis/road-assets",
            json=payload,
            headers=self._platform_headers("forbidden-gis-fields"),
        )

        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["code"], "MISSION_422")

    def test_invalid_geometry_returns_gis_422(self):
        payload = self._road_create_payload("G54")
        payload["geom_json"] = {"type": "Circle", "coordinates": []}

        response = self.client.post(
            "/api/v1/admin/gis/road-assets",
            json=payload,
            headers=self._platform_headers("invalid-geometry"),
        )

        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["code"], "GIS_422")

    def test_invalid_crs_returns_gis_422(self):
        payload = {
            "source_crs": "BD09",
            "target_crs": "CGCS2000",
            "method": "CONFIG_ONLY",
            "params_json": {},
            "version": "v2",
            "status": "PENDING_CONFIRMATION",
        }

        response = self.client.post(
            "/api/v1/admin/gis/coordinate-transforms",
            json=payload,
            headers=self._platform_headers("invalid-crs"),
        )

        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["code"], "GIS_422")

    def test_duplicate_bridge_code_returns_mission_422(self):
        payload = {
            "bridge_code": "BR-A",
            "bridge_name": "Duplicate Bridge",
            "route_code": "G60",
            "stake_no": 1600,
            "geom_json": {"type": "Point", "coordinates": [0, 0]},
            "structure_parts": [],
        }

        response = self.client.post(
            "/api/v1/admin/gis/bridge-assets",
            json=payload,
            headers=self._platform_headers("duplicate-bridge-code"),
        )

        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["code"], "MISSION_422")

    def test_platform_admin_updates_slope_and_coordinate_transform(self):
        slope = self.client.patch(
            "/api/v1/admin/gis/slope-assets/slope_a",
            json={"side": "BOTH", "data_version": "manual-v2"},
            headers=self._platform_headers("update-slope-a"),
        )
        transform = self.client.patch(
            "/api/v1/admin/gis/coordinate-transforms/ctr_a",
            json={"status": "ACTIVE", "params_json": {"source": "manual-review"}},
            headers=self._platform_headers("update-transform-a"),
        )

        self.assertEqual(slope.status_code, 200)
        self.assertEqual(slope.json()["side"], "BOTH")
        self.assertEqual(transform.status_code, 200)
        self.assertEqual(transform.json()["status"], "ACTIVE")

    def test_openapi_exposes_gis_admin_paths(self):
        paths = self.client.get("/openapi.json").json()["paths"]

        self.assertIn("/api/v1/admin/gis/road-assets", paths)
        self.assertIn("/api/v1/admin/gis/road-assets/{asset_id}", paths)
        self.assertIn("/api/v1/admin/gis/bridge-assets", paths)
        self.assertIn("/api/v1/admin/gis/bridge-assets/{asset_id}", paths)
        self.assertIn("/api/v1/admin/gis/slope-assets", paths)
        self.assertIn("/api/v1/admin/gis/slope-assets/{asset_id}", paths)
        self.assertIn("/api/v1/admin/gis/coordinate-transforms", paths)
        self.assertIn(
            "/api/v1/admin/gis/coordinate-transforms/{transform_id}",
            paths,
        )

    def _platform_headers(self, idempotency_key: str) -> dict[str, str]:
        return {
            "Authorization": "Bearer demo-platform",
            "X-Tenant-Id": "t_customer_001",
            "Idempotency-Key": idempotency_key,
        }

    @staticmethod
    def _road_create_payload(route_code: str) -> dict:
        return {
            "route_code": route_code,
            "road_name": f"{route_code} Main",
            "direction": "UP",
            "start_stake": 100,
            "end_stake": 300,
            "geom_json": {"type": "LineString", "coordinates": []},
            "source": "MANUAL_IMPORT",
            "crs": "PENDING_CONFIRMATION",
            "data_version": "manual-v1",
        }


if __name__ == "__main__":
    unittest.main()
