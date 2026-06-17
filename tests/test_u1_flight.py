import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from drone_inspection.errors import DomainError
from drone_inspection.flight import DjiDock3Simulator, MissionStateMachine, NetworkPolicy


class U1FlightTests(unittest.TestCase):
    def test_dji_simulator_emits_normalized_callback_payloads(self):
        simulator = DjiDock3Simulator()

        events = [
            simulator.bind_device("t_customer_001", "dock-sn-001"),
            simulator.telemetry("dock-sn-001", battery=76, signal=-62),
            simulator.low_battery("dock-sn-001", battery=18),
            simulator.media_upload_completed(
                device_sn="dock-sn-001",
                mission_id="ms_001",
                media_id="med_001",
                storage_uri="t_customer_001/proj_001/ms_001/media/med_001.mp4",
                checksum="sha256:abc",
            ),
        ]

        for event in events:
            self.assertEqual(
                set(event.payload.keys()),
                {"event_code", "event_time", "device_sn", "raw_payload"},
            )
            self.assertEqual(event.payload["device_sn"], "dock-sn-001")

    def test_dji_simulator_covers_required_failure_branches(self):
        simulator = DjiDock3Simulator()
        failures = simulator.failure_scenarios()

        self.assertEqual(
            set(failures.keys()),
            {
                "credential_error",
                "device_already_bound",
                "format_error",
                "timeout",
                "device_no_response",
                "checksum_error",
            },
        )
        self.assertEqual(failures["checksum_error"].code, "MEDIA_499")
        self.assertEqual(failures["credential_error"].code, "DJI_502")

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

    def test_only_dji_gateway_can_access_internet(self):
        policy = NetworkPolicy(dji_gateway_services={"dji_gateway"})

        self.assertTrue(policy.can_access_internet("dji_gateway"))
        self.assertFalse(policy.can_access_internet("flight_service"))
        self.assertFalse(policy.can_access_internet("analysis_service"))
        self.assertFalse(policy.can_access_internet("training_service"))


if __name__ == "__main__":
    unittest.main()
