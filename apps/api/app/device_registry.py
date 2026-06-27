from __future__ import annotations

from hashlib import sha256
from json import dumps
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from drone_inspection.dji_gateway import FlightEvent
from drone_inspection.errors import DomainError

from .models import DeviceModel, DockModel, utc_now
from .repositories import RequestMeta, U0Repository


class DeviceRegistryRepository:
    def __init__(self, session: Session):
        self.session = session

    def list_devices(self, tenant_id: str) -> list[DeviceModel]:
        statement = (
            select(DeviceModel)
            .where(DeviceModel.tenant_id == tenant_id)
            .order_by(DeviceModel.id)
        )
        return list(self.session.scalars(statement))

    def device(self, tenant_id: str, device_id: str) -> DeviceModel:
        item = self.session.scalar(
            select(DeviceModel).where(
                DeviceModel.tenant_id == tenant_id,
                DeviceModel.id == device_id,
            )
        )
        if item is None:
            raise DomainError("TENANT_404", "设备不存在或不可访问")
        return item

    def device_by_serial(self, serial_number: str) -> DeviceModel:
        item = self.session.scalar(
            select(DeviceModel).where(DeviceModel.serial_number == serial_number)
        )
        if item is None:
            raise DomainError("TENANT_404", "设备不存在或不可访问")
        return item

    def list_docks(self, tenant_id: str) -> list[DockModel]:
        statement = (
            select(DockModel)
            .where(DockModel.tenant_id == tenant_id)
            .order_by(DockModel.id)
        )
        return list(self.session.scalars(statement))

    def dock(self, tenant_id: str, dock_id: str) -> DockModel:
        item = self.session.scalar(
            select(DockModel).where(
                DockModel.tenant_id == tenant_id,
                DockModel.id == dock_id,
            )
        )
        if item is None:
            raise DomainError("TENANT_404", "机巢不存在或不可访问")
        return item


def device_payload(item: DeviceModel) -> dict:
    return {
        "id": item.id,
        "tenant_id": item.tenant_id,
        "device_type": item.device_type,
        "name": item.name,
        "manufacturer": item.manufacturer,
        "model": item.model,
        "serial_number": item.serial_number,
        "firmware_version": item.firmware_version,
        "status": item.status,
        "last_seen_at": _iso(item.last_seen_at),
        "created_at": _iso(item.created_at),
        "updated_at": _iso(item.updated_at),
    }


def dock_payload(item: DockModel) -> dict:
    return {
        "id": item.id,
        "tenant_id": item.tenant_id,
        "device_id": item.device_id,
        "bound_drone_device_id": item.bound_drone_device_id,
        "edge_node_device_id": item.edge_node_device_id,
        "environment_json": item.environment_json,
        "created_at": _iso(item.created_at),
        "updated_at": _iso(item.updated_at),
    }


def _iso(value) -> str | None:
    return value.isoformat() if value is not None else None


