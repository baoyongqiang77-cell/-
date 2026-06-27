import sys
import unittest
import warnings
from datetime import datetime, timezone
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
    DeviceModel,
    DockModel,
    RoadAssetModel,
    RouteModel,
    RouteVersionModel,
    TenantFeatureEntitlementModel,
)


class MissionCreationApiTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = TemporaryDirectory()
        database_path = (Path(self.temp_dir.name) / "api.db").as_posix()
        self.database_url = f"sqlite+pysqlite:///{database_path}"
        self.session_factory = build_session_factory(self.database_url)
        Base.metadata.create_all(self.session_factory.kw["bind"])
        models = __import__("app.models", fromlist=["MissionModel"])
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
                models.MissionModel(
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
        self.client = TestClient(create_app(database_url_override=self.database_url))

    def tearDown(self):
        self.client.close()
        self.client.app.state.session_factory.kw["bind"].dispose()
        self.session_factory.kw["bind"].dispose()
        self.temp_dir.cleanup()

    def _payload(self) -> dict:
        return {
            "route_id": "route_a",
            "route_version_id": "rv_a",
            "device_id": "dev_dock_a",
            "dock_id": "dock_a",
            "schedule_time": "2026-07-01T09:00:00+00:00",
            "inspection_targets": [{"asset_type": "road", "asset_id": "road_a"}],
            "media_policy": {"video": True, "image_interval_sec": 2},
        }

    def _record_telemetry_event(self, event_code: str, key: str) -> dict:
        response = self.client.post(
            "/api/v1/missions/ms_a/telemetry-events",
            json={
                "event_code": event_code,
                "event_time": "2026-07-01T09:03:00+00:00",
                "device_sn": "dock-a",
                "raw_payload": {"battery": 18, "signal": -70},
            },
            headers={
                "Authorization": "Bearer demo-customer-a",
                "Idempotency-Key": key,
            },
        )
        self.assertEqual(response.status_code, 200)
        return response.json()

    def test_customer_creates_draft_mission_once_and_reads_it(self):
        headers = {
            "Authorization": "Bearer demo-customer-a",
            "Idempotency-Key": "create-mission-a",
        }
        first = self.client.post("/api/v1/missions", json=self._payload(), headers=headers)
        replay = self.client.post("/api/v1/missions", json=self._payload(), headers=headers)
        listed = self.client.get(
            "/api/v1/missions",
            headers={"Authorization": "Bearer demo-customer-a"},
        )

        self.assertEqual(first.status_code, 200)
        self.assertEqual(replay.json(), first.json())
        self.assertEqual(first.json()["status"], "DRAFT")
        self.assertIn(first.json()["id"], [item["id"] for item in listed.json()["items"]])

    def test_cross_tenant_mission_detail_returns_tenant_404_and_audits(self):
        response = self.client.get(
            "/api/v1/missions/ms_missing",
            headers={
                "Authorization": "Bearer demo-customer-a",
                "X-Request-Id": "req_mission_missing",
            },
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["code"], "TENANT_404")
        with self.session_factory() as session:
            audit = session.scalar(
                select(AuditLogModel).where(
                    AuditLogModel.request_id == "req_mission_missing"
                )
            )
        self.assertEqual(audit.action, "mission_read_denied")

    def test_mission_create_requires_flight_control_entitlement(self):
        with self.session_factory() as session:
            session.execute(
                delete(TenantFeatureEntitlementModel).where(
                    TenantFeatureEntitlementModel.tenant_id == "t_customer_001",
                    TenantFeatureEntitlementModel.feature_code == "FLIGHT_CONTROL",
                )
            )
            session.commit()

        response = self.client.post(
            "/api/v1/missions",
            json=self._payload(),
            headers={
                "Authorization": "Bearer demo-customer-a",
                "Idempotency-Key": "mission-no-feature",
            },
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["code"], "FEATURE_403")

    def test_mission_create_requires_idempotency_key(self):
        response = self.client.post(
            "/api/v1/missions",
            json=self._payload(),
            headers={"Authorization": "Bearer demo-customer-a"},
        )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["code"], "IDEMP_409")

    def test_customer_submits_and_approves_mission_once(self):
        submit_headers = {
            "Authorization": "Bearer demo-customer-a",
            "Idempotency-Key": "submit-approval-a",
        }
        submit = self.client.post(
            "/api/v1/missions/ms_a/submit-approval",
            json={
                "external_system": "BUILT_IN",
                "external_id": "manual-001",
                "callback_payload": {"mode": "manual"},
                "comment": "submit",
            },
            headers=submit_headers,
        )
        replay = self.client.post(
            "/api/v1/missions/ms_a/submit-approval",
            json={
                "external_system": "BUILT_IN",
                "external_id": "manual-001",
                "callback_payload": {"mode": "manual"},
                "comment": "submit",
            },
            headers=submit_headers,
        )
        approve = self.client.post(
            f"/api/v1/missions/ms_a/approvals/{submit.json()['id']}/approve",
            json={"comment": "approved"},
            headers={
                "Authorization": "Bearer demo-customer-a",
                "Idempotency-Key": "approve-approval-a",
            },
        )

        self.assertEqual(submit.status_code, 200)
        self.assertEqual(replay.json(), submit.json())
        self.assertEqual(submit.json()["status"], "PENDING_APPROVAL")
        self.assertEqual(approve.status_code, 200)
        self.assertEqual(approve.json()["status"], "APPROVED")
        self.assertEqual(approve.json()["mission_status"], "APPROVED")

    def test_customer_rejects_pending_mission(self):
        submit = self.client.post(
            "/api/v1/missions/ms_a/submit-approval",
            json={"external_system": "BUILT_IN"},
            headers={
                "Authorization": "Bearer demo-customer-a",
                "Idempotency-Key": "submit-approval-reject",
            },
        )
        reject = self.client.post(
            f"/api/v1/missions/ms_a/approvals/{submit.json()['id']}/reject",
            json={
                "external_status": "REJECTED",
                "callback_payload": {"source": "manual"},
                "comment": "weather window missed",
            },
            headers={
                "Authorization": "Bearer demo-customer-a",
                "Idempotency-Key": "reject-approval-a",
            },
        )

        self.assertEqual(reject.status_code, 200)
        self.assertEqual(reject.json()["status"], "REJECTED")
        self.assertEqual(reject.json()["mission_status"], "REJECTED")

    def test_approval_submit_requires_idempotency_key(self):
        response = self.client.post(
            "/api/v1/missions/ms_a/submit-approval",
            json={"external_system": "BUILT_IN"},
            headers={"Authorization": "Bearer demo-customer-a"},
        )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["code"], "IDEMP_409")

    def test_approval_requires_flight_control_entitlement(self):
        with self.session_factory() as session:
            session.execute(
                delete(TenantFeatureEntitlementModel).where(
                    TenantFeatureEntitlementModel.tenant_id == "t_customer_001",
                    TenantFeatureEntitlementModel.feature_code == "FLIGHT_CONTROL",
                )
            )
            session.commit()

        response = self.client.post(
            "/api/v1/missions/ms_a/submit-approval",
            json={"external_system": "BUILT_IN"},
            headers={
                "Authorization": "Bearer demo-customer-a",
                "Idempotency-Key": "approval-no-feature",
            },
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["code"], "FEATURE_403")

    def test_cross_tenant_approval_does_not_reveal_mission(self):
        response = self.client.post(
            "/api/v1/missions/ms_a/submit-approval",
            json={"external_system": "BUILT_IN"},
            headers={
                "Authorization": "Bearer demo-customer-b",
                "Idempotency-Key": "approval-cross-tenant",
                "X-Request-Id": "req_approval_cross_tenant",
            },
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["code"], "TENANT_404")

    def _approve_seed_mission_via_api(self):
        submit = self.client.post(
            "/api/v1/missions/ms_a/submit-approval",
            json={"external_system": "BUILT_IN"},
            headers={
                "Authorization": "Bearer demo-customer-a",
                "Idempotency-Key": "dispatch-api-submit",
            },
        )
        self.client.post(
            f"/api/v1/missions/ms_a/approvals/{submit.json()['id']}/approve",
            json={"comment": "approved"},
            headers={
                "Authorization": "Bearer demo-customer-a",
                "Idempotency-Key": "dispatch-api-approve",
            },
        )

    def test_customer_dispatches_approved_mission_once(self):
        self._approve_seed_mission_via_api()
        headers = {
            "Authorization": "Bearer demo-customer-a",
            "Idempotency-Key": "dispatch-api-mission",
        }
        first = self.client.post(
            "/api/v1/missions/ms_a/dispatch",
            json={"dispatch_note": "start approved patrol"},
            headers=headers,
        )
        replay = self.client.post(
            "/api/v1/missions/ms_a/dispatch",
            json={"dispatch_note": "start approved patrol"},
            headers=headers,
        )

        self.assertEqual(first.status_code, 200)
        self.assertEqual(replay.json(), first.json())
        self.assertEqual(first.json()["mission_status"], "DISPATCHED")
        self.assertEqual(first.json()["gateway_mode"], "SIMULATOR")
        self.assertEqual(first.json()["raw_payload"]["execution_proof"], "SIMULATED_ONLY")

    def test_dispatch_requires_idempotency_key(self):
        self._approve_seed_mission_via_api()
        response = self.client.post(
            "/api/v1/missions/ms_a/dispatch",
            json={},
            headers={"Authorization": "Bearer demo-customer-a"},
        )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["code"], "IDEMP_409")

    def test_dispatch_requires_flight_control_entitlement(self):
        self._approve_seed_mission_via_api()
        with self.session_factory() as session:
            session.execute(
                delete(TenantFeatureEntitlementModel).where(
                    TenantFeatureEntitlementModel.tenant_id == "t_customer_001",
                    TenantFeatureEntitlementModel.feature_code == "FLIGHT_CONTROL",
                )
            )
            session.commit()

        response = self.client.post(
            "/api/v1/missions/ms_a/dispatch",
            json={},
            headers={
                "Authorization": "Bearer demo-customer-a",
                "Idempotency-Key": "dispatch-api-no-feature",
            },
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["code"], "FEATURE_403")

    def test_dispatch_cross_tenant_does_not_reveal_mission(self):
        response = self.client.post(
            "/api/v1/missions/ms_a/dispatch",
            json={},
            headers={
                "Authorization": "Bearer demo-customer-b",
                "Idempotency-Key": "dispatch-api-cross-tenant",
            },
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["code"], "TENANT_404")

    def test_dispatch_rejects_non_approved_mission(self):
        response = self.client.post(
            "/api/v1/missions/ms_a/dispatch",
            json={},
            headers={
                "Authorization": "Bearer demo-customer-a",
                "Idempotency-Key": "dispatch-api-draft",
            },
        )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["code"], "STATE_409")

    def test_customer_records_and_reads_telemetry_event_once(self):
        payload = {
            "event_code": "telemetry",
            "event_time": "2026-07-01T09:01:00+00:00",
            "device_sn": "dock-a",
            "raw_payload": {"battery": 82, "signal": -58, "mission_status": "EXECUTING"},
        }
        headers = {
            "Authorization": "Bearer demo-customer-a",
            "Idempotency-Key": "telemetry-api-001",
        }
        first = self.client.post(
            "/api/v1/missions/ms_a/telemetry-events",
            json=payload,
            headers=headers,
        )
        replay = self.client.post(
            "/api/v1/missions/ms_a/telemetry-events",
            json=payload,
            headers=headers,
        )
        listed = self.client.get(
            "/api/v1/missions/ms_a/telemetry-events",
            headers={"Authorization": "Bearer demo-customer-a"},
        )

        self.assertEqual(first.status_code, 200)
        self.assertEqual(replay.json(), first.json())
        self.assertEqual(listed.json()["items"][0]["id"], first.json()["id"])
        self.assertEqual(first.json()["payload_json"]["raw_payload"]["battery"], 82)

    def test_telemetry_event_requires_idempotency_key(self):
        response = self.client.post(
            "/api/v1/missions/ms_a/telemetry-events",
            json={
                "event_code": "telemetry",
                "event_time": "2026-07-01T09:01:00+00:00",
                "device_sn": "dock-a",
                "raw_payload": {"battery": 82},
            },
            headers={"Authorization": "Bearer demo-customer-a"},
        )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["code"], "IDEMP_409")

    def test_telemetry_cross_tenant_does_not_reveal_mission(self):
        response = self.client.get(
            "/api/v1/missions/ms_a/telemetry-events",
            headers={"Authorization": "Bearer demo-customer-b"},
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["code"], "TENANT_404")

    def test_telemetry_websocket_sends_current_snapshot(self):
        self.client.post(
            "/api/v1/missions/ms_a/telemetry-events",
            json={
                "event_code": "telemetry",
                "event_time": "2026-07-01T09:01:00+00:00",
                "device_sn": "dock-a",
                "raw_payload": {"battery": 82, "signal": -58},
            },
            headers={
                "Authorization": "Bearer demo-customer-a",
                "Idempotency-Key": "telemetry-ws-seed",
            },
        )

        with self.client.websocket_connect(
            "/api/v1/missions/ms_a/telemetry/ws",
            headers={"Authorization": "Bearer demo-customer-a"},
        ) as websocket:
            snapshot = websocket.receive_json()

        self.assertEqual(snapshot["type"], "snapshot")
        self.assertEqual(snapshot["mission_id"], "ms_a")
        self.assertEqual(snapshot["items"][0]["payload_json"]["raw_payload"]["battery"], 82)

    def test_telemetry_websocket_receives_realtime_hub_event(self):
        with self.client.websocket_connect(
            "/api/v1/missions/ms_a/telemetry/ws",
            headers={"Authorization": "Bearer demo-customer-a"},
        ) as websocket:
            snapshot = websocket.receive_json()
            self.assertEqual(snapshot["type"], "snapshot")
            self.assertEqual(snapshot["items"], [])

            self.client.app.state.telemetry_hub.broadcast(
                "t_customer_001",
                "ms_a",
                {
                    "type": "event",
                    "mission_id": "ms_a",
                    "item": {
                        "id": "fe_realtime",
                        "payload_json": {"raw_payload": {"battery": 79}},
                    },
                },
            )
            event = websocket.receive_json()

        self.assertEqual(event["type"], "event")
        self.assertEqual(event["mission_id"], "ms_a")
        self.assertEqual(event["item"]["id"], "fe_realtime")
        self.assertEqual(event["item"]["payload_json"]["raw_payload"]["battery"], 79)

    def test_telemetry_post_broadcasts_persisted_event(self):
        class RecordingHub:
            def __init__(self):
                self.messages = []

            def broadcast(self, tenant_id: str, mission_id: str, message: dict) -> None:
                self.messages.append((tenant_id, mission_id, message))

        hub = RecordingHub()
        self.client.app.state.telemetry_hub.broadcast = hub.broadcast

        response = self.client.post(
            "/api/v1/missions/ms_a/telemetry-events",
            json={
                "event_code": "telemetry",
                "event_time": "2026-07-01T09:02:00+00:00",
                "device_sn": "dock-a",
                "raw_payload": {"battery": 79, "signal": -60},
            },
            headers={
                "Authorization": "Bearer demo-customer-a",
                "Idempotency-Key": "telemetry-broadcast-001",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(hub.messages), 1)
        tenant_id, mission_id, message = hub.messages[0]
        self.assertEqual(tenant_id, "t_customer_001")
        self.assertEqual(mission_id, "ms_a")
        self.assertEqual(message["type"], "event")
        self.assertEqual(message["item"]["id"], response.json()["id"])

    def test_telemetry_websocket_requires_flight_control_entitlement(self):
        with self.session_factory() as session:
            session.execute(
                delete(TenantFeatureEntitlementModel).where(
                    TenantFeatureEntitlementModel.tenant_id == "t_customer_001",
                    TenantFeatureEntitlementModel.feature_code == "FLIGHT_CONTROL",
                )
            )
            session.commit()

        with self.client.websocket_connect(
            "/api/v1/missions/ms_a/telemetry/ws",
            headers={"Authorization": "Bearer demo-customer-a"},
        ) as websocket:
            error = websocket.receive_json()

        self.assertEqual(error["code"], "FEATURE_403")
        self.assertEqual(error["details"]["feature_code"], "FLIGHT_CONTROL")

    def test_customer_links_and_lists_flight_exception_once(self):
        event = self._record_telemetry_event("low_battery", "exception-seed-low")
        headers = {
            "Authorization": "Bearer demo-customer-a",
            "Idempotency-Key": "exception-link-low",
        }
        first = self.client.post(
            f"/api/v1/missions/ms_a/flight-events/{event['id']}/link-exception",
            headers=headers,
        )
        replay = self.client.post(
            f"/api/v1/missions/ms_a/flight-events/{event['id']}/link-exception",
            headers=headers,
        )
        listed = self.client.get(
            "/api/v1/missions/ms_a/flight-exceptions",
            headers={"Authorization": "Bearer demo-customer-a"},
        )

        self.assertEqual(first.status_code, 200)
        self.assertEqual(replay.json(), first.json())
        self.assertEqual(first.json()["exception_code"], "LOW_BATTERY")
        self.assertEqual(first.json()["severity"], "HIGH")
        self.assertEqual(listed.json()["items"][0]["id"], first.json()["id"])

    def test_flight_exception_link_requires_idempotency_key(self):
        event = self._record_telemetry_event("low_battery", "exception-seed-no-key")
        response = self.client.post(
            f"/api/v1/missions/ms_a/flight-events/{event['id']}/link-exception",
            headers={"Authorization": "Bearer demo-customer-a"},
        )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["code"], "IDEMP_409")

    def test_flight_exception_unsupported_event_returns_mission_422(self):
        event = self._record_telemetry_event("telemetry", "exception-seed-unsupported")
        response = self.client.post(
            f"/api/v1/missions/ms_a/flight-events/{event['id']}/link-exception",
            headers={
                "Authorization": "Bearer demo-customer-a",
                "Idempotency-Key": "exception-unsupported",
            },
        )

        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["code"], "MISSION_422")

    def test_flight_exception_cross_tenant_does_not_reveal_mission(self):
        event = self._record_telemetry_event("low_battery", "exception-seed-cross")
        response = self.client.post(
            f"/api/v1/missions/ms_a/flight-events/{event['id']}/link-exception",
            headers={
                "Authorization": "Bearer demo-customer-b",
                "Idempotency-Key": "exception-cross",
            },
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["code"], "TENANT_404")

    def test_flight_exception_requires_flight_control_entitlement(self):
        event = self._record_telemetry_event("low_battery", "exception-seed-feature")
        with self.session_factory() as session:
            session.execute(
                delete(TenantFeatureEntitlementModel).where(
                    TenantFeatureEntitlementModel.tenant_id == "t_customer_001",
                    TenantFeatureEntitlementModel.feature_code == "FLIGHT_CONTROL",
                )
            )
            session.commit()

        response = self.client.get(
            "/api/v1/missions/ms_a/flight-exceptions",
            headers={"Authorization": "Bearer demo-customer-a"},
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["code"], "FEATURE_403")

    def test_forbidden_server_managed_fields_return_mission_422(self):
        payload = self._payload()
        payload["tenant_id"] = "t_customer_002"
        payload["status"] = "APPROVED"

        response = self.client.post(
            "/api/v1/missions",
            json=payload,
            headers={
                "Authorization": "Bearer demo-customer-a",
                "Idempotency-Key": "mission-forbidden-fields",
            },
        )

        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["code"], "MISSION_422")

    def test_openapi_exposes_mission_paths(self):
        paths = self.client.get("/openapi.json").json()["paths"]

        self.assertIn("/api/v1/missions", paths)
        self.assertIn("/api/v1/missions/{mission_id}", paths)
        self.assertIn("/api/v1/missions/{mission_id}/submit-approval", paths)
        self.assertIn(
            "/api/v1/missions/{mission_id}/approvals/{approval_id}/approve", paths
        )
        self.assertIn(
            "/api/v1/missions/{mission_id}/approvals/{approval_id}/reject", paths
        )
        self.assertIn("/api/v1/missions/{mission_id}/dispatch", paths)
        self.assertIn("/api/v1/missions/{mission_id}/telemetry-events", paths)
        self.assertIn(
            "/api/v1/missions/{mission_id}/flight-events/{flight_event_id}/link-exception",
            paths,
        )
        self.assertIn("/api/v1/missions/{mission_id}/flight-exceptions", paths)


if __name__ == "__main__":
    unittest.main()
