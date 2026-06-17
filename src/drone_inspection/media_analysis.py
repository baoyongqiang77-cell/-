from __future__ import annotations

from dataclasses import dataclass

from .errors import DomainError
from .foundation import IdempotencyStore


@dataclass
class MediaFile:
    id: str
    tenant_id: str
    mission_id: str
    storage_uri: str
    checksum: str
    status: str


@dataclass
class FrameAsset:
    id: str
    tenant_id: str
    media_file_id: str
    storage_uri: str
    status: str = "FRAME_READY"


@dataclass
class AnalysisTask:
    id: str
    tenant_id: str
    media_file_id: str
    algorithm_codes: list[str]
    priority: str
    status: str = "CREATED"


@dataclass
class Event:
    id: str
    tenant_id: str
    analysis_task_id: str
    frame_asset_id: str
    label: str
    confidence: float
    status: str = "CANDIDATE"


@dataclass
class WorkOrder:
    id: str
    tenant_id: str
    event_id: str
    status: str = "DISPATCHED"


class MediaAnalysisPipeline:
    def __init__(self):
        self.idempotency = IdempotencyStore()
        self.media_files: dict[str, MediaFile] = {}
        self.frames: dict[str, FrameAsset] = {}
        self.analysis_tasks: dict[str, AnalysisTask] = {}
        self.events: dict[str, Event] = {}
        self.work_orders: dict[str, WorkOrder] = {}

    def _next_id(self, prefix: str, bucket: dict) -> str:
        return f"{prefix}_{len(bucket) + 1:03d}"

    def ingest_media(
        self,
        tenant_id: str,
        mission_id: str,
        storage_uri: str,
        checksum: str,
        idempotency_key: str,
    ) -> MediaFile:
        if not storage_uri.startswith(f"{tenant_id}/"):
            raise DomainError("TENANT_403", "对象路径缺少租户前缀")
        for media in self.media_files.values():
            if media.storage_uri == storage_uri and media.checksum != checksum:
                raise DomainError("MEDIA_499", "checksum 不一致")

        fingerprint = f"{tenant_id}:{mission_id}:{storage_uri}:{checksum}"
        if idempotency_key in self.idempotency._records:
            replay = self.idempotency.record(idempotency_key, fingerprint, None)
            return self.media_files[replay["id"]]

        media = MediaFile(
            id=self._next_id("med", self.media_files),
            tenant_id=tenant_id,
            mission_id=mission_id,
            storage_uri=storage_uri,
            checksum=checksum,
            status="READY",
        )
        self.media_files[media.id] = media
        self.idempotency.record(idempotency_key, fingerprint, {"id": media.id})
        return media

    def extract_frames(self, media_file_id: str, count: int) -> list[FrameAsset]:
        media = self.media_files[media_file_id]
        frames = []
        for index in range(count):
            frame = FrameAsset(
                id=self._next_id("frm", self.frames),
                tenant_id=media.tenant_id,
                media_file_id=media_file_id,
                storage_uri=f"{media.tenant_id}/frames/{media_file_id}_{index + 1}.jpg",
            )
            self.frames[frame.id] = frame
            frames.append(frame)
        return frames

    def create_analysis_task(
        self,
        tenant_id: str,
        media_file_id: str,
        algorithm_codes: list[str],
        priority: str,
    ) -> AnalysisTask:
        media = self.media_files[media_file_id]
        if media.tenant_id != tenant_id:
            raise DomainError("TENANT_403", "媒体不属于当前租户")
        task = AnalysisTask(
            id=self._next_id("ana", self.analysis_tasks),
            tenant_id=tenant_id,
            media_file_id=media_file_id,
            algorithm_codes=algorithm_codes,
            priority=priority,
        )
        self.analysis_tasks[task.id] = task
        return task

    def complete_analysis_with_detection(
        self,
        task_id: str,
        frame_asset_id: str,
        label: str,
        confidence: float,
    ) -> Event:
        task = self.analysis_tasks[task_id]
        frame = self.frames[frame_asset_id]
        if task.tenant_id != frame.tenant_id:
            raise DomainError("TENANT_403", "分析任务与帧租户不一致")
        task.status = "COMPLETED"
        event = Event(
            id=self._next_id("evt", self.events),
            tenant_id=task.tenant_id,
            analysis_task_id=task_id,
            frame_asset_id=frame_asset_id,
            label=label,
            confidence=confidence,
            status="CONFIRMED",
        )
        self.events[event.id] = event
        return event

    def dispatch_work_order(self, event_id: str, actor: str) -> WorkOrder:
        event = self.events[event_id]
        event.status = "DISPATCHED"
        work_order = WorkOrder(
            id=self._next_id("wo", self.work_orders),
            tenant_id=event.tenant_id,
            event_id=event_id,
        )
        self.work_orders[work_order.id] = work_order
        return work_order

    def get_event(self, event_id: str, tenant_id: str) -> Event:
        event = self.events[event_id]
        if event.tenant_id != tenant_id:
            raise DomainError("TENANT_404", "当前租户上下文下资源不存在")
        return event

