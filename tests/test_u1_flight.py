import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from drone_inspection.dji_gateway import (
    DeviceCommand,
    DjiDock3Simulator,
    ExceptionCommand,
    MediaSyncCommand,
    TelemetryCommand,
)
from drone_inspection.errors import DomainError
from drone_inspection.flight import (
    DjiDock3Simulator as FlightSimulator,
    MissionStateMachine,
    NetworkPolicy,
)


class U1FlightTests(unittest.TestCase):
    def test_flight_module_reexports_gateway_simulator(self):
        self.assertIs(FlightSimulator, DjiDock3Simulator)

    def test_dji_simulator_emits_normalized_callback_payloads(self):
        simulator = DjiDock3Simulator()
        simulator.bind_device(
            DeviceCommand(
                "t_customer_001",
                "req_bind",
                "key_bind",
                "dock-sn-001",
            )
        )
        events = [
            simulator.publish_telemetry(
                TelemetryCommand(
                    "t_customer_001",
                    "req_tel",
                    "key_tel",
                    "dock-sn-001",
                    76,
                    -62,
                )
            ),
            simulator.publish_exception(
                ExceptionCommand(
                    "t_customer_001",
                    "req_low",
                    "key_low",
                    "dock-sn-001",
                    "low_battery",
                    {"battery": 18},
                )
            ),
            simulator.complete_media_sync(
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
            ),
        ]

        for event in events:
            self.assertEqual(
                set(event.to_payload()),
                {"event_code", "event_time", "device_sn", "raw_payload"},
            )
            self.assertEqual(event.device_sn, "dock-sn-001")

    def test_dji_simulator_covers_required_failure_branches(self):
        self.assertEqual(
            set(DjiDock3Simulator.FAILURE_SPECS),
            {
                "credential_error",
                "device_already_bound",
                "format_error",
                "timeout",
                "device_no_response",
                "checksum_error",
            },
        )

    def test_mission_state_machine_accepts_only_documented_transitions(self):
        mission = MissionStateMachine(mission_id="ms_001", tenant_id="t_customer_001")

        mission.transition("PENDING_APPROVAL", actor="pilot")
        mission.transition("APPROVED", actor="approver")
        mission.transition("DISPATCHING", actor="pilot")
        mission.apply_device_ack(accepted=True, actor="dji_gateway")
        mission.transition("EXECUTING", actor="dji_gateway")
        mission.transition("COMPLETED", actor="dji_gateway")
        mission.transition("MEDIA_SYNCING", actor="dji_gateway")
        mission.transition("MEDIA_READY", actor="dji_gateway")
        mission.transition("ANALYSIS_READY", actor="system")

        self.assertEqual(mission.status, "ANALYSIS_READY")

        invalid = MissionStateMachine(mission_id="ms_002", tenant_id="t_customer_001")
        with self.assertRaises(DomainError) as raised:
            invalid.transition("DISPATCHED", actor="pilot")
        self.assertEqual(raised.exception.code, "STATE_409")

    def test_rejected_device_ack_is_the_only_dispatch_failure_transition(self):
        mission = MissionStateMachine("ms_rejected", "t_customer_001")
        mission.transition("PENDING_APPROVAL", "pilot")
        mission.transition("APPROVED", "approver")
        mission.transition("DISPATCHING", "pilot")

        mission.apply_device_ack(accepted=False, actor="dji_gateway")

        self.assertEqual(mission.status, "DISPATCH_FAILED")
        self.assertEqual(
            mission.history[-1],
            ("dji_gateway", "DISPATCHING", "DISPATCH_FAILED"),
        )

    def test_only_dji_gateway_can_access_internet(self):
        policy = NetworkPolicy(dji_gateway_services={"dji_gateway"})

        self.assertTrue(policy.can_access_internet("dji_gateway"))
        self.assertFalse(policy.can_access_internet("flight_service"))
        self.assertFalse(policy.can_access_internet("analysis_service"))
        self.assertFalse(policy.can_access_internet("training_service"))


if __name__ == "__main__":
    unittest.main()
