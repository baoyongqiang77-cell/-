from __future__ import annotations

from hashlib import sha256
from json import dumps
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from drone_inspection.dji_gateway import FlightEvent
from drone_inspection.errors import DomainError

from .models import DeviceModel, FlightEventModel, MissionModel
from .repositories import RequestMeta, U0Repository


def flight_event_payload(item: FlightEventModel) -> dict:
    return {
        "id": item.id,
        "tenant_id": item.tenant_id,
        "mission_id": item.mission_id,
        "device_id": item.device_id,
        "event_code": item.event_code,
        "event_time": item.event_time.isoformat(),
        "device_sn": item.device_sn,
        "payload_json": item.payload_json,
        "created_at": item.created_at.isoformat(),
    }


class TelemetryEventService:
    def __init__(self, session: Session):
        self.session = session
        self.u0 = U0Repository(session)

    def list_events(self, tenant_id: str, mission_id: str) -> list[dict]:
        self._mission(tenant_id, mission_id)
        statement = (
            select(FlightEventModel)
            .where(
                FlightEventModel.tenant_id == tenant_id,
                FlightEventModel.mission_id == mission_id,
            )
            .order_by(FlightEventModel.event_time, FlightEventModel.id)
        )
        return [flight_event_payload(item) for item in self.session.scalars(statement)]

    def record_event(
        self,
        actor_id: str,
        tenant_id: str,
        mission_id: str,
        event: FlightEvent,
        idempotency_key: str | None,
        request_meta: RequestMeta,
    ) -> dict:
        self.u0.tenant_context(tenant_id)
        payload = event.to_payload()
        fingerprint = self._fingerprint(
            {
                "action": "record_flight_event",
                "tenant_id": tenant_id,
                "mission_id": mission_id,
                "payload": payload,
            }
        )

        def operation() -> dict:
            mission = self._mission(tenant_id, mission_id)
            device = self._device_by_serial(tenant_id, event.device_sn)
            item = FlightEventModel(
                id=f"fe_{uuid4().hex[:12]}",
                tenant_id=tenant_id,
                mission_id=mission.id,
                device_id=device.id,
                event_code=event.event_code,
                event_time=event.event_time,
                device_sn=event.device_sn,
                payload_json=payload,
            )
            self.session.add(item)
            self.session.flush()
            self.u0.audit(
                tenant_id=tenant_id,
                actor=actor_id,
                action="flight_event_recorded",
                resource_type="flight_event",
                resource_id=item.id,
                request_meta=request_meta,
            )
            return flight_event_payload(item)

        return self.u0.run_idempotent(
            tenant_id,
            "POST",
            f"mission-{mission_id}-telemetry-events",
            idempotency_key,
            fingerprint,
            operation,
        )

    def _mission(self, tenant_id: str, mission_id: str) -> MissionModel:
        item = self.session.scalar(
            select(MissionModel).where(
                MissionModel.tenant_id == tenant_id,
                MissionModel.id == mission_id,
            )
        )
        if item is None:
            raise DomainError("TENANT_404", "Mission does not exist or is not accessible")
        return item

    def _device_by_serial(self, tenant_id: str, device_sn: str) -> DeviceModel:
        item = self.session.scalar(
            select(DeviceModel).where(
                DeviceModel.tenant_id == tenant_id,
                DeviceModel.serial_number == device_sn,
            )
        )
        if item is None:
            raise DomainError("TENANT_404", "Device does not exist or is not accessible")
        return item

    @staticmethod
    def _fingerprint(payload: dict) -> str:
        encoded = dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode(
            "utf-8"
        )
        return sha256(encoded).hexdigest()
