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
    FAILURE_SPECS = {
        "credential_error": ("DJI_502", "DJI 凭证错误", False),
        "device_already_bound": ("DJI_502", "设备已绑定", False),
        "format_error": ("DJI_502", "DJI 回调格式错误", False),
        "timeout": ("DJI_502", "DJI 调用超时", True),
        "device_no_response": ("DJI_502", "设备无响应", True),
        "checksum_error": ("MEDIA_499", "媒体 checksum 错误", True),
    }

    def __init__(self, clock: Callable[[], datetime] | None = None):
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._bound_devices: set[str] = set()
        self._idempotency: dict[
            tuple[str, str, str],
            tuple[str, object],
        ] = {}
        self._failures: dict[str, str] = {}

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

    def _fingerprint(self, command) -> str:
        value = json.dumps(
            asdict(command),
            sort_keys=True,
            separators=(",", ":"),
        )
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

    def _receipt(
        self,
        operation: str,
        command,
        raw_payload: dict,
    ) -> GatewayReceipt:
        suffix = sha256(
            (
                f"{operation}:{command.tenant_id}:"
                f"{command.idempotency_key}"
            ).encode()
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

    def _event(
        self,
        event_code: str,
        command,
        raw_payload: dict,
    ) -> FlightEvent:
        return FlightEvent(
            event_code=event_code,
            event_time=self._clock(),
            device_sn=command.device_sn,
            raw_payload=raw_payload,
        )

    def bind_device(self, command: DeviceCommand) -> GatewayReceipt:
        def operation():
            self._consume_failure("bind_device")
            if command.device_sn in self._bound_devices:
                self._raise_failure("device_already_bound")
            self._bound_devices.add(command.device_sn)
            return self._receipt(
                "bind_device",
                command,
                {
                    "tenant_id": command.tenant_id,
                    "status": "BOUND",
                },
            )

        return self._idempotent("bind_device", command, operation)

    def dispatch_mission(
        self,
        command: DispatchMissionCommand,
    ) -> GatewayReceipt:
        def operation():
            self._consume_failure("dispatch_mission")
            return self._receipt(
                "dispatch_mission",
                command,
                {
                    "mission_id": command.mission_id,
                    "route_version_id": command.route_version_id,
                    "execution_proof": "SIMULATED_ONLY",
                },
            )

        return self._idempotent(
            "dispatch_mission",
            command,
            operation,
        )

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
