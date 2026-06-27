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


if __name__ == "__main__":
    unittest.main()
