from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from .constants import MISSION_STATUSES
from .errors import DomainError


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class CallbackEvent:
    payload: dict


class DjiDock3Simulator:
    def __init__(self):
        self.bound_devices: set[str] = set()

    def _event(self, event_code: str, device_sn: str, raw_payload: dict) -> CallbackEvent:
        return CallbackEvent(
            {
                "event_code": event_code,
                "event_time": _now(),
                "device_sn": device_sn,
                "raw_payload": raw_payload,
            }
        )

    def bind_device(self, tenant_id: str, device_sn: str) -> CallbackEvent:
        if device_sn in self.bound_devices:
            raise DomainError("DJI_502", "设备已绑定", {"device_sn": device_sn})
        self.bound_devices.add(device_sn)
        return self._event(
            "device_bound",
            device_sn,
            {"tenant_id": tenant_id, "status": "BOUND"},
        )

    def telemetry(self, device_sn: str, battery: int, signal: int) -> CallbackEvent:
        return self._event(
            "telemetry",
            device_sn,
            {"battery": battery, "signal": signal},
        )

    def low_battery(self, device_sn: str, battery: int) -> CallbackEvent:
        return self._event("low_battery", device_sn, {"battery": battery})

    def media_upload_completed(
        self,
        device_sn: str,
        mission_id: str,
        media_id: str,
        storage_uri: str,
        checksum: str,
    ) -> CallbackEvent:
        return self._event(
            "media_upload_completed",
            device_sn,
            {
                "mission_id": mission_id,
                "media_id": media_id,
                "storage_uri": storage_uri,
                "checksum": checksum,
                "chunk_total": 1,
                "chunk_completed": 1,
            },
        )

    def failure_scenarios(self) -> dict[str, DomainError]:
        return {
            "credential_error": DomainError("DJI_502", "DJI 凭证错误"),
            "device_already_bound": DomainError("DJI_502", "设备已绑定"),
            "format_error": DomainError("DJI_502", "DJI 回调格式错误"),
            "timeout": DomainError("DJI_502", "DJI 调用超时"),
            "device_no_response": DomainError("DJI_502", "设备无响应"),
            "checksum_error": DomainError("MEDIA_499", "媒体 checksum 错误"),
        }


class MissionStateMachine:
    ALLOWED = {
        "DRAFT": {"PENDING_APPROVAL", "CANCELLED", "ARCHIVED"},
        "PENDING_APPROVAL": {"APPROVED", "REJECTED", "EXPIRED"},
        "APPROVED": {"DISPATCHING", "CANCELLED"},
        "DISPATCHING": {"DISPATCHED", "DISPATCH_FAILED"},
        "DISPATCHED": {"EXECUTING", "ABORTED"},
        "EXECUTING": {"PAUSED", "RETURNING", "LOST_LINK", "COMPLETED", "ABORTED"},
        "PAUSED": {"EXECUTING", "RETURNING", "ABORTED"},
        "RETURNING": {"COMPLETED", "ABORTED"},
        "LOST_LINK": {"EXECUTING", "RETURNING", "ABORTED"},
        "COMPLETED": {"MEDIA_SYNCING", "ARCHIVED"},
        "ABORTED": {"MEDIA_SYNCING", "ARCHIVED"},
        "MEDIA_SYNCING": {"PARTIAL_MEDIA_READY", "MEDIA_READY", "SYNC_FAILED"},
        "PARTIAL_MEDIA_READY": {"MEDIA_READY", "ANALYSIS_READY"},
        "MEDIA_READY": {"ANALYSIS_READY", "ARCHIVED"},
        "SYNC_FAILED": {"MEDIA_SYNCING", "ARCHIVED"},
        "ANALYSIS_READY": {"ARCHIVED"},
        "CANCELLED": {"ARCHIVED"},
        "REJECTED": {"ARCHIVED"},
        "EXPIRED": {"ARCHIVED"},
        "DISPATCH_FAILED": {"DISPATCHING", "ARCHIVED"},
        "ARCHIVED": set(),
    }

    def __init__(self, mission_id: str, tenant_id: str):
        self.mission_id = mission_id
        self.tenant_id = tenant_id
        self.status = "DRAFT"
        self.history: list[tuple[str, str, str]] = []

    def transition(self, target_status: str, actor: str) -> None:
        if target_status not in MISSION_STATUSES:
            raise DomainError("STATE_409", "未知任务状态", {"target_status": target_status})
        if target_status not in self.ALLOWED[self.status]:
            raise DomainError(
                "STATE_409",
                "当前状态不允许目标操作",
                {
                    "current_status": self.status,
                    "target_status": target_status,
                    "allowed": sorted(self.ALLOWED[self.status]),
                },
            )
        previous = self.status
        self.status = target_status
        self.history.append((actor, previous, target_status))

    def apply_device_ack(self, accepted: bool, actor: str) -> None:
        self.transition("DISPATCHED" if accepted else "DISPATCH_FAILED", actor)


@dataclass(frozen=True)
class NetworkPolicy:
    dji_gateway_services: set[str]

    def can_access_internet(self, service_name: str) -> bool:
        return service_name in self.dji_gateway_services

