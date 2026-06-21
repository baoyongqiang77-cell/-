from __future__ import annotations

from dataclasses import dataclass

from .constants import MISSION_STATUSES
from .dji_gateway import DjiDock3Simulator
from .errors import DomainError

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


__all__ = ["DjiDock3Simulator", "MissionStateMachine", "NetworkPolicy"]
