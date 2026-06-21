# U1 DJI Gateway Contract Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the U1-F01 DJI Dock 3 gateway protocol and deterministic development simulator without claiming or embedding real DJI production integration.

**Architecture:** Add a focused `drone_inspection.dji_gateway` package containing immutable command/result contracts, a runtime-checkable gateway protocol, and an in-process simulator. Keep mission state and network policy in `flight.py`, re-export the simulator there for compatibility, and require all DJI-facing behavior to flow through the protocol.

**Tech Stack:** Python 3.12, standard-library dataclasses/protocols/enums/hashlib/json, existing `DomainError`, `unittest`.

---

## File Map

- Create `src/drone_inspection/dji_gateway/__init__.py`: public gateway API exports.
- Create `src/drone_inspection/dji_gateway/contracts.py`: commands, receipts, events, mode, and `DjiGateway` protocol.
- Create `src/drone_inspection/dji_gateway/simulator.py`: deterministic simulator, idempotency, validation, and failure injection.
- Modify `src/drone_inspection/flight.py`: remove the old simulator implementation and re-export the new simulator while retaining mission state and network policy.
- Create `tests/test_u1_dji_gateway_contract.py`: contract, receipt, idempotency, event, and failure tests.
- Modify `tests/test_u1_flight.py`: migrate rule tests to command-based gateway calls.
- Modify `docs/60-test-reports/U1-flight-test-report.md`: record U1-F01 evidence and boundaries.

## Task 1: Immutable Gateway Contract

**Files:**
- Create: `src/drone_inspection/dji_gateway/__init__.py`
- Create: `src/drone_inspection/dji_gateway/contracts.py`
- Create: `tests/test_u1_dji_gateway_contract.py`

- [ ] **Step 1: Write the failing public-contract tests**

Create `tests/test_u1_dji_gateway_contract.py` with path setup matching the other unit tests, then add:

```python
from datetime import datetime, timezone
from unittest import TestCase

from drone_inspection.dji_gateway import (
    DeviceCommand,
    DjiGateway,
    DispatchMissionCommand,
    FlightEvent,
    GatewayMode,
    GatewayReceipt,
)


class GatewayContractTests(TestCase):
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
```

- [ ] **Step 2: Run the tests and confirm RED**

Run:

```powershell
& '.\.venv\Scripts\python.exe' -m unittest tests.test_u1_dji_gateway_contract.GatewayContractTests -v
```

Expected: import failure for `drone_inspection.dji_gateway`.

- [ ] **Step 3: Implement the exact contract types**

Create `contracts.py` with:

```python
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Protocol, runtime_checkable


class GatewayMode(str, Enum):
    SIMULATOR = "SIMULATOR"
    REAL = "REAL"


@dataclass(frozen=True)
class DeviceCommand:
    tenant_id: str
    request_id: str
    idempotency_key: str
    device_sn: str


@dataclass(frozen=True)
class DispatchMissionCommand(DeviceCommand):
    mission_id: str
    route_version_id: str


@dataclass(frozen=True)
class TelemetryCommand(DeviceCommand):
    battery: int
    signal: int


@dataclass(frozen=True)
class ExceptionCommand(DeviceCommand):
    event_code: str
    values: dict


@dataclass(frozen=True)
class MediaSyncCommand(DeviceCommand):
    mission_id: str
    media_id: str
    storage_uri: str
    checksum: str


@dataclass(frozen=True)
class GatewayReceipt:
    operation: str
    request_id: str
    device_sn: str
    accepted: bool
    external_request_id: str
    received_at: datetime
    raw_payload: dict
    mode: GatewayMode


@dataclass(frozen=True)
class FlightEvent:
    event_code: str
    event_time: datetime
    device_sn: str
    raw_payload: dict

    def to_payload(self) -> dict:
        event_time = self.event_time.astimezone(timezone.utc)
        return {
            "event_code": self.event_code,
            "event_time": event_time.isoformat().replace("+00:00", "Z"),
            "device_sn": self.device_sn,
            "raw_payload": self.raw_payload,
        }


@runtime_checkable
class DjiGateway(Protocol):
    mode: GatewayMode

    def bind_device(self, command: DeviceCommand) -> GatewayReceipt: ...
    def sync_device_status(self, command: DeviceCommand) -> FlightEvent: ...
    def dispatch_mission(self, command: DispatchMissionCommand) -> GatewayReceipt: ...
    def publish_telemetry(self, command: TelemetryCommand) -> FlightEvent: ...
    def publish_exception(self, command: ExceptionCommand) -> FlightEvent: ...
    def complete_media_sync(self, command: MediaSyncCommand) -> FlightEvent: ...
```

