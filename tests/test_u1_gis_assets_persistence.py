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


if __name__ == "__main__":
    unittest.main()
