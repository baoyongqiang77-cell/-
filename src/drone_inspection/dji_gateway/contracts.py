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

    def __post_init__(self) -> None:
        if self.event_time.utcoffset() is None:
            raise ValueError("event_time must include timezone information")

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

    def dispatch_mission(
        self, command: DispatchMissionCommand
    ) -> GatewayReceipt: ...

    def publish_telemetry(self, command: TelemetryCommand) -> FlightEvent: ...

    def publish_exception(self, command: ExceptionCommand) -> FlightEvent: ...

    def complete_media_sync(self, command: MediaSyncCommand) -> FlightEvent: ...