Create `__init__.py` that imports and exposes all nine public types through `__all__`.

- [ ] **Step 4: Run the contract tests and confirm GREEN**

Run the command from Step 2. Expected: 3 tests pass.

- [ ] **Step 5: Commit the contract**

```powershell
git add src/drone_inspection/dji_gateway tests/test_u1_dji_gateway_contract.py
git commit -m "feat: define U1 DJI gateway contract"
```

## Task 2: Device Actions, Receipts, and Idempotency

**Files:**
- Create: `src/drone_inspection/dji_gateway/simulator.py`
- Modify: `src/drone_inspection/dji_gateway/__init__.py`
- Modify: `tests/test_u1_dji_gateway_contract.py`

- [ ] **Step 1: Add failing simulator receipt tests**

```python
from dataclasses import replace
from datetime import datetime, timezone

from drone_inspection.dji_gateway import DjiDock3Simulator
from drone_inspection.errors import DomainError


class GatewayReceiptTests(TestCase):
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
        self.assertEqual(raised.exception.details["scenario"], "device_already_bound")

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
        self.assertEqual(receipt.raw_payload["execution_proof"], "SIMULATED_ONLY")
```

- [ ] **Step 2: Run and confirm RED**

Run:

```powershell
& '.\.venv\Scripts\python.exe' -m unittest tests.test_u1_dji_gateway_contract.GatewayReceiptTests -v
```

Expected: import failure for `DjiDock3Simulator`.

- [ ] **Step 3: Implement the minimal simulator core**

Create `simulator.py` with:

```python
from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from hashlib import sha256
import json
from typing import Callable

from drone_inspection.errors import DomainError

from .contracts import (
    DeviceCommand,
    DispatchMissionCommand,
    ExceptionCommand,
    FlightEvent,
    GatewayMode,
    GatewayReceipt,
    MediaSyncCommand,
    TelemetryCommand,
)


class DjiDock3Simulator:
    mode = GatewayMode.SIMULATOR

    def __init__(self, clock: Callable[[], datetime] | None = None):
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._bound_devices: set[str] = set()
        self._idempotency: dict[tuple[str, str, str], tuple[str, object]] = {}
        self._failures: dict[str, str] = {}

    def _fingerprint(self, command) -> str:
        value = json.dumps(asdict(command), sort_keys=True, separators=(",", ":"))
        return sha256(value.encode("utf-8")).hexdigest()

    def _idempotent(self, operation: str, command, callback):
        if not command.idempotency_key:
            raise DomainError("IDEMP_409", "缺少幂等键")
        key = (operation, command.tenant_id, command.idempotency_key)
        fingerprint = self._fingerprint(command)
        existing = self._idempotency.get(key)
        if existing:
            if existing[0] != fingerprint:
                raise DomainError("IDEMP_409", "幂等键请求冲突")
            return existing[1]
        result = callback()
        self._idempotency[key] = (fingerprint, result)
        return result

    def _receipt(self, operation: str, command, raw_payload: dict) -> GatewayReceipt:
        suffix = sha256(
            f"{operation}:{command.tenant_id}:{command.idempotency_key}".encode()
        ).hexdigest()[:12]
        return GatewayReceipt(
            operation=operation,
            request_id=command.request_id,
            device_sn=command.device_sn,
            accepted=True,
            external_request_id=f"sim_{suffix}",
            received_at=self._clock(),
            raw_payload=raw_payload,
            mode=self.mode,
        )

    def bind_device(self, command: DeviceCommand) -> GatewayReceipt:
        def operation():
            if command.device_sn in self._bound_devices:
                raise DomainError(
                    "DJI_502",
                    "设备已绑定",
                    {"scenario": "device_already_bound", "retryable": False},
                )
            self._bound_devices.add(command.device_sn)
            return self._receipt(
                "bind_device",
                command,
                {"tenant_id": command.tenant_id, "status": "BOUND"},
            )
        return self._idempotent("bind_device", command, operation)

    def dispatch_mission(self, command: DispatchMissionCommand) -> GatewayReceipt:
        return self._idempotent(
            "dispatch_mission",
            command,
            lambda: self._receipt(
                "dispatch_mission",
                command,
                {
                    "mission_id": command.mission_id,
                    "route_version_id": command.route_version_id,
                    "execution_proof": "SIMULATED_ONLY",
                },
            ),
        )
```

