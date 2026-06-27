from __future__ import annotations

from hashlib import sha256
from json import dumps
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from drone_inspection.errors import DomainError

from .models import FlightEventModel, FlightExceptionLinkModel, MissionModel
from .repositories import RequestMeta, U0Repository


EXCEPTION_MAPPING = {
    "low_battery": ("LOW_BATTERY", "HIGH"),
    "device_unresponsive": ("DEVICE_UNRESPONSIVE", "HIGH"),
    "lost_link": ("LOST_LINK", "CRITICAL"),
    "timeout": ("TIMEOUT", "MEDIUM"),
}


def flight_exception_payload(item: FlightExceptionLinkModel) -> dict:
    return {
        "id": item.id,
        "tenant_id": item.tenant_id,
        "mission_id": item.mission_id,
        "flight_event_id": item.flight_event_id,
        "device_id": item.device_id,
        "exception_code": item.exception_code,
        "severity": item.severity,
        "status": item.status,
        "payload_json": item.payload_json,
        "created_at": item.created_at.isoformat(),
        "updated_at": item.updated_at.isoformat(),
    }


class FlightExceptionService:
    def __init__(self, session: Session):
        self.session = session
        self.u0 = U0Repository(session)

    def list_exceptions(self, tenant_id: str, mission_id: str) -> list[dict]:
        self._mission(tenant_id, mission_id)
        statement = (
            select(FlightExceptionLinkModel)
            .where(
                FlightExceptionLinkModel.tenant_id == tenant_id,
                FlightExceptionLinkModel.mission_id == mission_id,
            )
            .order_by(FlightExceptionLinkModel.created_at, FlightExceptionLinkModel.id)
        )
        return [
            flight_exception_payload(item) for item in self.session.scalars(statement)
        ]

    def link_exception(
        self,
        actor_id: str,
        tenant_id: str,
        mission_id: str,
        flight_event_id: str,
        idempotency_key: str | None,
        request_meta: RequestMeta,
    ) -> dict:
        self.u0.tenant_context(tenant_id)
        fingerprint = self._fingerprint(
            {
                "action": "link_flight_exception",
                "tenant_id": tenant_id,
                "mission_id": mission_id,
                "flight_event_id": flight_event_id,
            }
        )

        def operation() -> dict:
            self._mission(tenant_id, mission_id)
            event = self._flight_event(tenant_id, flight_event_id)
            if event.mission_id != mission_id:
                raise DomainError(
                    "MISSION_422",
                    "Flight event does not belong to the requested mission",
                    {"flight_event_id": flight_event_id, "mission_id": mission_id},
                )
            mapping = EXCEPTION_MAPPING.get(event.event_code)
            if mapping is None:
                raise DomainError(
                    "MISSION_422",
                    "Flight event code is not linkable as a flight exception",
                    {"event_code": event.event_code},
                )
            exception_code, severity = mapping
            item = FlightExceptionLinkModel(
                id=f"fex_{uuid4().hex[:12]}",
                tenant_id=tenant_id,
                mission_id=mission_id,
                flight_event_id=event.id,
                device_id=event.device_id,
                exception_code=exception_code,
                severity=severity,
                status="OPEN",
                payload_json={
                    "source": "flight_event",
                    "mapping": {
                        "event_code": event.event_code,
                        "exception_code": exception_code,
                        "severity": severity,
                    },
                    "flight_event": {
                        "event_code": event.event_code,
                        "event_time": event.event_time.isoformat(),
                        "device_sn": event.device_sn,
                        "payload_json": event.payload_json,
                    },
                },
            )
            self.session.add(item)
            try:
                self.session.flush()
            except IntegrityError as exc:
                raise DomainError(
                    "IDEMP_409",
                    "Flight event has already been linked as an exception",
                    {"flight_event_id": flight_event_id},
                ) from exc
            self.u0.audit(
                tenant_id=tenant_id,
                actor=actor_id,
                action="flight_exception_linked",
                resource_type="flight_exception",
                resource_id=item.id,
                request_meta=request_meta,
            )
            return flight_exception_payload(item)

        return self.u0.run_idempotent(
            tenant_id,
            "POST",
            f"mission-{mission_id}-flight-event-{flight_event_id}-exception",
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

    def _flight_event(self, tenant_id: str, flight_event_id: str) -> FlightEventModel:
        item = self.session.scalar(
            select(FlightEventModel).where(
                FlightEventModel.tenant_id == tenant_id,
                FlightEventModel.id == flight_event_id,
            )
        )
        if item is None:
            raise DomainError(
                "TENANT_404", "Flight event does not exist or is not accessible"
            )
        return item

    @staticmethod
    def _fingerprint(payload: dict) -> str:
        encoded = dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode(
            "utf-8"
        )
        return sha256(encoded).hexdigest()
