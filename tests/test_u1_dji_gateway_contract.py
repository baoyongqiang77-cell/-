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
    FlightEvent,
    GatewayMode,
    GatewayReceipt,
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


if __name__ == "__main__":
    unittest.main()