Add `DjiDock3Simulator` to the package exports. Leave the four event methods unimplemented only until Task 3; protocol runtime checks only method presence, so add these exact stubs:

```python
    def sync_device_status(self, command: DeviceCommand) -> FlightEvent:
        raise NotImplementedError

    def publish_telemetry(self, command: TelemetryCommand) -> FlightEvent:
        raise NotImplementedError

    def publish_exception(self, command: ExceptionCommand) -> FlightEvent:
        raise NotImplementedError

    def complete_media_sync(self, command: MediaSyncCommand) -> FlightEvent:
        raise NotImplementedError
```

- [ ] **Step 4: Run receipt and contract tests**

Expected: 8 total tests pass.

- [ ] **Step 5: Commit simulator device actions**

```powershell
git add src/drone_inspection/dji_gateway tests/test_u1_dji_gateway_contract.py
git commit -m "feat: simulate idempotent DJI device actions"
```

## Task 3: Standard Events and Deterministic Failure Injection

**Files:**
- Modify: `src/drone_inspection/dji_gateway/simulator.py`
- Modify: `tests/test_u1_dji_gateway_contract.py`

- [ ] **Step 1: Add failing event tests**

Add tests that construct `TelemetryCommand`, `ExceptionCommand`, and `MediaSyncCommand` with fixed request IDs and keys. Assert:

```python
class GatewayEventTests(TestCase):
    def setUp(self):
        self.now = datetime(2026, 6, 19, 5, 0, tzinfo=timezone.utc)
        self.gateway = DjiDock3Simulator(clock=lambda: self.now)

    def test_four_baseline_events_use_fixed_outer_contract(self):
        bound = self.gateway.bind_device(DeviceCommand(
            "t_customer_001", "req_bind", "key_bind", "dock-sn-001"
        ))
        status = self.gateway.sync_device_status(DeviceCommand(
            "t_customer_001", "req_status", "key_status", "dock-sn-001"
        ))
        telemetry = self.gateway.publish_telemetry(TelemetryCommand(
            "t_customer_001", "req_tel", "key_tel", "dock-sn-001", 76, -62
        ))
        low_battery = self.gateway.publish_exception(ExceptionCommand(
            "t_customer_001", "req_low", "key_low", "dock-sn-001",
            "low_battery", {"battery": 18}
        ))
        media = self.gateway.complete_media_sync(MediaSyncCommand(
            "t_customer_001", "req_media", "key_media", "dock-sn-001",
            "ms_001", "med_001",
            "t_customer_001/proj_001/ms_001/media/med_001.mp4",
            "sha256:abc"
        ))

        self.assertTrue(bound.accepted)
        self.assertEqual(status.event_code, "device_status")
        for event in (status, telemetry, low_battery, media):
            self.assertEqual(
                set(event.to_payload()),
                {"event_code", "event_time", "device_sn", "raw_payload"},
            )

    def test_invalid_telemetry_maps_to_format_error(self):
        command = TelemetryCommand(
            "t_customer_001", "req_tel", "key_tel", "dock-sn-001", 101, -62
        )
        with self.assertRaises(DomainError) as raised:
            self.gateway.publish_telemetry(command)
        self.assertEqual(raised.exception.code, "DJI_502")
        self.assertEqual(raised.exception.details["scenario"], "format_error")

    def test_invalid_checksum_maps_to_media_499(self):
        command = MediaSyncCommand(
            "t_customer_001", "req_media", "key_media", "dock-sn-001",
            "ms_001", "med_001", "tenant/path/media.mp4", "md5:abc"
        )
        with self.assertRaises(DomainError) as raised:
            self.gateway.complete_media_sync(command)
        self.assertEqual(raised.exception.code, "MEDIA_499")
        self.assertEqual(raised.exception.details["scenario"], "checksum_error")
```

- [ ] **Step 2: Add failing failure-matrix tests**

```python
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
                    gateway.bind_device(DeviceCommand(
                        "t_customer_001", "req", f"key-{scenario}", "dock-sn-001"
                    ))
                self.assertEqual(raised.exception.code, code)
                self.assertEqual(raised.exception.details["scenario"], scenario)
                self.assertEqual(raised.exception.details["retryable"], retryable)
                self.assertNotIn("credential", raised.exception.details)
```

