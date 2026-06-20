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
        self._idempotency: dict[
            tuple[str, str, str],
            tuple[str, object],
        ] = {}

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

    def bind_device(self, command: DeviceCommand) -> GatewayReceipt:
        def operation():
            if command.device_sn in self._bound_devices:
                raise DomainError(
                    "DJI_502",
                    "设备已绑定",
                    {
                        "scenario": "device_already_bound",
                        "retryable": False,
                    },
                )
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

    def sync_device_status(self, command: DeviceCommand) -> FlightEvent:
        raise NotImplementedError

    def publish_telemetry(self, command: TelemetryCommand) -> FlightEvent:
        raise NotImplementedError

    def publish_exception(self, command: ExceptionCommand) -> FlightEvent:
        raise NotImplementedError

    def complete_media_sync(self, command: MediaSyncCommand) -> FlightEvent:
        raise NotImplementedError
