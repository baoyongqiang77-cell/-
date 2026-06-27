import importlib
import sys
import unittest
from datetime import datetime, timezone
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
    DeviceModel,
    DockModel,
    RoadAssetModel,
    RouteModel,
    RouteVersionModel,
)
from app.repositories import RequestMeta
from drone_inspection.errors import DomainError


class MissionModelTests(unittest.TestCase):
    def test_metadata_contains_missions_table(self):
        self.assertIn("missions", Base.metadata.tables)

    def test_mission_model_registers_required_constraints(self):
        models = importlib.import_module("app.models")
        constraints = {item.name for item in models.MissionModel.__table__.constraints}

        self.assertIn("ck_missions_status", constraints)
        self.assertIn("fk_missions_tenant_route", constraints)
        self.assertIn("fk_missions_tenant_route_version", constraints)
        self.assertIn("fk_missions_tenant_device", constraints)

    def test_alembic_mission_creation_round_trip_sqlite(self):
        with TemporaryDirectory() as temp_dir:
            database_url = f"sqlite+pysqlite:///{Path(temp_dir) / 'test.db'}"
            config = Config(str(ROOT / "alembic.ini"))
            config.set_main_option("sqlalchemy.url", database_url)

            command.upgrade(config, "head")
            engine = build_session_factory(database_url).kw["bind"]
            try:
                self.assertIn("missions", set(inspect(engine).get_table_names()))
            finally:
                engine.dispose()

            command.downgrade(config, "20260627_0004")
            engine = build_session_factory(database_url).kw["bind"]
            try:
                self.assertNotIn("missions", set(inspect(engine).get_table_names()))
            finally:
                engine.dispose()


class MissionServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = TemporaryDirectory()
        self.database_url = f"sqlite+pysqlite:///{Path(self.temp_dir.name) / 'svc.db'}"
        self.session_factory = build_session_factory(self.database_url)
        Base.metadata.create_all(self.session_factory.kw["bind"])
        with self.session_factory() as session:
            bootstrap_u0(session)
            session.add_all(
                [
                    DeviceModel(
                        id="dev_dock_a",
                        tenant_id="t_customer_001",
                        device_type="DOCK",
                        name="Dock A",
                        manufacturer="DJI",
                        serial_number="dock-a",
                    ),
                    DeviceModel(
                        id="dev_drone_b",
                        tenant_id="t_customer_002",
                        device_type="DRONE",
                        name="Drone B",
                        manufacturer="DJI",
                        serial_number="drone-b",
                    ),
                    DockModel(
                        id="dock_a",
                        tenant_id="t_customer_001",
                        device_id="dev_dock_a",
                    ),
                    RoadAssetModel(
                        id="road_a",
                        tenant_id="t_customer_001",
                        route_code="G60",
                        road_name="G60 Main",
                        direction="UP",
                        start_stake=100,
                        end_stake=200,
                        geom_json={"type": "LineString", "coordinates": []},
                    ),
                    RouteModel(
                        id="route_a",
                        tenant_id="t_customer_001",
                        route_code="G60-DAILY",
                        name="G60 daily",
                    ),
                    RouteVersionModel(
                        id="rv_a",
                        tenant_id="t_customer_001",
                        route_id="route_a",
                        version="v1",
                        route_file_uri="t_customer_001/routes/g60/v1.wpml",
                        route_format="DJI_WPML",
                        checksum="sha256:" + "a" * 64,
                        path_geom_json={"type": "LineString", "coordinates": []},
                    ),
                ]
            )
            session.commit()

    def tearDown(self):
        self.session_factory.kw["bind"].dispose()
        self.temp_dir.cleanup()

    def _payload(self) -> dict:
        return {
            "route_id": "route_a",
            "route_version_id": "rv_a",
            "device_id": "dev_dock_a",
            "dock_id": "dock_a",
            "schedule_time": datetime(2026, 7, 1, 9, 0, tzinfo=timezone.utc),
            "inspection_targets": [{"asset_type": "road", "asset_id": "road_a"}],
            "media_policy": {"video": True, "image_interval_sec": 2},
        }

    def test_creates_draft_mission_once_with_idempotent_replay(self):
        service_module = importlib.import_module("app.mission_management")
        with self.session_factory() as session:
            service = service_module.MissionManagementService(session)
            first = service.create_mission(
                "u_customer_a_operator",
                "t_customer_001",
                self._payload(),
                "mission-create",
                RequestMeta("req_mission_create", "127.0.0.1"),
            )
            replay = service.create_mission(
                "u_customer_a_operator",
                "t_customer_001",
                self._payload(),
                "mission-create",
                RequestMeta("req_mission_create", "127.0.0.1"),
            )

        self.assertEqual(replay, first)
        self.assertEqual(first["status"], "DRAFT")
        self.assertEqual(first["tenant_id"], "t_customer_001")

    def test_cross_tenant_device_returns_tenant_404(self):
        service_module = importlib.import_module("app.mission_management")
        payload = self._payload()
        payload["device_id"] = "dev_drone_b"
        with self.session_factory() as session:
            service = service_module.MissionManagementService(session)
            with self.assertRaises(DomainError) as raised:
                service.create_mission(
                    "u_customer_a_operator",
                    "t_customer_001",
                    payload,
                    "mission-bad-device",
                    RequestMeta("req_bad_device", "127.0.0.1"),
                )
        self.assertEqual(raised.exception.code, "TENANT_404")

    def test_empty_media_policy_returns_mission_422(self):
        service_module = importlib.import_module("app.mission_management")
        payload = self._payload()
        payload["media_policy"] = {}
        with self.session_factory() as session:
            service = service_module.MissionManagementService(session)
            with self.assertRaises(DomainError) as raised:
                service.create_mission(
                    "u_customer_a_operator",
                    "t_customer_001",
                    payload,
                    "mission-bad-media",
                    RequestMeta("req_bad_media", "127.0.0.1"),
                )
        self.assertEqual(raised.exception.code, "MISSION_422")

    def test_mission_create_writes_audit(self):
        service_module = importlib.import_module("app.mission_management")
        with self.session_factory() as session:
            service = service_module.MissionManagementService(session)
            service.create_mission(
                "u_customer_a_operator",
                "t_customer_001",
                self._payload(),
                "mission-audit",
                RequestMeta("req_mission_audit", "127.0.0.1"),
            )

        with self.session_factory() as session:
            audit = session.scalar(
                select(AuditLogModel).where(
                    AuditLogModel.request_id == "req_mission_audit"
                )
            )
        self.assertEqual(audit.action, "mission_created")


if __name__ == "__main__":
    unittest.main()
