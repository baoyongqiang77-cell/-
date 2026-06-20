import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from drone_inspection.dji_gateway import (
    DeviceCommand,
    DjiGateway,
    FlightEvent,
    GatewayMode,
    GatewayReceipt,
)


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


if __name__ == "__main__":
    unittest.main()