- [ ] **Step 3: Run and confirm RED**

Run the `GatewayEventTests`; expected failures are the `NotImplementedError` methods and missing `fail_next`.

- [ ] **Step 4: Implement event conversion and failure injection**

Add this mapping and helpers to `DjiDock3Simulator`:

```python
    FAILURE_SPECS = {
        "credential_error": ("DJI_502", "DJI 凭证错误", False),
        "device_already_bound": ("DJI_502", "设备已绑定", False),
        "format_error": ("DJI_502", "DJI 回调格式错误", False),
        "timeout": ("DJI_502", "DJI 调用超时", True),
        "device_no_response": ("DJI_502", "设备无响应", True),
        "checksum_error": ("MEDIA_499", "媒体 checksum 错误", True),
    }

    def fail_next(self, operation: str, scenario: str) -> None:
        if scenario not in self.FAILURE_SPECS:
            raise ValueError(f"unknown failure scenario: {scenario}")
        self._failures[operation] = scenario

    def _raise_failure(self, scenario: str) -> None:
        code, message, retryable = self.FAILURE_SPECS[scenario]
        raise DomainError(
            code,
            message,
            {"scenario": scenario, "retryable": retryable},
        )

    def _consume_failure(self, operation: str) -> None:
        scenario = self._failures.pop(operation, None)
        if scenario:
            self._raise_failure(scenario)

    def _event(self, event_code: str, command, raw_payload: dict) -> FlightEvent:
        return FlightEvent(
            event_code=event_code,
            event_time=self._clock(),
            device_sn=command.device_sn,
            raw_payload=raw_payload,
        )
```

Call `_consume_failure(operation)` as the first line inside each idempotent operation callback, then replace the four stubs with:

```python
    def sync_device_status(self, command: DeviceCommand) -> FlightEvent:
        def operation():
            self._consume_failure("sync_device_status")
            return self._event(
                "device_status",
                command,
                {"status": "ONLINE", "mode": self.mode.value},
            )
        return self._idempotent("sync_device_status", command, operation)

    def publish_telemetry(self, command: TelemetryCommand) -> FlightEvent:
        def operation():
            self._consume_failure("publish_telemetry")
            if not 0 <= command.battery <= 100:
                self._raise_failure("format_error")
            return self._event(
                "telemetry",
                command,
                {"battery": command.battery, "signal": command.signal},
            )
        return self._idempotent("publish_telemetry", command, operation)

    def publish_exception(self, command: ExceptionCommand) -> FlightEvent:
        def operation():
            self._consume_failure("publish_exception")
            if not command.event_code.strip():
                self._raise_failure("format_error")
            return self._event(command.event_code, command, command.values)
        return self._idempotent("publish_exception", command, operation)

    def complete_media_sync(self, command: MediaSyncCommand) -> FlightEvent:
        def operation():
            self._consume_failure("complete_media_sync")
            if not command.checksum.startswith("sha256:"):
                self._raise_failure("checksum_error")
            return self._event(
                "media_upload_completed",
                command,
                {
                    "mission_id": command.mission_id,
                    "media_id": command.media_id,
                    "storage_uri": command.storage_uri,
                    "checksum": command.checksum,
                    "chunk_total": 1,
                    "chunk_completed": 1,
                },
            )
        return self._idempotent("complete_media_sync", command, operation)
```

Also call `_consume_failure("bind_device")` and `_consume_failure("dispatch_mission")` inside those callbacks. Replace the inline duplicate-device `DomainError` with `_raise_failure("device_already_bound")` so every failure has the same safe details.

- [ ] **Step 5: Run all new gateway tests and confirm GREEN**

```powershell
& '.\.venv\Scripts\python.exe' -m unittest tests.test_u1_dji_gateway_contract -v
```

Expected: all contract, receipt, event, validation, and six scenario subtests pass.

- [ ] **Step 6: Commit events and failures**

```powershell
git add src/drone_inspection/dji_gateway/simulator.py tests/test_u1_dji_gateway_contract.py
git commit -m "feat: normalize DJI simulator events and failures"
```

## Task 4: Integrate the Contract with Existing Flight Rules

**Files:**
- Modify: `src/drone_inspection/flight.py`
- Modify: `tests/test_u1_flight.py`

- [ ] **Step 1: Rewrite existing simulator tests against commands**

Update the imports in `tests/test_u1_flight.py`:

