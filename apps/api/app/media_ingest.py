from __future__ import annotations

from datetime import datetime
from hashlib import sha256
from json import dumps
import re
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from drone_inspection.errors import DomainError

from .models import MediaChunkModel, MediaFileModel, MissionModel
from .repositories import RequestMeta, U0Repository


SUPPORTED_SOURCE_TYPES = {"DJI_DOCK_3", "MANUAL_IMPORT", "SIMULATOR"}
SUPPORTED_MEDIA_TYPES = {"VIDEO", "IMAGE", "THUMBNAIL"}
SUPPORTED_MIME_TYPES = {"video/mp4", "image/jpeg", "image/png"}
CHECKSUM_PATTERN = re.compile(r"^(sha256:[0-9a-fA-F]{64}|md5:[0-9a-fA-F]{32})$")


def media_ingest_payload(
    item: MediaFileModel,
    chunk_completed: int = 0,
    chunk_total: int = 0,
) -> dict:
    return {
        "id": item.id,
        "tenant_id": item.tenant_id,
        "mission_id": item.mission_id,
        "device_id": item.device_id,
        "source_event_id": item.source_event_id,
        "media_id": item.media_id,
        "media_type": item.media_type,
        "source_type": item.source_type,
        "storage_uri": item.storage_uri,
        "checksum": item.checksum,
        "original_filename": item.original_filename,
        "mime_type": item.mime_type,
        "size_bytes": item.size_bytes,
        "captured_at": item.captured_at.isoformat() if item.captured_at else None,
        "status": item.status,
        "failure_reason": item.failure_reason,
        "payload_json": item.payload_json,
        "chunk_summary": {
            "chunk_total": chunk_total,
            "chunk_completed": chunk_completed,
        },
        "created_at": item.created_at.isoformat(),
        "updated_at": item.updated_at.isoformat(),
    }


