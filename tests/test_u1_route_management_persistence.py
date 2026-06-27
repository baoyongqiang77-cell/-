import importlib
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, select

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))
sys.path.insert(0, str(ROOT / "src"))

from app.bootstrap import bootstrap_u0
from app.database import build_session_factory
from app.models import (
    AuditLogModel,
    Base,
    BridgeAssetModel,
    RoadAssetModel,
    SlopeAssetModel,
)
from app.repositories import RequestMeta
from drone_inspection.errors import DomainError


class RouteManagementModelTests(unittest.TestCase):
    def test_metadata_contains_route_tables(self):
        self.assertIn("routes", Base.metadata.tables)
        self.assertIn("route_versions", Base.metadata.tables)

    def test_route_models_register_required_constraints(self):
        models = importlib.import_module("app.models")
        route_constraints = {
            item.name for item in models.RouteModel.__table__.constraints
        }
        version_constraints = {
            item.name for item in models.RouteVersionModel.__table__.constraints
        }

        self.assertIn("uq_routes_tenant_code", route_constraints)
        self.assertIn("uq_route_versions_tenant_route_version", version_constraints)
        self.assertIn("ck_route_versions_route_format", version_constraints)
        self.assertIn("ck_route_versions_checksum", version_constraints)

    def test_alembic_route_management_round_trip_sqlite(self):
        with TemporaryDirectory() as temp_dir:
            database_url = f"sqlite+pysqlite:///{Path(temp_dir) / 'test.db'}"
            config = Config(str(ROOT / "alembic.ini"))
            config.set_main_option("sqlalchemy.url", database_url)

            command.upgrade(config, "head")
            engine = build_session_factory(database_url).kw["bind"]
            try:
                tables = set(inspect(engine).get_table_names())
                self.assertIn("routes", tables)
                self.assertIn("route_versions", tables)
            finally:
                engine.dispose()

            command.downgrade(config, "20260627_0003")
            engine = build_session_factory(database_url).kw["bind"]
            try:
                tables = set(inspect(engine).get_table_names())
                self.assertNotIn("routes", tables)
                self.assertNotIn("route_versions", tables)
            finally:
                engine.dispose()

            command.upgrade(config, "head")
            engine = build_session_factory(database_url).kw["bind"]
            try:
                self.assertIn("route_versions", set(inspect(engine).get_table_names()))
            finally:
                engine.dispose()


class RouteManagementServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = TemporaryDirectory()
        self.database_url = f"sqlite+pysqlite:///{Path(self.temp_dir.name) / 'svc.db'}"
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
                        road_name="G60 Main",
                        direction="UP",
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
                        structure_parts=[],
                    ),
                    SlopeAssetModel(
                        id="slope_b",
                        tenant_id="t_customer_002",
                        slope_code="SL-B",
                        route_code="G60",
                        start_stake=1500,
                        end_stake=1800,
                        side="LEFT",
                        geom_json={"type": "Polygon", "coordinates": []},
                    ),
                ]
            )
            session.commit()

    def tearDown(self):
        self.session_factory.kw["bind"].dispose()
        self.temp_dir.cleanup()

    def test_creates_route_once_with_idempotent_replay(self):
        service_module = importlib.import_module("app.route_management")
        with self.session_factory() as session:
            service = service_module.RouteManagementService(session)
            first = service.create_route(
                "u_platform_admin",
                "t_customer_001",
                {
                    "route_code": "G60-DAILY",
                    "name": "G60 daily inspection",
                    "description": "M1 route",
                },
                "route-create-key",
                RequestMeta("req_route_create", "127.0.0.1"),
            )
            replay = service.create_route(
                "u_platform_admin",
                "t_customer_001",
                {
                    "route_code": "G60-DAILY",
                    "name": "G60 daily inspection",
                    "description": "M1 route",
                },
                "route-create-key",
                RequestMeta("req_route_create", "127.0.0.1"),
            )

        self.assertEqual(replay, first)
        self.assertEqual(first["tenant_id"], "t_customer_001")
        self.assertEqual(first["route_code"], "G60-DAILY")

    def test_creates_traceable_version_with_same_tenant_asset_bindings(self):
        service_module = importlib.import_module("app.route_management")
        with self.session_factory() as session:
            service = service_module.RouteManagementService(session)
            route = service.create_route(
                "u_platform_admin",
                "t_customer_001",
                {"route_code": "G60-TRACE", "name": "Trace route"},
                "route-trace-key",
                RequestMeta("req_route_trace", "127.0.0.1"),
            )
            version = service.create_route_version(
                "u_platform_admin",
                "t_customer_001",
                route["id"],
                {
                    "version": "v1",
                    "route_file_uri": "t_customer_001/routes/g60/v1.wpml",
                    "route_format": "DJI_WPML",
                    "checksum": "sha256:" + "a" * 64,
                    "path_geom_json": {"type": "LineString", "coordinates": []},
                    "asset_bindings": [
                        {"asset_type": "road", "asset_id": "road_a"},
                        {"asset_type": "bridge", "asset_id": "bridge_a"},
                    ],
                    "validation_report": {"simulated": True},
                },
                "route-version-v1",
                RequestMeta("req_route_version", "127.0.0.1"),
            )

        self.assertEqual(version["route_id"], route["id"])
        self.assertEqual(version["version"], "v1")
        self.assertEqual(
            version["asset_bindings"],
            [
                {"asset_type": "road", "asset_id": "road_a"},
                {"asset_type": "bridge", "asset_id": "bridge_a"},
            ],
        )

    def test_cross_tenant_asset_binding_returns_tenant_404(self):
        service_module = importlib.import_module("app.route_management")
        with self.session_factory() as session:
            service = service_module.RouteManagementService(session)
            route = service.create_route(
                "u_platform_admin",
                "t_customer_001",
                {"route_code": "G60-BAD-ASSET", "name": "Bad asset route"},
                "bad-asset-route",
                RequestMeta("req_bad_asset_route", "127.0.0.1"),
            )
            with self.assertRaises(DomainError) as raised:
                service.create_route_version(
                    "u_platform_admin",
                    "t_customer_001",
                    route["id"],
                    {
                        "version": "v1",
                        "route_file_uri": "t_customer_001/routes/bad/v1.wpml",
                        "route_format": "DJI_WPML",
                        "checksum": "sha256:" + "b" * 64,
                        "path_geom_json": {"type": "LineString", "coordinates": []},
                        "asset_bindings": [
                            {"asset_type": "slope", "asset_id": "slope_b"}
                        ],
                    },
                    "bad-asset-version",
                    RequestMeta("req_bad_asset_version", "127.0.0.1"),
                )
        self.assertEqual(raised.exception.code, "TENANT_404")

    def test_invalid_path_geometry_returns_gis_422(self):
        service_module = importlib.import_module("app.route_management")
        with self.session_factory() as session:
            service = service_module.RouteManagementService(session)
            route = service.create_route(
                "u_platform_admin",
                "t_customer_001",
                {"route_code": "G60-BAD-GEOM", "name": "Bad geometry route"},
                "bad-geom-route",
                RequestMeta("req_bad_geom_route", "127.0.0.1"),
            )
            with self.assertRaises(DomainError) as raised:
                service.create_route_version(
                    "u_platform_admin",
                    "t_customer_001",
                    route["id"],
                    {
                        "version": "v1",
                        "route_file_uri": "t_customer_001/routes/bad-geom/v1.wpml",
                        "route_format": "DJI_WPML",
                        "checksum": "sha256:" + "c" * 64,
                        "path_geom_json": {"type": "Polygon", "coordinates": []},
                    },
                    "bad-geom-version",
                    RequestMeta("req_bad_geom_version", "127.0.0.1"),
                )
        self.assertEqual(raised.exception.code, "GIS_422")

    def test_invalid_checksum_returns_mission_422(self):
        service_module = importlib.import_module("app.route_management")
        with self.session_factory() as session:
            service = service_module.RouteManagementService(session)
            route = service.create_route(
                "u_platform_admin",
                "t_customer_001",
                {"route_code": "G60-BAD-CHECKSUM", "name": "Bad checksum route"},
                "bad-checksum-route",
                RequestMeta("req_bad_checksum_route", "127.0.0.1"),
            )
            with self.assertRaises(DomainError) as raised:
                service.create_route_version(
                    "u_platform_admin",
                    "t_customer_001",
                    route["id"],
                    {
                        "version": "v1",
                        "route_file_uri": "t_customer_001/routes/bad/v1.wpml",
                        "route_format": "DJI_WPML",
                        "checksum": "md5:not-allowed",
                        "path_geom_json": {"type": "LineString", "coordinates": []},
                    },
                    "bad-checksum-version",
                    RequestMeta("req_bad_checksum_version", "127.0.0.1"),
                )
        self.assertEqual(raised.exception.code, "MISSION_422")

    def test_duplicate_route_version_returns_mission_422(self):
        service_module = importlib.import_module("app.route_management")
        with self.session_factory() as session:
            service = service_module.RouteManagementService(session)
            route = service.create_route(
                "u_platform_admin",
                "t_customer_001",
                {"route_code": "G60-DUP", "name": "Duplicate route"},
                "dup-route",
                RequestMeta("req_dup_route", "127.0.0.1"),
            )
            payload = {
                "version": "v1",
                "route_file_uri": "t_customer_001/routes/dup/v1.wpml",
                "route_format": "DJI_WPML",
                "checksum": "sha256:" + "d" * 64,
                "path_geom_json": {"type": "LineString", "coordinates": []},
            }
            service.create_route_version(
                "u_platform_admin",
                "t_customer_001",
                route["id"],
                payload,
                "dup-version-1",
                RequestMeta("req_dup_version_1", "127.0.0.1"),
            )
            with self.assertRaises(DomainError) as raised:
                service.create_route_version(
                    "u_platform_admin",
                    "t_customer_001",
                    route["id"],
                    payload,
                    "dup-version-2",
                    RequestMeta("req_dup_version_2", "127.0.0.1"),
                )
        self.assertEqual(raised.exception.code, "MISSION_422")

    def test_route_update_writes_audit(self):
        service_module = importlib.import_module("app.route_management")
        with self.session_factory() as session:
            service = service_module.RouteManagementService(session)
            route = service.create_route(
                "u_platform_admin",
                "t_customer_001",
                {"route_code": "G60-UPD", "name": "Before"},
                "update-route",
                RequestMeta("req_update_route_create", "127.0.0.1"),
            )
            service.update_route(
                "u_platform_admin",
                "t_customer_001",
                route["id"],
                {"name": "After"},
                "update-route-name",
                RequestMeta("req_update_route", "127.0.0.1"),
            )

        with self.session_factory() as session:
            audit = session.scalar(
                select(AuditLogModel).where(
                    AuditLogModel.request_id == "req_update_route"
                )
            )
        self.assertEqual(audit.action, "route_updated")


if __name__ == "__main__":
    unittest.main()
