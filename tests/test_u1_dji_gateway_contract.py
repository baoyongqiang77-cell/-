import sys
import unittest
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from drone_inspection.dji_gateway import (
    DeviceCommand,
    DispatchMissionCommand,
    DjiGateway,
    DjiDock3Simulator,
    ExceptionCommand,
    FlightEvent,
    GatewayMode,
    GatewayReceipt,
    MediaSyncCommand,
    TelemetryCommand,
)
from drone_inspection.errors import DomainError


class GatewayContractTests(unittest.TestCase):
    def test_event_payload_has_exact_fixed_outer_fields(self):
        event = FlightEvent(
            event_code="telemetry",
            event_time=datetime(2026, 6, 19, 5, 0, tzinfo=timezone.utc),
            device_sn="dock-sn-001",
            raw_payload={"battery": 76},
        )

        self.assertEqual(
            event.to_payload(),
            {
                "event_code": "telemetry",
                "event_time": "2026-06-19T05:00:00Z",
                "device_sn": "dock-sn-001",
                "raw_payload": {"battery": 76},
            },
        )

    def test_event_rejects_naive_time(self):
        with self.assertRaises(ValueError):
            FlightEvent(
                event_code="telemetry",
                event_time=datetime(2026, 6, 19, 5, 0),
                device_sn="dock-sn-001",
                raw_payload={},
            )

    def test_commands_and_receipts_are_immutable(self):
        command = DeviceCommand(
            tenant_id="t_customer_001",
            request_id="req_001",
            idempotency_key="key-001",
            device_sn="dock-sn-001",
        )
        receipt = GatewayReceipt(
            operation="bind_device",
            request_id="req_001",
            device_sn="dock-sn-001",
            accepted=True,
            external_request_id="sim_req_001",
            received_at=datetime(2026, 6, 19, 5, 0, tzinfo=timezone.utc),
            raw_payload={"status": "BOUND"},
            mode=GatewayMode.SIMULATOR,
        )

        with self.assertRaises(AttributeError):
            command.device_sn = "changed"
        with self.assertRaises(AttributeError):
            receipt.accepted = False

    def test_protocol_lists_the_six_gateway_capabilities(self):
        self.assertEqual(
            {
                name
                for name, value in DjiGateway.__dict__.items()
                if callable(value) and not name.startswith("_")
            },
            {
                "bind_device",
                "sync_device_status",
                "dispatch_mission",
                "publish_telemetry",
                "publish_exception",
                "complete_media_sync",
            },
        )
        self.assertIn("mode", DjiGateway.__annotations__)


class GatewayReceiptTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 6, 19, 5, 0, tzinfo=timezone.utc)
        self.gateway = DjiDock3Simulator(clock=lambda: self.now)
        self.command = DeviceCommand(
            tenant_id="t_customer_001",
            request_id="req_bind_001",
            idempotency_key="bind-key-001",
            device_sn="dock-sn-001",
        )

    def test_simulator_satisfies_protocol_and_marks_receipt_mode(self):
        self.assertIsInstance(self.gateway, DjiGateway)
        receipt = self.gateway.bind_device(self.command)
        self.assertTrue(receipt.accepted)
        self.assertEqual(receipt.mode, GatewayMode.SIMULATOR)
        self.assertEqual(receipt.raw_payload["status"], "BOUND")

    def test_same_idempotent_request_replays_original_receipt(self):
        first = self.gateway.bind_device(self.command)
        replay = self.gateway.bind_device(self.command)
        self.assertEqual(replay, first)

    def test_idempotency_fingerprint_conflict_returns_idemp_409(self):
        self.gateway.bind_device(self.command)
        conflict = replace(self.command, device_sn="dock-sn-002")
        with self.assertRaises(DomainError) as raised:
            self.gateway.bind_device(conflict)
        self.assertEqual(raised.exception.code, "IDEMP_409")

    def test_new_key_for_bound_device_uses_required_failure(self):
        self.gateway.bind_device(self.command)
        duplicate = replace(
            self.command,
            request_id="req_bind_002",
            idempotency_key="bind-key-002",
        )
        with self.assertRaises(DomainError) as raised:
            self.gateway.bind_device(duplicate)
        self.assertEqual(raised.exception.code, "DJI_502")
        self.assertEqual(
            raised.exception.details["scenario"],
            "device_already_bound",
        )

    def test_dispatch_receipt_is_accepted_but_explicitly_simulated(self):
        command = DispatchMissionCommand(
            tenant_id="t_customer_001",
            request_id="req_dispatch_001",
            idempotency_key="dispatch-key-001",
            device_sn="dock-sn-001",
            mission_id="ms_001",
            route_version_id="route-v1",
        )
        receipt = self.gateway.dispatch_mission(command)
        self.assertTrue(receipt.accepted)
        self.assertEqual(
            receipt.raw_payload["execution_proof"],
            "SIMULATED_ONLY",
        )


class GatewayEventTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 6, 19, 5, 0, tzinfo=timezone.utc)
        self.gateway = DjiDock3Simulator(clock=lambda: self.now)

    def test_four_baseline_events_use_fixed_outer_contract(self):
        bound = self.gateway.bind_device(
            DeviceCommand(
                "t_customer_001",
                "req_bind",
                "key_bind",
                "dock-sn-001",
            )
        )
        status = self.gateway.sync_device_status(
            DeviceCommand(
                "t_customer_001",
                "req_status",
                "key_status",
                "dock-sn-001",
            )
        )
        telemetry = self.gateway.publish_telemetry(
            TelemetryCommand(
                "t_customer_001",
                "req_tel",
                "key_tel",
                "dock-sn-001",
                76,
                -62,
            )
        )
        low_battery = self.gateway.publish_exception(
            ExceptionCommand(
                "t_customer_001",
                "req_low",
                "key_low",
                "dock-sn-001",
                "low_battery",
                {"battery": 18},
            )
        )
        media = self.gateway.complete_media_sync(
            MediaSyncCommand(
                "t_customer_001",
                "req_media",
                "key_media",
                "dock-sn-001",
                "ms_001",
                "med_001",
                "t_customer_001/proj_001/ms_001/media/med_001.mp4",
                "sha256:abc",
            )
        )

        self.assertTrue(bound.accepted)
        self.assertEqual(status.event_code, "device_bound")
        self.assertEqual(status.raw_payload["status"], "BOUND")
        for event in (status, telemetry, low_battery, media):
            self.assertEqual(
                set(event.to_payload()),
                {
                    "event_code",
                    "event_time",
                    "device_sn",
                    "raw_payload",
                },
            )

    def test_invalid_telemetry_maps_to_format_error(self):
        command = TelemetryCommand(
            "t_customer_001",
            "req_tel",
            "key_tel",
            "dock-sn-001",
            101,
            -62,
        )
        with self.assertRaises(DomainError) as raised:
            self.gateway.publish_telemetry(command)
        self.assertEqual(raised.exception.code, "DJI_502")
        self.assertEqual(
            raised.exception.details["scenario"],
            "format_error",
        )

    def test_invalid_checksum_maps_to_media_499(self):
        command = MediaSyncCommand(
            "t_customer_001",
            "req_media",
            "key_media",
            "dock-sn-001",
            "ms_001",
            "med_001",
            "tenant/path/media.mp4",
            "md5:abc",
        )
        with self.assertRaises(DomainError) as raised:
            self.gateway.complete_media_sync(command)
        self.assertEqual(raised.exception.code, "MEDIA_499")
        self.assertEqual(
            raised.exception.details["scenario"],
            "checksum_error",
        )

    def test_all_required_failure_scenarios_have_fixed_mapping(self):
        expected = {
            "credential_error": ("DJI_502", False),
            "device_already_bound": ("DJI_502", False),
            "format_error": ("DJI_502", False),
            "timeout": ("DJI_502", True),
            "device_no_response": ("DJI_502", True),
            "checksum_error": ("MEDIA_499", True),
        }
        for scenario, (code, retryable) in expected.items():
            with self.subTest(scenario=scenario):
                gateway = DjiDock3Simulator(clock=lambda: self.now)
                gateway.fail_next("bind_device", scenario)
                with self.assertRaises(DomainError) as raised:
                    gateway.bind_device(
                        DeviceCommand(
                            "t_customer_001",
                            "req",
                            f"key-{scenario}",
                            "dock-sn-001",
                        )
                    )
                self.assertEqual(raised.exception.code, code)
                self.assertEqual(
                    raised.exception.details["scenario"],
                    scenario,
                )
                self.assertEqual(
                    raised.exception.details["retryable"],
                    retryable,
                )
                self.assertNotIn("credential", raised.exception.details)


if __name__ == "__main__":
    unittest.main()
