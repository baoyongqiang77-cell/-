from __future__ import annotations

from datetime import datetime
from hashlib import sha256
from json import dumps
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from drone_inspection.dji_gateway import DispatchMissionCommand, DjiGateway
from drone_inspection.errors import DomainError
from drone_inspection.flight import MissionStateMachine

from .models import (
    BridgeAssetModel,
    DeviceModel,
    DockModel,
    MissionApprovalModel,
    MissionDispatchReceiptModel,
    MissionModel,
    RoadAssetModel,
    RouteModel,
    RouteVersionModel,
    SlopeAssetModel,
)
from .repositories import RequestMeta, U0Repository


TARGET_TYPES = {"road", "bridge", "slope"}


class MissionRepository:
    def __init__(self, session: Session):
        self.session = session

    def list_missions(self, tenant_id: str) -> list[MissionModel]:
        statement = (
            select(MissionModel)
            .where(MissionModel.tenant_id == tenant_id)
            .order_by(MissionModel.id)
        )
        return list(self.session.scalars(statement))

    def mission(self, tenant_id: str, mission_id: str) -> MissionModel:
        item = self.session.scalar(
            select(MissionModel).where(
                MissionModel.tenant_id == tenant_id,
                MissionModel.id == mission_id,
            )
        )
        if item is None:
            raise DomainError("TENANT_404", "Mission does not exist or is not accessible")
        return item

    def approval(
        self, tenant_id: str, mission_id: str, approval_id: str
    ) -> MissionApprovalModel:
        item = self.session.scalar(
            select(MissionApprovalModel).where(
                MissionApprovalModel.tenant_id == tenant_id,
                MissionApprovalModel.mission_id == mission_id,
                MissionApprovalModel.id == approval_id,
            )
        )
        if item is None:
            raise DomainError(
                "TENANT_404", "Mission approval does not exist or is not accessible"
            )
        return item


def mission_payload(item: MissionModel) -> dict:
    return {
        "id": item.id,
        "tenant_id": item.tenant_id,
        "route_id": item.route_id,
        "route_version_id": item.route_version_id,
        "device_id": item.device_id,
        "dock_id": item.dock_id,
        "status": item.status,
        "schedule_time": item.schedule_time.isoformat(),
        "inspection_targets": item.inspection_targets,
        "media_policy": item.media_policy,
        "created_at": item.created_at.isoformat(),
        "updated_at": item.updated_at.isoformat(),
    }


def approval_payload(item: MissionApprovalModel, mission_status: str) -> dict:
    return {
        "id": item.id,
        "tenant_id": item.tenant_id,
        "mission_id": item.mission_id,
        "status": item.status,
        "mission_status": mission_status,
        "external_system": item.external_system,
        "external_id": item.external_id,
        "external_status": item.external_status,
        "callback_payload": item.callback_payload,
        "submitted_by": item.submitted_by,
        "decided_by": item.decided_by,
        "decision_comment": item.decision_comment,
        "created_at": item.created_at.isoformat(),
        "updated_at": item.updated_at.isoformat(),
    }


def dispatch_receipt_payload(
    item: MissionDispatchReceiptModel, mission_status: str
) -> dict:
    return {
        "id": item.id,
        "tenant_id": item.tenant_id,
        "mission_id": item.mission_id,
        "mission_status": mission_status,
        "device_id": item.device_id,
        "route_version_id": item.route_version_id,
        "operation": item.operation,
        "device_sn": item.device_sn,
        "accepted": item.accepted,
        "external_request_id": item.external_request_id,
        "gateway_mode": item.gateway_mode,
        "raw_payload": item.raw_payload,
        "received_at": item.received_at.isoformat(),
        "created_at": item.created_at.isoformat(),
    }


