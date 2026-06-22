import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from alembic import command
from alembic.config import Config
from sqlalchemy import CheckConstraint, create_engine, func, inspect, select
from sqlalchemy.exc import IntegrityError


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))
sys.path.insert(0, str(ROOT / "src"))

from app.bootstrap import bootstrap_u0
from app.database import build_session_factory
from app.device_registry import DeviceRegistryRepository, DeviceRegistryService
from app.models import AuditLogModel, Base, DeviceModel, DockModel
from app.repositories import RequestMeta
from drone_inspection.errors import DomainError


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


class DeviceRegistryRepositoryTests(unittest.TestCase):
    def setUp(self):
        self.factory = build_session_factory("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.factory.kw["bind"])
        self.session = self.factory()
        bootstrap_u0(self.session)
        self.session.add_all(
            [
                DeviceModel(
                    id="dev_customer_a",
                    tenant_id="t_customer_001",
                    device_type="DOCK",
                    name="客户A机场",
                    manufacturer="DJI",
                    model="DJI Dock 3",
                    serial_number="DOCK-A-001",
                ),
                DeviceModel(
                    id="dev_customer_b",
                    tenant_id="t_customer_002",
                    device_type="DOCK",
                    name="客户B机场",
                    manufacturer="DJI",
                    model="DJI Dock 3",
                    serial_number="DOCK-B-001",
                ),
            ]
        )
        self.session.flush()
        self.session.add_all(
            [
                DockModel(
                    id="dock_customer_a",
                    tenant_id="t_customer_001",
                    device_id="dev_customer_a",
                ),
                DockModel(
                    id="dock_customer_b",
                    tenant_id="t_customer_002",
                    device_id="dev_customer_b",
                ),
            ]
        )
        self.session.commit()
        self.repository = DeviceRegistryRepository(self.session)

    def tearDown(self):
        self.session.close()
        self.factory.kw["bind"].dispose()

    def test_list_devices_is_always_tenant_filtered(self):
        items = self.repository.list_devices("t_customer_001")

        self.assertEqual([item.id for item in items], ["dev_customer_a"])

    def test_cross_tenant_device_detail_returns_tenant_404(self):
        with self.assertRaises(DomainError) as raised:
            self.repository.device("t_customer_001", "dev_customer_b")

        self.assertEqual(raised.exception.code, "TENANT_404")

    def test_serial_lookup_is_reserved_for_internal_status_sync(self):
        item = self.repository.device_by_serial("DOCK-A-001")

        self.assertEqual(item.tenant_id, "t_customer_001")

    def test_list_and_detail_docks_are_tenant_filtered(self):
        items = self.repository.list_docks("t_customer_002")

        self.assertEqual([item.id for item in items], ["dock_customer_b"])
        with self.assertRaises(DomainError) as raised:
            self.repository.dock("t_customer_002", "dock_customer_a")
        self.assertEqual(raised.exception.code, "TENANT_404")


class DeviceRegistryServiceTests(unittest.TestCase):
    def setUp(self):
        self.factory = build_session_factory("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.factory.kw["bind"])
        self.session = self.factory()
        bootstrap_u0(self.session)
        self.service = DeviceRegistryService(self.session)

    def tearDown(self):
        self.session.close()
        self.factory.kw["bind"].dispose()

    def test_creates_device_once_with_idempotent_replay(self):
        values = self._device_values("DOCK", "DOCK-A-001", "机场一号")

        first = self.service.create_device(
            actor_id="u_platform_admin",
            tenant_id="t_customer_001",
            values=values,
            idempotency_key="device-create-001",
            request_meta=RequestMeta("req_device_001", "127.0.0.1"),
        )
        replay = self.service.create_device(
            actor_id="u_platform_admin",
            tenant_id="t_customer_001",
            values=values,
            idempotency_key="device-create-001",
            request_meta=RequestMeta("req_device_001", "127.0.0.1"),
        )

        self.assertEqual(replay, first)
        self.assertEqual(
            self.session.scalar(select(func.count(DeviceModel.id))),
            1,
        )
        self.assertEqual(
            self.session.scalar(
                select(func.count(AuditLogModel.id)).where(
                    AuditLogModel.action == "device_created"
                )
            ),
            1,
        )

    def test_same_key_is_independent_between_target_tenants(self):
        first = self._create_device(
            "t_customer_001",
            "DOCK-A-001",
            "shared-key",
        )
        second = self._create_device(
            "t_customer_002",
            "DOCK-B-001",
            "shared-key",
        )

        self.assertNotEqual(first["tenant_id"], second["tenant_id"])

    def test_duplicate_serial_returns_mission_422(self):
        self._create_device("t_customer_001", "DOCK-A-001", "first-key")

        with self.assertRaises(DomainError) as raised:
            self._create_device("t_customer_002", "DOCK-A-001", "duplicate-key")

        self.assertEqual(raised.exception.code, "MISSION_422")

    def test_device_update_changes_only_allowed_fields(self):
        created = self._create_device(
            "t_customer_001",
            "DOCK-A-001",
            "device-create",
        )

        result = self.service.update_device(
            actor_id="u_platform_admin",
            tenant_id="t_customer_001",
            device_id=created["id"],
            values={"name": "机场一号更新", "firmware_version": "1.1.0"},
            idempotency_key="device-update-001",
            request_meta=RequestMeta("req_device_update", None),
        )

        self.assertEqual(result["name"], "机场一号更新")
        self.assertEqual(result["firmware_version"], "1.1.0")
        self.assertIsNone(result["status"])

    def test_dock_rejects_wrong_device_type(self):
        drone = self._create_device(
            "t_customer_001",
            "DRONE-A-001",
            "drone-create",
            device_type="DRONE",
        )

        with self.assertRaises(DomainError) as raised:
            self.service.create_dock(
                actor_id="u_platform_admin",
                tenant_id="t_customer_001",
                values={"device_id": drone["id"]},
                idempotency_key="dock-create-wrong-type",
                request_meta=RequestMeta("req_dock_wrong", None),
            )

        self.assertEqual(raised.exception.code, "MISSION_422")

    def test_dock_create_and_update_validate_tenant_and_types(self):
        dock_device = self._create_device(
            "t_customer_001", "DOCK-A-001", "dock-device-create"
        )
        drone = self._create_device(
            "t_customer_001",
            "DRONE-A-001",
            "drone-create",
            device_type="DRONE",
        )
        edge = self._create_device(
            "t_customer_001",
            "EDGE-A-001",
            "edge-create",
            device_type="EDGE_NODE",
        )
        created = self.service.create_dock(
            actor_id="u_platform_admin",
            tenant_id="t_customer_001",
            values={"device_id": dock_device["id"]},
            idempotency_key="dock-create",
            request_meta=RequestMeta("req_dock_create", None),
        )

        updated = self.service.update_dock(
            actor_id="u_platform_admin",
            tenant_id="t_customer_001",
            dock_id=created["id"],
            values={
                "bound_drone_device_id": drone["id"],
                "edge_node_device_id": edge["id"],
            },
            idempotency_key="dock-update",
            request_meta=RequestMeta("req_dock_update", None),
        )

        self.assertEqual(updated["bound_drone_device_id"], drone["id"])
        self.assertEqual(updated["edge_node_device_id"], edge["id"])
        audit = self.session.scalar(
            select(AuditLogModel).where(
                AuditLogModel.action == "dock_updated"
            )
        )
        self.assertEqual(audit.tenant_id, "t_customer_001")
        self.assertEqual(audit.request_id, "req_dock_update")

    def test_cross_tenant_dock_association_returns_tenant_404(self):
        dock_device = self._create_device(
            "t_customer_001", "DOCK-A-001", "dock-device-create"
        )
        other_drone = self._create_device(
            "t_customer_002",
            "DRONE-B-001",
            "other-drone-create",
            device_type="DRONE",
        )

        with self.assertRaises(DomainError) as raised:
            self.service.create_dock(
                actor_id="u_platform_admin",
                tenant_id="t_customer_001",
                values={
                    "device_id": dock_device["id"],
                    "bound_drone_device_id": other_drone["id"],
                },
                idempotency_key="dock-cross-tenant",
                request_meta=RequestMeta("req_dock_cross", None),
            )

        self.assertEqual(raised.exception.code, "TENANT_404")

    def _create_device(
        self,
        tenant_id: str,
        serial_number: str,
        key: str,
        *,
        device_type: str = "DOCK",
    ) -> dict:
        return self.service.create_device(
            actor_id="u_platform_admin",
            tenant_id=tenant_id,
            values=self._device_values(
                device_type,
                serial_number,
                serial_number,
            ),
            idempotency_key=key,
            request_meta=RequestMeta(f"req_{key}", None),
        )

    @staticmethod
    def _device_values(
        device_type: str,
        serial_number: str,
        name: str,
    ) -> dict:
        return {
            "device_type": device_type,
            "name": name,
            "manufacturer": "DJI",
            "model": "DJI Dock 3" if device_type == "DOCK" else None,
            "serial_number": serial_number,
            "firmware_version": "1.0.0",
        }

if __name__ == "__main__":
    unittest.main()