class MediaIngestService:
    def __init__(self, session: Session):
        self.session = session
        self.u0 = U0Repository(session)

    def ingest_event(
        self,
        actor_id: str,
        tenant_id: str,
        values: dict,
        idempotency_key: str | None,
        request_meta: RequestMeta,
    ) -> dict:
        normalized = self._normalize_values(tenant_id, values)
        fingerprint = self._fingerprint(
            {
                "action": "media_ingest",
                "tenant_id": tenant_id,
                "payload": normalized,
            }
        )
        return self.u0.run_idempotent(
            tenant_id,
            "POST",
            "media-ingest-events",
            idempotency_key,
            fingerprint,
            lambda: self._create_media(actor_id, tenant_id, normalized, request_meta),
        )

    def get_media_file(self, tenant_id: str, media_file_id: str) -> dict:
        item = self._media_file(tenant_id, media_file_id)
        chunk_total, chunk_completed = self._chunk_summary(tenant_id, media_file_id)
        return media_ingest_payload(item, chunk_completed, chunk_total)

    def list_chunks(self, tenant_id: str, media_file_id: str) -> list[dict]:
        self._media_file(tenant_id, media_file_id)
        statement = (
            select(MediaChunkModel)
            .where(
                MediaChunkModel.tenant_id == tenant_id,
                MediaChunkModel.media_file_id == media_file_id,
            )
            .order_by(MediaChunkModel.chunk_index)
        )
        return [
            {
                "id": chunk.id,
                "tenant_id": chunk.tenant_id,
                "media_file_id": chunk.media_file_id,
                "chunk_index": chunk.chunk_index,
                "chunk_total": chunk.chunk_total,
                "size_bytes": chunk.size_bytes,
                "checksum": chunk.checksum,
                "status": chunk.status,
                "created_at": chunk.created_at.isoformat(),
                "updated_at": chunk.updated_at.isoformat(),
            }
            for chunk in self.session.scalars(statement)
        ]

    def _create_media(
        self,
        actor_id: str,
        tenant_id: str,
        values: dict,
        request_meta: RequestMeta,
    ) -> dict:
        mission = self._mission(tenant_id, values["mission_id"])
        existing = self.session.scalar(
            select(MediaFileModel).where(
                MediaFileModel.tenant_id == tenant_id,
                MediaFileModel.storage_uri == values["storage_uri"],
            )
        )
        if existing is not None and existing.checksum != values["checksum"]:
            raise DomainError(
                "MEDIA_499",
                "Media checksum does not match existing object registration",
                {"storage_uri": values["storage_uri"]},
            )

        item = MediaFileModel(
            id=f"med_{uuid4().hex[:12]}",
            tenant_id=tenant_id,
            mission_id=mission.id,
            device_id=mission.device_id,
            source_event_id=None,
            media_id=values["media_id"],
            media_type=values["media_type"],
            source_type=values["source_type"],
            storage_uri=values["storage_uri"],
            checksum=values["checksum"],
            original_filename=values.get("original_filename"),
            mime_type=values["mime_type"],
            size_bytes=values["size_bytes"],
            captured_at=self._parse_datetime(values["captured_at"]),
            status="READY",
            failure_reason=None,
            payload_json={"source": "media_ingest", "ingest_request": values},
        )
        self.session.add(item)
        self.session.flush()

        chunks = values.get("chunks", [])
        for chunk in chunks:
            self.session.add(
                MediaChunkModel(
                    id=f"mchk_{uuid4().hex[:12]}",
                    tenant_id=tenant_id,
                    media_file_id=item.id,
                    chunk_index=chunk["chunk_index"],
                    chunk_total=chunk["chunk_total"],
                    size_bytes=chunk["size_bytes"],
                    checksum=chunk["checksum"],
                    status="UPLOADED",
                )
            )
        try:
            self.session.flush()
        except IntegrityError as exc:
            raise DomainError(
                "IDEMP_409",
                "Media ingest chunk metadata conflicts with an existing record",
                {"media_file_id": item.id},
            ) from exc

        self.u0.audit(
            tenant_id=tenant_id,
            actor=actor_id,
            action="media_ingested",
            resource_type="media_file",
            resource_id=item.id,
            request_meta=request_meta,
        )
        return media_ingest_payload(
            item,
            chunk_completed=len(chunks),
            chunk_total=chunks[0]["chunk_total"] if chunks else 0,
        )

    def _normalize_values(self, tenant_id: str, values: dict) -> dict:
        required = (
            "mission_id",
            "media_id",
            "media_type",
            "source_type",
            "storage_uri",
            "checksum",
            "captured_at",
            "mime_type",
            "size_bytes",
        )
        missing = [key for key in required if values.get(key) in (None, "")]
        if missing:
            raise DomainError("MISSION_422", "Media ingest payload is incomplete", {"missing": missing})

        normalized = dict(values)
        normalized["media_type"] = str(values["media_type"]).upper()
        normalized["source_type"] = str(values["source_type"]).upper()
        normalized["mime_type"] = str(values["mime_type"]).lower()
        normalized["storage_uri"] = str(values["storage_uri"])
        normalized["checksum"] = str(values["checksum"])
        normalized["size_bytes"] = int(values["size_bytes"])
        normalized["captured_at"] = str(values["captured_at"])
        normalized["chunks"] = [dict(chunk) for chunk in values.get("chunks") or []]

        if not normalized["storage_uri"].startswith(f"{tenant_id}/"):
            raise DomainError(
                "TENANT_403",
                "Media storage URI is not tenant-scoped",
                {"storage_uri": normalized["storage_uri"]},
            )
        if CHECKSUM_PATTERN.fullmatch(normalized["checksum"]) is None:
            raise DomainError("MEDIA_499", "Media checksum is invalid")
        if normalized["mime_type"] not in SUPPORTED_MIME_TYPES:
            raise DomainError(
                "MEDIA_415",
                "Media MIME type is not supported",
                {"mime_type": normalized["mime_type"]},
            )
        if normalized["media_type"] not in SUPPORTED_MEDIA_TYPES:
            raise DomainError(
                "MEDIA_415",
                "Media type is not supported",
                {"media_type": normalized["media_type"]},
            )
        if normalized["source_type"] not in SUPPORTED_SOURCE_TYPES:
            raise DomainError(
                "MISSION_422",
                "Media source type is not supported",
                {"source_type": normalized["source_type"]},
            )
        if normalized["size_bytes"] <= 0:
            raise DomainError(
                "MISSION_422",
                "Media size must be positive",
                {"size_bytes": normalized["size_bytes"]},
            )
        self._parse_datetime(normalized["captured_at"])
        self._validate_chunks(normalized["chunks"])
        return normalized

    def _validate_chunks(self, chunks: list[dict]) -> None:
        if not chunks:
            return
        totals = {int(chunk.get("chunk_total", 0)) for chunk in chunks}
        if len(totals) != 1:
            raise DomainError("MEDIA_499", "Media chunk totals are inconsistent")
        chunk_total = totals.pop()
        indexes = set()
        for chunk in chunks:
            chunk["chunk_index"] = int(chunk.get("chunk_index", 0))
            chunk["chunk_total"] = int(chunk.get("chunk_total", 0))
            chunk["size_bytes"] = int(chunk.get("size_bytes", 0))
            chunk["checksum"] = str(chunk.get("checksum", ""))
            if chunk["size_bytes"] <= 0:
                raise DomainError("MEDIA_499", "Media chunk size is invalid")
            if CHECKSUM_PATTERN.fullmatch(chunk["checksum"]) is None:
                raise DomainError("MEDIA_499", "Media chunk checksum is invalid")
            indexes.add(chunk["chunk_index"])
        if chunk_total <= 0 or indexes != set(range(1, chunk_total + 1)):
            raise DomainError(
                "MEDIA_499",
                "Media chunk upload is incomplete",
                {"chunk_total": chunk_total, "chunk_completed": len(indexes)},
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

    def _media_file(self, tenant_id: str, media_file_id: str) -> MediaFileModel:
        item = self.session.scalar(
            select(MediaFileModel).where(
                MediaFileModel.tenant_id == tenant_id,
                MediaFileModel.id == media_file_id,
            )
        )
        if item is None:
            raise DomainError(
                "TENANT_404",
                "Media file does not exist or is not accessible",
            )
        return item

    def _chunk_summary(self, tenant_id: str, media_file_id: str) -> tuple[int, int]:
        chunks = self.list_chunks(tenant_id, media_file_id)
        if not chunks:
            return 0, 0
        return chunks[0]["chunk_total"], len(chunks)

    @staticmethod
    def _parse_datetime(value: str) -> datetime:
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise DomainError(
                "MISSION_422",
                "Media captured_at is invalid",
                {"captured_at": value},
            ) from exc

    @staticmethod
    def _fingerprint(payload: dict) -> str:
        encoded = dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode(
            "utf-8"
        )
        return sha256(encoded).hexdigest()