class MissionManagementService:
    def __init__(self, session: Session):
        self.session = session
        self.missions = MissionRepository(session)
        self.u0 = U0Repository(session)

    def create_mission(
        self,
        actor_id: str,
        tenant_id: str,
        values: dict,
        idempotency_key: str | None,
        request_meta: RequestMeta,
    ) -> dict:
        self.u0.tenant_context(tenant_id)
        normalized = self._normalize(tenant_id, values)
        fingerprint = self._fingerprint(
            {"action": "create_mission", "tenant_id": tenant_id, **normalized}
        )

        def operation() -> dict:
            item = MissionModel(
                id=f"ms_{uuid4().hex[:12]}",
                tenant_id=tenant_id,
                status="DRAFT",
                **normalized,
            )
            self.session.add(item)
            self.session.flush()
            self.u0.audit(
                tenant_id=tenant_id,
                actor=actor_id,
                action="mission_created",
                resource_type="mission",
                resource_id=item.id,
                request_meta=request_meta,
                after_status="DRAFT",
            )
            return mission_payload(item)

        return self.u0.run_idempotent(
            tenant_id, "POST", "mission-create", idempotency_key, fingerprint, operation
        )

    def submit_approval(
        self,
        actor_id: str,
        tenant_id: str,
        mission_id: str,
        values: dict,
        idempotency_key: str | None,
        request_meta: RequestMeta,
    ) -> dict:
        self.u0.tenant_context(tenant_id)
        normalized = self._normalize_approval(values)
        fingerprint = self._fingerprint(
            {
                "action": "submit_approval",
                "tenant_id": tenant_id,
                "mission_id": mission_id,
                **normalized,
            }
        )

        def operation() -> dict:
            mission = self.missions.mission(tenant_id, mission_id)
            self._require_transition(mission.status, "PENDING_APPROVAL")
            before_status = mission.status
            mission.status = "PENDING_APPROVAL"
            item = MissionApprovalModel(
                id=f"ma_{uuid4().hex[:12]}",
                tenant_id=tenant_id,
                mission_id=mission.id,
                status="PENDING_APPROVAL",
                external_system=normalized["external_system"],
                external_id=normalized["external_id"],
                external_status=normalized["external_status"],
                callback_payload=normalized["callback_payload"],
                submitted_by=actor_id,
                decision_comment=normalized["comment"],
            )
            self.session.add(item)
            self.session.flush()
            self.u0.audit(
                tenant_id=tenant_id,
                actor=actor_id,
                action="mission_approval_submitted",
                resource_type="mission_approval",
                resource_id=item.id,
                request_meta=request_meta,
                before_status=before_status,
                after_status="PENDING_APPROVAL",
            )
            return approval_payload(item, mission.status)

        return self.u0.run_idempotent(
            tenant_id,
            "POST",
            f"mission-{mission_id}-submit-approval",
            idempotency_key,
            fingerprint,
            operation,
        )

    def decide_approval(
        self,
        actor_id: str,
        tenant_id: str,
        mission_id: str,
        approval_id: str,
        decision: str,
        values: dict,
        idempotency_key: str | None,
        request_meta: RequestMeta,
    ) -> dict:
        if decision not in {"APPROVED", "REJECTED"}:
            raise DomainError("MISSION_422", "Approval decision is invalid")
        self.u0.tenant_context(tenant_id)
        normalized = self._normalize_approval(values)
        fingerprint = self._fingerprint(
            {
                "action": "decide_approval",
                "tenant_id": tenant_id,
                "mission_id": mission_id,
                "approval_id": approval_id,
                "decision": decision,
                **normalized,
            }
        )

        def operation() -> dict:
            mission = self.missions.mission(tenant_id, mission_id)
            approval = self.missions.approval(tenant_id, mission_id, approval_id)
            if approval.status != "PENDING_APPROVAL":
                raise DomainError(
                    "STATE_409",
                    "Approval has already been decided",
                    {"current_status": approval.status},
                )
            self._require_transition(mission.status, decision)
            before_status = mission.status
            mission.status = decision
            approval.status = decision
            approval.external_status = normalized["external_status"]
            approval.external_id = normalized["external_id"] or approval.external_id
            approval.callback_payload = normalized["callback_payload"]
            approval.decided_by = actor_id
            approval.decision_comment = normalized["comment"]
            self.session.flush()
            self.u0.audit(
                tenant_id=tenant_id,
                actor=actor_id,
                action="mission_approved" if decision == "APPROVED" else "mission_rejected",
                resource_type="mission_approval",
                resource_id=approval.id,
                request_meta=request_meta,
                before_status=before_status,
                after_status=decision,
            )
            return approval_payload(approval, mission.status)

        return self.u0.run_idempotent(
            tenant_id,
            "POST",
            f"mission-{mission_id}-approval-{approval_id}-{decision.lower()}",
            idempotency_key,
            fingerprint,
            operation,
        )

    def dispatch_mission(
        self,
        actor_id: str,
        tenant_id: str,
        mission_id: str,
        values: dict,
        idempotency_key: str | None,
        request_meta: RequestMeta,
        gateway: DjiGateway,
    ) -> dict:
        self.u0.tenant_context(tenant_id)
        normalized = {"dispatch_note": _optional_str(values.get("dispatch_note"))}
        fingerprint = self._fingerprint(
            {
                "action": "dispatch_mission",
                "tenant_id": tenant_id,
                "mission_id": mission_id,
                **normalized,
            }
        )

        def operation() -> dict:
            mission = self.missions.mission(tenant_id, mission_id)
            self._require_transition(mission.status, "DISPATCHING")
            before_status = mission.status
            device = self._device(tenant_id, mission.device_id)
            mission.status = "DISPATCHING"
            command = DispatchMissionCommand(
                tenant_id=tenant_id,
                request_id=request_meta.request_id,
                idempotency_key=idempotency_key or "",
                device_sn=device.serial_number,
                mission_id=mission.id,
                route_version_id=mission.route_version_id,
            )
            receipt = gateway.dispatch_mission(command)
            target_status = "DISPATCHED" if receipt.accepted else "DISPATCH_FAILED"
            self._require_transition(mission.status, target_status)
            mission.status = target_status
            item = MissionDispatchReceiptModel(
                id=f"mdr_{uuid4().hex[:12]}",
                tenant_id=tenant_id,
                mission_id=mission.id,
                device_id=mission.device_id,
                route_version_id=mission.route_version_id,
                operation=receipt.operation,
                device_sn=receipt.device_sn,
                accepted=receipt.accepted,
                external_request_id=receipt.external_request_id,
                gateway_mode=receipt.mode.value,
                raw_payload=receipt.raw_payload,
                received_at=receipt.received_at,
            )
            self.session.add(item)
            self.session.flush()
            self.u0.audit(
                tenant_id=tenant_id,
                actor=actor_id,
                action=(
                    "mission_dispatched"
                    if target_status == "DISPATCHED"
                    else "mission_dispatch_failed"
                ),
                resource_type="mission_dispatch_receipt",
                resource_id=item.id,
                request_meta=request_meta,
                before_status=before_status,
                after_status=target_status,
            )
            return dispatch_receipt_payload(item, mission.status)

        return self.u0.run_idempotent(
            tenant_id,
            "POST",
            f"mission-{mission_id}-dispatch",
            idempotency_key,
            fingerprint,
            operation,
        )

    def _normalize(self, tenant_id: str, values: dict) -> dict:
        route_id = values.get("route_id")
        route_version_id = values.get("route_version_id")
        device_id = values.get("device_id")
        dock_id = values.get("dock_id")
        schedule_time = values.get("schedule_time")
        targets = values.get("inspection_targets") or []
        media_policy = values.get("media_policy")
        _require_non_empty(
            {
                "route_id": route_id,
                "route_version_id": route_version_id,
                "device_id": device_id,
            },
            ("route_id", "route_version_id", "device_id"),
        )
        route = self._route(tenant_id, route_id)
        version = self._route_version(tenant_id, route.id, route_version_id)
        device = self._device(tenant_id, device_id)
        if device.device_type not in {"DOCK", "DRONE"}:
            raise DomainError(
                "MISSION_422",
                "Mission device must be a dock or drone",
                {"field": "device_id"},
            )
        if dock_id is not None:
            self._dock(tenant_id, dock_id)
        if not isinstance(schedule_time, datetime):
            raise DomainError(
                "MISSION_422",
                "Mission schedule_time is invalid",
                {"field": "schedule_time"},
            )
        targets = self._normalize_targets(tenant_id, targets)
        if not isinstance(media_policy, dict) or not (
            media_policy.get("video") is True
            or isinstance(media_policy.get("image_interval_sec"), int)
        ):
            raise DomainError(
                "MISSION_422",
                "Mission media policy is invalid",
                {"field": "media_policy"},
            )
        return {
            "route_id": route.id,
            "route_version_id": version.id,
            "device_id": device.id,
            "dock_id": dock_id,
            "schedule_time": schedule_time,
            "inspection_targets": targets,
            "media_policy": media_policy,
        }

    def _normalize_approval(self, values: dict) -> dict:
        callback_payload = values.get("callback_payload") or {}
        if not isinstance(callback_payload, dict):
            raise DomainError(
                "MISSION_422",
                "Approval callback payload is invalid",
                {"field": "callback_payload"},
            )
        external_system = _optional_str(values.get("external_system"))
        if external_system is not None and external_system not in {
            "BUILT_IN",
            "OA",
            "AIRSPACE",
            "MANUAL",
        }:
            raise DomainError(
                "MISSION_422",
                "Approval external system is invalid",
                {"field": "external_system"},
            )
        return {
            "external_system": external_system,
            "external_id": _optional_str(values.get("external_id")),
            "external_status": _optional_str(values.get("external_status")),
            "callback_payload": callback_payload,
            "comment": _optional_str(values.get("comment")),
        }

    @staticmethod
    def _require_transition(current_status: str, target_status: str) -> None:
        allowed = MissionStateMachine.ALLOWED.get(current_status, set())
        if target_status not in allowed:
            raise DomainError(
                "STATE_409",
                "Mission status does not allow this approval action",
                {
                    "current_status": current_status,
                    "target_status": target_status,
                    "allowed": sorted(allowed),
                },
            )

    def _route(self, tenant_id: str, route_id: str) -> RouteModel:
        item = self.session.scalar(
            select(RouteModel).where(RouteModel.tenant_id == tenant_id, RouteModel.id == route_id)
        )
        if item is None:
            raise DomainError("TENANT_404", "Route does not exist or is not accessible")
        return item

    def _route_version(
        self, tenant_id: str, route_id: str, version_id: str
    ) -> RouteVersionModel:
        item = self.session.scalar(
            select(RouteVersionModel).where(
                RouteVersionModel.tenant_id == tenant_id,
                RouteVersionModel.route_id == route_id,
                RouteVersionModel.id == version_id,
            )
        )
        if item is None:
            raise DomainError(
                "TENANT_404", "Route version does not exist or is not accessible"
            )
        return item

    def _device(self, tenant_id: str, device_id: str) -> DeviceModel:
        item = self.session.scalar(
            select(DeviceModel).where(
                DeviceModel.tenant_id == tenant_id,
                DeviceModel.id == device_id,
            )
        )
        if item is None:
            raise DomainError("TENANT_404", "Device does not exist or is not accessible")
        return item

    def _dock(self, tenant_id: str, dock_id: str) -> DockModel:
        item = self.session.scalar(
            select(DockModel).where(DockModel.tenant_id == tenant_id, DockModel.id == dock_id)
        )
        if item is None:
            raise DomainError("TENANT_404", "Dock does not exist or is not accessible")
        return item

    def _normalize_targets(self, tenant_id: str, targets: list) -> list[dict]:
        if not isinstance(targets, list) or not targets:
            raise DomainError(
                "MISSION_422",
                "Mission inspection targets are required",
                {"field": "inspection_targets"},
            )
        normalized = []
        for index, target in enumerate(targets):
            if not isinstance(target, dict):
                raise DomainError("GIS_422", "Mission target is invalid", {"field": str(index)})
            asset_type = target.get("asset_type")
            asset_id = target.get("asset_id")
            if asset_type not in TARGET_TYPES or not str(asset_id or "").strip():
                raise DomainError("GIS_422", "Mission target is invalid", {"field": str(index)})
            self._require_asset(tenant_id, asset_type, asset_id)
            normalized.append({"asset_type": asset_type, "asset_id": asset_id})
        return normalized

    def _require_asset(self, tenant_id: str, asset_type: str, asset_id: str) -> None:
        model = {"road": RoadAssetModel, "bridge": BridgeAssetModel, "slope": SlopeAssetModel}[
            asset_type
        ]
        found = self.session.scalar(
            select(model.id).where(model.tenant_id == tenant_id, model.id == asset_id)
        )
        if found is None:
            raise DomainError(
                "TENANT_404",
                "Mission target does not exist or is not accessible",
            )

    @staticmethod
    def _fingerprint(payload: dict) -> str:
        encoded = dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode(
            "utf-8"
        )
        return sha256(encoded).hexdigest()


def _require_non_empty(values: dict, fields: tuple[str, ...]) -> None:
    for field in fields:
        if not str(values.get(field, "")).strip():
            raise DomainError(
                "MISSION_422",
                "Required mission field is empty",
                {"field": field},
            )


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
