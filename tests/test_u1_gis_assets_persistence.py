import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect
from sqlalchemy import select

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))
sys.path.insert(0, str(ROOT / "src"))

from app.bootstrap import bootstrap_u0
from app.database import build_session_factory
from app.models import (
    AuditLogModel,
    Base,
    BridgeAssetModel,
    CoordinateTransformModel,
    RoadAssetModel,
    SlopeAssetModel,
)
from app.repositories import RequestMeta
from drone_inspection.errors import DomainError


class GisAssetModelTests(unittest.TestCase):
    def test_metadata_contains_gis_asset_tables(self):
        expected = {
            "road_assets",
            "bridge_assets",
            "slope_assets",
            "coordinate_transforms",
        }

        self.assertTrue(expected.issubset(set(Base.metadata.tables)))

    def test_asset_models_register_required_constraints(self):
        road_constraints = {item.name for item in RoadAssetModel.__table__.constraints}
        bridge_constraints = {item.name for item in BridgeAssetModel.__table__.constraints}
        slope_constraints = {item.name for item in SlopeAssetModel.__table__.constraints}
        transform_constraints = {
            item.name for item in CoordinateTransformModel.__table__.constraints
        }

        self.assertIn("ck_road_assets_direction", road_constraints)
        self.assertIn("ck_road_assets_stake_range", road_constraints)
        self.assertIn("uq_road_assets_tenant_range", road_constraints)
        self.assertIn("uq_bridge_assets_tenant_code", bridge_constraints)
        self.assertIn("ck_bridge_assets_stake_no", bridge_constraints)
        self.assertIn("ck_slope_assets_side", slope_constraints)
        self.assertIn("ck_slope_assets_stake_range", slope_constraints)
        self.assertIn("uq_coordinate_transforms_scope", transform_constraints)
        self.assertIn("ck_coordinate_transforms_crs_pair", transform_constraints)

    def test_alembic_gis_assets_round_trip_sqlite(self):
        with TemporaryDirectory() as temp_dir:
            database_url = f"sqlite+pysqlite:///{Path(temp_dir) / 'test.db'}"
            config = Config(str(ROOT / "alembic.ini"))
            config.set_main_option("sqlalchemy.url", database_url)

            command.upgrade(config, "head")
            engine = build_session_factory(database_url).kw["bind"]
            try:
                tables = set(inspect(engine).get_table_names())
                self.assertIn("road_assets", tables)
                self.assertIn("bridge_assets", tables)
                self.assertIn("slope_assets", tables)
                self.assertIn("coordinate_transforms", tables)
            finally:
                engine.dispose()

            command.downgrade(config, "20260621_0002")
            engine = build_session_factory(database_url).kw["bind"]
            try:
                tables = set(inspect(engine).get_table_names())
                self.assertNotIn("road_assets", tables)
                self.assertNotIn("bridge_assets", tables)
                self.assertNotIn("slope_assets", tables)
                self.assertNotIn("coordinate_transforms", tables)
            finally:
                engine.dispose()

            command.upgrade(config, "head")
            engine = build_session_factory(database_url).kw["bind"]
            try:
                tables = set(inspect(engine).get_table_names())
                self.assertIn("coordinate_transforms", tables)
            finally:
                engine.dispose()


class GisAssetRepositoryTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = TemporaryDirectory()
        self.database_url = f"sqlite+pysqlite:///{Path(self.temp_dir.name) / 'repo.db'}"
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
                        structure_parts=["pier", "deck"],
                    ),
                    SlopeAssetModel(
                        id="slope_a",
                        tenant_id="t_customer_001",
                        slope_code="SL-A",
                        route_code="G60",
                        side="LEFT",
                        start_stake=1600,
                        end_stake=1800,
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

    def tearDown(self):
        self.session_factory.kw["bind"].dispose()
        self.temp_dir.cleanup()

    def test_lists_are_tenant_filtered(self):
        from app.gis_assets import GisAssetRepository

        with self.session_factory() as session:
            repo = GisAssetRepository(session)
            self.assertEqual(
                [item.id for item in repo.list_road_assets("t_customer_001")],
                ["road_a"],
            )
            self.assertEqual(
                [item.id for item in repo.list_road_assets("t_customer_002")],
                ["road_b"],
            )
            self.assertEqual(
                [item.id for item in repo.list_bridge_assets("t_customer_001")],
                ["bridge_a"],
            )
            self.assertEqual(
                [item.id for item in repo.list_slope_assets("t_customer_001")],
                ["slope_a"],
            )
            self.assertEqual(
                [item.id for item in repo.list_coordinate_transforms("t_customer_001")],
                ["ctr_a"],
            )

    def test_cross_tenant_detail_returns_tenant_404(self):
        from app.gis_assets import GisAssetRepository
        from drone_inspection.errors import DomainError

        with self.session_factory() as session:
            repo = GisAssetRepository(session)
            with self.assertRaises(DomainError) as ctx:
                repo.road_asset("t_customer_001", "road_b")
            self.assertEqual(ctx.exception.code, "TENANT_404")

    def test_serializers_do_not_drop_boundary_fields(self):
        from app.gis_assets import (
            GisAssetRepository,
            bridge_asset_payload,
            coordinate_transform_payload,
            road_asset_payload,
            slope_asset_payload,
        )

        with self.session_factory() as session:
            repo = GisAssetRepository(session)
            road = road_asset_payload(repo.road_asset("t_customer_001", "road_a"))
            bridge = bridge_asset_payload(
                repo.bridge_asset("t_customer_001", "bridge_a")
            )
            slope = slope_asset_payload(repo.slope_asset("t_customer_001", "slope_a"))
            transform = coordinate_transform_payload(
                repo.coordinate_transform("t_customer_001", "ctr_a")
            )

        self.assertEqual(road["crs"], "PENDING_CONFIRMATION")
        self.assertEqual(bridge["structure_parts"], ["pier", "deck"])
        self.assertEqual(slope["side"], "LEFT")
        self.assertEqual(transform["source_crs"], "WGS84")


class GisAssetServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = TemporaryDirectory()
        self.database_url = f"sqlite+pysqlite:///{Path(self.temp_dir.name) / 'svc.db'}"
        self.session_factory = build_session_factory(self.database_url)
        Base.metadata.create_all(self.session_factory.kw["bind"])
        with self.session_factory() as session:
            bootstrap_u0(session)
            session.add(
                BridgeAssetModel(
                    id="bridge_existing",
                    tenant_id="t_customer_001",
                    bridge_code="BR-EXIST",
                    bridge_name="Existing Bridge",
                    route_code="G60",
                    stake_no=1000,
                    geom_json={"type": "Point", "coordinates": [0, 0]},
                    structure_parts=[],
                )
            )
            session.add(
                CoordinateTransformModel(
                    id="ctr_existing",
                    tenant_id="t_customer_001",
                    source_crs="WGS84",
                    target_crs="CGCS2000",
                    method="CONFIG_ONLY",
                    params_json={"note": "pending"},
                    version="v1",
                    status="PENDING_CONFIRMATION",
                )
            )
            session.commit()

    def tearDown(self):
        self.session_factory.kw["bind"].dispose()
        self.temp_dir.cleanup()

    def test_creates_road_asset_once_with_idempotent_replay(self):
        from app.gis_assets import GisAssetService

        with self.session_factory() as session:
            service = GisAssetService(session)
            values = {
                "route_code": "G60",
                "road_name": "G60 Main",
                "direction": "UP",
                "start_stake": 1000,
                "end_stake": 2000,
                "geom_json": {"type": "LineString", "coordinates": []},
                "source": "MANUAL_IMPORT",
                "crs": "PENDING_CONFIRMATION",
                "data_version": "manual-v1",
            }
            first = service.create_road_asset(
                "u_platform_admin",
                "t_customer_001",
                values,
                "road-key",
                RequestMeta("req_road_create", "127.0.0.1"),
            )
            replay = service.create_road_asset(
                "u_platform_admin",
                "t_customer_001",
                values,
                "road-key",
                RequestMeta("req_road_create", "127.0.0.1"),
            )

        self.assertEqual(replay, first)
        self.assertEqual(first["tenant_id"], "t_customer_001")
        self.assertEqual(first["crs"], "PENDING_CONFIRMATION")

    def test_invalid_stake_range_returns_gis_422(self):
        from app.gis_assets import GisAssetService

        with self.session_factory() as session:
            service = GisAssetService(session)
            with self.assertRaises(DomainError) as raised:
                service.create_road_asset(
                    "u_platform_admin",
                    "t_customer_001",
                    {
                        "route_code": "G60",
                        "road_name": "Bad Range",
                        "direction": "UP",
                        "start_stake": 2000,
                        "end_stake": 1000,
                        "geom_json": {"type": "LineString", "coordinates": []},
                    },
                    "bad-range",
                    RequestMeta("req_bad_range", "127.0.0.1"),
                )
        self.assertEqual(raised.exception.code, "GIS_422")

    def test_invalid_geom_returns_gis_422(self):
        from app.gis_assets import GisAssetService

        with self.session_factory() as session:
            service = GisAssetService(session)
            with self.assertRaises(DomainError) as raised:
                service.create_slope_asset(
                    "u_platform_admin",
                    "t_customer_001",
                    {
                        "slope_code": "SL-BAD",
                        "route_code": "G60",
                        "start_stake": 100,
                        "end_stake": 200,
                        "side": "LEFT",
                        "geom_json": {"type": "Circle", "coordinates": []},
                    },
                    "bad-geom",
                    RequestMeta("req_bad_geom", "127.0.0.1"),
                )
        self.assertEqual(raised.exception.code, "GIS_422")

    def test_invalid_crs_returns_gis_422(self):
        from app.gis_assets import GisAssetService

        with self.session_factory() as session:
            service = GisAssetService(session)
            with self.assertRaises(DomainError) as raised:
                service.create_coordinate_transform(
                    "u_platform_admin",
                    "t_customer_001",
                    {
                        "source_crs": "BD09",
                        "target_crs": "CGCS2000",
                        "method": "CONFIG_ONLY",
                        "params_json": {},
                        "version": "v2",
                        "status": "PENDING_CONFIRMATION",
                    },
                    "bad-crs",
                    RequestMeta("req_bad_crs", "127.0.0.1"),
                )
        self.assertEqual(raised.exception.code, "GIS_422")

    def test_duplicate_bridge_code_returns_mission_422(self):
        from app.gis_assets import GisAssetService

        with self.session_factory() as session:
            service = GisAssetService(session)
            with self.assertRaises(DomainError) as raised:
                service.create_bridge_asset(
                    "u_platform_admin",
                    "t_customer_001",
                    {
                        "bridge_code": "BR-EXIST",
                        "bridge_name": "Duplicate Bridge",
                        "route_code": "G60",
                        "stake_no": 1200,
                        "geom_json": {"type": "Point", "coordinates": [0, 0]},
                        "structure_parts": [],
                    },
                    "duplicate-bridge",
                    RequestMeta("req_dup_bridge", "127.0.0.1"),
                )
        self.assertEqual(raised.exception.code, "MISSION_422")

    def test_same_idempotency_key_is_independent_between_tenants(self):
        from app.gis_assets import GisAssetService

        values = {
            "slope_code": "SL-IDEMP",
            "route_code": "G60",
            "start_stake": 100,
            "end_stake": 200,
            "side": "LEFT",
            "geom_json": {"type": "Polygon", "coordinates": []},
        }
        with self.session_factory() as session:
            service = GisAssetService(session)
            first = service.create_slope_asset(
                "u_platform_admin",
                "t_customer_001",
                values,
                "same-slope-key",
                RequestMeta("req_slope_a", "127.0.0.1"),
            )
            second = service.create_slope_asset(
                "u_platform_admin",
                "t_customer_002",
                values,
                "same-slope-key",
                RequestMeta("req_slope_b", "127.0.0.1"),
            )

        self.assertNotEqual(first["tenant_id"], second["tenant_id"])

    def test_updates_coordinate_transform_status_and_audits(self):
        from app.gis_assets import GisAssetService

        with self.session_factory() as session:
            service = GisAssetService(session)
            response = service.update_coordinate_transform(
                "u_platform_admin",
                "t_customer_001",
                "ctr_existing",
                {"status": "ACTIVE", "params_json": {"source": "manual-review"}},
                "update-transform",
                RequestMeta("req_ctr_update", "127.0.0.1"),
            )

        self.assertEqual(response["status"], "ACTIVE")
        with self.session_factory() as session:
            audit = session.scalar(
                select(AuditLogModel).where(
                    AuditLogModel.request_id == "req_ctr_update"
                )
            )
        self.assertEqual(audit.action, "coordinate_transform_updated")


if __name__ == "__main__":
    unittest.main()
