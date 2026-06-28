from __future__ import annotations

from hashlib import sha256
from json import dumps
import re
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from drone_inspection.errors import DomainError

from .models import FlightEventModel, MediaFileModel, MissionModel
from .repositories import RequestMeta, U0Repository


SUPPORTED_MEDIA_TYPES = {"VIDEO", "IMAGE", "THUMBNAIL"}
CHECKSUM_PATTERN = re.compile(r"^(sha256:[0-9a-fA-F]{64}|md5:[0-9a-fA-F]{32})$")


def media_file_payload(item: MediaFileModel) -> dict:
    return {
        "id": item.id,
        "tenant_id": item.tenant_id,
        "mission_id": item.mission_id,
        "device_id": item.device_id,
        "source_event_id": item.source_event_id,
        "media_id": item.media_id,
        "media_type": item.media_type,
        "storage_uri": item.storage_uri,
        "checksum": item.checksum,
        "status": item.status,
        "payload_json": item.payload_json,
        "created_at": item.created_at.isoformat(),
        "updated_at": item.updated_at.isoformat(),
    }


class MediaSyncService:
    def __init__(self, session: Session):
        self.session = session
        self.u0 = U0Repository(session)

    def list_media_files(self, tenant_id: str, mission_id: str) -> list[dict]:
        self._mission(tenant_id, mission_id)
        statement = (
            select(MediaFileModel)
            .where(
                MediaFileModel.tenant_id == tenant_id,
                MediaFileModel.mission_id == mission_id,
            )
            .order_by(MediaFileModel.created_at, MediaFileModel.id)
        )
        return [media_file_payload(item) for item in self.session.scalars(statement)]

    def sync_media(
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
                "action": "sync_media_file",
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
            if event.event_code != "media_upload_completed":
                raise DomainError(
                    "MISSION_422",
                    "Flight event code is not a media upload completion",
                    {"event_code": event.event_code},
                )
            media = self._media_payload(tenant_id, event)
            item = MediaFileModel(
                id=f"med_{uuid4().hex[:12]}",
                tenant_id=tenant_id,
                mission_id=mission_id,
                device_id=event.device_id,
                source_event_id=event.id,
                media_id=media["media_id"],
                media_type=media["media_type"],
                storage_uri=media["storage_uri"],
                checksum=media["checksum"],
                status="READY",
                payload_json={
                    "source": "flight_event",
                    "flight_event": event.payload_json,
                },
            )
            self.session.add(item)
            try:
                self.session.flush()
            except IntegrityError as exc:
                raise DomainError(
                    "IDEMP_409",
                    "Flight event has already been synced as media",
                    {"flight_event_id": flight_event_id},
                ) from exc
            self.u0.audit(
                tenant_id=tenant_id,
                actor=actor_id,
                action="media_file_synced",
                resource_type="media_file",
                resource_id=item.id,
                request_meta=request_meta,
            )
            return media_file_payload(item)

        return self.u0.run_idempotent(
            tenant_id,
            "POST",
            f"mission-{mission_id}-flight-event-{flight_event_id}-media-sync",
            idempotency_key,
            fingerprint,
            operation,
        )

    def _media_payload(self, tenant_id: str, event: FlightEventModel) -> dict:
        raw_payload = event.payload_json.get("raw_payload") or {}
        required = ("media_id", "storage_uri", "checksum", "media_type")
        missing = [key for key in required if not raw_payload.get(key)]
        if missing:
            code = "MEDIA_499" if "checksum" in missing else "MISSION_422"
            raise DomainError(
                code, "Media upload payload is incomplete", {"missing": missing}
            )
        checksum = str(raw_payload["checksum"])
        if CHECKSUM_PATTERN.fullmatch(checksum) is None:
            raise DomainError("MEDIA_499", "Media checksum is invalid")
        media_type = str(raw_payload["media_type"]).upper()
        if media_type not in SUPPORTED_MEDIA_TYPES:
            raise DomainError(
                "MISSION_422",
                "Media type is not supported",
                {"media_type": raw_payload["media_type"]},
            )
        storage_uri = str(raw_payload["storage_uri"])
        if not storage_uri.startswith(f"{tenant_id}/"):
            raise DomainError(
                "MISSION_422",
                "Media storage URI is not tenant-scoped",
                {"storage_uri": storage_uri},
            )
        return {
            "media_id": str(raw_payload["media_id"]),
            "media_type": media_type,
            "storage_uri": storage_uri,
            "checksum": checksum,
        }

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
