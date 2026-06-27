import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))
sys.path.insert(0, str(ROOT / "src"))

from app.bootstrap import bootstrap_u0
from app.database import build_session_factory
from app.models import (
    Base,
    BridgeAssetModel,
    CoordinateTransformModel,
    RoadAssetModel,
    SlopeAssetModel,
)


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


if __name__ == "__main__":
    unittest.main()
