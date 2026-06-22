import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from alembic import command
from alembic.config import Config
from sqlalchemy import CheckConstraint, create_engine, inspect
from sqlalchemy.exc import IntegrityError


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))
sys.path.insert(0, str(ROOT / "src"))

from app.bootstrap import bootstrap_u0
from app.database import build_session_factory
from app.models import Base, DeviceModel, DockModel


class DeviceRegistryModelTests(unittest.TestCase):
    def test_metadata_contains_device_registry_tables(self):
        self.assertIn("devices", Base.metadata.tables)
        self.assertIn("docks", Base.metadata.tables)

    def test_devices_register_only_documented_types_and_statuses(self):
        table = Base.metadata.tables["devices"]
        checks = {
            str(item.sqltext)
            for item in table.constraints
            if isinstance(item, CheckConstraint)
        }

        self.assertTrue(
            any("DOCK" in value and "EDGE_NODE" in value for value in checks)
        )
        self.assertTrue(
            any("ONLINE" in value and "OFFLINE" in value for value in checks)
        )

    def test_docks_use_composite_tenant_foreign_keys(self):
        table = Base.metadata.tables["docks"]
        references = {
            tuple(element.target_fullname for element in constraint.elements)
            for constraint in table.foreign_key_constraints
        }

        self.assertIn(("devices.tenant_id", "devices.id"), references)

    def test_alembic_device_registry_round_trip_sqlite(self):
        with TemporaryDirectory() as temp_dir:
            database_path = (Path(temp_dir) / "migration.db").as_posix()
            url = f"sqlite+pysqlite:///{database_path}"
            config = Config(str(ROOT / "alembic.ini"))
            config.set_main_option("sqlalchemy.url", url)

            command.upgrade(config, "head")
            self.assertEqual(
                self._registry_tables(url),
                {"devices", "docks"},
            )

            command.downgrade(config, "20260618_0001")
            self.assertEqual(self._registry_tables(url), set())

            command.upgrade(config, "head")
            self.assertEqual(
                self._registry_tables(url),
                {"devices", "docks"},
            )

    def test_database_rejects_cross_tenant_dock_relationship(self):
        factory = build_session_factory("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(factory.kw["bind"])
        try:
            with factory() as session:
                bootstrap_u0(session)
                session.add_all(
                    [
                        DeviceModel(
                            id="dev_dock_a",
                            tenant_id="t_customer_001",
                            device_type="DOCK",
                            name="机场一号",
                            manufacturer="DJI",
                            model="DJI Dock 3",
                            serial_number="DOCK-A-001",
                        ),
                        DeviceModel(
                            id="dev_drone_b",
                            tenant_id="t_customer_002",
                            device_type="DRONE",
                            name="无人机二号",
                            manufacturer="DJI",
                            model=None,
                            serial_number="DRONE-B-001",
                        ),
                    ]
                )
                session.flush()
                session.add(
                    DockModel(
                        id="dock_a",
                        tenant_id="t_customer_001",
                        device_id="dev_dock_a",
                        bound_drone_device_id="dev_drone_b",
                    )
                )

                with self.assertRaises(IntegrityError):
                    session.flush()
        finally:
            factory.kw["bind"].dispose()

    @staticmethod
    def _registry_tables(url: str) -> set[str]:
        engine = create_engine(url)
        try:
            return {"devices", "docks"}.intersection(
                inspect(engine).get_table_names()
            )
        finally:
            engine.dispose()


if __name__ == "__main__":
    unittest.main()