```python
from drone_inspection.dji_gateway import (
    DeviceCommand,
    DjiDock3Simulator,
    ExceptionCommand,
    MediaSyncCommand,
    TelemetryCommand,
)
from drone_inspection.flight import MissionStateMachine, NetworkPolicy
```

Replace the two old simulator tests with:

```python
    def test_dji_simulator_emits_normalized_callback_payloads(self):
        simulator = DjiDock3Simulator()
        simulator.bind_device(DeviceCommand(
            "t_customer_001", "req_bind", "key_bind", "dock-sn-001"
        ))
        events = [
            simulator.publish_telemetry(TelemetryCommand(
                "t_customer_001", "req_tel", "key_tel",
                "dock-sn-001", 76, -62
            )),
            simulator.publish_exception(ExceptionCommand(
                "t_customer_001", "req_low", "key_low",
                "dock-sn-001", "low_battery", {"battery": 18}
            )),
            simulator.complete_media_sync(MediaSyncCommand(
                "t_customer_001", "req_media", "key_media",
                "dock-sn-001", "ms_001", "med_001",
                "t_customer_001/proj_001/ms_001/media/med_001.mp4",
                "sha256:abc"
            )),
        ]
        for event in events:
            self.assertEqual(
                set(event.to_payload()),
                {"event_code", "event_time", "device_sn", "raw_payload"},
            )

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
```

Keep the mission-state and network-policy tests unchanged, and add:

```python
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
```

- [ ] **Step 2: Run the existing U1 suite and confirm RED**

```powershell
& '.\.venv\Scripts\python.exe' -m unittest tests.test_u1_flight -v
```

Expected: imports or calls fail because `flight.py` still exposes the old simulator contract.

- [ ] **Step 3: Replace the old simulator with a compatibility export**

Remove `CallbackEvent` and the old `DjiDock3Simulator` class from `flight.py`. Add:

```python
from .dji_gateway import DjiDock3Simulator

__all__ = ["DjiDock3Simulator", "MissionStateMachine", "NetworkPolicy"]
```

Do not change `MissionStateMachine.ALLOWED`, `apply_device_ack`, or `NetworkPolicy`.

- [ ] **Step 4: Run U1 and full gateway tests**

```powershell
& '.\.venv\Scripts\python.exe' -m unittest tests.test_u1_flight tests.test_u1_dji_gateway_contract -v
```

Expected: all U1 tests pass, including state-machine rejection and network isolation.

- [ ] **Step 5: Commit flight integration**

```powershell
git add src/drone_inspection/flight.py tests/test_u1_flight.py
git commit -m "refactor: route U1 flight rules through DJI gateway contract"
```

## Task 5: Test Evidence, Full Regression, and Remote Sync

**Files:**
- Modify: `docs/60-test-reports/U1-flight-test-report.md`

- [ ] **Step 1: Update U1 evidence**

Record the exact new test count and evidence for protocol compatibility, simulator mode, accepted receipts, idempotency replay/conflict, fixed callback schema, six failure scenarios, mission-state separation, and network boundary. Preserve these explicit limitations:

```text
- DJI Cloud API version, credentials, callback signatures, aircraft, and payload models remain unconfirmed.
- The simulator is M1 development evidence only and cannot satisfy real-flight or production acceptance.
- Device, route, mission, approval, telemetry WebSocket, and flight-event persistence remain later U1 increments.
```

- [ ] **Step 2: Run the focused U1 suite**

```powershell
& '.\.venv\Scripts\python.exe' -m unittest tests.test_u1_dji_gateway_contract tests.test_u1_flight -v
```

Expected: all U1-F01 and existing flight tests pass.

- [ ] **Step 3: Run the complete project regression**

```powershell
& '.\.venv\Scripts\python.exe' -m unittest discover -s tests -v
git diff --check
git status --short --branch
```

Expected: the previous 66 tests plus the new U1-F01 tests pass; `git diff --check` has no output; only the intended report change remains.

- [ ] **Step 4: Commit the evidence**

```powershell
git add docs/60-test-reports/U1-flight-test-report.md
git commit -m "docs: record U1 DJI gateway verification"
```

- [ ] **Step 5: Push and verify the branch**

```powershell
git -c http.proxy=http://127.0.0.1:7897 push origin codex/u1-dji-gateway
git rev-list --left-right --count origin/codex/u1-dji-gateway...HEAD
```

Expected: remote difference is `0 0`.
