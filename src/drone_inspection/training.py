from __future__ import annotations

from dataclasses import dataclass, field

from .algorithms import AlgorithmRegistry
from .constants import FeatureCode
from .errors import DomainError
from .foundation import PlatformState


@dataclass
class TrainingJob:
    id: str
    actor_tenant_id: str
    dataset_owner_tenant_id: str
    sample_ids: list[str]
    algorithm_code: str
    status: str = "CREATED"


@dataclass
class ModelVersion:
    id: str
    algorithm_code: str
    metrics: dict[str, float]
    status: str = "CREATED"
    runtime_artifacts: dict[str, str] = field(default_factory=dict)


@dataclass
class AlgorithmRelease:
    id: str
    actor_tenant_id: str
    target_tenant_id: str
    model_version_id: str
    status: str


class TrainingReleaseService:
    def __init__(self, state: PlatformState):
        self.state = state
        self.registry = AlgorithmRegistry.phase_one()
        self.training_jobs: dict[str, TrainingJob] = {}
        self.model_versions: dict[str, ModelVersion] = {}
        self.releases: dict[str, AlgorithmRelease] = {}

    def _next_id(self, prefix: str, bucket: dict) -> str:
        return f"{prefix}_{len(bucket) + 1:03d}"

    def create_training_job(
        self,
        actor_tenant_id: str,
        dataset_owner_tenant_id: str,
        sample_ids: list[str],
        algorithm_code: str,
    ) -> TrainingJob:
        self.state.require_feature(
            actor_tenant_id,
            FeatureCode.MODEL_TRAINING,
            actor=actor_tenant_id,
        )
        self.state.require_data_grant(
            owner_tenant_id=dataset_owner_tenant_id,
            grantee_tenant_id=actor_tenant_id,
            purpose="training",
            sample_ids=sample_ids,
        )
        job = TrainingJob(
            id=self._next_id("train", self.training_jobs),
            actor_tenant_id=actor_tenant_id,
            dataset_owner_tenant_id=dataset_owner_tenant_id,
            sample_ids=list(sample_ids),
            algorithm_code=algorithm_code,
        )
        self.training_jobs[job.id] = job
        return job

    def create_model_version(
        self,
        algorithm_code: str,
        metrics: dict[str, float],
    ) -> ModelVersion:
        status = "READY" if self.registry.metrics_meet_target(algorithm_code, metrics) else "BLOCKED"
        version = ModelVersion(
            id=self._next_id("mv", self.model_versions),
            algorithm_code=algorithm_code,
            metrics=dict(metrics),
            status=status,
        )
        self.model_versions[version.id] = version
        return version

    def add_runtime_artifact(self, model_version_id: str, backend: str, image_digest: str) -> None:
        if backend not in {"nvidia", "domestic"}:
            raise DomainError("RUNTIME_428", "指定硬件后端未完成验证")
        self.model_versions[model_version_id].runtime_artifacts[backend] = image_digest

    def publish_release(
        self,
        actor_tenant_id: str,
        model_version_id: str,
        target_tenant_id: str,
    ) -> AlgorithmRelease:
        self.state.require_feature(
            actor_tenant_id,
            FeatureCode.MODEL_RELEASE,
            actor=actor_tenant_id,
        )
        version = self.model_versions[model_version_id]
        if not self.registry.metrics_meet_target(version.algorithm_code, version.metrics):
            raise DomainError("MODEL_412", "模型未满足发布准入")
        if set(version.runtime_artifacts) != {"nvidia", "domestic"}:
            raise DomainError("RUNTIME_428", "双硬件 runtime_artifacts 未完成")
        release = AlgorithmRelease(
            id=self._next_id("rel", self.releases),
            actor_tenant_id=actor_tenant_id,
            target_tenant_id=target_tenant_id,
            model_version_id=model_version_id,
            status="ACTIVE",
        )
        self.releases[release.id] = release
        self.state.audit(
            tenant_id=actor_tenant_id,
            actor=actor_tenant_id,
            action="model_release",
            resource_type="algorithm_release",
            resource_id=release.id,
        )
        return release

    def rollback_release(self, release_id: str, actor_tenant_id: str) -> AlgorithmRelease:
        original = self.releases[release_id]
        rollback = AlgorithmRelease(
            id=self._next_id("rollback", self.releases),
            actor_tenant_id=actor_tenant_id,
            target_tenant_id=original.target_tenant_id,
            model_version_id=original.model_version_id,
            status="ROLLED_BACK",
        )
        self.releases[rollback.id] = rollback
        self.state.audit(
            tenant_id=actor_tenant_id,
            actor=actor_tenant_id,
            action="model_rollback",
            resource_type="algorithm_release",
            resource_id=release_id,
        )
        return rollback

