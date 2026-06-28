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

from drone_inspection.dji_gateway import FlightEvent

from app.bootstrap import bootstrap_u0
from app.database import build_session_factory
from app.models import (
    AuditLogModel,
    Base,
    DeviceModel,
    DockModel,
    MissionModel,
    RoadAssetModel,
    RouteModel,
    RouteVersionModel,
)
from app.repositories import RequestMeta
from drone_inspection.errors import DomainError


class MissionModelTests(unittest.TestCase):
    def test_metadata_contains_missions_table(self):
        self.assertIn("missions", Base.metadata.tables)
        self.assertIn("mission_approvals", Base.metadata.tables)
        self.assertIn("mission_dispatch_receipts", Base.metadata.tables)
        self.assertIn("flight_events", Base.metadata.tables)
        self.assertIn("flight_exception_links", Base.metadata.tables)
        self.assertIn("media_files", Base.metadata.tables)

    def test_mission_model_registers_required_constraints(self):
        models = importlib.import_module("app.models")
        constraints = {item.name for item in models.MissionModel.__table__.constraints}

        self.assertIn("ck_missions_status", constraints)
        self.assertIn("fk_missions_tenant_route", constraints)
        self.assertIn("fk_missions_tenant_route_version", constraints)
        self.assertIn("fk_missions_tenant_device", constraints)

    def test_mission_approval_model_registers_required_constraints(self):
        models = importlib.import_module("app.models")
        constraints = {
            item.name for item in models.MissionApprovalModel.__table__.constraints
        }

        self.assertIn("ck_mission_approvals_status", constraints)
        self.assertIn("fk_mission_approvals_tenant_mission", constraints)

    def test_mission_dispatch_receipt_model_registers_required_constraints(self):
        models = importlib.import_module("app.models")
        constraints = {
            item.name for item in models.MissionDispatchReceiptModel.__table__.constraints
        }

        self.assertIn("ck_mission_dispatch_receipts_gateway_mode", constraints)
        self.assertIn("fk_mission_dispatch_receipts_tenant_mission", constraints)

    def test_flight_event_model_registers_required_constraints(self):
        models = importlib.import_module("app.models")
        constraints = {item.name for item in models.FlightEventModel.__table__.constraints}

        self.assertIn("fk_flight_events_tenant_mission", constraints)

    def test_flight_exception_link_model_registers_required_constraints(self):
        models = importlib.import_module("app.models")
        constraints = {
            item.name for item in models.FlightExceptionLinkModel.__table__.constraints
        }

        self.assertIn("fk_flight_exception_links_tenant_mission", constraints)
        self.assertIn("uq_flight_exception_links_tenant_event", constraints)
        self.assertIn("ck_flight_exception_links_severity", constraints)
        self.assertIn("ck_flight_exception_links_status", constraints)

    def test_media_file_model_registers_required_constraints(self):
        models = importlib.import_module("app.models")
        constraints = {item.name for item in models.MediaFileModel.__table__.constraints}

        self.assertIn("fk_media_files_tenant_mission", constraints)
        self.assertIn("uq_media_files_tenant_source_event", constraints)
        self.assertIn("uq_media_files_tenant_id", constraints)
        self.assertIn("ck_media_files_status", constraints)
        self.assertIn("ck_media_files_media_type", constraints)

    def test_alembic_mission_creation_round_trip_sqlite(self):
        with TemporaryDirectory() as temp_dir:
            database_url = f"sqlite+pysqlite:///{Path(temp_dir) / 'test.db'}"
            config = Config(str(ROOT / "alembic.ini"))
            config.set_main_option("sqlalchemy.url", database_url)

            command.upgrade(config, "head")
            engine = build_session_factory(database_url).kw["bind"]
            try:
                self.assertIn("missions", set(inspect(engine).get_table_names()))
                self.assertIn(
                    "mission_approvals", set(inspect(engine).get_table_names())
                )
                self.assertIn(
                    "mission_dispatch_receipts",
                    set(inspect(engine).get_table_names()),
                )
                self.assertIn("flight_events", set(inspect(engine).get_table_names()))
                self.assertIn(
                    "flight_exception_links", set(inspect(engine).get_table_names())
                )
                self.assertIn("media_files", set(inspect(engine).get_table_names()))
            finally:
                engine.dispose()

            command.downgrade(config, "20260627_0009")
            engine = build_session_factory(database_url).kw["bind"]
            try:
                self.assertIn("missions", set(inspect(engine).get_table_names()))
                self.assertIn("mission_approvals", set(inspect(engine).get_table_names()))
                self.assertIn(
                    "mission_dispatch_receipts", set(inspect(engine).get_table_names())
                )
                self.assertIn("flight_events", set(inspect(engine).get_table_names()))
                self.assertIn(
                    "flight_exception_links", set(inspect(engine).get_table_names())
                )
                self.assertNotIn("media_files", set(inspect(engine).get_table_names()))
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
            session.add(
                MissionModel(
                    id="ms_a",
                    tenant_id="t_customer_001",
                    route_id="route_a",
                    route_version_id="rv_a",
                    device_id="dev_dock_a",
                    dock_id="dock_a",
                    status="DRAFT",
                    schedule_time=datetime(2026, 7, 1, 9, 0, tzinfo=timezone.utc),
                    inspection_targets=[{"asset_type": "road", "asset_id": "road_a"}],
                    media_policy={"video": True},
                )
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

    def test_submits_approval_once_and_moves_mission_to_pending(self):
        service_module = importlib.import_module("app.mission_management")
        with self.session_factory() as session:
            service = service_module.MissionManagementService(session)
            first = service.submit_approval(
                "u_customer_a_operator",
                "t_customer_001",
                "ms_a",
                {
                    "external_system": "BUILT_IN",
                    "external_id": "manual-001",
                    "callback_payload": {"mode": "manual"},
                    "comment": "submit for airspace review",
                },
                "approval-submit",
                RequestMeta("req_approval_submit", "127.0.0.1"),
            )
            replay = service.submit_approval(
                "u_customer_a_operator",
                "t_customer_001",
                "ms_a",
                {
                    "external_system": "BUILT_IN",
                    "external_id": "manual-001",
                    "callback_payload": {"mode": "manual"},
                    "comment": "submit for airspace review",
                },
                "approval-submit",
                RequestMeta("req_approval_submit", "127.0.0.1"),
            )
            mission = session.get(MissionModel, "ms_a")

        self.assertEqual(replay, first)
        self.assertEqual(first["status"], "PENDING_APPROVAL")
        self.assertEqual(first["mission_status"], "PENDING_APPROVAL")
        self.assertEqual(mission.status, "PENDING_APPROVAL")

    def test_approves_and_rejects_only_pending_missions(self):
        service_module = importlib.import_module("app.mission_management")
        with self.session_factory() as session:
            service = service_module.MissionManagementService(session)
            submitted = service.submit_approval(
                "u_customer_a_operator",
                "t_customer_001",
                "ms_a",
                {"external_system": "BUILT_IN"},
                "approval-submit-approve",
                RequestMeta("req_submit_approve", "127.0.0.1"),
            )
            approved = service.decide_approval(
                "u_customer_a_approver",
                "t_customer_001",
                "ms_a",
                submitted["id"],
                "APPROVED",
                {"comment": "approved"},
                "approval-approve",
                RequestMeta("req_approve", "127.0.0.1"),
            )
            mission = session.get(MissionModel, "ms_a")
            with self.assertRaises(DomainError) as raised:
                service.decide_approval(
                    "u_customer_a_approver",
                    "t_customer_001",
                    "ms_a",
                    submitted["id"],
                    "REJECTED",
                    {"comment": "too late"},
                    "approval-reject-after-approve",
                    RequestMeta("req_reject_after_approve", "127.0.0.1"),
                )

        self.assertEqual(approved["status"], "APPROVED")
        self.assertEqual(approved["mission_status"], "APPROVED")
        self.assertEqual(mission.status, "APPROVED")
        self.assertEqual(raised.exception.code, "STATE_409")

    def test_approval_cross_tenant_mission_returns_tenant_404(self):
        service_module = importlib.import_module("app.mission_management")
        with self.session_factory() as session:
            service = service_module.MissionManagementService(session)
            with self.assertRaises(DomainError) as raised:
                service.submit_approval(
                    "u_customer_b_operator",
                    "t_customer_002",
                    "ms_a",
                    {"external_system": "BUILT_IN"},
                    "approval-cross-tenant",
                    RequestMeta("req_approval_cross", "127.0.0.1"),
                )

        self.assertEqual(raised.exception.code, "TENANT_404")

    def test_approval_decision_writes_audit(self):
        service_module = importlib.import_module("app.mission_management")
        with self.session_factory() as session:
            service = service_module.MissionManagementService(session)
            submitted = service.submit_approval(
                "u_customer_a_operator",
                "t_customer_001",
                "ms_a",
                {"external_system": "BUILT_IN"},
                "approval-submit-audit",
                RequestMeta("req_submit_audit", "127.0.0.1"),
            )
            service.decide_approval(
                "u_customer_a_approver",
                "t_customer_001",
                "ms_a",
                submitted["id"],
                "REJECTED",
                {"comment": "weather window missed"},
                "approval-reject-audit",
                RequestMeta("req_reject_audit", "127.0.0.1"),
            )

        with self.session_factory() as session:
            audit = session.scalar(
                select(AuditLogModel).where(
                    AuditLogModel.request_id == "req_reject_audit"
                )
            )
        self.assertEqual(audit.action, "mission_rejected")
        self.assertEqual(audit.before_status, "PENDING_APPROVAL")
        self.assertEqual(audit.after_status, "REJECTED")

    def _approve_seed_mission(self, session):
        service_module = importlib.import_module("app.mission_management")
        service = service_module.MissionManagementService(session)
        submitted = service.submit_approval(
            "u_customer_a_operator",
            "t_customer_001",
            "ms_a",
            {"external_system": "BUILT_IN"},
            "dispatch-submit-approval",
            RequestMeta("req_dispatch_submit", "127.0.0.1"),
        )
        service.decide_approval(
            "u_customer_a_approver",
            "t_customer_001",
            "ms_a",
            submitted["id"],
            "APPROVED",
            {"comment": "approved"},
            "dispatch-approve-mission",
            RequestMeta("req_dispatch_approve", "127.0.0.1"),
        )
        return service

    def test_dispatches_approved_mission_once_and_records_gateway_receipt(self):
        service_module = importlib.import_module("app.mission_management")
        gateway_module = importlib.import_module("drone_inspection.dji_gateway")
        with self.session_factory() as session:
            service = self._approve_seed_mission(session)
            gateway = gateway_module.DjiDock3Simulator()
            first = service.dispatch_mission(
                "u_customer_a_operator",
                "t_customer_001",
                "ms_a",
                {"dispatch_note": "start approved patrol"},
                "mission-dispatch",
                RequestMeta("req_dispatch", "127.0.0.1"),
                gateway,
            )
            replay = service.dispatch_mission(
                "u_customer_a_operator",
                "t_customer_001",
                "ms_a",
                {"dispatch_note": "start approved patrol"},
                "mission-dispatch",
                RequestMeta("req_dispatch", "127.0.0.1"),
                gateway,
            )
            mission = session.get(MissionModel, "ms_a")

        self.assertEqual(replay, first)
        self.assertEqual(first["mission_status"], "DISPATCHED")
        self.assertTrue(first["accepted"])
        self.assertEqual(first["gateway_mode"], "SIMULATOR")
        self.assertEqual(first["raw_payload"]["execution_proof"], "SIMULATED_ONLY")
        self.assertEqual(mission.status, "DISPATCHED")

    def test_dispatch_requires_approved_mission(self):
        service_module = importlib.import_module("app.mission_management")
        gateway_module = importlib.import_module("drone_inspection.dji_gateway")
        with self.session_factory() as session:
            service = service_module.MissionManagementService(session)
            with self.assertRaises(DomainError) as raised:
                service.dispatch_mission(
                    "u_customer_a_operator",
                    "t_customer_001",
                    "ms_a",
                    {},
                    "dispatch-draft",
                    RequestMeta("req_dispatch_draft", "127.0.0.1"),
                    gateway_module.DjiDock3Simulator(),
                )

        self.assertEqual(raised.exception.code, "STATE_409")

    def test_dispatch_cross_tenant_mission_returns_tenant_404(self):
        service_module = importlib.import_module("app.mission_management")
        gateway_module = importlib.import_module("drone_inspection.dji_gateway")
        with self.session_factory() as session:
            service = service_module.MissionManagementService(session)
            with self.assertRaises(DomainError) as raised:
                service.dispatch_mission(
                    "u_customer_b_operator",
                    "t_customer_002",
                    "ms_a",
                    {},
                    "dispatch-cross-tenant",
                    RequestMeta("req_dispatch_cross", "127.0.0.1"),
                    gateway_module.DjiDock3Simulator(),
                )

        self.assertEqual(raised.exception.code, "TENANT_404")

    def test_dispatch_gateway_failure_returns_dji_502_without_final_state(self):
        gateway_module = importlib.import_module("drone_inspection.dji_gateway")
        with self.session_factory() as session:
            service = self._approve_seed_mission(session)
            gateway = gateway_module.DjiDock3Simulator()
            gateway.fail_next("dispatch_mission", "timeout")
            with self.assertRaises(DomainError) as raised:
                service.dispatch_mission(
                    "u_customer_a_operator",
                    "t_customer_001",
                    "ms_a",
                    {},
                    "dispatch-timeout",
                    RequestMeta("req_dispatch_timeout", "127.0.0.1"),
                    gateway,
                )
            session.rollback()
            mission = session.get(MissionModel, "ms_a")

        self.assertEqual(raised.exception.code, "DJI_502")
        self.assertEqual(mission.status, "APPROVED")

    def test_records_telemetry_event_once_and_lists_it(self):
        telemetry_module = importlib.import_module("app.telemetry_events")
        event = FlightEvent(
            event_code="telemetry",
            event_time=datetime(2026, 7, 1, 9, 1, tzinfo=timezone.utc),
            device_sn="dock-a",
            raw_payload={"battery": 82, "signal": -58, "mission_status": "EXECUTING"},
        )
        with self.session_factory() as session:
            service = telemetry_module.TelemetryEventService(session)
            first = service.record_event(
                "u_customer_a_operator",
                "t_customer_001",
                "ms_a",
                event,
                "telemetry-001",
                RequestMeta("req_telemetry", "127.0.0.1"),
            )
            replay = service.record_event(
                "u_customer_a_operator",
                "t_customer_001",
                "ms_a",
                event,
                "telemetry-001",
                RequestMeta("req_telemetry", "127.0.0.1"),
            )
            listed = service.list_events("t_customer_001", "ms_a")

        self.assertEqual(replay, first)
        self.assertEqual(first["payload_json"]["event_code"], "telemetry")
        self.assertEqual(first["payload_json"]["raw_payload"]["battery"], 82)
        self.assertEqual([item["id"] for item in listed], [first["id"]])

    def test_telemetry_event_cross_tenant_mission_returns_tenant_404(self):
        telemetry_module = importlib.import_module("app.telemetry_events")
        event = FlightEvent(
            event_code="telemetry",
            event_time=datetime(2026, 7, 1, 9, 1, tzinfo=timezone.utc),
            device_sn="dock-a",
            raw_payload={"battery": 82, "signal": -58},
        )
        with self.session_factory() as session:
            service = telemetry_module.TelemetryEventService(session)
            with self.assertRaises(DomainError) as raised:
                service.record_event(
                    "u_customer_b_operator",
                    "t_customer_002",
                    "ms_a",
                    event,
                    "telemetry-cross",
                    RequestMeta("req_telemetry_cross", "127.0.0.1"),
                )

        self.assertEqual(raised.exception.code, "TENANT_404")

    def test_links_low_battery_exception_once_and_lists_it(self):
        event_id = self._record_flight_event("low_battery")
        exceptions_module = importlib.import_module("app.flight_exceptions")
        with self.session_factory() as session:
            service = exceptions_module.FlightExceptionService(session)
            first = service.link_exception(
                "u_customer_a_operator",
                "t_customer_001",
                "ms_a",
                event_id,
                "exception-low-battery",
                RequestMeta("req_exception_low_battery", "127.0.0.1"),
            )
            replay = service.link_exception(
                "u_customer_a_operator",
                "t_customer_001",
                "ms_a",
                event_id,
                "exception-low-battery",
                RequestMeta("req_exception_low_battery", "127.0.0.1"),
            )
            listed = service.list_exceptions("t_customer_001", "ms_a")

        self.assertEqual(replay, first)
        self.assertEqual(first["exception_code"], "LOW_BATTERY")
        self.assertEqual(first["severity"], "HIGH")
        self.assertEqual(first["status"], "OPEN")
        self.assertEqual(first["flight_event_id"], event_id)
        self.assertEqual([item["id"] for item in listed], [first["id"]])

    def test_exception_link_writes_audit(self):
        event_id = self._record_flight_event("device_unresponsive")
        exceptions_module = importlib.import_module("app.flight_exceptions")
        with self.session_factory() as session:
            service = exceptions_module.FlightExceptionService(session)
            linked = service.link_exception(
                "u_customer_a_operator",
                "t_customer_001",
                "ms_a",
                event_id,
                "exception-audit",
                RequestMeta("req_exception_audit", "127.0.0.1"),
            )

        with self.session_factory() as session:
            audit = session.scalar(
                select(AuditLogModel).where(
                    AuditLogModel.request_id == "req_exception_audit"
                )
            )

        self.assertEqual(audit.action, "flight_exception_linked")
        self.assertEqual(audit.resource_id, linked["id"])

    def test_unsupported_exception_event_returns_mission_422(self):
        event_id = self._record_flight_event("telemetry")
        exceptions_module = importlib.import_module("app.flight_exceptions")
        with self.session_factory() as session:
            service = exceptions_module.FlightExceptionService(session)
            with self.assertRaises(DomainError) as raised:
                service.link_exception(
                    "u_customer_a_operator",
                    "t_customer_001",
                    "ms_a",
                    event_id,
                    "exception-unsupported",
                    RequestMeta("req_exception_unsupported", "127.0.0.1"),
                )

        self.assertEqual(raised.exception.code, "MISSION_422")

    def test_exception_link_cross_tenant_mission_returns_tenant_404(self):
        event_id = self._record_flight_event("low_battery")
        exceptions_module = importlib.import_module("app.flight_exceptions")
        with self.session_factory() as session:
            service = exceptions_module.FlightExceptionService(session)
            with self.assertRaises(DomainError) as raised:
                service.link_exception(
                    "u_customer_b_operator",
                    "t_customer_002",
                    "ms_a",
                    event_id,
                    "exception-cross",
                    RequestMeta("req_exception_cross", "127.0.0.1"),
                )

        self.assertEqual(raised.exception.code, "TENANT_404")

    def test_syncs_media_upload_event_once_and_lists_it(self):
        event_id = self._record_media_event(key="media-seed-ok")
        media_module = importlib.import_module("app.media_sync")
        with self.session_factory() as session:
            service = media_module.MediaSyncService(session)
            first = service.sync_media(
                "u_customer_a_operator",
                "t_customer_001",
                "ms_a",
                event_id,
                "media-sync-ok",
                RequestMeta("req_media_sync_ok", "127.0.0.1"),
            )
            replay = service.sync_media(
                "u_customer_a_operator",
                "t_customer_001",
                "ms_a",
                event_id,
                "media-sync-ok",
                RequestMeta("req_media_sync_ok", "127.0.0.1"),
            )
            listed = service.list_media_files("t_customer_001", "ms_a")

        self.assertEqual(replay, first)
        self.assertEqual(first["status"], "READY")
        self.assertEqual(first["source_event_id"], event_id)
        self.assertEqual(first["media_type"], "VIDEO")
        self.assertEqual([item["id"] for item in listed], [first["id"]])

    def test_media_sync_writes_audit(self):
        event_id = self._record_media_event(key="media-seed-audit")
        media_module = importlib.import_module("app.media_sync")
        with self.session_factory() as session:
            service = media_module.MediaSyncService(session)
            synced = service.sync_media(
                "u_customer_a_operator",
                "t_customer_001",
                "ms_a",
                event_id,
                "media-sync-audit",
                RequestMeta("req_media_sync_audit", "127.0.0.1"),
            )

        with self.session_factory() as session:
            audit = session.scalar(
                select(AuditLogModel).where(
                    AuditLogModel.request_id == "req_media_sync_audit"
                )
            )

        self.assertEqual(audit.action, "media_file_synced")
        self.assertEqual(audit.resource_id, synced["id"])

    def test_non_media_event_returns_mission_422(self):
        event_id = self._record_media_event(
            event_code="telemetry", key="media-seed-bad-code"
        )
        media_module = importlib.import_module("app.media_sync")
        with self.session_factory() as session:
            service = media_module.MediaSyncService(session)
            with self.assertRaises(DomainError) as raised:
                service.sync_media(
                    "u_customer_a_operator",
                    "t_customer_001",
                    "ms_a",
                    event_id,
                    "media-sync-bad-code",
                    RequestMeta("req_media_bad_code", "127.0.0.1"),
                )

        self.assertEqual(raised.exception.code, "MISSION_422")

    def test_media_sync_bad_checksum_returns_media_499(self):
        event_id = self._record_media_event(
            raw_payload={
                "media_id": "med_bad",
                "storage_uri": "t_customer_001/proj_001/ms_a/media/med_bad.mp4",
                "checksum": "bad-checksum",
                "media_type": "VIDEO",
            },
            key="media-seed-bad-checksum",
        )
        media_module = importlib.import_module("app.media_sync")
        with self.session_factory() as session:
            service = media_module.MediaSyncService(session)
            with self.assertRaises(DomainError) as raised:
                service.sync_media(
                    "u_customer_a_operator",
                    "t_customer_001",
                    "ms_a",
                    event_id,
                    "media-sync-bad-checksum",
                    RequestMeta("req_media_bad_checksum", "127.0.0.1"),
                )

        self.assertEqual(raised.exception.code, "MEDIA_499")

    def test_media_sync_cross_tenant_mission_returns_tenant_404(self):
        event_id = self._record_media_event(key="media-seed-cross")
        media_module = importlib.import_module("app.media_sync")
        with self.session_factory() as session:
            service = media_module.MediaSyncService(session)
            with self.assertRaises(DomainError) as raised:
                service.sync_media(
                    "u_customer_b_operator",
                    "t_customer_002",
                    "ms_a",
                    event_id,
                    "media-sync-cross",
                    RequestMeta("req_media_cross", "127.0.0.1"),
                )

        self.assertEqual(raised.exception.code, "TENANT_404")

    def _record_flight_event(self, event_code: str, mission_id: str = "ms_a") -> str:
        telemetry_module = importlib.import_module("app.telemetry_events")
        event = FlightEvent(
            event_code=event_code,
            event_time=datetime(2026, 7, 1, 9, 2, tzinfo=timezone.utc),
            device_sn="dock-a",
            raw_payload={"battery": 18, "signal": -70},
        )
        with self.session_factory() as session:
            service = telemetry_module.TelemetryEventService(session)
            result = service.record_event(
                "u_customer_a_operator",
                "t_customer_001",
                mission_id,
                event,
                f"telemetry-{event_code}-{mission_id}",
                RequestMeta(f"req_telemetry_{event_code}", "127.0.0.1"),
            )
        return result["id"]

    def _record_media_event(
        self,
        *,
        event_code: str = "media_upload_completed",
        raw_payload: dict | None = None,
        mission_id: str = "ms_a",
        key: str = "media-seed",
    ) -> str:
        telemetry_module = importlib.import_module("app.telemetry_events")
        event = FlightEvent(
            event_code=event_code,
            event_time=datetime(2026, 7, 1, 9, 3, tzinfo=timezone.utc),
            device_sn="dock-a",
            raw_payload=raw_payload
            or {
                "media_id": "med_001",
                "storage_uri": "t_customer_001/proj_001/ms_a/media/med_001.mp4",
                "checksum": "sha256:" + "b" * 64,
                "media_type": "VIDEO",
            },
        )
        with self.session_factory() as session:
            service = telemetry_module.TelemetryEventService(session)
            result = service.record_event(
                "u_customer_a_operator",
                "t_customer_001",
                mission_id,
                event,
                key,
                RequestMeta(f"req_{key}", "127.0.0.1"),
            )
        return result["id"]


if __name__ == "__main__":
    unittest.main()
