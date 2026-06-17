from __future__ import annotations

from dataclasses import dataclass, field

from .constants import FeatureCode
from .errors import DomainError
from .foundation import PlatformState


ALLOWED_ANNOTATION_TYPES = {"bbox", "polygon", "polyline", "scene_label", "density"}


@dataclass
class Sample:
    id: str
    tenant_id: str
    frame_asset_id: str


@dataclass
class AnnotationTask:
    id: str
    tenant_id: str
    algorithm_code: str
    sample_ids: list[str]
    assignee: str
    status: str = "ASSIGNED"


@dataclass
class Annotation:
    id: str
    tenant_id: str
    task_id: str
    sample_id: str
    annotation_type: str


@dataclass
class Dataset:
    id: str
    tenant_id: str
    algorithm_code: str
    sample_ids: list[str] = field(default_factory=list)
    status: str = "DRAFT"


class AnnotationService:
    def __init__(self, state: PlatformState):
        self.state = state
        self.samples: dict[str, Sample] = {}
        self.tasks: dict[str, AnnotationTask] = {}
        self.annotations: dict[str, Annotation] = {}
        self.datasets: dict[str, Dataset] = {}

    def _next_id(self, prefix: str, bucket: dict) -> str:
        return f"{prefix}_{len(bucket) + 1:03d}"

    def add_sample(self, tenant_id: str, frame_asset_id: str) -> Sample:
        sample = Sample(
            id=self._next_id("sample", self.samples),
            tenant_id=tenant_id,
            frame_asset_id=frame_asset_id,
        )
        self.samples[sample.id] = sample
        return sample

    def create_task(
        self,
        tenant_id: str,
        algorithm_code: str,
        sample_ids: list[str],
        assignee: str,
    ) -> AnnotationTask:
        self.state.require_feature(tenant_id, FeatureCode.DATA_ANNOTATION, assignee)
        for sample_id in sample_ids:
            if self.samples[sample_id].tenant_id != tenant_id:
                raise DomainError("TENANT_403", "客户租户不能处理其他租户样本")
        task = AnnotationTask(
            id=self._next_id("ann_task", self.tasks),
            tenant_id=tenant_id,
            algorithm_code=algorithm_code,
            sample_ids=list(sample_ids),
            assignee=assignee,
        )
        self.tasks[task.id] = task
        return task

    def submit_annotation(
        self,
        task_id: str,
        sample_id: str,
        annotation_type: str,
        actor: str,
    ) -> Annotation:
        task = self.tasks[task_id]
        if actor != task.assignee:
            raise DomainError("PERM_403", "标注任务未分配给当前用户")
        if sample_id not in task.sample_ids:
            raise DomainError("TENANT_403", "样本未授权给当前标注任务")
        if annotation_type not in ALLOWED_ANNOTATION_TYPES:
            raise DomainError("MISSION_422", "标注类型不支持")
        task.status = "SUBMITTED"
        annotation = Annotation(
            id=self._next_id("anno", self.annotations),
            tenant_id=task.tenant_id,
            task_id=task_id,
            sample_id=sample_id,
            annotation_type=annotation_type,
        )
        self.annotations[annotation.id] = annotation
        return annotation

    def review(self, task_id: str, passed: bool, actor: str, reason: str) -> None:
        task = self.tasks[task_id]
        task.status = "FINAL_PASSED" if passed else "RETURNED"

    def create_dataset(
        self,
        tenant_id: str,
        algorithm_code: str,
        sample_ids: list[str],
    ) -> Dataset:
        for sample_id in sample_ids:
            if self.samples[sample_id].tenant_id != tenant_id:
                raise DomainError("TENANT_403", "数据集样本不属于当前租户")
        dataset = Dataset(
            id=self._next_id("ds", self.datasets),
            tenant_id=tenant_id,
            algorithm_code=algorithm_code,
            sample_ids=list(sample_ids),
        )
        self.datasets[dataset.id] = dataset
        return dataset

    def freeze_dataset(self, dataset_id: str) -> None:
        self.datasets[dataset_id].status = "FROZEN"

    def add_sample_to_dataset(self, dataset_id: str, sample_id: str) -> None:
        dataset = self.datasets[dataset_id]
        if dataset.status == "FROZEN":
            raise DomainError("STATE_409", "FROZEN 数据集不可修改")
        dataset.sample_ids.append(sample_id)

    def export_dataset(self, dataset_id: str, actor: str) -> str:
        dataset = self.datasets[dataset_id]
        self.state.require_feature(dataset.tenant_id, FeatureCode.DATASET_EXPORT, actor)
        return f"{dataset.tenant_id}/datasets/{dataset.id}.zip"