class DeviceRegistryService:
    DEVICE_UPDATE_FIELDS = {"name", "manufacturer", "model", "firmware_version"}
    DOCK_UPDATE_FIELDS = {
        "bound_drone_device_id",
        "edge_node_device_id",
        "environment_json",
    }

    def __init__(self, session: Session):
        self.session = session
        self.registry = DeviceRegistryRepository(session)
        self.u0 = U0Repository(session)

    def create_device(
        self,
        actor_id: str,
        tenant_id: str,
        values: dict,
        idempotency_key: str | None,
        request_meta: RequestMeta,
    ) -> dict:
        self.u0.tenant_context(tenant_id)
        fingerprint = self._fingerprint(
            {"action": "create_device", "tenant_id": tenant_id, "values": values}
        )

        def operation() -> dict:
            duplicate = self.session.scalar(
                select(DeviceModel.id).where(
                    DeviceModel.serial_number == values["serial_number"]
                )
            )
            if duplicate is not None:
                raise DomainError(
                    "MISSION_422",
                    "Device serial number already exists",
                    {"field": "serial_number"},
                )
            item = DeviceModel(
                id=f"dev_{uuid4().hex[:12]}",
                tenant_id=tenant_id,
                device_type=values["device_type"],
                name=values["name"],
                manufacturer=values["manufacturer"],
                model=values.get("model"),
                serial_number=values["serial_number"],
                firmware_version=values.get("firmware_version"),
            )
            self.session.add(item)
            self.session.flush()
            self.u0.audit(
                tenant_id=tenant_id,
                actor=actor_id,
                action="device_created",
                resource_type="device",
                resource_id=item.id,
                request_meta=request_meta,
            )
            return device_payload(item)

        return self.u0.run_idempotent(
            tenant_id,
            "POST",
            "device-create",
            idempotency_key,
            fingerprint,
            operation,
        )

    def update_device(
        self,
        actor_id: str,
        tenant_id: str,
        device_id: str,
        values: dict,
        idempotency_key: str | None,
        request_meta: RequestMeta,
    ) -> dict:
        item = self.registry.device(tenant_id, device_id)
        normalized = {
            key: value for key, value in values.items() if key in self.DEVICE_UPDATE_FIELDS
        }
        fingerprint = self._fingerprint(
            {
                "action": "update_device",
                "tenant_id": tenant_id,
                "device_id": device_id,
                "values": normalized,
            }
        )

        def operation() -> dict:
            for key, value in normalized.items():
                setattr(item, key, value)
            item.updated_at = utc_now()
            self.session.flush()
            self.u0.audit(
                tenant_id=tenant_id,
                actor=actor_id,
                action="device_updated",
                resource_type="device",
                resource_id=item.id,
                request_meta=request_meta,
            )
            return device_payload(item)

        return self.u0.run_idempotent(
            tenant_id,
            "PATCH",
            f"device-update:{device_id}",
            idempotency_key,
            fingerprint,
            operation,
        )

    def create_dock(
        self,
        actor_id: str,
        tenant_id: str,
        values: dict,
        idempotency_key: str | None,
        request_meta: RequestMeta,
    ) -> dict:
        dock_device = self._typed_device(
            tenant_id, values["device_id"], "DOCK", "device_id"
        )
        bound_drone_id = values.get("bound_drone_device_id")
        edge_node_id = values.get("edge_node_device_id")
        if bound_drone_id is not None:
            self._typed_device(
                tenant_id, bound_drone_id, "DRONE", "bound_drone_device_id"
            )
        if edge_node_id is not None:
            self._typed_device(
                tenant_id, edge_node_id, "EDGE_NODE", "edge_node_device_id"
            )
        fingerprint = self._fingerprint(
            {"action": "create_dock", "tenant_id": tenant_id, "values": values}
        )

        def operation() -> dict:
            existing = self.session.scalar(
                select(DockModel.id).where(DockModel.device_id == dock_device.id)
            )
            if existing is not None:
                raise DomainError(
                    "MISSION_422",
                    "Dock registry already exists for this device",
                    {"field": "device_id"},
                )
            item = DockModel(
                id=f"dock_{uuid4().hex[:12]}",
                tenant_id=tenant_id,
                device_id=dock_device.id,
                bound_drone_device_id=bound_drone_id,
                edge_node_device_id=edge_node_id,
                environment_json=values.get("environment_json", {}),
            )
            self.session.add(item)
            self.session.flush()
            self.u0.audit(
                tenant_id=tenant_id,
                actor=actor_id,
                action="dock_created",
                resource_type="dock",
                resource_id=item.id,
                request_meta=request_meta,
            )
            return dock_payload(item)

        return self.u0.run_idempotent(
            tenant_id,
            "POST",
            "dock-create",
            idempotency_key,
            fingerprint,
            operation,
        )

    def update_dock(
        self,
        actor_id: str,
        tenant_id: str,
        dock_id: str,
        values: dict,
        idempotency_key: str | None,
        request_meta: RequestMeta,
    ) -> dict:
        item = self.registry.dock(tenant_id, dock_id)
        normalized = {
            key: value for key, value in values.items() if key in self.DOCK_UPDATE_FIELDS
        }
        bound_drone_id = normalized.get("bound_drone_device_id")
        edge_node_id = normalized.get("edge_node_device_id")
        if bound_drone_id is not None:
            self._typed_device(
                tenant_id, bound_drone_id, "DRONE", "bound_drone_device_id"
            )
        if edge_node_id is not None:
            self._typed_device(
                tenant_id, edge_node_id, "EDGE_NODE", "edge_node_device_id"
            )
        fingerprint = self._fingerprint(
            {
                "action": "update_dock",
                "tenant_id": tenant_id,
                "dock_id": dock_id,
                "values": normalized,
            }
        )

        def operation() -> dict:
            for key, value in normalized.items():
                setattr(item, key, value)
            item.updated_at = utc_now()
            self.session.flush()
            self.u0.audit(
                tenant_id=tenant_id,
                actor=actor_id,
                action="dock_updated",
                resource_type="dock",
                resource_id=item.id,
                request_meta=request_meta,
            )
            return dock_payload(item)

        return self.u0.run_idempotent(
            tenant_id,
            "PATCH",
            f"dock-update:{dock_id}",
            idempotency_key,
            fingerprint,
            operation,
        )

    def _typed_device(
        self,
        tenant_id: str,
        device_id: str,
        expected_type: str,
        field: str,
    ) -> DeviceModel:
        item = self.registry.device(tenant_id, device_id)
        if item.device_type != expected_type:
            raise DomainError(
                "MISSION_422",
                "Device type does not match dock binding",
                {"field": field, "expected_type": expected_type},
            )
        return item

    @staticmethod
    def _fingerprint(payload: dict) -> str:
        encoded = dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
        return sha256(encoded).hexdigest()


class DeviceStatusService:
    ENVIRONMENT_KEYS = {
        "dock_door",
        "charging",
        "weather",
        "payload_status",
    }

    def __init__(self, session: Session):
        self.session = session
        self.registry = DeviceRegistryRepository(session)
        self.u0 = U0Repository(session)

    def apply_event(self, event: FlightEvent, request_meta: RequestMeta) -> dict:
        device = self.registry.device_by_serial(event.device_sn)
        if event.event_code != "device_status":
            return device_payload(device)

        status = event.raw_payload.get("status")
        if status not in {"ONLINE", "OFFLINE"}:
            raise DomainError(
                "DJI_502",
                "DJI 设备状态格式错误",
                {"field": "raw_payload.status"},
            )

        before_status = device.status
        device.status = status
        if status == "ONLINE":
            device.last_seen_at = event.event_time
        device.updated_at = utc_now()

        dock = self.session.scalar(
            select(DockModel).where(
                DockModel.tenant_id == device.tenant_id,
                DockModel.device_id == device.id,
            )
        )
        if dock is not None:
            environment = dict(dock.environment_json)
            environment.update(
                {
                    key: event.raw_payload[key]
                    for key in self.ENVIRONMENT_KEYS
                    if key in event.raw_payload
                }
            )
            dock.environment_json = environment
            dock.updated_at = utc_now()

        self.u0.audit(
            tenant_id=device.tenant_id,
            actor="dji_gateway",
            action="device_status_synced",
            resource_type="device",
            resource_id=device.id,
            request_meta=request_meta,
            before_status=before_status,
            after_status=status,
        )
        self.session.commit()
        return device_payload(device)
