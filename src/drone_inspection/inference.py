from __future__ import annotations

from dataclasses import dataclass, field

from .errors import DomainError


@dataclass(frozen=True)
class BBox:
    x: float
    y: float
    width: float
    height: float


@dataclass
class Detection:
    label: str
    confidence: float
    bbox: BBox | None = None
    mask: bytes | None = None
    polyline: list[tuple[float, float]] | None = None
    attributes: dict[str, str] = field(default_factory=dict)

    def __post_init__(self):
        geometry_count = sum(
            1 for value in (self.bbox, self.mask, self.polyline) if value is not None
        )
        if geometry_count != 1:
            raise DomainError("INFER_504", "Detection.geometry 必须在 bbox/mask/polyline 中三选一")

    @property
    def geometry_type(self) -> str:
        if self.bbox is not None:
            return "bbox"
        if self.mask is not None:
            return "mask"
        return "polyline"


@dataclass
class PredictRequest:
    inference_job_id: str
    algorithm_id: str
    model_version_id: str
    frame_asset_id: str
    image_width: int
    image_height: int
    backend: str
    image_data: bytes | None = None
    image_uri: str | None = None
    runtime_params: dict[str, str] = field(default_factory=dict)

    def __post_init__(self):
        if self.backend not in {"nvidia", "domestic"}:
            raise DomainError("RUNTIME_428", "指定硬件后端未完成验证")
        has_data = self.image_data is not None
        has_uri = self.image_uri is not None
        if has_data == has_uri:
            raise DomainError("INFER_504", "image_data 与 image_uri 必须二选一")


@dataclass
class PredictResponse:
    inference_job_id: str
    status: str
    error_code: str
    detections: list[Detection]
    latency_ms: int
    backend: str
    model_version_id: str


class InferenceRuntime:
    def predict(
        self,
        request: PredictRequest,
        detections: list[Detection] | None = None,
    ) -> PredictResponse:
        return PredictResponse(
            inference_job_id=request.inference_job_id,
            status="SUCCEEDED",
            error_code="",
            detections=detections or [],
            latency_ms=1,
            backend=request.backend,
            model_version_id=request.model_version_id,
        )


@dataclass(frozen=True)
class PublicationGate:
    allowed: bool
    error_code: str | None
    reason: str


def compare_backend_outputs(
    frame_asset_id: str,
    model_version_id: str,
    nvidia: list[Detection],
    domestic: list[Detection],
    max_confidence_delta: float,
) -> PublicationGate:
    if len(nvidia) != len(domestic):
        return PublicationGate(False, "RUNTIME_428", "双后端检测数量不一致")
    for left, right in zip(nvidia, domestic):
        if left.label != right.label:
            return PublicationGate(False, "RUNTIME_428", "双后端检测类别不一致")
        if abs(left.confidence - right.confidence) > max_confidence_delta:
            return PublicationGate(
                False,
                "RUNTIME_428",
                f"{frame_asset_id}/{model_version_id} 双后端置信度差异超过阈值",
            )
    return PublicationGate(True, None, "双后端输出一致")

